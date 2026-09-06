# 数据、依赖与分发范围

| 材料 | 来源及授权记录 | 包内范围 |
|---|---|---|
| 空气质量城市月度数据 | Harvard Dataverse，doi:10.7910/DVN/LEOXAK，冻结协议记录 CC0-1.0 | 原工作簿、协议及结果 |
| 企业绿色创新面板 | Wei, D.，Industry Peer Effect of Corporate Green Innovation，Mendeley Data v1，doi:10.17632/rrfwny7byp.1，CC BY 4.0 | 原始 Stata 文件、分析抽取、转换清单与结果；字段重命名和变换在 manifest 中披露 |
| 碳信息披露候选数据 | PLOS ONE 补充材料，doi:10.1371/journal.pone.0319997.s001，项目来源审计记录 CC BY 4.0 | 原始补充数据及候选审计 |
| Qwen-VL 表格材料 | Muganyi, Yan & Sun，Green finance, fintech and environmental protection: Evidence from China，doi:10.1016/j.ese.2021.100107，PMCID PMC9487990 | 开放获取原文、单页图像、Table 5 裁剪、金标准；图像由该文制作 |
| 数据就绪夹具 | 项目生成，CC0 | 小型合成面板及说明；不作为实证结果 |
| 默认知识样例 | 本次交付编写的数据与方法说明 | 明确标记 metadata_only，不构成历史文献全文 |

源文件与许可证依据见冻结协议、数据抽取 manifest 和案例 source_audit；使用第三方资料时保留上述来源和作者信息。代码使用的 React、FastAPI、统计软件及其他依赖遵循各自上游许可证；依赖本体通过包管理器安装，不重复打包。

原全文知识库 manifest 的访问标签为 `authenticated_internal_research_only`，其中大部分为内部科研缓存。因此本包不分发该全文库、其完整向量文件、原始提示/响应或开发机运行数据库。历史实验的 `generation_public.json` 是另命名的公开派生件，移除检索原文并保留原文件哈希；它不能通过冒充原文件的方式满足原文完整性校验。系统性能在线重跑需要另外取得授权快照。

两类统计案例的协议和关键结果保留原始字节以维持哈希绑定，个别历史环境字段可能包含当时机器路径，仅作为溯源记录，不作为部署默认值。对其他文件所做的本机路径替换见 `docs/PUBLIC_REDACTIONS.json`。

本次打包未替项目作者选择开源许可证，也未新增对第三方资料的授权。源码交付用于本次评审与授权复现，后续公开开源的许可应由权利人明确。
