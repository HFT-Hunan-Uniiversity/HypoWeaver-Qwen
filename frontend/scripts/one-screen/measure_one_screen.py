"""一屏验收：每个视图在 1440×900 / 1280×800 下不得整页滚动，只允许 [data-scroll-region] 内滚动。
用法：python measure_one_screen.py [--shots] [视图名关键字...]   （脚本后端 :8001）"""
import json, sys, asyncio
from playwright.async_api import async_playwright
d = json.load(open('/tmp/fake_ids')); P = d['P']
SEC = ['方法与变量', '模型与识别', '稳健性检查', '置换与决策规则', '计划结论与边界']
VIEWS = [('01_项目列表', '/', None), ('02_总览', f'/p/{P}', None), ('03_方向', f'/p/{P}/direction', None),
         ('04_文献', f'/p/{P}/literature', None), ('05_候选_逐个', f'/p/{P}/candidates', None),
         ('05b_候选_对比', f'/p/{P}/candidates', 'text=对比视图'), ('06_方案_概要', f'/p/{P}/plan', None)] + [
         (f'06{chr(98+i)}_方案_{t}', f'/p/{P}/plan', f'.plan-nav >> text={t}') for i, t in enumerate(SEC)] + [
         ('07_数据_资产', f'/p/{P}/data?tab=assets', None), ('07b_数据_绑定', f'/p/{P}/data?tab=binding', None),
         ('08_数据_结果', f'/p/{P}/data?tab=results', None), ('09_提案', f'/p/{P}/proposal', None), ('10_设置', '/settings', None)]
JS = """() => {
  const v = document.querySelector('.shell-view');
  const doc = document.scrollingElement;
  const bad = [];
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('[data-scroll-region]') && !el.matches('[data-scroll-region]')) continue;
    if (el.matches('[data-scroll-region], textarea, .task-context__scroll, .sidebar__list')) continue;
    const oy = getComputedStyle(el).overflowY;
    if ((oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight + 1)
      bad.push((el.className && el.className.toString().slice(0, 40)) || el.tagName);
  }
  const regions = [...document.querySelectorAll('[data-scroll-region]')].filter(e => e.scrollHeight > e.clientHeight + 1).length;
  const r = v.getBoundingClientRect();
  return { need: Math.round(r.top + v.scrollHeight), view: innerHeight,
           page_scroll: doc.scrollHeight > doc.clientHeight + 1 || v.scrollHeight > v.clientHeight + 1,
           other_scroll: bad, regions_scrolling: regions };
}"""
async def main():
    args = sys.argv[1:]; shots = '--shots' in args; only = [a for a in args if a != '--shots']
    out = {}
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for vw, vh in [(1440, 900), (1280, 800)]:
            pg = await b.new_page(viewport={'width': vw, 'height': vh})
            await pg.goto('http://localhost:8001/'); await pg.evaluate("localStorage.clear(); sessionStorage.clear()")
            for name, path, click in VIEWS:
                if only and not any(o in name for o in only): continue
                await pg.goto(f'http://localhost:8001{path}'); await pg.wait_for_load_state('networkidle'); await pg.wait_for_timeout(900)
                if click: await pg.click(click); await pg.wait_for_timeout(400)
                m = await pg.evaluate(JS); m['pass'] = not m['page_scroll'] and not m['other_scroll']
                out.setdefault(name, {})[f'{vw}x{vh}'] = m
                if shots: await pg.screenshot(path=f'/workspace/hw/review/screens/one-screen/{vw}x{vh}/{name}.png')
            await pg.close()
        await b.close()
    json.dump(out, open('/workspace/hw/review/screens/one-screen/measure.json', 'w'), ensure_ascii=False, indent=1)
    ok = True
    print('视图\t1440×900 需要/视口\t通过\t1280×800 需要/视口\t通过\t局部滚动区')
    for k, v in out.items():
        row = [k]
        for vp in ['1440x900', '1280x800']:
            m = v.get(vp)
            if not m: row += ['-', '-']; continue
            ok &= m['pass']
            row += [f"{m['need']}/{m['view']}", '✓' if m['pass'] else '✗ ' + ','.join(m['other_scroll'][:2])]
        row.append(str(max(x['regions_scrolling'] for x in v.values())))
        print('\t'.join(row))
    print('ALL PASS' if ok else 'FAILED'); sys.exit(0 if ok else 1)
asyncio.run(main())
