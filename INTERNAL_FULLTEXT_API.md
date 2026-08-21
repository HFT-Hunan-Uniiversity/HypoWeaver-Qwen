# 绿色金融数据：同学直接抓取指南

这份文档可以直接发给参与内部研究、数据清洗和正文实验的同学。公开元数据从
Vercel 获取；正文从腾讯云的认证接口下载。协作方不需要连接 PostgreSQL，也不需要
登录服务器或取得 COS 权限。

## 已验证状态

截至 2026-08-08 的生产验收结果：

- 正文接口包含 551 篇独立文章、564 份正文资产；同一文章可能有多份资产；
- 其中 520 份为仅供内部研究的 `research_cache`，44 份具备复用条件；
- 完整下载验收为 `records=564`、`written=495`、`unchanged=69`；此前已经下载的
  69 份也重新通过 SHA-256 校验，因此总计 564 份全部可用；
- 对同一目录完整重跑后的结果为 `records=564`、`written=0`、
  `unchanged=564`，证明断点续传和重复拉取有效；
- 自动化测试为 103 项全部通过。

这里的结论是“正文文件已经实际抓取并能够交付”，不是只获得 DOI、网页链接或
`identifier_only` 记录。564 是正文资产数，551 是去重后的文章数。

## 先选择抓取路径

| 目标 | 是否需要 Token | 是否需要克隆项目 | 当前数量 | 输出 |
|---|---|---|---:|---|
| 路径 A：标题、摘要等公开元数据 | 否 | 否 | 全部公开 1,847 篇；绿色候选 1,059 篇 | JSON |
| 路径 B：内部研究正文 | 是 | 是 | 551 篇文章、564 份资产 | NDJSON + TXT/XML |

只需要标题和摘要时执行路径 A；需要把正文文件下载到本机时执行路径 B。路径 B 的
`articles.ndjson` 也包含对应文章的元数据，不需要再重复抓取路径 A。

## 路径 A：抓取标题、摘要等公开元数据

路径 A 不需要 Token、Node.js、Git、服务器账号或 COS 权限，浏览器、HTTP 客户端和
能够访问网页的 AI 都可以执行。

### A1. 读取清单

先访问：

```text
https://green-finance-dashboard.vercel.app/api/feed
```

记录返回的 `snapshot_at` 和 `dataset_version`。当前清单会同时给出 `all` 和 `green`
数量，但数量会随每日任务更新，应以本次接口返回值为准。

### A2. 选择范围并读取第一页

抓取全部公开元数据：

```text
https://green-finance-dashboard.vercel.app/api/feed/articles?scope=all&limit=500
```

只抓取最新结论为 `include` 或 `review` 的绿色金融候选：

```text
https://green-finance-dashboard.vercel.app/api/feed/articles?scope=green&limit=500
```

每条记录包含 `article_id`、标题、摘要、作者、关键词、期刊、日期、官网链接、
DOI/arXiv ID、来源系统、绿色金融筛选结论和标签。没有正文的文章仍然会保留这些
元数据；当前 508 篇正文缺口都包含在绿色候选元数据中。

### A3. 读取全部分页

保存当前响应中的 `records`。如果响应的 `next` 不是 `null`，直接访问 `next` 给出的
网址并继续保存 `records`；重复操作，直到 `next=null`。不要自行修改 `next` 中的
游标。下游始终按 `article_id` 去重或 upsert。

当前全部公开元数据约需 4 页，绿色候选约需 3 页。不能只读取第一页就报告抓取完成。

### A4. 完成一致性检查

分页结束后再次访问 `/api/feed`。只有前后两次 `dataset_version` 相同，才接受本次
结果；如果版本变化，说明抓取过程中生产数据发生了更新，应重新从第一页开始。

## 路径 B：下载内部研究正文

### B1. 准备项目

电脑需要安装 Git 和 Node.js 24。首次使用时执行：

```bash
git clone https://github.com/yuzhou4t/green-finance-data-center.git
cd green-finance-data-center
npm install
```

如果已经克隆过项目，只需进入目录后执行 `git pull`。

### B2. 私下取得正文 Token

管理员通过团队内部的安全渠道单独提供原始 Token。Token 只能保存在同学电脑的
环境变量或权限受限的本地凭据文件中，不能写入 Git、网址、公开文档、聊天记录或
AI 提示词。

在当前终端配置环境变量：

```bash
export GREEN_FINANCE_RESEARCH_TOKEN='<单独收到的Token>'
```

### B3. 一条命令下载全部正文

在项目根目录执行：

```bash
npm run fulltext:download -- \
  --base-url https://106.53.153.215 \
  --output-dir ./green-finance-research-input
```

服务器有限流，完整核验通常需要几分钟。下载器会自动处理短暂的 429/503，并在
写入前校验每份正文的 SHA-256。正常完成时会输出类似：

```json
{
  "records": 564,
  "written": 564,
  "unchanged": 0,
  "output_dir": ".../green-finance-research-input"
}
```

同一目录再次运行时，已通过哈希校验的文件不会重复写入。当前完整复跑的已验证结果
为 `written=0`、`unchanged=564`。

### B4. 交给清洗程序的文件

```text
green-finance-research-input/
├── manifest.json       # 接口版本、资产数量和同步时间
├── articles.ndjson     # 文章元数据、筛选结果、资产ID、哈希和文件名映射
└── fulltexts/          # TXT/XML 正文文件
```

正文实验应以 `articles.ndjson` 中的 `article_id` 关联元数据，不要用文件名或相似标题
自行合并文章。

## 让 AI 代为抓取

### 路径 A 的 AI 提示词

只抓标题和摘要时，可以直接把下面这段话交给能够访问网页的 AI：

```text
请抓取绿色金融数据中心的公开元数据。先读取
https://green-finance-dashboard.vercel.app/api/feed
并记录 snapshot_at 和 dataset_version。然后读取
https://green-finance-dashboard.vercel.app/api/feed/articles?scope=green&limit=500
保存 records，并持续访问响应中的 next，直到 next=null。按 article_id 去重。
最后重新读取 /api/feed，只有前后 dataset_version 相同才接受结果。
请保存标题、摘要、作者、关键词、期刊、日期、official_url、identifiers、
source_systems、final_decision 和 tags。不要尝试从公开接口获取正文。
```

把其中的 `scope=green` 改为 `scope=all`，即可抓取全部公开元数据。

### 路径 B 的 AI 提示词

如果需要正文，先由本人在终端设置 `GREEN_FINANCE_RESEARCH_TOKEN`，再把下面这段话
交给能够操作本机终端的 AI。不要把 Token 值写进提示词。

```text
请进入 green-finance-data-center 项目，不要读取、打印或回传
GREEN_FINANCE_RESEARCH_TOKEN 的值。运行 npm install，然后执行：
npm run fulltext:download -- --base-url https://106.53.153.215
--output-dir ./green-finance-research-input
完成后只报告 records、written、unchanged，并检查 manifest.json、
articles.ndjson 和 fulltexts/ 是否存在。不要上传或公开其中的正文。
```

仅把公开网站发给 AI，AI 可以抓取元数据，但不能自动获得受限正文；正文接口必须
同时具备内部 Token，这是公开信息与内部研究材料之间的访问边界。

## 接口契约

```text
GET /internal/fulltexts
GET /internal/fulltexts/articles?limit=100
GET /internal/fulltexts/assets/<asset_id>
Authorization: Bearer <token>
```

首次请求返回接口版本、数量和更新时间。资产清单通过 `next` 分页；每条记录的
`content_url` 下载一份经过 SHA-256 校验的 TXT 或 XML 正文。推荐统一使用项目中的
下载命令，不要自行拼接分页和文件名。

## 常见问题

- `401 unauthorized`：没有设置 Token、Token 输入错误或已经被撤销；联系管理员，
  不要在群聊中粘贴 Token 排查。
- `429` 或 `503`：下载器会有限次数自动重试；不要用高并发绕过服务器限流。
- `fetch failed`：先检查本机网络能否访问 `https://106.53.153.215`，然后原命令重跑。
- `SHA-256 mismatch`：文件未通过完整性验证，下载器会停止；保留错误信息并联系
  管理员，不要把该文件送入清洗流程。
- 中途退出：再次运行同一命令和同一 `--output-dir`，已验证文件会被跳过。

## 数据使用边界

- `research_cache` 仅供获准的内部研究成员进行实验、统计分析和数据清洗；
- 不得上传 COS、公开快照、公共网盘、公开 Git 仓库或转交团队外部人员；
- 接口使用 HTTPS、Bearer Token、GET-only、限流和逐次访问审计；
- Vercel 公开站点及 `/api/feed` 始终只提供元数据，不提供正文、本机路径或资产 URI；
- Token 撤销后，已经下载的文件仍然属于内部研究材料，不会转为公开数据。

元数据的稳定分页、增量水位和下游 upsert 协议见
[`METADATA_FEED.md`](METADATA_FEED.md)。
