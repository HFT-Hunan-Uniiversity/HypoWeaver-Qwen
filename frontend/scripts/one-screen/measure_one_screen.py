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
WIDTH_MIN = 0.75   # 内容横向跨度须 ≥ 可用宽度 75%（硬断言）
BLANK_WARN = 0.30  # 最大连续空白矩形 > 内容区 30% 时告警（软提示，人工复核截图）
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
  // 宽度利用率与大块空白：以内容区 .stage-body/.page-body 为基准，统计可见“叶子”内容（文字、控件、图表）
  const B = document.querySelector('.stage-body, .page-body');
  let width_util = 1, blank = 0;
  if (B) {
    const br = B.getBoundingClientRect(), cs = getComputedStyle(B);
    const L = br.left + parseFloat(cs.paddingLeft), R = br.right - parseFloat(cs.paddingRight);
    const T = br.top + parseFloat(cs.paddingTop), Bo = br.bottom - parseFloat(cs.paddingBottom);
    const GX = 32, GY = 20, grid = Array.from({length: GY}, () => new Array(GX).fill(0));
    let minX = Infinity, maxX = -Infinity;
    const leaf = (el) => el.matches('input, select, textarea, button, svg, img, canvas, th, td') ||
      [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    for (const el of B.querySelectorAll('*')) {
      if (el.closest('svg') && !el.matches('svg')) continue;
      if (!leaf(el)) continue;
      let r = el.getBoundingClientRect();
      if (!r.width || !r.height || getComputedStyle(el).visibility === 'hidden') continue;
      let x1 = r.left, x2 = r.right, y1 = r.top, y2 = r.bottom;
      const sr = el.closest('[data-scroll-region]');
      if (sr) { const q = sr.getBoundingClientRect(); x1 = Math.max(x1, q.left); x2 = Math.min(x2, q.right); y1 = Math.max(y1, q.top); y2 = Math.min(y2, q.bottom); }
      x1 = Math.max(x1, L); x2 = Math.min(x2, R); y1 = Math.max(y1, T); y2 = Math.min(y2, Bo);
      if (x2 <= x1 || y2 <= y1) continue;
      minX = Math.min(minX, x1); maxX = Math.max(maxX, x2);
      for (let gy = Math.floor((y1 - T) / (Bo - T) * GY); gy < Math.min(GY, Math.ceil((y2 - T) / (Bo - T) * GY)); gy++)
        for (let gx = Math.floor((x1 - L) / (R - L) * GX); gx < Math.min(GX, Math.ceil((x2 - L) / (R - L) * GX)); gx++)
          grid[gy][gx] = 1;
    }
    width_util = maxX > minX ? (maxX - minX) / (R - L) : 0;
    // 最大全空矩形（网格单元），占内容区面积比例
    const h = new Array(GX).fill(0); let best = 0;
    for (let y = 0; y < GY; y++) {
      for (let x = 0; x < GX; x++) h[x] = grid[y][x] ? 0 : h[x] + 1;
      const st = [];
      for (let x = 0; x <= GX; x++) {
        const cur = x === GX ? 0 : h[x];
        while (st.length && h[st[st.length - 1]] >= cur) {
          const top = h[st.pop()], w = st.length ? x - st[st.length - 1] - 1 : x;
          best = Math.max(best, top * w);
        }
        st.push(x);
      }
    }
    blank = best / (GX * GY);
  }
  const r = v.getBoundingClientRect();
  return { need: Math.round(r.top + v.scrollHeight), view: innerHeight,
           page_scroll: doc.scrollHeight > doc.clientHeight + 1 || v.scrollHeight > v.clientHeight + 1,
           other_scroll: bad, regions_scrolling: regions,
           width_util: Math.round(width_util * 100) / 100, blank: Math.round(blank * 100) / 100 };
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
                m = await pg.evaluate(JS); m['pass'] = not m['page_scroll'] and not m['other_scroll'] and m['width_util'] >= WIDTH_MIN
                out.setdefault(name, {})[f'{vw}x{vh}'] = m
                if shots: await pg.screenshot(path=f'/workspace/hw/review/screens/one-screen/{vw}x{vh}/{name}.png')
            await pg.close()
        await b.close()
    json.dump(out, open('/workspace/hw/review/screens/one-screen/measure.json', 'w'), ensure_ascii=False, indent=1)
    ok = True
    print('视图\t1440×900 需要/视口\t宽度\t空白\t通过\t1280×800 需要/视口\t宽度\t空白\t通过\t局部滚动区')
    for k, v in out.items():
        row = [k]
        for vp in ['1440x900', '1280x800']:
            m = v.get(vp)
            if not m: row += ['-'] * 4; continue
            ok &= m['pass']
            why = m['other_scroll'][:2] + (['宽度<75%'] if m['width_util'] < WIDTH_MIN else [])
            row += [f"{m['need']}/{m['view']}", f"{m['width_util']:.0%}",
                    f"{m['blank']:.0%}" + (' ⚠' if m['blank'] > BLANK_WARN else ''),
                    '✓' if m['pass'] else '✗ ' + ','.join(why)]
        row.append(str(max(x['regions_scrolling'] for x in v.values())))
        print('\t'.join(row))
    print('ALL PASS' if ok else 'FAILED'); sys.exit(0 if ok else 1)
asyncio.run(main())
