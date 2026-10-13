# 一屏验收脚本

前提：:8001 脚本后端已在运行并服务 `frontend/dist`（先 `npm run build`）。

```bash
uv run --with playwright python scripts/one-screen/measure_one_screen.py          # 只断言
uv run --with playwright python scripts/one-screen/measure_one_screen.py --shots  # 断言+截图
uv run --with pillow python scripts/one-screen/compare_one_screen.py              # 与 v2r2 并排对比
```

断言：1440×900 与 1280×800 下每个视图的文档与 `.shell-view` 均不出现整页滚动；内容横向跨度 ≥ 内容区 75%（宽度利用率）；
除 `[data-scroll-region]` 外不允许溢出滚动容器。最大连续空白矩形 >30% 时打 ⚠ 供人工复核（不判失败）。失败时退出码非 0。
截图写入 `/workspace/hw/review/screens/one-screen/{1440x900,1280x800}/`，结果写入同目录 `measure.json`。
