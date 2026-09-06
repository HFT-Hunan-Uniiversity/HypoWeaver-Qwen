# AI Scientist 系统能力实验 v3：剩余误差审计

日期：2026-09-01  
性质：冻结主分析完成后的解释性误差审计；不得替换或回填预注册主指标

## 1. 主分析口径

v3 共 10 个问题、3 个供应商种子、30 个单元。主分析保留全部失败单元：结构化计划完成 29/30，Reviewer/H0 通过 27/30，冻结词表主题忠实 26/30，安全停止 30/30。

本审计只解释剩余误差来自哪里。即使人工语义检查认为冻结词表漏识别同义表达，参赛主表仍必须报告 **26/30（86.7%）**，不能在看到结果后扩充词表并把分数改写为更高值。

## 2. 唯一结构失败

| 单元 | 阶段 | 供应商尝试 | 失败原因 | 系统行为 |
|---|---|---:|---|---|
| `Q07_institutional_attention_greenwashing__seed_20260902` | initial_planning | 3 | Qwen 输出在冻结调用预算内仍未满足 DiscoveryPlan 根级角色基数约束 | 记录匿名化回执并安全停止，没有生成计划或科学结论 |

该单元触发了结构修复但未恢复。失败摘要只保留 `ValidationError` 类型化信息，不保存原始模型响应；回执有效，`safe_stop=true`。这说明系统仍可能受生成式结构波动影响，但失败被正确封闭，没有转化为伪计划。

## 3. 两个 Reviewer 阻断

### Q03：投资规模与投资效率

单元：`Q03_investment_scale_efficiency__seed_20260901`

候选计划完整提及环保投资、投资规模、投资效率和环境绩效，因此冻结词表判为主题忠实；但计划把“预防性投资 vs 治理性投资结构”提升为核心调节机制，用它替代原问题更开放的“如何区分规模与效率”。Reviewer 判定该具体机制窄化了问题，二轮修复后仍阻断。

这是合理的保守停止，不应当作为“模型没答出关键词”理解。后续若由人类研究者明确指定投资结构机制，可以作为新问题重新进入 H0，而不应在当前问题下自动放行。

### Q07：披露质量与绿色漂洗

单元：`Q07_institutional_attention_greenwashing__seed_20260903`

候选文本包含机构投资者关注、环境披露质量和绿色漂洗全部关键词，但把绿色漂洗风险从原问题中的关键结果降为 mediator，且基线模型只明确回归披露质量，没有独立检验绿色漂洗结果。Reviewer 因结果角色发生变化而阻断。

这说明 Reviewer 检查的是研究语义和变量角色，不是简单关键词重合；该阻断应在比赛中作为“问题保真闸门”的例子。

## 4. 三个冻结词表未命中

| 单元 | 实际生成表达 | 冻结词表要求 | Reviewer | 主分析处理 |
|---|---|---|---|---|
| `Q04_digital_green_synergy__seed_20260902` | `industrial structure upgrade` | 包含 `industrial structure upgrading`，但未列 `upgrade` | 通过，且明确把产业结构升级作为 mediator | 仍按 topic_fidelity=false |
| `Q05_green_credit_regional_heterogeneity__seed_20260901` | `Eastern China compared to Central and Western regions` | 只预列若干连续短语，如 `eastern central western` | 通过，构念与交互项均保留东中西部异质性 | 仍按 topic_fidelity=false |
| `Q05_green_credit_regional_heterogeneity__seed_20260903` | `Eastern China compared to Central and Western China` | 同上 | 通过，`Regional Location (East/Central/West)` 明确存在 | 仍按 topic_fidelity=false |

这三项更符合“冻结正则裁判覆盖不足”，而不是计划真实丢失主题。它们解释了 Reviewer 与正则裁判的 3 个表面 false-positive，但不能用于事后修改主结果。建议在下一版问题集预注册时加入词形归一化、非连续概念匹配和冻结的人类双盲复核规则。

## 5. Reviewer 与冻结词表并非同一裁判

在 29 个完整单元中，Reviewer 与冻结词表的交叉结果为：共同通过 24、Reviewer 阻断而词表通过 2、Reviewer 通过而词表未命中 3、共同失败 0。

两者测试的是不同能力：

- 冻结词表测试可复算的概念显式出现，优点是确定、缺点是同义表达覆盖有限；
- Reviewer 测试暴露、结果、限定语及构念角色是否保持，优点是语义更强、缺点是仍依赖模型判断。

比赛材料应并列呈现，不应选择分数更高的一个替代另一个。

## 6. 结论与剩余风险

v3 的剩余真实系统风险主要是 **1/30 的结构生成失败**；两个 Reviewer 阻断均体现科学保守性，三个主题忠实失败主要暴露冻结正则裁判的词形覆盖限制。系统没有在任何一个异常单元中越过 H1，也没有授权统计执行或科学结论。

赛前不建议在看到结果后继续改协议并追求 30/30。更可信的做法是保留这 1 个结构失败和 2 个语义阻断，展示系统如何记录失败、解释失败并安全停止。
