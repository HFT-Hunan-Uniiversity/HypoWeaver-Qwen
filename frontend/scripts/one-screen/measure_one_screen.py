"""版面验收（整页滚动版）：内容页允许整页纵向滚动；但任何卡片/区块不得出现内部纵向滚动条，内容不得被裁剪或无提示省略。
（2026-10-14 起替代旧的"一屏不滚动"规则；侧栏项目列表、文本框、弹窗/抽屉、左侧阶段进度栏不在此列。）
用法：python measure_one_screen.py [--shots] [视图名关键字...]   （脚本后端 :8001）"""
import json, sys, asyncio
from playwright.async_api import async_playwright
d = json.load(open('/tmp/fake_ids')); P = d['P']
SEC = ['方法与变量', '模型与识别', '稳健性检查', '置换与决策规则', '计划结论与边界']
VIEWS = [('01_项目列表', '/', None), ('02_总览', f'/p/{P}', None), ('03_方向', f'/p/{P}/direction', None),
         ('04_文献', f'/p/{P}/literature', None), ('05_候选', f'/p/{P}/candidates', None), ('06_方案_概要', f'/p/{P}/plan', None)] + [
         (f'06{chr(98+i)}_方案_{t}', f'/p/{P}/plan', f'.plan-nav >> text={t}') for i, t in enumerate(SEC)] + [
         ('07_数据_资产', f'/p/{P}/data?tab=assets', None), ('07b_数据_绑定', f'/p/{P}/data?tab=binding', None),
         ('08_数据_结果', f'/p/{P}/data?tab=results', None), ('09_提案', f'/p/{P}/proposal', None), ('10_设置', '/settings', None)]
VIEWPORTS = [(1024, 576), (1180, 640), (1280, 720), (1366, 768), (1440, 900)]
CARD_BLANK_MAX = 0.15  # 卡片内部空白上限（总览网格卡片强制，其他页仅报告）
SIDEBAR_OPEN = '--collapsed' not in sys.argv
WIDTH_MIN = 0.75   # 内容横向跨度须 ≥ 可用宽度 75%（硬断言）
BLANK_WARN = 0.30  # 最大连续空白矩形 > 内容区 30% 时告警（软提示，人工复核截图）
JS = """() => {
  const v = document.querySelector('.shell-view');
  const doc = document.scrollingElement;
  const bad = [];
  for (const el of document.querySelectorAll('.shell-view *')) {
    if (el.matches('textarea, select, option') || el.closest('[role="dialog"], .side-drawer, .modal, .rail-drawer, .rail-dock')) continue;
    const oy = getComputedStyle(el).overflowY;
    if ((oy === 'auto' || oy === 'scroll' || oy === 'hidden') && el.scrollHeight > el.clientHeight + 1 && el.clientHeight > 0 && oy !== 'hidden')
      bad.push('内部滚动:' + ((el.className && el.className.toString().split(' ')[0]) || el.tagName));
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
  // 截断/溢出：scroll region 之外，元素内容超出自身且被裁剪，或触发了 text-overflow 省略
  const clipped = [];
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('svg') || el.closest('.recharts-wrapper')) continue;
    const inRegion = !!el.closest('[data-scroll-region]');
    if (el.matches('input, select, textarea, option, svg, img, canvas, .sr-only, [hidden]')) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || !el.getClientRects().length) continue;
    if (el.clientWidth <= 2 && el.clientHeight <= 2) continue;
    const ox = cs.overflowX, oy = cs.overflowY;
    const w = el.scrollWidth > el.clientWidth + 1, h = el.scrollHeight > el.clientHeight + 1;
    const hasText = (el.innerText || '').trim().length > 0;
    if (!hasText) continue;
    let why = '';
    // 说明文字允许单行省略，但必须带 title 提示全文；数值（以数字开头的短文本）一律不得省略
    const titled = !!el.closest('[title]') && (el.closest('[title]').getAttribute('title') || '').trim().length > 0;
    const numeric = /^[-+−]?[0-9.,]+(e[-+]?\d+)?%?$/i.test((el.innerText || '').trim());
    if (cs.textOverflow === 'ellipsis' && w && (!titled || numeric)) why = '省略号';
    else if (cs.textOverflow === 'ellipsis' && w) continue;
    else if (w && ox !== 'visible') why = '横向裁剪';
    else if (h && oy !== 'visible' && !el.closest('.sidebar, [role="dialog"], .rail-dock, .rail-drawer') && !el.matches('textarea') && el !== v && el !== doc && !el.matches('.shell, .shell-main, .shell-body, .shell-view, body, html')) why = '纵向裁剪';
    if (why) clipped.push(why + ':' + ((el.className && el.className.toString().split(' ')[0]) || el.tagName) + '「' + (el.innerText || '').trim().slice(0, 14) + '」');
  }
  // 卡片内部空白与同行等高（总览 .overview-grid 卡片）
  const cards = [];
  const leafOf = (el) => el.matches('input, select, textarea, button, svg, img, canvas, th, td') ||
    [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  for (const c of document.querySelectorAll('.stage-body .panel, .page-body .panel')) {
    if (!c.getClientRects().length || c.closest('[hidden]')) continue;
    const cr = c.getBoundingClientRect(), cs2 = getComputedStyle(c);
    const inner = cr.height - parseFloat(cs2.paddingTop) - parseFloat(cs2.paddingBottom);
    let bottom = cr.top + parseFloat(cs2.paddingTop);
    for (const el of c.querySelectorAll('*')) {
      const bg = getComputedStyle(el).backgroundColor;
      const box = bg && bg !== 'transparent' && !/rgba\(.*,\s*0\)$/.test(bg);  // 有底色的块（如阶段小卡）算内容
      if ((!leafOf(el) && !box) || !el.getClientRects().length) continue;
      const er = el.getBoundingClientRect();
      if (er.height && getComputedStyle(el).visibility !== 'hidden') bottom = Math.max(bottom, Math.min(er.bottom, cr.bottom));
    }
    // 含滚动区的卡片：滚动区本身算作内容（其内部可滚）
    for (const sr of c.querySelectorAll('[data-scroll-region]')) { const q = sr.getBoundingClientRect(); if (q.height) bottom = Math.max(bottom, q.bottom); }
    const blank = Math.max(0, (cr.bottom - parseFloat(cs2.paddingBottom) - bottom)) / Math.max(1, inner);
    cards.push({ name: (c.querySelector('h2,h3')?.innerText || c.className).slice(0, 10), top: Math.round(cr.top), h: Math.round(cr.height), blank: Math.round(blank * 100) / 100, overview: !!c.closest('.overview-grid') });
  }
  const ov = cards.filter(c => c.overview);
  const rows = {};
  for (const c of ov) (rows[c.top] = rows[c.top] || []).push(c.h);
  const row_mismatch = Object.values(rows).some(hs => Math.max(...hs) - Math.min(...hs) > 1);
  const card_blank_max = cards.length ? Math.max(...cards.map(c => c.blank)) : 0;
  const ov_blank_bad = ov.filter(c => c.blank > 0.15).map(c => c.name + ' ' + Math.round(c.blank * 100) + '%');
  const r = v.getBoundingClientRect();
  return { need: Math.round(r.top + v.scrollHeight), view: innerHeight,
           page_scroll: doc.scrollHeight > doc.clientHeight + 1 || v.scrollHeight > v.clientHeight + 1,
           other_scroll: bad, regions_scrolling: regions,
           clipped: clipped, cards: cards, row_mismatch: row_mismatch, card_blank_max: card_blank_max, ov_blank_bad: ov_blank_bad,
           width_util: Math.round(width_util * 100) / 100, blank: Math.round(blank * 100) / 100 };
}"""
async def main():
    args = sys.argv[1:]; shots = '--shots' in args; only = [a for a in args if not a.startswith('--')]
    out = {}
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for vw, vh in VIEWPORTS:
            pg = await b.new_page(viewport={'width': vw, 'height': vh})
            await pg.goto('http://localhost:8001/'); await pg.evaluate("localStorage.clear(); sessionStorage.clear()")
            if SIDEBAR_OPEN: await pg.evaluate("localStorage.setItem('hw-sidebar', '0')")  # 与用户 Mac 一致：侧栏展开（最坏情况）
            for name, path, click in VIEWS:
                if only and not any(o in name for o in only): continue
                await pg.goto(f'http://localhost:8001{path}'); await pg.wait_for_load_state('networkidle'); await pg.wait_for_timeout(900)
                if click: await pg.click(click); await pg.wait_for_timeout(400)
                m = await pg.evaluate(JS); m['pass'] = not m['other_scroll'] and not m['clipped'] and m['width_util'] >= WIDTH_MIN and not m['row_mismatch'] and not m['ov_blank_bad']
                out.setdefault(name, {})[f'{vw}x{vh}'] = m
                if shots: await pg.screenshot(path=f'/workspace/hw/review/screens/one-screen/{vw}x{vh}/{name}.png')
            await pg.close()
        await b.close()
    json.dump(out, open('/workspace/hw/review/screens/one-screen/measure.json', 'w'), ensure_ascii=False, indent=1)
    ok = True
    print('视图\t' + '\t'.join(f'{w}×{h}' for w, h in VIEWPORTS) + '\t局部滚动区\t（每格：需要/视口 卡内最大空白 结果）')
    for k, v in out.items():
        row = [k]
        for vp in [f'{w}x{h}' for w, h in VIEWPORTS]:
            m = v.get(vp)
            if not m: row.append('-'); continue
            ok &= m['pass']
            why = m['other_scroll'][:2] + m['clipped'][:3] + (['宽度<75%'] if m['width_util'] < WIDTH_MIN else []) + \
                  (['同行卡片不等高'] if m['row_mismatch'] else []) + ['卡内空白 ' + x for x in m['ov_blank_bad']]
            row.append(f"{m['need']}/{m['view']} 卡空{m['card_blank_max']:.0%} " + ('✓' if m['pass'] else '✗ ' + ','.join(why)))
        row.append(str(max(x['regions_scrolling'] for x in v.values())))
        print('\t'.join(row))
    print('ALL PASS' if ok else 'FAILED'); sys.exit(0 if ok else 1)
if __name__ == "__main__":
    asyncio.run(main())
