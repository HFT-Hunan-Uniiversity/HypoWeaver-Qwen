# 一屏验收脚本

前提：:8001 脚本后端已在运行并服务 `frontend/dist`（先 `npm run build`）。

```bash
uv run --with playwright python scripts/one-screen/measure_one_screen.py          # 只断言
uv run --with playwright python scripts/one-screen/measure_one_screen.py --shots  # 断言+截图
uv run --with pillow python scripts/one-screen/compare_one_screen.py              # 与 v2r2 并排对比
```

断言：1280×720、1366×768、1440×900（侧栏展开，`--collapsed` 可改折叠）下每个视图的文档与 `.shell-view` 均不出现整页滚动；内容横向跨度 ≥ 内容区 75%（宽度利用率）；
除 `[data-scroll-region]` 外不允许溢出滚动容器。最大连续空白矩形 >30% 时打 ⚠ 供人工复核（不判失败）。失败时退出码非 0。
截图写入 `/workspace/hw/review/screens/one-screen/{1440x900,1280x800}/`，结果写入同目录 `measure.json`。

`verify_r5.py`：用 Playwright route 拦截模拟 R5 字段（suggested_binding、继承绑定 confirmed=false、提案 narrative_status=partial、settings/status 的 llm_model/旧 model），PUT 也被拦截不写数据；截图到 `screens/one-screen/r5/`。
另断言文字不截断：任何元素触发 text-overflow 省略号即失败；data-scroll-region 之外的元素内容被横向/纵向裁剪也失败。

## measure_one_screen.py

Run: `uv run --with playwright python measure_one_screen.py [--shots] [view-name filters] [--collapsed]`
(the frontend must be served by the backends on :8000/:8001; screenshots go to `review/screens/one-screen/<w>x<h>/`).

Viewports: 1024×576, 1180×640, 1280×720, 1366×768, 1440×900. Assertions per view:

- one screen: page does not scroll; only `[data-scroll-region]` areas may scroll;
- no clipping or overflow outside scroll regions;
- no truncation: an ellipsis is allowed only for non-numeric text inside an element with `title` (full text on hover); numbers are never truncated;
- width utilisation ≥ 0.75;
- cards in the same row have equal height;
- blank space inside each card ≤ 15%.
  Output: table "need/viewport, largest card blank, ✓/✗ + reasons", plus `measure.json`.
