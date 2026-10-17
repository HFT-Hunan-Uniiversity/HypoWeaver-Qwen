<p align="center"><img src="frontend/public/brand/hw-logo-192.png" width="96" alt="HypoWeaver 标志"></p>

# HypoWeaver v2

**HypoWeaver 是一个在本机运行的实证研究工作台。** 你写下一个研究问题，它带你按六步走完：查文献、生成候选假设、定研究方案、导入真实数据并跑统计检验，最后写出一份十项结构的研究提案。

它的核心价值有三点：

1. **大模型负责广度。** 生成检索式、候选假设、研究方案和提案文字，接入阿里云百炼的通义千问（DashScope Qwen）。
2. **计量负责可信。** 所有数字都由代码在真实数据上算出来，包括主回归、事件研究、稳健性、置换检验和独立复算。大模型不能编造数字，引用的文献必须真实存在于证据库中。
3. **结论强度由数据封顶。** 系统根据检验结果和处理变量的性质，给每条结论定一个“最高允许强度”。研究者只能降级，不能升级，提案里超出强度的措辞（如“促进”“导致”）会被拦下。

> 相关文档：后端 [backend/README](backend/README.md) · 前端 [frontend/README](frontend/README.md) · 后端接口约定 [API_NOTES](docs/API_NOTES.md) · 碳市场数据 [DATA_carbon_case](docs/DATA_carbon_case.md)

---

## 一、六个阶段在做什么

界面是向导式的：只有一条路，每页一个主按钮，确认后进入下一阶段。还没走到的阶段锁定；修改已确认的阶段会生成新版本，下游阶段标黄点“需要更新”，按顺序重做即可，历史版本都保留可查。

| # | 阶段（界面名） | 你做什么 | 系统做什么 |
|---|---|---|---|
| 1 | 研究方向 | 写下问题、研究对象和约束 | 保存方向，作为后续所有步骤的起点 |
| 2 | 文献调研 | 用模型生成或手写最多 6 条中英文检索式；筛选证据；可上传 PDF | OpenAlex + Crossref 联合检索、去重、按相关性融合排序（默认纳入前 40 条）；画出年度、期刊、关键词、方法分布概况 |
| 3 | 缺口与候选 | 比较多组候选，打开引用查看依据，选定一个并可编辑 | 基于证据卡生成多组可检验的候选假设（缺口、假设、数据需求、风险），自审一次，删除无效引用 |
| 4 | 研究方案 | 审阅变量定义、识别假设、事件窗口、稳健性和决策规则，确认后锁定 | 起草方案，方法分三类：政策因果、面板关联、机制与边界 |
| 5 | 数据与检验 | 上传 `.csv/.xlsx/.dta`，把方案变量绑定到数据字段，点“统计检验” | 就绪检查后跑主模型（双向固定效应）、事件研究与前趋势检验、稳健性、置换检验（默认 499 次）、statsmodels 独立复算，再给出结论评估 |
| 6 | 研究提案 | 审阅、编辑叙述，确认提案，导出 Markdown 或打印成 PDF | 生成十项提案；有数据时带实证结果，没有数据时生成计划型提案和待补清单 |

### 结论强度如何被“封顶”

结论强度从低到高共五级：**证据不足 → 初步线索 → 混合证据 → 关联 → 谨慎因果**。系统按以下规则自动定出上限（代码见 `backend/hypoweaver/claims/service.py`）：

- 主模型失败，或独立复算与主模型不一致：上限为“证据不足”。
- 主系数方向或显著性不符合预期：上限为“证据不足”（判定为“不支持”）。
- 方向对，但稳健性同向比例不够、置换检验没过，或政策因果设计的前趋势检验没过：上限为“初步线索”。
- 以上全部通过：上限为“关联”。
- 只有当方法是政策因果、**且**研究者确认处理变量是真实的政策分配时，才可能到“谨慎因果”。像“行业同群暴露”这类变量，最高只能写“关联”。

研究者可以接受、降级、暂缓或拒绝结论，但不能升级（直接调接口升级也会被拒绝）。提案叙述会检查措辞，超出强度的说法无法保存。

### 十项研究提案

一、待研究问题；二、解决思路；三、必要的技术手段；四、数据集；五、标题；六、摘要；七、方法论；八、实验设计；九、实验结果；十、参考论文。

其中“实验结果”和“参考论文”由系统根据检验结果和证据卡生成，只读；其余八项由模型撰写，数字以占位符注入，经过数字和措辞校验。确认提案后（`POST /api/proposals/{id}/confirm`），首页侧栏里该项目显示“已完成”。

---

## 二、整体架构

```
浏览器 (React 19 + Vite 7 + TypeScript)
   │  /api 请求（开发时由 Vite 代理到 127.0.0.1:8000）
   ▼
后端 FastAPI (Python 3.12, uvicorn)
   ├─ projects / jobs        项目、后台任务、阶段状态与过期传播
   ├─ literature / landscape 文献检索（OpenAlex、Crossref）、PDF 解析、文献概况
   ├─ candidates / plans     候选假设与研究方案（调用大模型，Pydantic 校验输出）
   ├─ datasets / binding     数据导入、字段语义、变量绑定与就绪检查
   ├─ stats / claims         统计引擎（linearmodels / statsmodels）、置换、复算、结论评估
   ├─ proposal               十项提案生成、校验、确认与 Markdown 导出
   ├─ llm                    大模型配置与调用（OpenAI 兼容接口 → DashScope Qwen）
   └─ cases                  碳市场案例数据准备；旧案例只读标记
   │
   ▼
DATA_DIR（默认仓库根目录 var/）
   ├─ hypoweaver.sqlite      全部项目数据
   ├─ .env.llm               设置页保存的模型配置（权限 0600，不入 Git）
   ├─ staging/ datasets/ raw/ 上传原件、分析用 CSV、案例原始数据
```

- **大模型**：后端用 OpenAI 官方 SDK 连接 DashScope 的“OpenAI 兼容模式”，地址 `https://dashscope.aliyuncs.com/compatible-mode/v1`。模型名不写死，从配置读取：代码默认 `qwen-plus`，演示机在设置页配置的是 `qwen3.8-flash`。早期验收用过的 Luna/Codex 桥接已经移除，后端只走这一条 OpenAI 兼容通道。
- **数据库**：单机 SQLite，刷新或重启不丢数据。
- **构建后**，后端也可以直接托管 `frontend/dist`，只开 8000 一个端口也能用。

---

## 三、快速开始

### 1. 需要准备

- Python 3.12 和 [uv](https://docs.astral.sh/uv/)
- Node 22（仓库里有 `.nvmrc`）
- 一个阿里云百炼（DashScope）API Key。没有 Key 也能启动，文献检索、PDF、数据导入和统计检验都能用，只是需要大模型的步骤会提示“未配置模型”。

### 2. 配置

```sh
cp .env.example .env
```

打开 `.env` 填写（**不要把真实密钥提交到 Git**，`.env` 已在 `.gitignore` 中）：

| 变量 | 含义 | 示例 |
|---|---|---|
| `LLM_API_KEY` | DashScope API Key | `sk-你的密钥`（留空则模型步骤不可用） |
| `LLM_BASE_URL` | OpenAI 兼容地址 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `LLM_MODEL` | 模型名 | `qwen-plus`、`qwen3.8-flash` 等 |
| `CONTACT_EMAIL` | 联系邮箱，随 OpenAlex/Crossref 请求发送（可空） | |
| `DATA_DIR` | 数据目录，相对路径以仓库根目录为准 | `./var` |
| `LOCAL_LIBRARY_DIR` | 可选，本地文献库目录 | 留空 |

**也可以不改 `.env`**：启动后点侧栏底部的“服务与设置”（地址 `/settings`），填写地址、密钥和模型名并测试连接。设置页保存到 `DATA_DIR/.env.llm`，优先于 `.env`，重启后仍生效。

### 3. 安装与启动

```sh
make setup     # 安装后端（uv sync）和前端（npm ci）依赖
make dev       # 同时启动后端 :8000 和前端 :5173
```

打开 http://localhost:5173 。也可以分开启动：

```sh
# 后端
cd backend && uv run uvicorn hypoweaver.app:app --reload --port 8000
# 前端（另开一个终端）
cd frontend && npm run dev -- --host 127.0.0.1 --port 5174
```

前端默认端口是 5173，加 `--port` 可改，答辩演示机用的是 **5174**。前端把 `/api` 转发到 `http://127.0.0.1:8000`，可用环境变量 `HW_API` 改成别的后端地址。如果电脑开了代理，访问本机地址时请设置 `NO_PROXY=127.0.0.1,localhost`。

只开后端的方式：先 `make build`，再启动后端，打开 http://localhost:8000 。

### 4. 答辩演示机的实际部署（参考）

演示机上，前后端在 `screen` 会话里常驻：

- `hw_back`：在本仓库 `backend/` 下运行 uvicorn `--port 8000`，`DATA_DIR` 指向旧检出目录 `../HypoWeaver-Qwen/var`（真实演示数据都在那里），Python 环境借用 `../HypoWeaver-Qwen/backend/.venv`。
- `hw_front_flow`：在本仓库 `frontend/` 下运行 `vite --host 127.0.0.1 --port 5174`。

查看：`screen -ls`；进入：`screen -r hw_back`；退出但不关闭：先按 `Ctrl-A` 再按 `D`。**不要随意删除或覆盖 `var/` 下的数据库和备份文件。**

---

## 四、演示案例

首页侧栏里有三个真实项目：

| 项目 | 来源 | 说明 |
|---|---|---|
| 碳市场行业同群暴露与企业绿色发明 | 在本系统里实际走完六步的项目 | 研究问题：碳市场行业同群暴露是否提升企业绿色发明？使用碳市场公开数据，结论上限为“关联”；提案已确认（第 1 版），侧栏显示“已完成” |
| 碳市场约束能否转化为企业高质量绿色创新？ | 旧仓库的真实案例，导入为只读项目 | 14,196 条企业—年份观测、1,183 家上市公司（2010—2021）；政策暴露系数 0.0717（企业聚类 SE=0.0204，p=0.00043）；前趋势联合检验 p=0.494；499 次置换 p=0.004。数据来自 Mendeley 公开数据集（CC BY 4.0） |
| 绿色金融试验区能否改善城市空气质量？（Case009） | 旧仓库的真实案例，导入为只读项目 | Harvard Dataverse 公开数据（CC0）；8 个核心校验门全部通过，但目标因果结论**未获准写入**，用来展示系统的“科学防线” |

两个旧案例的正文原样取自 `docs/legacy_cases/carbon.md` 和 `case009.md`，碳市场案例的配图在 `frontend/public/cases/carbon/`。重新导入（会先自动备份数据库，可重复执行）：

```sh
DATA_DIR=<数据目录> python3 scripts/import_legacy_cases.py
# 或直接指定数据库
python3 scripts/import_legacy_cases.py --db <数据目录>/hypoweaver.sqlite
```

### 自己准备碳市场数据

想在“数据与检验”阶段从头跑碳市场数据：

```sh
cd backend
uv run python -m hypoweaver.cases.carbon fetch     # 下载公开数据（约 330 MB）
uv run python -m hypoweaver.cases.carbon prepare   # 核验并登记为数据资产
```

如果手上已有原始 `data.dta`，放到 `DATA_DIR/raw/data.dta` 后只运行 `prepare`。下载来源、字段含义和引用方式见 [DATA_carbon_case.md](docs/DATA_carbon_case.md)。

建议绑定：结果变量 `log1p(green_invention_independent + green_invention_joint)`，核心解释变量 `industry_peer_exposure`，个体 `firm_id`，时期 `year`，控制变量 `log(total_assets)`、`leverage`、`return_on_assets`。原始 `Size` 是资产总计，不能再当成已取对数的值。该数据的核心变量是**行业同群暴露**，不是企业实际的控排身份，所以“真实处理分配”要保持为否，结论最高只到“关联”。默认按企业聚类；如需核验行业层面误差，可在新方案版本里把聚类字段改为 `industry_code` 单独运行。事件研究只用路径单调的样本，前趋势检验通过不等于识别假设成立。数据引用 Daihui Wei 的 Mendeley 数据集，不能当成某篇期刊论文的结论。

---

## 五、数据与文献的细节

**导入研究数据**：在“数据与检验”页上传 `.csv`、`.xlsx` 或 `.dta`，查看列名和标签，选择需要的列后确认导入。Excel 可以切换工作表，Stata 只加载选中的列。已上传的文件可以复用。

**上限**：单文件 500 MB、300 列、200 万行；`DATA_DIR` 下 `staging/`、`datasets/`、`raw/` 合计不超过 3 GB。达到上限会停止新导入并提示原因，不会删除历史数据。`staging/` 存上传原件，`datasets/` 存已登记资产引用的 CSV，`raw/` 存案例原件。产品不提供自动清理，要释放空间请先备份，也不要删除数据库正在引用的 CSV。

**文献**：最多 6 条中英文检索式，OpenAlex 和 Crossref 联合检索，每个来源的成功或失败都会显示，一个来源失败不影响另一个。上传的 PDF 提取前 100 页文字，保留前 12000 字摘录；扫描件需要先 OCR。`LOCAL_LIBRARY_DIR` 可指向一个本地目录：优先读取 `library.jsonl`（每行一张证据卡，至少有字符串 `title`，可带 `year`、`doi`、`authors`、`abstract`、`concepts`），没有时读取目录顶层的 PDF。索引最多 10 MB / 2000 行，PDF 最多 200 个、每个 30 MB。

**大模型未配置时**：生成检索式、候选、方案、绑定建议、提案和连接测试都会直接返回 HTTP 409（`llm_not_configured`），不会创建任务。

---

## 六、目录结构

```
HypoWeaver-Qwen-flow/
├─ README.md               本文件
├─ Makefile                setup / dev / test / build
├─ .env.example            配置示例（不含真实密钥）
├─ backend/
│  ├─ pyproject.toml       Python 依赖（uv 管理）
│  ├─ hypoweaver/          后端代码，按功能分模块（见上文架构图）
│  │  ├─ app.py            FastAPI 入口，注册所有路由，可托管前端 dist
│  │  └─ config.py         配置项（LLM_*、DATA_DIR 等）
│  └─ tests/               自动测试（pytest）
├─ frontend/
│  ├─ index.html           入口（favicon 使用新 HW 标志）
│  ├─ vite.config.ts       开发服务器与 /api 代理
│  ├─ public/brand/        HW 标志：hw-logo.svg、hw-logo-16.svg 及 16/32/64/192/512 像素 PNG
│  ├─ public/cases/        旧案例配图
│  ├─ scripts/             界面验收脚本（一屏检查、文字重叠检查）
│  └─ src/
│     ├─ pages/            六个阶段页面、项目列表、设置页
│     ├─ components/       通用组件（home 首页侧栏、shell 外框、flow 流程等）
│     ├─ lib/              阶段定义、标题清洗等工具
│     ├─ api/              后端接口封装
│     └─ styles/           样式（tokens.css 定义主色：砖红 #b5533a 等）
├─ docs/
│  ├─ API_NOTES.md         各轮后端接口约定
│  ├─ DATA_carbon_case.md  碳市场公开数据说明
│  └─ legacy_cases/        两个旧案例的十项提案原文
└─ scripts/
   ├─ dev.py               make dev 调用，同时启动前后端
   └─ import_legacy_cases.py  导入旧案例为只读项目
```

---

## 七、开发与测试

```sh
make test     # 后端测试：cd backend && uv run pytest -q
make build    # 前端类型检查 + 生产构建
```

- 测试覆盖统计引擎、结论评估、数据导入、旧案例导入、提案确认，以及从建项目到提案的 API 主流程。大模型和文献网络在测试中用隔离的替身，**测试通过不代表真实模型输出质量已验证**。
- 2026-10-17 在演示机上运行结果：164 项通过，2 项跳过。跳过的是依赖真实碳市场数据的测试，测试数据目录里没有登记碳数据时会自动跳过；先 `carbon prepare` 再跑才能覆盖这一项。
- 开发约定：模型名不写死；产品里没有模拟数据或演示旁路；所有数字只由代码产生；大模型输出必须经过 Pydantic 校验，引用的证据 ID 必须真实存在；失败时直接显示清楚的错误。
- 当前演示分支是 `ui-merged`，答辩版本标签为 `v2-demo-20261017`。旧标签 `v2-demo-20261016`（提交 `51d46be`）早于旧案例导入、提案确认和新标志，仅作历史保留。

---

## 八、常见问题与已知局限

**Q：打开页面提示“未配置模型”？**
到侧栏底部的“服务与设置”页填写 DashScope 地址、密钥和模型名，点测试连接；或在 `.env` 里填 `LLM_API_KEY` 后重启后端。

**Q：页面打不开或接口报错？**
确认后端 8000 端口在运行（访问 http://127.0.0.1:8000/api/health 应返回 `{"status":"ok"}`）；开了代理时设置 `NO_PROXY=127.0.0.1,localhost`。

**Q：数据存在哪？会丢吗？**
都在 `DATA_DIR`（默认 `var/`）的 SQLite 里，刷新或重启不会丢。删除项目需要二次确认。

**已知局限**

- **方法论中的公式显示为原文**：旧案例导入时，LaTeX 公式被转成了代码块或行内代码，前端也没有接入公式渲染，所以“七、方法论”里的公式显示为 LaTeX 源码。
- **旧案例只有提案**：碳市场和 Case009 是只读导入，总览里六个阶段都显示“已完成”，但前五个阶段（方向以外的文献、候选、方案、数据与检验）没有实际内容，点进去基本是空的。演示时请直接看提案。
- **ESG 案例尚未恢复**：旧仓库中的 ESG 案例没有导入。
- **只支持单用户、本机使用**，没有账号体系和自动数据清理。
