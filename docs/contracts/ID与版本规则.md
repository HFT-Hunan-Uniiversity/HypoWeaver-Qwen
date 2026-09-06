# Group1 v2：ID 与版本规则

> 状态：阶段 0 待全员用首轮固定的 3 篇论文小样确认。  
> 适用范围：A 采集、B 解析、C 切片/索引、D 图谱/检索、E 空白/假设全链路。

## 1. 先统一一句话

团队口头所说的 `doc_id`，在 A/B/C 的代码、SQLite 和交接文件中统一写成 **`document_id`**。两者指同一件事，但上游机器文件中只允许使用 `document_id`，避免同一个字段出现两个名字。

`document_id` 是一份材料终身不变的“身份证”。标题、分类、年份、文件路径以后可以改，`document_id` 不改、不回收、不重复使用。

D 写入 `research_graph.schema.json` v0.2 时必须做一次明确映射：

| 上游字段 | 图谱 v0.2 字段 |
|---|---|
| `document_id` | Evidence 的 `source_document_id` |
| `document_version` | `document_version` |
| `evidence_id` | Evidence 对象的 `id`，并被 node/edge 的 `evidence_ids` 引用 |
| `quote_text` | `content` |
| `quote_sha256` | `content_hash` |
| 页码、章节、字符位置、表格位置 | `locator` 对象 |

## 2. 各类 ID 的固定格式

| ID | 用途 | 固定格式 | 示例 |
|---|---|---|---|
| `source_record_id` | 一次来源发现记录；同一论文来自两个网站时有两条 | `src-<26位小写ULID>` | `src-01k0abc...` |
| `document_id` | 去重后的一份逻辑文档 | `doc-<26位小写ULID>` | `doc-01k0def...` |
| `document_version` | 同一文档的某个内容版本；与 `document_id` 组成唯一键 | `vNNN` | `v001` |
| `block_id` | B 解析后的稳定文本块 | `<document_id>-<document_version>-blk-NNNNNN` | `doc-...-v001-blk-000031` |
| `chunk_id` | C 按某版切片规则产生的切片 | `<document_id>-<document_version>-csNN-chk-NNNNNN` | `doc-...-v001-cs01-chk-000012` |
| `evidence_id` | 一条可引用原文证据 | `evd:<定位信息SHA256前20位>` | `evd:a81f9c...` |
| `profile_id` | C 的高层文档卡片版本 | `profile-<document_id>-pNN` | `profile-doc-...-p01` |
| 图节点 `id` | D 的图节点 | `<v0.2小写节点类型>:<稳定键或指纹>` | `paper:doc-01k0def...` |
| 图边 `id` | D 的图关系 | `edge:<关系指纹>` | `edge:4fd19c...` |
| `batch_id` | A/B 的处理批次 | `batch-YYYYMMDD-NNN` | `batch-20260723-001` |
| `snapshot_id` | C 索引或 D 图谱快照 | `<对象>-YYYYMMDD-NNN` | `graph-20260723-001` |
| `run_id` | 一次检索/推理运行 | `run-YYYYMMDD-HHMMSS-<短码>` | `run-20260723-143000-a1b2` |

说明：

- ULID 由程序生成，按时间可排序；统一转为小写，文件名也能安全使用。
- `evidence_id` 不把标题、页码直接拼进 ID。定位信息放在字段中，ID 只做稳定引用。
- 切片规则改变时，`csNN` 必须升级；旧 `chunk_id` 不覆盖。
- 图谱 `id` 必须匹配 v0.2 的小写字符规则。中文、DOI、URL 或带 `/` 的名称不能直接放进 ID；先生成规范键，再取 SHA-256 指纹。`label` 和别名仍保留可读原文。

## 3. `document_id` 什么时候新建，什么时候复用

| 情况 | 处理方式 |
|---|---|
| 同一论文从 OpenAlex 和期刊官网各找到一次 | 复用一个 `document_id`，新增两条 `source_record_id` |
| 同一 PDF 被重复下载 | 复用原 `document_id` 和版本，记录重复来源，不再保存第二份相同文件 |
| 同一政策网页内容更新，或论文出现修订版 | `document_id` 不变，新增 `document_version` |
| 同一企业不同年份的 ESG 报告 | 分配不同 `document_id` |
| 后来发现两个 `document_id` 实为重复 | 不删除旧 ID；在重复映射表中把旧 ID 指向 `canonical_document_id` |
| 只有摘要，没有合法可下载全文 | 仍可建 `document_id`，但标记 `fulltext_status=metadata_only`，不得冒充全文证据 |

## 4. A 的去重顺序

A 在分配新 `document_id` 前，按以下顺序检查：

1. 外部稳定标识：DOI、OpenAlex ID、政策文号、公告 ID。
2. 规范化 URL。
3. 已下载文件的 SHA-256。
4. Unicode 规范化后的标题 + 年份 + 作者/发布机构。
5. 正文指纹或人工复核。

命中“确定重复”就复用已有 `document_id`；只命中“疑似重复”则进入人工复核，不自动合并。

## 5. 全链路溯源必须闭合

最短链路为：

```text
document_id
  → document_version
  → block_id
  → chunk_id
  → evidence_id
  → node/edge.evidence_ids
  → GapCard/HypothesisCard 的证据引用
```

每条文本证据至少保存：

| 字段 | 含义 |
|---|---|
| `document_id` | 哪一份材料 |
| `document_version` | 哪一个文件版本 |
| `block_id` | B 解析后的哪个文本块 |
| `chunk_id` | C 的哪个切片 |
| `source_type` | `paper_fulltext/policy_text/report_text/...` |
| `evidence_type` / `evidence_level` | 直接引文、元数据、表格单元格、派生统计等及其证据层级 |
| `quote_text` | 实际引用原文 |
| `quote_sha256` | 引文校验指纹 |
| `source_ref` | 原始 URL、文件对象或其他来源定位 |
| `retrieved_at` | 证据取得时间 |
| `locator` | 页码、章节、字符范围或表格/行/列组成的定位对象 |
| `verification_status` | `unverified/source_located/cross_checked/rejected` |

条件规则：

- PDF 直接引文必须有物理页码；HTML 证据必须有 URL/锚点或字符范围。
- 表格单元格证据使用 `table_id + row + column`，不强行填写 `chunk_id` 或字符范围。
- 元数据、派生统计、人工标注和设计决策按 v0.2 的 `evidence_type` 填相应来源，不伪造 PDF 页码。
- C 发布时只能把新证据标为 `unverified`；`source_located/cross_checked/rejected` 的最终状态由 D 的引用核验器写入。

## 6. 图谱节点如何避免重复

节点分为两类，不能用同一套合并规则。

| 节点类别 | 例子 | 合并规则 |
|---|---|---|
| 必须按文档隔离 | `Finding`、`Limitation`、论文中的具体主张 | 使用 `document_id + local_id`，不同论文不自动合并 |
| 可以跨文档归一 | 机构、政策工具、地区、主题、方法、数据集、变量、指标 | 使用受控词表或 `canonical_key`；保留原名、别名和待复核状态 |

第一版只做确定性较高的合并。同义词、中文/英文、缩写等不确定情况先用 `SAME_AS` 候选或人工复核，不直接覆盖节点。

## 7. 发布门槛

- 进入正式图谱的节点和边必须至少绑定一条非 `rejected` 的 `evidence_id`；Evidence 对象转换后必须通过 `research_graph.schema.json` v0.2。
- 摘要只能用于粗筛和搭骨架，不能单独充当事实证据。
- 计算或推断产生的节点/边除证据外，还要记录输入快照、算法/提示词版本和来源节点/边。
- 任何 ID 规则变化都必须升级 schema 版本，并用同一批 2–3 篇样例回归测试。

## 8. 责任人

| 事项 | 主责 | 必须共同确认 |
|---|---|---|
| `document_id` 分配、来源去重、文件版本 | A | B |
| `block_id` 与页码/字符定位 | B | C、D |
| `chunk_id`、`evidence_id` 与切片规则 | C | B、D |
| 图节点/边 ID、归一与证据绑定 | D | C、E |
| Gap/Hypothesis 对证据的引用 | E | D |
