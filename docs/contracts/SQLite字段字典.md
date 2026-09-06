# Group1 v2：SQLite 字段字典与存储边界

> 状态：MVP 设计稿，供 A/B/C/D 联调。  
> 目标规模：近五年约 4000 份论文、ESG 报告和政策材料。

## 1. 先说结论

4000 份材料不需要一开始就搭复杂的大数据平台，但也不能把所有东西塞进一个 Excel 或一个 SQLite 大表。

| 位置 | 放什么 | 不放什么 |
|---|---|---|
| 共享文件存储/对象存储 | 原 PDF、网页快照、B 的解析文件、C 的摘要与切片文件、D 的图谱快照、备份 | 不负责查询关系 |
| `catalog.sqlite` | 文件目录、ID、版本、路径、状态、hash、证据定位和处理记录 | 不存 PDF 二进制；不存向量 |
| 向量库 | 向量、`document_id/chunk_id` 和少量筛选字段 | 不作为唯一真相；原文不只存在这里 |
| D 的图谱文件/图数据库 | 节点、边、证据关联和图谱快照 | 不替代原文和 SQLite 主账本 |
| 飞书 | 规则文档、交接表、质检表、人工复核结果 | 不作为主数据库或向量库 |

原 PDF 应在许可允许的前提下保存。摘要向量用于快速找“哪篇可能相关”，原文切片向量用于找“哪句话能作证据”；二者都要保留。

## 2. SQLite 的使用规则

- SQLite 只允许一个导入程序写入；组员通过交接文件或只读查询使用。
- 不把同一个 `.sqlite` 文件放在飞书云盘中让多人同时修改。
- 每天备份数据库；批次发布前再生成一份只读快照。
- 若以后出现多人并发写入或常驻服务，再迁移 PostgreSQL；字段和 ID 规则保持不变。
- SQLite 中所有文件路径使用相对路径，根目录从 `config/paths.yaml` 读取。

## 3. MVP 数据表

### 3.1 `documents`：一份逻辑文档一行

| 字段 | 必填 | 说明 |
|---|---|---|
| `document_id` | 是 | 全局主键，见《ID 与版本规则》 |
| `document_type` | 是 | `paper/policy/esg_report/annual_report/announcement/prospectus/research_report/news/table` |
| `title` | 是 | 清洗后的标题 |
| `publication_date` | 否 | `YYYY-MM-DD` |
| `publication_year` | 否 | 四位年份 |
| `authors_or_issuer` | 否 | 作者或发布机构，JSON 数组 |
| `language` | 是 | 如 `zh/en` |
| `doi_or_official_no` | 否 | DOI、政策文号等 |
| `collection_status` | 是 | A 的采集状态：`discovered/downloaded/metadata_only/skipped/error` |
| `collection_note` | 否 | A 的采集范围、失败或跳过说明；不代替 C 的内容筛选 |
| `fulltext_status` | 是 | `fulltext/metadata_only/restricted/missing` |
| `current_version` | 否 | 当前可用文件版本 |
| `canonical_document_id` | 否 | 若为重复记录，指向保留的文档 |
| `created_at` / `updated_at` | 是 | 建立和更新时间 |

D 入图时使用以下固定映射：

| `documents.document_type` | 图谱节点类型 |
|---|---|
| `paper` | `paper` |
| `policy` | `policy_document` |
| `esg_report/annual_report/research_report` | `report` |
| `announcement/prospectus/news/table` | 不直接入图；必须先由 D 明确映射到 v0.2 合法类型或排除 |

### 3.2 `source_records`：每个来源入口一行

| 字段 | 必填 | 说明 |
|---|---|---|
| `source_record_id` | 是 | 来源记录主键 |
| `document_id` | 否 | 去重确认后关联文档 |
| `source_name` | 是 | OpenAlex、知网、巨潮、政府网站等 |
| `external_id` | 否 | 来源自己的 ID |
| `source_url` | 否 | 在线来源入口；手工文件可为空 |
| `object_path` | 否 | 手工上传或已保存原件的相对路径；与 `source_url` 至少有一个 |
| `url_sha256` | 否 | 规范化 URL 指纹 |
| `first_seen_at` / `last_seen_at` | 是 | 首次和最近发现时间 |
| `acquisition_method` | 是 | `api/html/browser/file_drop/database_export/manual_upload` |
| `access_level` | 是 | `open/restricted/commercial/unknown` |
| `license_status` | 是 | 是否允许保存、挖掘和共享 |
| `crawl_status` | 是 | `new/downloaded/failed/blocked/skipped` |
| `error_message` | 否 | 失败原因 |

### 3.3 `document_versions`：每个实际文件版本一行

| 字段 | 必填 | 说明 |
|---|---|---|
| `document_id` | 是 | 所属逻辑文档；与 `document_version` 组成主键 |
| `document_version` | 是 | `v001` 起递增 |
| `file_sha256` | 否 | 文件去重与完整性校验 |
| `object_path` | 否 | 共享存储中的相对路径 |
| `media_type` | 是 | `application/pdf/text/html/...` |
| `file_size_bytes` | 否 | 文件大小 |
| `page_count` | 否 | PDF 页数 |
| `downloaded_at` | 否 | 下载时间 |
| `parse_status` | 是 | `pending/success/partial/failed` |
| `ocr_status` | 是 | `not_needed/pending/success/failed` |
| `supersedes_version` | 否 | 被此版本替代的旧版本 |

### 3.4 `parsed_blocks`：B 的解析块登记

| 字段 | 必填 | 说明 |
|---|---|---|
| `block_id` | 是 | 稳定文本块 ID |
| `document_id` / `document_version` | 是 | 所属文档和文件版本 |
| `block_no` | 是 | 文档内顺序 |
| `block_type` | 是 | 标题、正文、表格、图注、参考文献等 |
| `section_title` | 否 | 章节名 |
| `pdf_page_start` / `pdf_page_end` | 否 | PDF 物理页 |
| `char_start` / `char_end` | 否 | 解析文本中的字符范围 |
| `text_path` | 是 | B 产物中的相对路径/对象定位 |
| `text_sha256` | 是 | 文本校验指纹 |
| `qc_status` | 是 | `pass/warn/fail` |
| `parse_run_id` | 是 | 哪次解析产生 |

### 3.5 `document_profiles`：C 的高层文档卡片

| 字段 | 必填 | 说明 |
|---|---|---|
| `profile_id` | 是 | Profile 主键 |
| `document_id` / `document_version` | 是 | 对应文档和版本 |
| `profile_schema_version` | 是 | 摘要/结构化信息版本 |
| `profile_path` | 是 | `PaperProfile` 等 JSON 路径 |
| `summary_text` | 否 | 供人工浏览的短摘要 |
| `include_status` | 是 | C 的文档级过滤结论 |
| `review_status` | 是 | `not_reviewed/sampled/approved/rejected` |
| `created_at` | 是 | 生成时间 |

### 3.6 `chunks`：C 的原文切片登记

| 字段 | 必填 | 说明 |
|---|---|---|
| `chunk_id` | 是 | 切片主键 |
| `document_id` / `document_version` | 是 | 对应文档和版本 |
| `block_id` | 是 | 来自哪个 B 文本块 |
| `chunk_no` | 是 | 文档内顺序 |
| `chunk_schema_version` | 是 | 切片规则版本，如 `cs01` |
| `chunk_label` | 是 | `evidence/background/boilerplate/references/bad_ocr/uncertain` |
| `pdf_page_start` / `pdf_page_end` | 否 | PDF 物理页 |
| `section_title` | 否 | 章节 |
| `char_start` / `char_end` | 否 | 在 block 中的位置 |
| `text_path` | 是 | `chunks.jsonl` 中的对象定位或相对路径 |
| `text_sha256` | 是 | 切片文本指纹 |
| `qc_status` | 是 | `pass/warn/fail` |

### 3.7 `evidence`：统一证据登记

| 字段 | 必填 | 说明 |
|---|---|---|
| `evidence_id` | 是 | 证据主键 |
| `document_id` / `document_version` | 是 | 对应文档和版本 |
| `profile_id` | 否 | 对应 C 的 Profile |
| `block_id` / `chunk_id` | 条件必填 | 文本切片证据必填；元数据、表格、派生统计等可为空 |
| `source_type` | 是 | 与图谱 v0.2 一致：`paper_fulltext/paper_abstract/policy_text/report_text/...` |
| `evidence_type` | 是 | `direct_quote/metadata_record/table_cell/derived_statistic/human_annotation/design_decision` |
| `evidence_level` | 是 | `primary_source/metadata/derived/design` |
| `content` | 是 | 文本、数值或 JSON；直接引文即原句 |
| `content_hash` | 是 | `content` 的校验指纹 |
| `source_ref` | 否 | URL、文件对象、图谱快照或项目规范定位 |
| `published_at` | 否 | 原材料发布时间 |
| `retrieved_at` | 是 | 证据取得时间 |
| `verification_status` | 是 | `unverified/source_located/cross_checked/rejected` |
| `access_level` / `license` | 否 | 访问和许可状态 |
| `locator_json` | 是 | v0.2 `locator` 对象：`page/section/start_char/end_char/table_id/row/column` |
| `reviewer` / `reviewed_at` | 否 | D 的核验记录 |

条件必填规则：

| `evidence_type` | 必须定位 |
|---|---|
| `direct_quote`（PDF） | `chunk_id`、`locator.page`，并尽量给 section 和字符范围 |
| `direct_quote`（HTML） | `source_ref`，以及锚点/section/字符范围中的可用组合 |
| `table_cell` | `locator.table_id + row + column` |
| `metadata_record` | `source_ref` 和元数据内容；不强填 chunk/page |
| `derived_statistic` | 来源快照/输入对象及可复现运行信息；不伪造引文 |
| `human_annotation/design_decision` | 人工记录或项目规范定位 |

转换到 `research_graph.schema.json` v0.2 时：

| SQLite | 图谱 Evidence |
|---|---|
| `evidence_id` | `id` |
| `document_id` | `source_document_id` |
| `document_version` | `document_version` |
| `content` | `content` |
| `content_hash` | `content_hash` |
| `locator_json` | `locator` |

C 新产出的证据默认只能是 `unverified`；D 完成定位或交叉核验后，才更新为 `source_located/cross_checked/rejected`。

### 3.8 `embedding_registry`：向量索引登记，不存向量本身

| 字段 | 必填 | 说明 |
|---|---|---|
| `record_id` | 是 | `profile_id` 或 `chunk_id` |
| `record_level` | 是 | `document_summary/evidence_chunk` |
| `embedding_model` | 是 | 模型名称和版本 |
| `collection_name` | 是 | 向量集合名称 |
| `index_snapshot_id` | 是 | 索引快照 |
| `embedded_at` | 是 | 建立时间 |
| `status` | 是 | `ready/stale/failed` |

建议固定两个集合：

- `document_summary_v1`：每份文档一个摘要向量，负责粗筛。
- `evidence_chunk_v1`：每个有效切片一个向量，负责原文证据检索。

### 3.9 D 的图谱登记与人工审查表

| 表 | 核心字段 |
|---|---|
| `graph_snapshots` | `graph_id, snapshot_id, as_of, domain, schema_version, scope_json, build_json, artifact_path, artifact_sha256` |
| `graph_nodes` | `snapshot_id, node_id, node_type, label, payload_json` |
| `graph_edges` | `snapshot_id, edge_id, source_node_id, relation_type, target_node_id, payload_json` |
| `node_evidence` | `snapshot_id, node_id, evidence_id` |
| `edge_evidence` | `snapshot_id, edge_id, evidence_id` |

Schema-valid 的 `research_graph.json` 是 D 的正式主产物；SQLite 表和 CSV 只是便于查询、人工复核或导入其他图数据库的展开视图。`payload_json` 必须保存 v0.2 节点/边完整对象，保证能够无损还原 `origin、confidence、version、validity、evidence_ids、derivation、context、properties` 等全部必填字段。`canonical_key` 只能作为 `properties` 中的辅助字段，不能替代正式 ID 或 Schema 字段。

### 3.10 `pipeline_runs`：每次处理都留下版本

| 字段 | 必填 | 说明 |
|---|---|---|
| `run_id` | 是 | 运行主键 |
| `stage` | 是 | `collect/parse/index/extract/graph/retrieve/think` |
| `batch_or_snapshot_id` | 是 | 对应批次或快照 |
| `schema_version` | 是 | 使用的 schema |
| `code_version` / `config_hash` | 是 | 代码和配置版本 |
| `input_manifest_hash` | 是 | 输入清单指纹 |
| `started_at` | 是 | 开始时间 |
| `completed_at` | 终态必填 | `running` 时为空，成功/部分成功/失败时必填 |
| `status` | 是 | `running/success/partial/failed` |
| `error_summary` | 否 | 错误摘要 |

## 4. 为什么不采用单表 `source_file`

单表适合最早期下载登记，但不足以支撑完整项目：

- 同一文档可能来自多个来源；
- 同一文档可能有多个版本；
- 一篇文档会产生多个 block、chunk 和 evidence；
- 一个节点或关系可能有多条证据；
- 索引、图谱和模型都会更新，必须保留快照与运行版本。

因此，参考文档中的 `source_file` 可作为 A 的临时导入表，正式主账本应按上面的对象拆表。

## 5. 谁写哪些数据

| 数据 | 内容主责 | 建议写入方式 |
|---|---|---|
| `documents/source_records/document_versions` | A | A 交批次 manifest，由统一导入程序写 |
| `parsed_blocks` | B | B 交解析 manifest，由统一导入程序写 |
| `document_profiles/chunks/evidence/embedding_registry` | C | C 交 H3 发布包，由统一导入程序写 |
| 图节点、边和证据关联 | D | D 写独立图谱快照；发布时登记到主账本 |
| Gap/Hypothesis | E | E 写 `think/` 产物；通过 D 审核后登记 |

B 作为 Tech Lead 维护 schema 和导入程序；任何人都不直接用数据库编辑器手工改生产库。
