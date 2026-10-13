# 文字重叠验收

`check_overlap.py` 用真实浏览器（Playwright）打开每个页面和每个标签页（包括展开全部折叠区、修改确认框、空项目的方向页和未解锁页），对比所有可见叶子文字的逐行矩形：

- 两段文字交叠超过 2px，或者一段文字被普通流式内容（非弹层）盖住，都算失败；
- 祖先与后代天然不会互比；
- 被 overflow 裁掉、隐藏、透明、处在未展开 details 中的文字不参与比较；
- 被弹窗、抽屉等浮层盖住的文字也跳过。

```
HW_API=http://127.0.0.1:8002 npx vite --port 5193      # 指向任一后端
uv run --with playwright python scripts/overlap/check_overlap.py \
  --base http://localhost:5193 --project <已走完流程的项目> [--fresh <空项目>] \
  [--shots DIR] [--viewports 1024x576,1280x720,1440x900] [--only 关键字]
```

退出码非 0 表示存在重叠。
