"""J 研究手记交互验收（SPEC §7 中可自动化的部分）。
用法：uv run --with playwright==1.63.0 python scripts/notebook/check_j.py [--base http://localhost:5193] [--shots DIR]
默认 :5193（→ :8002 审阅后端）。R7 副本 + 空项目。"""
import asyncio, sys, json
from playwright.async_api import async_playwright
args = sys.argv[1:]
BASE = args[args.index('--base') + 1] if '--base' in args else 'http://localhost:5193'
SHOTS = args[args.index('--shots') + 1] if '--shots' in args else None
R7 = 'pr_0ba00b5bb3ba480c9c654a129ab92bd6'; FRESH = 'pr_ad75e9a5778d47e3a74225dbc5a6e1fa'
res = []
def ok(name, cond, info=''):
    res.append((name, bool(cond), info)); print(('✓' if cond else '✗'), name, info)

async def shot(pg, vp, name):
    if SHOTS:
        import os; os.makedirs(f'{SHOTS}/{vp}', exist_ok=True)
        await pg.screenshot(path=f'{SHOTS}/{vp}/{name}.png')

async def run(b, vw, vh):
    vp = f'{vw}x{vh}'
    pg = await b.new_page(viewport={'width': vw, 'height': vh})
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    # 1 空项目默认展开方向
    await pg.goto(f'{BASE}/p/{FRESH}'); await pg.wait_for_timeout(2500)
    secs = await pg.eval_on_selector_all('.wz-card', 'els => els.map(e => [e.id, e.className])')
    ok(f'{vp} 六节完整渲染', len(secs) == 6, str(len(secs)))
    ok(f'{vp} 空项目默认展开方向卡', 'is-open' in secs[0][1], secs[0][1])
    await shot(pg, vp, 'J01_fresh_direction_open')
    await pg.click('#nb-literature .nb-sh', force=True); await pg.wait_for_timeout(400)
    lit = await pg.get_attribute('#nb-literature', 'class')
    tip = await pg.inner_text('#nb-literature .nb-sh')
    ok(f'{vp} 锁定节不可展开且提示', 'is-open' not in lit and '先完成上一步' in tip, tip.replace('\n', ' '))
    # 2 R7 默认
    await pg.goto(f'{BASE}/p/{R7}'); await pg.wait_for_timeout(3000)
    heads = await pg.eval_on_selector_all('.wz-card', "els => els.map(e => e.className.match(/is-(locked|active|running|confirmed|stale)/)[1] + ' | ' + e.querySelector('.nb-sh').innerText.replace(/\\n/g,' '))")
    ok(f'{vp} R7 卡头（圆点态 | 名称 摘要 耗时）', True, ' ;; '.join(heads))
    hero = await pg.eval_on_selector('.wz-top', 'e => e.getBoundingClientRect().height')
    ok(f'{vp} hero ≤70px', hero <= 70, f'{hero}px')
    await shot(pg, vp, 'J02_r7_default')
    # 3 深链 + 滚动到卡顶
    await pg.goto(f'{BASE}/p/{R7}/plan'); await pg.wait_for_timeout(3000)
    st = await pg.evaluate("() => { const s = document.getElementById('nb-plan'); const h = document.querySelector('.wz-top').getBoundingClientRect().bottom; return [s.className, Math.round(s.getBoundingClientRect().top - h)] }")
    ok(f'{vp} 深链 /plan 展开并滚到 hero 下方', 'is-open' in st[0] and -2 <= st[1] <= 40, str(st))
    await shot(pg, vp, 'J03_deeplink_plan')
    # 4 折叠 / 展开
    await pg.click('#nb-plan .nb-sh'); await pg.wait_for_timeout(300)
    c1 = await pg.get_attribute('#nb-plan', 'class')
    await pg.click('#nb-candidates .nb-sh'); await pg.wait_for_timeout(1500)
    c2 = await pg.get_attribute('#nb-candidates', 'class')
    ok(f'{vp} 点卡头折叠/展开', 'is-open' not in c1 and 'is-open' in c2)
    await shot(pg, vp, 'J04_candidates_open')
    # 5 产物 chip → 阅读层
    await pg.click('#nb-candidates .nb-sh'); await pg.wait_for_timeout(300)
    y0 = await pg.evaluate('scrollY')
    await pg.click('#nb-data .mini-art >> text=检验结果报告'); await pg.wait_for_timeout(2500)
    rd = await pg.evaluate("() => { const r = document.querySelector('.nb-reader'); return r ? [getComputedStyle(r).overflowY, r.innerText.slice(0, 40)] : null }")
    ok(f'{vp} 产物 chip 打开白底阅读层', rd and rd[0] == 'auto', str(rd))
    await shot(pg, vp, 'J05_reader_report')
    await pg.click('.nb-reader [aria-label="关闭"]'); await pg.wait_for_timeout(400)
    y1 = await pg.evaluate('scrollY')
    ok(f'{vp} 关闭阅读层回到原位置', abs(y1 - y0) < 4 and not await pg.query_selector('.nb-reader'), f'{y0}->{y1}')
    # 6 全部文件
    await pg.click('.wz-top >> text=全部文件'); await pg.wait_for_timeout(500)
    n = len(await pg.query_selector_all('.nb-reader .wb-files__grp'))
    ok(f'{vp} 全部文件为次要入口（hero 按钮）', n == 6, f'{n} 组')
    await shot(pg, vp, 'J06_all_files')
    await pg.click('.nb-reader >> text=返回时间线')
    # 7 文案
    body = await pg.inner_text('body')
    ok(f'{vp} 无「示意/未接入」、无聊天输入', '示意' not in body and '未接入' not in body and not await pg.query_selector('.wb-chat, .dir-msgs'))
    ok(f'{vp} 无页面错误', not errs, '; '.join(errs)[:200])
    await pg.close()

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for vw, vh in [(1024, 576), (1280, 720), (1440, 900)]:
            await run(b, vw, vh)
        pg = await b.new_page(viewport={'width': 480, 'height': 800})
        await pg.goto(f'{BASE}/p/{R7}'); await pg.wait_for_timeout(2500)
        d = await pg.eval_on_selector('.nb-sh__sum', 'e => getComputedStyle(e).display')
        ok('480px 隐藏折叠摘要', d == 'none', d)
        await shot(pg, '480x800', 'J07_narrow')
        await b.close()
    bad = [r for r in res if not r[1]]
    print('ALL PASS' if not bad else f'FAILED {len(bad)}')
    sys.exit(1 if bad else 0)
asyncio.run(main())
