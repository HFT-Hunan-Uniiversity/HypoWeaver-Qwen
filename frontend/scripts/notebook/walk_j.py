"""J 手记新项目实走（:5193 → :8002 审阅后端，模型未配置）：方向 → 文献，修改上游 → 下游 stale。
需要大模型的步骤（候选 / 方案 / 提案生成）在此后端无法真实执行，只记录界面给出的阻断提示。"""
import asyncio, sys, json, urllib.request
from playwright.async_api import async_playwright
BASE = 'http://localhost:5193'; API = 'http://localhost:8002/api'
SH = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else None
def post(path, data):
    r = urllib.request.Request(API + path, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    return json.load(urllib.request.urlopen(r))
async def main():
    pid = post('/projects', {'title': 'J 验收 · 新项目（可删除）'})['id']; print('project', pid)
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={'width': 1280, 'height': 720})
        async def shot(n):
            if SH: await pg.screenshot(path=f'{SH}/{n}.png')
        await pg.goto(f'{BASE}/p/{pid}'); await pg.wait_for_timeout(2500)
        await pg.click('.dir-chip >> nth=0'); await pg.wait_for_timeout(500)
        ans = {'变量': '碳交易试点、绿色专利数量', '原因': '碳交易试点、绿色专利数量', '地区': '中国 A 股上市公司', '范围': '中国 A 股上市公司', '时间': '2010—2020', '因果': '关联'}
        for i in range(10):
            ask = await pg.query_selector('.dir-ask')
            if not ask: break
            q = await ask.inner_text()
            chips = await pg.query_selector_all('.dir-ask .dir-chip')
            if chips: await chips[0].click()
            else:
                a = next((v for k, v in ans.items() if k in q), '中国 A 股上市公司')
                await pg.fill('.dir-ask input', a); await pg.click('.dir-ask button:has-text("填入")')
            await pg.wait_for_timeout(300)
        await shot('W01_direction_filled')
        prim = await pg.inner_text('#nb-direction [data-primary]'); print('direction primary:', prim)
        await pg.click('#nb-direction [data-primary]'); await pg.wait_for_timeout(3500)
        cls = await pg.eval_on_selector_all('.nb-sec', 'es => es.map(e => e.id + ":" + e.className)'); print('after confirm:', cls)
        top = await pg.evaluate("() => Math.round(document.getElementById('nb-literature').getBoundingClientRect().top - document.querySelector('.nb-hero').getBoundingClientRect().bottom)")
        print('literature top below hero:', top)
        await shot('W02_after_direction_confirm')
        # 文献：观察界面（检索需要检索式；无模型时给出提示）
        if '检索文献' in await pg.inner_text('#nb-literature [data-primary]'):
            print('auto search did not start; clicking 检索文献'); await pg.click('#nb-literature [data-primary]')
        for _ in range(60):
            t = await pg.inner_text('#nb-literature .nb-sh')
            if '纳入' in t and '纳入 0' not in t: break
            await pg.wait_for_timeout(1000)
        await pg.wait_for_timeout(1500)
        txt = (await pg.inner_text('#nb-literature'))[:600].replace('\n', ' | '); print('literature card:', txt)
        await shot('W03_literature')
        prim = await pg.inner_text('#nb-literature [data-primary]'); print('literature primary:', prim)
        await pg.click('#nb-literature [data-primary]'); await pg.wait_for_timeout(3500)
        cls = await pg.eval_on_selector_all('.nb-sec', 'es => es.map(e => e.id + ":" + e.className)'); print('after literature confirm:', cls)
        print('candidates acts:', (await pg.inner_text('#nb-candidates .acts')).replace('\n', ' | '))
        await shot('W04_candidates_needs_llm')
        if '--no-edit' in sys.argv: await b.close(); return
        # 修改上游：方向 → 修改 → 保存 → 文献变为 stale
        await pg.click('#nb-direction .nb-sh'); await pg.wait_for_timeout(1500)
        await pg.click('#nb-direction .nb-ro button:has-text("修改")'); await pg.wait_for_timeout(300)
        await pg.click('[role=dialog] button:has-text("继续修改")'); await pg.wait_for_timeout(800)
        await shot('W05_direction_editing')
        await pg.fill('#nb-direction textarea >> nth=0', '碳交易试点会不会提高企业绿色专利数量？')
        await pg.wait_for_timeout(300)
        await pg.click('#nb-direction [data-primary]'); await pg.wait_for_timeout(3500)
        cls = await pg.eval_on_selector_all('.nb-sec', "es => es.map(e => e.id + ':' + e.className + ' | ' + e.querySelector('.nb-sh').innerText.replace(/\\n/g,' '))"); print('after upstream edit:', cls)
        await pg.evaluate('scrollTo(0,0)'); await shot('W06_downstream_stale')
        await b.close()
asyncio.run(main())
