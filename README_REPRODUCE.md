# 实验复现说明

所有命令在包根目录执行。`output/experiments/` 保存交付证据；统一入口将新复核结果写入 `reproduced/`，不覆盖冻结证据。先执行 `python tools/verify_package.py`。

## 1 无需模型调用的指标复核

以下命令仅使用 Python 标准库，不使用密钥、不发起网络请求：

```bash
python tools/reproduce.py metrics
python tools/reproduce.py qwen-vl
```

`metrics` 重新读取基础与完整系统、四个消融分支的逐单元状态及公开计划，按原词表重新计算主题忠实性，并核对六项门控指标和 Wilson 区间。共覆盖六组各30单元记录，不删除失败单元。

受限的检索原文已从 `generation_public.json` 中移除，保留来源 ID、原文哈希、结构化计划和调用回执。本命令不重新验证被移除原文的内容哈希或引用是否忠实于原文；完整原始评价器仍保留在 `scripts/experiments/`，获得原始授权材料后可使用。历史 `evaluation.json` 是原实验记录，`reproduced/public_metrics.json` 是本次公开材料复核，两者不可混称。

`qwen-vl` 重新比较两种输入条件下共6份正式抽取结果与47字段金标准，输出每次得分。原始页面、表格图像、来源信息及真实调用回执同时保存在对应输出目录。

## 2 两类真实案例独立复算

安装统计依赖后执行：

```bash
python -m pip install -r requirements-reproduce.txt
python tools/reproduce.py case009
python tools/reproduce.py case010
python tools/reproduce.py readiness
```

- `case009`：从附带的 CC0 城市—月份工作簿独立构造固定效应回归，核对核心系数、处理前趋势与两轮反馈绑定。
- `case010`：从附带的 CC BY 4.0 原始 Stata 数据及分析抽取校验数据血缘，使用另一套 NumPy 实现复算模型、事件研究、机制及异质性结果和499次置换。复算包含文件哈希检查；请勿手工编辑冻结协议或结果。
- `readiness`：执行数据就绪门的正负对照，不调用模型，不生成科学结论。

当前统一入口是“对已冻结分析的独立复算”，不是把历史百炼调用当作实时重跑。核心两轮执行源码仍分别为 `run_track1b_case009_two_round.py` 和 `run_case010_carbon_market_adaptive.py`。碳市场第一轮的原始 Qwen 证据涉及受限知识资产，因此完整第一轮重跑需另行授权材料；包内已冻结第一轮及其绑定的第二轮可供统计复核。

系统解释以原诊断和 Claim Gate 状态为准；系数吻合不代表因果识别成立。不要为追求通过而改变阈值、样本、随机种子或结果文件。

## 3 在线系统实验

需要自己的百炼凭证、与协议匹配的模型、获授权的冻结知识快照及对应 BGE 版本。将本机目录通过 `HYPOWEAVER_EXPERIMENT_KNOWLEDGE_DIR` 指定；若未指定，运行器查找包根目录下的 `knowledge-data-authorized/`。默认公开样例不能替代原知识库。

```bash
python scripts/experiments/run_ai_scientist_system_capability_v2.py --protocol experiments/ai_scientist_system_capability_v3_protocol.json --output-dir reproduced/online_v3 --concurrency 3
python scripts/experiments/evaluate_ai_scientist_system_capability_v2.py --protocol experiments/ai_scientist_system_capability_v3_protocol.json --input-dir reproduced/online_v3 --json-output reproduced/online_v3/evaluation.json --report-output reproduced/online_v3/evaluation.md
```

运行器读取本地 `.env` 的百炼配置，不包含也不推断账号凭证。正式协议为10个问题、3个种子、温度0.2、检索前6条及每文献至多2条、最多一轮审查修订。三个种子为20260901、20260902、20260903。

交付版修正了旧运行器的文献登记表路径，因此在完整登记表生效时，检索结果可能与旧快照运行不同。旧运行的知识状态警告已保留；新运行必须报告自己的知识状态和结果，不宣称与历史实验逐位一致。

消融脚本为 `run_ai_scientist_component_ablation.py`；使用 `--output-root` 指向新的结果目录。云端运行会消耗调用额度，固定种子不保证逐字一致。

## 4 在线 Qwen-VL 重跑

```bash
python scripts/experiments/run_qwen_vl_table_batch.py --full-page output/experiments/qwen_vl_scientific_table/source_page-5.png --crop output/experiments/qwen_vl_scientific_table/table5_crop-5.png --ground-truth output/experiments/qwen_vl_scientific_table/ground_truth.json --out-dir reproduced/qwen_vl_online --model qwen3-vl-plus --repeats 3
```

需要在当前进程环境中设置 `DASHSCOPE_API_KEY`，该独立脚本不会自动加载 `.env`；如接口地址不同，使用其 `--endpoint` 参数指定完整 Chat Completions 地址。正式历史参数为温度0、每条件3次。

## 5 软件测试

```bash
python backend/run_tests.py
npm --prefix frontend test
npm --prefix frontend run build
```

后端测试入口会隔离测试子进程中的供应商配置，避免误用真实模型。实际交付验证版本、结果和限制见 `VALIDATION.md`。包中旧实验清单记录的是当时文件；分发文件以 `PACKAGE_MANIFEST.json` 为准，公开派生记录的处理见 `docs/PUBLIC_REDACTIONS.json`。
