# Qwen-VL 科研图表理解小实验：回归表结构化抽取

> 实验编号：QVL-TABLE-001  
> 目标：验证 Qwen-VL 对真实科研论文回归表的数字、符号、显著性和空值抽取能力  
> 当前状态：实验已完成；`qwen3-vl-plus` 正式批次 6/6 调用成功，裁剪条件严格全表匹配率 100%，整页干扰条件为 0%，全部结果已绑定百炼 request ID 与本地哈希

## 1. 为什么选择这个实验

AI Scientist 不应只会概括论文正文。科研证据中最容易发生“看起来合理、实际抄错”的位置，是回归表中的负号、小数点、括号内标准误、显著性星号、跨列空值和固定效应。本实验把这些高风险字段同时放入一张真实论文表格，并加入“整页干扰表”条件，测试模型能否遵守目标表边界。

实验来源为 Muganyi、Yan 与 Sun 的[开放获取论文](https://pmc.ncbi.nlm.nih.gov/articles/PMC9487990/) *Green finance, fintech and environmental protection: Evidence from China*（[DOI：10.1016/j.ese.2021.100107](https://doi.org/10.1016/j.ese.2021.100107)，PMCID：PMC9487990）。目标为第 5 表 “Impact of fintech on industrial gas emissions.”，表中包含两个模型、回归系数、聚类标准误、显著性星号、固定效应、样本量、F 统计量和 \(R^2\)。

![Table 5 真实实验输入](<WORKSPACE>/output/experiments/qwen_vl_scientific_table/table5_crop-5.png)

## 2. 实验问题与假设

- **RQ1**：Qwen-VL 能否把表格完整转换成预定义 JSON，而不丢失负号、标准误或显著性？
- **RQ2**：当目标表与另一张表同时出现在整页图像中时，模型能否忽略干扰内容？
- **RQ3**：裁剪目标表是否显著提高严格全表匹配率？

预期裁剪条件在字段准确率和严格匹配率上不低于整页条件；如果整页条件明显下降，则系统的工程策略应改为“版面检测/表格裁剪 → Qwen-VL 抽取 → 数字规则复核”。

## 3. 输入、真值与任务边界

### 3.1 两个输入条件

| 条件 | 文件 | 含义 |
|---|---|---|
| Full-page | `source_page-5.png` | 原论文第 5 页，同时包含 Table 4、Table 5 和正文，用于测试目标边界与抗干扰能力 |
| Crop | `table5_crop-5.png` | 仅保留 Table 5，用于测试清晰目标下的抽取上限 |

两张图均由同一来源 PDF 第 5 页以 200 DPI 渲染；原文 PDF、页面图、裁剪图和真值 JSON 均保存 SHA-256，见 `experiment_manifest.json`。

### 3.2 人工金标准

金标准由开放全文 HTML 表格与渲染图双重核对，主要数值如下：

| 字段 | Model (1) | Model (2) |
|---|---:|---:|
| Fintech\(_{it-1}\) | −0.166***（0.060） | −0.153***（0.049） |
| DSD\(_{it}\) | 空值 | 0.471***（0.052） |
| GDPpc\(_{it-1}\) | −1.172***（0.179） | −0.832***（0.146） |
| TOP\(_{it-1}\) | 0.011（0.021） | 0.014***（0.018） |
| Ind\(_{it-1}\) | 1.491***（0.237） | 0.999***（0.180） |
| City FE / Year FE | Yes / Yes | Yes / Yes |
| Observations | 1,797 | 1,787 |
| F-statistic | 116.54*** | 133.16*** |
| \(R^2\) | 0.3774 | 0.5522 |

完整真值为 `ground_truth.json`，共 **47 个原子字段**。空白 DSD 单元格必须输出 `null`，不得填 0；无显著性的 TOP(1) 必须输出空字符串，不能补星号。

## 4. 模型与上下文工程

- 模型：`qwen3-vl-plus`；
- 接口：[阿里云百炼 Qwen-VL OpenAI-compatible Chat Completions](https://help.aliyun.com/zh/model-studio/qwen-vl-compatible-with-openai)；
- 图像：PNG 以 Base64 `data:image/png` 传入；
- 解码：`temperature=0.0`；
- 重复：每种输入条件独立运行 3 次，共 6 次；
- 输出：严格 JSON，不允许 Markdown 围栏或解释文字。

Prompt 采用“角色—目标表边界—五条抽取规则—固定 JSON Schema”四段式设计。它要求模型：只读取标题完全匹配的 Table 5；分别保留系数、标准误和星号；数字为 JSON number；固定效应为 boolean；表中空白为 `null`。Prompt 的 SHA-256 与图像哈希随响应元数据一同保存，使每次百炼调用记录可以与本地结果一一对应。

## 5. 评测指标

| 指标 | 定义 | 重点捕捉的错误 |
|---|---|---|
| Field Accuracy | 正确真值字段数 / 47 | 漏字段、抄错值 |
| Field Precision | 正确字段数 / 模型输出原子字段数 | 自行增加或展开不存在的字段 |
| Numeric Accuracy | 容差 0.0005 内正确数字占比 | 小数点、负号、转写错误 |
| Significance Accuracy | 显著性字符串完全一致比例 | 漏星、多星、无星变有星 |
| Null Handling Accuracy | 真值为空的字段正确保持 `null` 的比例 | 把空白臆测成 0 或其他值 |
| Strict Exact Match | 47 字段全对且无额外字段 | 是否可直接进入证据对象，无需人工修补 |

正式报告分别给出两个条件的均值、逐次分数和严格匹配率，不把多次调用平均后掩盖单次失败。

## 6. 已执行的评测管线自检

为验证评测器确实能发现科研表格常见错误，已执行两组软件自检：

| 自检输入 | Field Acc. | Precision | Numeric Acc. | Significance Acc. | Null Acc. | Strict Match |
|---|---:|---:|---:|---:|---:|---:|
| 与人工真值完全一致 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 是 |
| 人为注入 4 类错误 | 0.9149 | 0.8776 | 0.9259 | 0.9091 | 0.0000 | 否 |

注入错误包括：负号反转、凭空填写空白单元格、错误增加显著性星号和 \(R^2\) 数字转写。评测器正确识别 1 个缺失路径和 3 个额外路径。**上述 100% 是评测程序自检结果，不是 Qwen-VL 模型得分。**

## 7. Qwen-VL 真实调用结果

2026-09-01，经项目方授权使用既有百炼密钥，先完成 1 次裁剪图冒烟测试（47/47 字段全对），再执行预注册的正式批次：整页与裁剪两条件各 3 次，共 6 次，全部成功。冒烟测试仅用于确认链路，不计入下表正式统计。此前两个失效 Key 的 401 记录仍保留在 `qwen_call_status.json` 作为审计轨迹，但不进入模型成绩。

| 条件 | 成功调用 | Field Acc. | Numeric Acc. | Significance Acc. | Null Acc. | Strict Match Rate |
|---|---:|---:|---:|---:|---:|---:|
| Full-page | 3/3 | 0.9787 | 1.0000 | 0.9091 | 1.0000 | 0.0000 |
| Crop | 3/3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| Overall | 6/6 | 0.9893 | 1.0000 | 0.9546 | 1.0000 | 0.5000 |

整页条件的 3 次调用出现同一个稳定错误：Model (2) 的 `TOP_it-1` 显著性应为 `***`，模型均识别为 `**`。除此之外，整页条件的数值、正负号、标准误、样本量、F 统计量、\(R^2\)、固定效应与空值均正确。裁剪条件 3 次均为 47/47 字段严格全对。这说明系统应把“版面检测/目标表裁剪”设为科研图表处理的必要前置步骤，而不是把整页图像直接交给模型。

正式批次累计输入 12,444 tokens、输出 3,291 tokens、总计 15,735 tokens，六次模型调用耗时合计 82.215 秒。单次裁剪图输入 1,067 tokens，整页图为 3,081 tokens，裁剪使输入 token 下降约 **65.4%**，同时把严格匹配率从 0% 提升到 100%。

百炼平台的调用记录可作为服务端证据；本地 `response_*.json` 中的 6 个正式 request ID、模型名、token usage、耗时、图像哈希与 Prompt 哈希把平台记录绑定到具体实验输入。正式聚合结果见 `qwen_runs/batch_summary.json`，其 SHA-256 为 `33c4f6a49ef11ed8309ba99aead6ac09d77d106aa5095e9ae160951ffca0cf7d`。

## 8. 一键复跑

如需复跑，在项目根目录设置已获授权的有效密钥后运行：

```powershell
$env:DASHSCOPE_API_KEY = '<active-key>'
python scripts\experiments\run_qwen_vl_table_batch.py `
  --full-page output\experiments\qwen_vl_scientific_table\source_page-5.png `
  --crop output\experiments\qwen_vl_scientific_table\table5_crop-5.png `
  --ground-truth output\experiments\qwen_vl_scientific_table\ground_truth.json `
  --out-dir output\experiments\qwen_vl_scientific_table\qwen_runs `
  --repeats 3 `
  --model qwen3-vl-plus
```

批处理脚本会为每次调用保存原始响应、结构化抽取、逐字段评测和 request ID，并自动输出两个条件及总体的平均指标与严格匹配率。密钥只从环境变量读取，不进入任何结果文件。

## 9. 参赛文档中的推荐表达

技术方案中建议只保留一张图、一张小表和一句结论：

> 在真实开放论文的 47 字段回归表抽取中，Qwen3-VL-Plus 完成 6/6 次真实调用：目标表裁剪条件 3 次均实现 47/47 字段严格全对，整页含干扰表条件的数值准确率仍为 100%，但 3 次均将一个三星显著性识别为两星，严格匹配率为 0%。裁剪使输入 token 减少约 65.4%，并将严格匹配率从 0% 提升至 100%。平台记录、本地 request ID、图像/Prompt 哈希与逐字段误差可一一回查。

由此形成可复现的工程发现：**科研多模态能力的关键不只是换更大模型，而是先用版面理解缩小证据边界，再让 Qwen-VL 做受约束抽取和数值审计。**

## 10. 文件清单

| 文件 | 用途 |
|---|---|
| `source_article.pdf` | 开放获取原论文 |
| `source_page-5.png` | 整页干扰条件 |
| `table5_crop-5.png` | 目标表裁剪条件 |
| `ground_truth.json` | 47 字段人工金标准 |
| `experiment_manifest.json` | 来源、哈希、协议与状态 |
| `qwen_call_status.json` | 不含密钥的历史失败与本次成功调用审计 |
| `qwen_runs/batch_summary.json` | 6 次正式调用的条件级与总体量化结果 |
| `run_qwen_vl_table_experiment.py` | 单次调用与原始响应保存 |
| `run_qwen_vl_table_batch.py` | 两条件 × 三次批量运行与聚合 |
| `evaluate_qwen_vl_table_experiment.py` | 逐字段严格评测 |
| `selfcheck_reference.json` / `selfcheck_mutated.json` | 评测器正反自检证据 |
