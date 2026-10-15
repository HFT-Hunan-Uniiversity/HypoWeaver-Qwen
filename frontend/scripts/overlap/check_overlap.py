"""文字重叠验收：任意两个可见的叶子文字（文本节点逐行矩形）不得互相重叠。
- 只比较文本节点（叶子），天然排除祖先/后代嵌套；同一文本节点的多行不互比。
- 被祖先 overflow 裁剪掉的部分先裁掉；完全裁掉、隐藏、透明的跳过。
- 被浮层盖住（该点最上层元素不是此文字所在元素）的文字视为不可见，跳过（弹窗、抽屉属正常遮挡）。
用法：
  python check_overlap.py --base http://localhost:5193 --project <id> [--shots DIR] [--viewports 1024x576,1280x720,1440x900]
退出码非 0 表示存在重叠。"""
import argparse, asyncio, json, os, sys
from playwright.async_api import async_playwright

TOL = 2  # 交叠宽/高都超过 2px 才算重叠（抗锯齿与行距误差）

JS = r"""(tol) => {
  const vis = (el) => {
    for (let e = el; e && e !== document.documentElement; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false;
      if (e.matches('.sr-only, [aria-hidden="true"]')) return false;
      if (e.parentElement && e.parentElement.matches('details:not([open])') && !e.matches('summary')) return false;
    }
    return true;
  };
  const clipOf = (el) => {
    let c = { l: 0, t: 0, r: innerWidth, b: innerHeight };
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.overflowX !== 'visible' || cs.overflowY !== 'visible') {
        const r = e.getBoundingClientRect();
        c = { l: Math.max(c.l, r.left), t: Math.max(c.t, r.top), r: Math.min(c.r, r.right), b: Math.min(c.b, r.bottom) };
      }
    }
    return c;
  };
  const items = [], covered = [];
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n, id = 0;
  while ((n = w.nextNode())) {
    if (!n.textContent.trim()) continue;
    const el = n.parentElement;
    if (!el || el.closest('svg, script, style, option, textarea, select') || !vis(el)) continue;
    const c = clipOf(el);
    const range = document.createRange(); range.selectNodeContents(n);
    const myId = id++;
    for (const r of range.getClientRects()) {
      const l = Math.max(r.left, c.l), t = Math.max(r.top, c.t), ri = Math.min(r.right, c.r), b = Math.min(r.bottom, c.b);
      if (ri - l < 1 || b - t < 1) continue;
      const top = document.elementFromPoint((l + ri) / 2, (t + b) / 2);
      const txt = n.textContent.trim().slice(0, 30);
      if (!top) continue;
      if (!(el === top || el.contains(top) || top.contains(el))) {
        // 被浮层（fixed/sticky/absolute 弹层、对话框、抽屉）盖住属正常；被普通流式内容盖住则是布局错误
        let overlay = false;
        for (let e = top; e && e !== document.body; e = e.parentElement) {
          const p = getComputedStyle(e).position;
          if (p === 'fixed' || p === 'sticky' || e.matches('dialog, [role="dialog"], [role="tooltip"], [role="menu"]')) { overlay = true; break; }
          if (e.contains(el)) break;
        }
        if (!overlay) covered.push(`「${txt}」(${el.className || el.tagName}) 被 ${(top.className && top.className.toString().split(' ')[0]) || top.tagName} 遮住`);
        continue;
      }
      items.push({ id: myId, l, t, r: ri, b, text: n.textContent.trim().slice(0, 30),
                   sel: (el.className && el.className.toString().split(' ')[0]) || el.tagName.toLowerCase() });
    }
  }
  const hits = [...new Set(covered)];
  for (let i = 0; i < items.length; i++) for (let j = i + 1; j < items.length; j++) {
    const a = items[i], b = items[j];
    if (a.id === b.id) continue;
    const ox = Math.min(a.r, b.r) - Math.max(a.l, b.l), oy = Math.min(a.b, b.b) - Math.max(a.t, b.t);
    if (ox > tol && oy > tol) hits.push(`「${a.text}」(${a.sel}) × 「${b.text}」(${b.sel}) ${ox.toFixed(0)}×${oy.toFixed(0)}px`);
  }
  return hits;
}"""

def views(P, F=None):
    SEC = ['方法与变量', '模型与识别', '稳健性检查', '置换与决策规则', '计划结论与边界']
    v = [('01_projects', '/', []), ('02_overview', f'/p/{P}', []),
         ('03_direction', f'/p/{P}/direction', []), ('04_literature', f'/p/{P}/literature', []),
         ('04b_literature_open', f'/p/{P}/literature', ['details']),
         ('05_candidates', f'/p/{P}/candidates', []), ('05b_candidates_open', f'/p/{P}/candidates', ['details']),
         ('06_plan', f'/p/{P}/plan', [])]
    v += [(f'06{chr(98 + i)}_plan_{i + 1}', f'/p/{P}/plan', [f'.plan-nav >> text={t}']) for i, t in enumerate(SEC)]
    v += [('07_data_assets', f'/p/{P}/data?tab=assets', []), ('07b_data_assets_open', f'/p/{P}/data?tab=assets', ['details']),
          ('08_data_binding', f'/p/{P}/data?tab=binding', []), ('08b_data_binding_open', f'/p/{P}/data?tab=binding', ['details']),
          ('09_data_results', f'/p/{P}/data?tab=results', []), ('09b_data_results_open', f'/p/{P}/data?tab=results', ['details']),
          ('10_proposal', f'/p/{P}/proposal', []), ('10b_proposal_open', f'/p/{P}/proposal', ['details']),
          ('11_edit_dialog', f'/p/{P}/plan', ['edit']), ('12_settings', '/settings', [])]
    if F:  # 空项目：方向空状态、对话中、未解锁阶段
        v += [('20_fresh_direction_empty', f'/p/{F}/direction', []),
              ('21_fresh_direction_idea', f'/p/{F}/direction', ['chat']),
              ('22_fresh_literature_locked', f'/p/{F}/literature', []),
              ('23_fresh_data_locked', f'/p/{F}/data', [])]
    return v

async def run(a):
    vps = [tuple(map(int, s.split('x'))) for s in a.viewports.split(',')]
    total = 0
    async with async_playwright() as p:
        br = await p.chromium.launch()
        for W, H in vps:
            for intro in (True, False):
                ctx = await br.new_context(viewport={'width': W, 'height': H}, device_scale_factor=1)
                if not intro:
                    await ctx.add_init_script("for (const s of ['direction','literature','candidates','plan','data','proposal']) localStorage.setItem('hw.intro.'+s,'0')")
                pg = await ctx.new_page()
                for name, path, acts in [v for v in views(a.project, a.fresh) if a.only in v[0]]:
                    if intro and not name[:2] in ('03', '04', '05', '06', '07', '10', '20') or (intro and len(name) > 3 and name[2] == 'b'):
                        continue
                    await pg.goto(a.base + path); await pg.wait_for_load_state('networkidle'); await pg.wait_for_timeout(500)
                    for act in acts:
                        if act == 'details':
                            await pg.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
                        elif act == 'chat':
                            await pg.evaluate("localStorage.removeItem('hw.dirdraft.' + location.pathname.split('/')[2])")
                            await pg.reload(); await pg.wait_for_load_state('networkidle')
                            # J：一句话想法（示例）→ 方向卡 + 卡内澄清提示，点两次提示选项
                            chip = pg.locator('.dir-chip').first
                            if await chip.count(): await chip.click(); await pg.wait_for_timeout(300)
                            for _ in range(2):
                                chip = pg.locator('.dir-ask .dir-chip').first
                                if await chip.count(): await chip.click(); await pg.wait_for_timeout(300)
                        elif act == 'edit':
                            b = pg.locator('.nb-ro button:has-text("修改")')
                            if await b.count(): await b.first.click()
                        else:
                            loc = pg.locator(act)
                            if await loc.count(): await loc.first.click()
                        await pg.wait_for_timeout(300)
                    tag = name + ('_intro' if intro else '')
                    # 整页滚动：逐屏滚动主视图检查（吸顶页头属浮层，被它盖住的文字跳过）
                    hits, sh = [], await pg.evaluate("document.scrollingElement.scrollHeight")
                    for y in range(0, max(1, sh - H + 1), max(200, H - 120)):
                        await pg.evaluate(f"window.scrollTo(0, {y})")
                        await pg.wait_for_timeout(60)
                        hits += [h for h in await pg.evaluate(JS, TOL) if h not in hits]
                    await pg.evaluate("window.scrollTo(0, 0)")
                    total += len(hits)
                    print(f"{'PASS' if not hits else 'FAIL'} {W}x{H} {tag}" + ''.join(f'\n    {h}' for h in hits[:12]))
                    if a.shots:
                        d = os.path.join(a.shots, f'{W}x{H}'); os.makedirs(d, exist_ok=True)
                        if a.full and 'edit' not in acts:  # 整页截图（J：html/body 整页滚动）；弹窗视图截视口
                            await pg.screenshot(path=os.path.join(d, tag + '.png'), full_page=True)
                        else:
                            await pg.screenshot(path=os.path.join(d, tag + '.png'))
                await ctx.close()
        await br.close()
    print('ALL PASS' if total == 0 else f'{total} OVERLAPS')
    return total

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5193'); ap.add_argument('--project', required=True)
    ap.add_argument('--shots'); ap.add_argument('--only', default=''); ap.add_argument('--full', action='store_true', help='整页截图'); ap.add_argument('--fresh', help='一个尚未填写方向的项目 id（可选）'); ap.add_argument('--viewports', default='1024x576,1280x720,1440x900')
    sys.exit(1 if asyncio.run(run(ap.parse_args())) else 0)
