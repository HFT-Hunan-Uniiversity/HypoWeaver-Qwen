# 代码定位

| 功能 | 源码位置 |
|---|---|
| 工作流状态机与人工审核 | backend/src/hypoweaver/engine.py、definition.py |
| 研究规划、问题一致性及反馈修订 | backend/src/hypoweaver/discovery_planner.py |
| 角色提示与上下文模板 | backend/src/hypoweaver/prompts.py、blind_prompts.py |
| 百炼适配、回执与结构修复 | backend/src/hypoweaver/adapters.py、runtime_config.py |
| 类型化模型与约束 | backend/src/hypoweaver/models.py、knowledge_models.py |
| 检索、多文献来源配额与知识目录 | backend/src/hypoweaver/knowledge_service.py、legacy_rag.py |
| 发现结果编译与交接 | backend/src/hypoweaver/discovery_engine/、discovery_handoff.py |
| 统计执行及模型调度 | backend/src/hypoweaver/research_engine.py、policy_causal.py、test_dag.py |
| 独立复算与结论准入 | backend/src/hypoweaver/reproducer.py、claim_gate.py |
| 状态持久化与封存 | backend/src/hypoweaver/repository.py、seal.py |
| 三服务接口 | backend/src/hypoweaver/api.py、knowledge_api.py、research_api.py |
| 前端研究工作台 | frontend/src/components/、runtime/、product/ |
| 知识处理与数据契约 | src/、schemas/、scripts/research/ |
| 两类案例与系统实验 | scripts/experiments/、experiments/ |

没有另附编译后的 Python 字节码，也没有使用代码截图替代源文件。默认演示数据、确定性执行与在线模型调用均保留明确的模式和准入条件。旧版本辅助脚本和文档中的历史路径不代表当前运行位置；推荐从根目录 README 指定的入口运行。
