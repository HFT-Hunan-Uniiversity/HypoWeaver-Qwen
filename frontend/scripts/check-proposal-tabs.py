"""研究提案「科学十项 / 论文」标签双向切换检查。
用法：uv run --with playwright==1.63.0 python scripts/check-proposal-tabs.py <proposal 页 URL> [...]
每个 URL 在 1280x720 与 1024x576 下依次点 科学十项 → 论文 → 科学十项，确认选中标签与内容（论文=.hw-paper）一致。"""
import sys
from playwright.sync_api import sync_playwright

ok = True
with sync_playwright() as p:
    b = p.chromium.launch()
    for u in sys.argv[1:]:
        for w, h in [(1280, 720), (1024, 576)]:
            pg = b.new_page(viewport={'width': w, 'height': h})
            pg.goto(u)
            pg.wait_for_selector('.proposal-tabs', timeout=20000)
            pg.wait_for_timeout(1500)
            for t in ['科学十项', '论文', '科学十项']:
                pg.click(f'.proposal-tabs [role=tab]:has-text("{t}")')
                pg.wait_for_timeout(1500)
                got = pg.evaluate("document.querySelector('[role=tab][aria-selected=true] strong')?.innerText")
                paper = pg.evaluate("!!document.querySelector('.hw-paper')")
                if got != t or paper != (t == '论文'):
                    ok = False
                    print('FAIL', u, w, 'clicked', t, 'selected', got, 'paper', paper)
            pg.close()
    b.close()
print('ALL OK' if ok else 'FAILED')
sys.exit(0 if ok else 1)
