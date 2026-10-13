"""R5 前端适配验证：用 Playwright route 拦截模拟后端 R5 字段（不写真实数据，PUT 也被拦截）。"""
import asyncio, json, re, sys
from playwright.async_api import async_playwright
sys.path.insert(0, '.')
from measure_one_screen import JS, WIDTH_MIN  # noqa: E402  (导入不执行 main：见文件末尾守卫)
P = json.load(open('/tmp/fake_ids'))['P']; BASE = 'http://localhost:8001'
OUT = '/workspace/hw/review/screens/one-screen/r5'
results = []

async def real(route):
    r = await route.fetch(); return r, await r.json()

async def run(pg, vp):
    async def fit(name):
        m = await pg.evaluate(JS); ok = not m['page_scroll'] and not m['other_scroll'] and m['width_util'] >= WIDTH_MIN
        return ok, m
    # 计划 id
    plans = await (await pg.request.get(f'{BASE}/api/projects/{P}/plans')).json()
    plan = next(p for p in plans if p['status'] == 'confirmed')
    saved = await (await pg.request.get(f"{BASE}/api/plans/{plan['id']}/bindings")).json()

    # 1) suggested_binding：方案带建议，已保存绑定为空
    async def plans_with_suggest(route):
        r, d = await real(route)
        for p in d:
            if p['id'] == plan['id']:
                p['suggested_binding'] = {'peer_exposure': {'field': 'industry_peer_exposure', 'formula': None},
                                          'size': {'field': None, 'formula': 'log(total_assets)'}, 'lev': {'field': 'leverage'}}
        await route.fulfill(response=r, json=d)
    await pg.route(f'**/api/projects/{P}/plans', plans_with_suggest)
    await pg.route(f"**/api/plans/{plan['id']}/bindings", lambda r: r.fulfill(json={'plan_id': plan['id'], 'dataset_id': saved['dataset_id'], 'bindings': {'peer_exposure': {'field': 'industry_peer_exposure'}}, 'confirmed': False, 'note': '建议预填，请重新确认', 'inherited_from': None}))
    await pg.goto(f'{BASE}/p/{P}/data?tab=binding'); await pg.wait_for_timeout(1500)
    tags = await pg.locator('.tag-suggested').count()
    note = await pg.locator('text=已按方案建议预填').count()
    vals = await pg.evaluate("""()=>[...document.querySelectorAll('.binding-row')].map(r=>[r.querySelector('strong')?.innerText, [...r.querySelectorAll('select,input')].map(e=>e.value)])""")
    ok, m = await fit('s')
    await pg.screenshot(path=f'{OUT}/{vp}_1_suggested_binding.png')
    results.append((vp, 'suggested_binding 预填', tags == 3 and note == 1, f'建议标签 {tags}，提示 {note}，一屏 {ok}', vals))
    await pg.unroute(f'**/api/projects/{P}/plans'); await pg.unroute(f"**/api/plans/{plan['id']}/bindings")

    # 2) 继承绑定 confirmed=false + 一键确认（拦截 PUT，回显）
    puts = []
    inherited = dict(saved, confirmed=False, inherited_from='plan_prev_mock', note='继承自 v1，请重新确认')
    async def bindings(route):
        if route.request.method == 'PUT':
            b = json.loads(route.request.post_data); puts.append(b)
            inherited.update(confirmed=b['confirmed']); await route.fulfill(json=dict(inherited))
        else:
            await route.fulfill(json=dict(inherited))
    await pg.route(f"**/api/plans/{plan['id']}/bindings", bindings)
    # 流程：数据阶段待确认（绑定未确认），后续未开始 → 主按钮为"确认数据绑定"
    async def overview(route):
        r, d = await real(route)
        for s in d['stages']:
            if s['key'] == 'data': s['status'] = 'ready'
            if s['key'] == 'proposal': s['status'] = 'not_started'
        await route.fulfill(response=r, json=d)
    await pg.route(f'**/api/projects/{P}/overview', overview)
    await pg.goto(f'{BASE}/p/{P}/data?tab=binding'); await pg.wait_for_timeout(1500)
    badge = await pg.locator('.status-badge', has_text='待重新确认').count()
    sugg_badge_ok = True
    ok, m = await fit('c')
    await pg.screenshot(path=f'{OUT}/{vp}_2_pending_reconfirm.png')
    primary = await pg.locator('[data-primary]').inner_text()
    await pg.click('[data-primary]'); await pg.wait_for_timeout(1000)
    badge_after = await pg.locator('.status-badge', has_text='待重新确认').count()
    await pg.screenshot(path=f'{OUT}/{vp}_3_after_reconfirm.png')
    good = '确认数据绑定' in primary and badge == 1 and badge_after == 0 and len(puts) == 1 and puts[0]['confirmed'] is True and puts[0]['bindings'] == saved['bindings']
    results.append((vp, 'confirmed=false 待重新确认 + 一键确认', good and ok,
                    f'徽章 前{badge}/后{badge_after}；PUT {len(puts)} 次 confirmed={puts[0]["confirmed"] if puts else None} 映射原样={bool(puts) and puts[0]["bindings"] == saved["bindings"]}；一屏 {ok}', None))
    await pg.unroute(f"**/api/plans/{plan['id']}/bindings"); await pg.unroute(f'**/api/projects/{P}/overview')

    # 3) 提案 narrative_status=partial
    async def proposals(route):
        if route.request.method != 'GET': return await route.continue_()
        r, d = await real(route)
        if d:
            d[0].update(narrative_status='partial',
                        narrative_failures=[{'section': 'literature', 'reason': '引用了未纳入的证据编号'}, {'section': 'hypotheses', 'reason': '模型超时'}])
        await route.fulfill(response=r, json=d)
    await pg.route(f'**/api/projects/{P}/proposals', proposals)
    # "重新生成本节"只在模型已配置时出现：此步模拟模型已配置
    async def llm_on(route):
        if route.request.method != 'GET': return await route.continue_()
        await route.fulfill(json={'base_url': 'mock', 'llm_model': 'qwen-mock', 'configured': True})
    await pg.route('**/api/settings/llm', llm_on)
    await pg.goto(f'{BASE}/p/{P}/proposal'); await pg.wait_for_timeout(1500)
    # 失败原因：能对应到章节的在该节原地显示（含"重新生成本节"），对不上的列在提示条里
    txt = await pg.locator('.proposal-scroll, .narrative-partial').all_inner_texts()
    txt = ' '.join(txt) + (' 有重新生成本节' if await pg.locator('text=重新生成本节').count() else '')
    ok, m = await fit('p')
    await pg.screenshot(path=f'{OUT}/{vp}_4_proposal_partial.png')
    results.append((vp, '提案 narrative_status=partial', '模型超时' in txt and '引用了未纳入' in txt and '重新生成本节' in txt and ok, f'一屏 {ok}', txt.replace('\n', ' / ')))
    await pg.unroute(f'**/api/projects/{P}/proposals'); await pg.unroute('**/api/settings/llm')
    # 3b) 无 narrative_status 时不显示
    await pg.goto(f'{BASE}/p/{P}/proposal'); await pg.wait_for_timeout(1200)
    results.append((vp, '提案缺字段降级', await pg.locator('.narrative-partial').count() == 0, '', None))

    # 4) settings/status 只有 llm_model / 只有旧 model；llm 接口返回空模型以测兜底
    for label, patch in [('llm_model', {'llm_model': 'qwen-max-mock'}), ('旧 model', {'model': 'qwen-old-mock'})]:
        def mk(patch):
            async def status(route):
                try:
                    r, d = await real(route); d.pop('model', None); d.pop('llm_model', None); d.update(patch)
                    await route.fulfill(response=r, json=d)
                except Exception:
                    pass  # 页面切换时在途请求被取消
            return status
        status = mk(patch)
        async def _unused(route):
            r, d = await real(route); d.pop('model', None); d.pop('llm_model', None); d.update(patch)
            await route.fulfill(response=r, json=d)
        await pg.route('**/api/settings/status', status)
        async def llm(route):
            if route.request.method == 'GET':
                await route.fulfill(json={'base_url': '', 'llm_model': '', 'configured': False})
            else:
                await route.continue_()
        await pg.route('**/api/settings/llm', llm)
        await pg.goto(f'{BASE}/settings'); await pg.wait_for_load_state('networkidle'); await pg.wait_for_timeout(1500)
        want = list(patch.values())[0]
        shown = await pg.get_by_text(want).count()
        if label == 'llm_model': await pg.screenshot(path=f'{OUT}/{vp}_5_settings_llm_model.png')
        results.append((vp, f'设置页兜底读 {label}', shown > 0, f'显示 {want}: {shown}', None))
        await pg.goto('about:blank')
        await pg.unroute('**/api/settings/status'); await pg.unroute('**/api/settings/llm')

    # 5) 结果页置换检验标注
    await pg.goto(f'{BASE}/p/{P}/data?tab=results'); await pg.wait_for_timeout(1500)
    lab = await pg.locator('h2:has-text("置换检验") >> text=无控制变量模型').count()
    el = pg.locator('h2:has-text("置换检验")'); await el.scroll_into_view_if_needed()
    await pg.screenshot(path=f'{OUT}/{vp}_6_results_permutation.png')
    results.append((vp, '置换检验标注', lab == 1, '', None))

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for w, h in [(1440, 900), (1280, 800)]:
            pg = await b.new_page(viewport={'width': w, 'height': h})
            await pg.goto(BASE); await pg.evaluate('localStorage.clear(); sessionStorage.clear()')
            await run(pg, f'{w}x{h}'); await pg.close()
        await b.close()
    allok = True
    for vp, name, ok, info, extra in results:
        allok &= ok; print(f"{vp}\t{'✓' if ok else '✗'}\t{name}\t{info}" + (f"\t{extra}" if extra else ''))
    print('ALL PASS' if allok else 'FAILED'); sys.exit(0 if allok else 1)
asyncio.run(main())
