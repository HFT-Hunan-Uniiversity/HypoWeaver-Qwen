# HypoWeaver 前端

React 19 + Vite 7 + TypeScript，数据请求用 TanStack Query，图表用 Recharts，提案正文用 react-markdown 渲染。整体说明见根目录 [README](../README.md)。

## 运行

```sh
npm ci
npm run dev                                   # 默认 http://127.0.0.1:5173
npm run dev -- --host 127.0.0.1 --port 5174   # 演示机使用的端口
npm run build                                 # 类型检查 + 生产构建到 dist/
```

`/api` 默认代理到 `http://127.0.0.1:8000`，可用环境变量 `HW_API` 指向其他后端。需要 Node 22。

## 目录

- `src/pages/`：六个阶段页面（Direction、Literature、Candidates、Plan、Data/Analysis、Proposal）、项目列表和设置页
- `src/components/`：`home/`（首页与侧栏）、`shell/`（外框与阶段布局）、`flow/`、`notebook/` 等
- `src/lib/stages.ts`：阶段顺序与中文名；`src/lib/displayTitle.ts`：侧栏标题清洗（把内部测试名替换为展示名）
- `src/styles/tokens.css`：配色变量（主色砖红 `#b5533a`、墨色 `#18181b`、背景 `#f4f5f7`）
- `public/brand/`：HW 标志（`hw-logo.svg`、`hw-logo-16.svg`，以及 16/32/64/192/512 像素 PNG），用于侧栏、外框、阶段页和 favicon
- `public/cases/carbon/`：碳市场旧案例的配图
- `scripts/`：界面验收脚本，说明见各自 README
- `src/prototype/flow`：流程原型，`npm run proto:flow` 打开
