"""I 向导新项目实走（:5193 → :8002）：方向 → 文献；候选因无 LLM 停在「去设置模型」。"""
import asyncio, sys, json, urllib.request
from playwright.async_api import async_playwright
BASE = 'http://localhost:5193'; API = 'http://localhost:8002/api'
SH = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else None
def post(path, data):
    r = urllib.request.Request(API + path, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    return json.load(urllib.request.urlopen(r))
async def main():
    pid = post('/projects', {'title': 'I 验收 · 新项目（可删除）'})['id']; print('project', pid)
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={'width': 1280, 'height': 720})
        async def shot(n):
            if SH: await pg.screenshot(path=f'{SH}/{n}.png')
        await pg.goto(f'{BASE}/p/{pid}'); await pg.wait_for_timeout(2500)
        await pg.click('.dir-chip >> nth=0'); await pg.wait_for_timeout(500)
        ans = {'变量': '碳交易试点、绿色专利数量', '原因': '碳交易试点、绿色专利数量', '地区': '中国 A 股上市公司', '范围': '中国 A 股上市公司', '时间': '2010—2020', '因果': '关联'}
        for _ in range(10):
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
        print('direction primary:', await pg.inner_text('.wz-card [data-primary]'))
        await pg.click('.wz-card [data-primary]'); await pg.wait_for_timeout(3500)
        print('after confirm url:', pg.url)
        await shot('W02_after_direction_confirm')
        if '检索文献' in await pg.inner_text('.wz-card [data-primary]'):
            print('auto search did not start; clicking 检索文献')
            await pg.click('.wz-card [data-primary]')
        for _ in range(60):
            t = await pg.inner_text('.wz-card')
            if '纳入' in t and '纳入 0' not in t: break
            await pg.wait_for_timeout(1000)
        await pg.wait_for_timeout(1500)
        await shot('W03_literature')
        print('literature primary:', await pg.inner_text('.wz-card [data-primary]'))
        await pg.click('.wz-card [data-primary]'); await pg.wait_for_timeout(3500)
        print('candidates acts:', (await pg.inner_text('.wz-card .acts')).replace('\n', ' | '))
        await shot('W04_candidates_needs_llm')
        if '--no-edit' not in sys.argv:
            await pg.goto(f'{BASE}/p/{pid}/direction'); await pg.wait_for_timeout(2000)
            await pg.click(".nb-ro button:has-text('修改')"); await pg.wait_for_timeout(300)
            await pg.click('[role=dialog] button:has-text("继续修改")'); await pg.wait_for_timeout(800)
            await shot('W05_direction_editing')
            await pg.fill('.wz-card textarea >> nth=0', '碳交易试点会不会提高企业绿色专利数量？')
            await pg.click('.wz-card [data-primary]'); await pg.wait_for_timeout(3500)
            await shot('W06_downstream_stale')
            print('after edit badge:', await pg.inner_text('.wz-badge'))
        await b.close()
asyncio.run(main())
