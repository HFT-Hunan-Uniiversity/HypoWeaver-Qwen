"""I 分步向导交互验收。用法：uv run --with playwright==1.63.0 python scripts/notebook/check_i.py [--shots DIR]"""
import asyncio, sys
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
    vp = f'{vw}x{vh}'; pg = await b.new_page(viewport={'width': vw, 'height': vh})
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    await pg.goto(f'{BASE}/p/{FRESH}'); await pg.wait_for_timeout(2500)
    title = await pg.inner_text('.wz-card h2')
    nsp = len(await pg.query_selector_all('.wz-sp'))
    ok(f'{vp} 六步 stepper', nsp == 6, str(nsp))
    ok(f'{vp} 空项目默认打开方向卡', '研究方向' in title, title)
    await shot(pg, vp, 'I01_fresh_direction')
    locked = await pg.eval_on_selector('.wz-sp.is-locked', 'e => e.disabled')
    ok(f'{vp} 锁定步不可点', locked is True)
    await pg.goto(f'{BASE}/p/{R7}'); await pg.wait_for_timeout(3000)
    hero = await pg.eval_on_selector('.wz-top', 'e => e.getBoundingClientRect().height')
    ok(f'{vp} sticky 顶栏（含 stepper）合理', hero <= 120, f'{hero}px')
    await shot(pg, vp, 'I02_r7_default')
    await pg.goto(f'{BASE}/p/{R7}/plan'); await pg.wait_for_timeout(2500)
    t = await pg.inner_text('.wz-card h2')
    ok(f'{vp} 深链 /plan', '研究方案' in t, t)
    await shot(pg, vp, 'I03_deeplink_plan')
    chips = await pg.query_selector_all('.wz-chip:not(.is-ghost)')
    ok(f'{vp} 产物芯片存在', len(chips) >= 1, str(len(chips)))
    if chips:
        await chips[0].click(); await pg.wait_for_timeout(2000)
        rd = await pg.query_selector('.nb-reader')
        ok(f'{vp} 芯片打开阅读层', rd is not None)
        await shot(pg, vp, 'I04_reader')
        close = pg.locator('.nb-reader [aria-label="关闭"], .nb-reader button:has-text("返回")')
        if await close.count(): await close.first.click(); await pg.wait_for_timeout(400)
    await pg.click('.wz-chip.is-ghost'); await pg.wait_for_timeout(500)
    ok(f'{vp} 全部文件次要入口', await pg.query_selector('.nb-reader .wb-files') is not None)
    await shot(pg, vp, 'I05_all_files')
    await pg.click('.nb-reader >> text=返回向导')
    body = await pg.inner_text('body')
    ok(f'{vp} 无示意/未接入、无聊天', '示意' not in body and '未接入' not in body and not await pg.query_selector('.wb-chat, .dir-msgs'))
    ok(f'{vp} 无页面错误', not errs, '; '.join(errs)[:160])
    # R7 各阶段
    for k, name in [('direction','方向'),('literature','文献'),('data','数据'),('proposal','提案')]:
        await pg.goto(f'{BASE}/p/{R7}/{k}'); await pg.wait_for_timeout(2000)
        await shot(pg, vp, f'I10_{k}')
    await pg.close()
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for vw, vh in [(1024, 576), (1280, 720), (1440, 900)]:
            await run(b, vw, vh)
        await b.close()
    bad = [r for r in res if not r[1]]
    print('ALL PASS' if not bad else f'FAILED {len(bad)}')
    sys.exit(1 if bad else 0)
asyncio.run(main())
