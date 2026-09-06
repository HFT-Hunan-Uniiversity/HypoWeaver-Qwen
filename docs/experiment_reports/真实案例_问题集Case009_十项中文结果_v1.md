# 问题集真实案例：GFRI 与城市空气质量（十项中文生成结果）

> 问题集 ID：`case_009_gfri_air_quality`  
> 数据许可：CC0-1.0；来源记录为 Harvard Dataverse DOI `10.7910/DVN/LEOXAK`  
> 模型执行：DashScope / Qwen3.7-plus，7 次成功调用、0 次失败  
> 科学裁决：8 个核心校验门全部通过；目标因果结论未获准写入  
> 展示定位：真实数据执行案例 + 科学防线案例

## 一、待研究问题（Problem Statement）

绿色金融改革创新试验区（GFRI）能否改善城市空气质量，是绿色金融政策评估中的核心问题。已有研究利用 2015—2019 年中国地级市数据和双重差分模型报告了政策实施后的 AQI 改善，但这类结论高度依赖平行趋势、处理组规模、控制变量缺失、政策时间编码与聚类推断是否成立。

本问题集要求 AI Scientist 回答的不是“回归系数是否显著”这一单点问题，而是：**在冻结的城市—月度面板与共同政策起点下，GFRI 对 AQI 的估计能否通过前趋势、小处理组推断、样本缺失和独立复算等科学门，达到因果结论准入标准？**

## 二、解决思路（Rationale）

系统采用“先执行、再审计、后授权”的研究闭环：

1. Qwen Research Planner 根据数据字典形成可执行分析计划；
2. 确定性代码执行共同起点 DID、事件研究和全部敏感性分析；
3. Method Reviewer 核对实体键、政策日历、固定效应、聚类层级和样本流；
4. Statistical Reviewer 检查前趋势、wild cluster bootstrap、处理组置换和 leave-one-treated-out；
5. Reproduction Agent 用独立实现复算关键系数；
6. Claim Gate 根据诊断结果决定“因果结论、条件关联结论或识别失败报告”三种输出模式。

这个设计的亮点是：**模型完成任务并不等于结论自动过关。** 即使代码、数据血缘和复算全部正确，只要识别条件失败，系统仍会把“政策有效”的强结论拦截在最终文本之外。

## 三、必要的技术手段（Technical Details）

- Qwen3.7-plus 多阶段规划、结果解释、审稿修订与中文写作；
- 类型化 `AnalysisPlan`、`ExecutionResult`、`DiagnosticReport`、`ClaimLedger` 对象；
- 城市固定效应与月份固定效应的共同起点 DID；
- 实体层聚类标准误及 \(G-1\) 自由度修正；
- 事件研究与处理前系数联合 Wald 检验；
- 999 次 wild cluster bootstrap；
- 999 次处理城市随机置换；
- 逐一剔除处理城市的 leave-one-treated-out；
- 假政策时点、无控制扩展样本与缺失样本流敏感性；
- 独立估计器复算、哈希绑定、结果语义和虚假证据门禁。

## 四、数据集（Datasets）

### Source

- 论文与数据记录：Xu、Xie、Obobisa 与 Sun（2023），*Has the establishment of green finance reform and innovation pilot zones improved air quality? Evidence from China*；
- 数据存档：Harvard Dataverse，DOI `10.7910/DVN/LEOXAK`，CC0-1.0；
- 冻结主数据 SHA-256：`3a8e913bffa8de2e5f90b1d2677a24af0f77974c2b699ccf57f5c5002a44471b`。

### Target / 实际执行面板

| 项目 | 冻结定义 |
|---|---|
| 原始规模 | 8,760 行，146 个 panel ID，60 个月，145 个唯一城市名 |
| 处理分配 | 9 个处理 panel ID；共同政策起点为 2017-07（月份索引 31） |
| 结局 | `AQI` |
| 核心暴露 | `dudt = treat × post` |
| 控制变量 | `Temp`、`lnGDP`、`lngdp2`、`greenration`、`pop`、`fdi` |
| 实体/时间键 | `id` / `month`；不用非唯一的城市名称代替实体键 |
| 完整控制样本 | 7,236 行，132 个 panel ID，7 个处理 panel ID |
| 缺失影响 | 六项控制变量使 1,524 行退出主规格 |

## 五、标题（Paper Title）

中文标题：

> **绿色金融试验区真的改善了城市空气质量吗？一项由 AI Scientist 驱动的 DID 复现与识别压力测试**

英文标题：

> **Did Green Finance Pilot Zones Improve Urban Air Quality? An AI-Scientist Replication and Identification Stress Test**

## 六、摘要（Paper Abstract）

本文使用一个公开许可的中国城市—月度问题集，复核绿色金融改革创新试验区对空气质量指数的影响。我们以 2017 年 7 月为共同政策起点，在城市与月份固定效应下估计 DID，并执行事件研究、wild cluster bootstrap、处理组置换、逐一剔除处理城市、假时点和缺失样本敏感性分析。主规格使用 7,236 个城市—月观测和 7 个处理 panel，政策交互项为 −0.136（SE=2.069，p=0.948）；wild cluster bootstrap 与处理组置换 p 值分别为 0.961 和 0.960。更关键的是，处理前系数联合检验显著拒绝平行趋势，且主系数对控制变量缺失样本较为敏感。独立实现将核心系数复算至 \(1.82\times10^{-11}\) 的最大绝对差。由此，系统拒绝“政策无效”与“政策显著改善 AQI”两种因果表达，只允许报告“冻结规格下未检测到稳定条件关联，并存在严重识别障碍”。该案例展示了 AI Scientist 不仅能生成和执行分析，更能在结果不符合预期时阻止伪因果结论进入论文。

## 七、方法论（Methods）

### 7.1 主规格

对城市面板实体 \(i\) 和月份 \(t\)，估计：

\[
AQI_{it}=\alpha_i+\lambda_t+\beta(Treat_i\times Post_t)
+\gamma'X_{it}+\varepsilon_{it},
\]

其中 \(Post_t=1\) 表示 2017 年 7 月及以后，\(X_{it}\) 为六项冻结控制变量。主推断按 `id` 聚类；城市名称仅用于展示，因为数据中存在一个城市名映射到多个 panel ID。

### 7.2 识别与稳健性流程

1. 核验 `dudt` 与 `treat × post` 完全一致，并确认是共同起点而非错写为 staggered DID。
2. 以政策前一个月为基准构造事件时间，远端提前期和滞后期分别合并；联合检验全部提前项。
3. 在仅 7 个完整样本处理实体的条件下，使用 999 次 wild cluster bootstrap 和 999 次处理组置换补充常规聚类推断。
4. 逐一剔除 7 个处理 panel，检查单个城市是否驱动结果。
5. 将假政策时间设置为 2016-07，并在真实政策发生前截断样本。
6. 比较六控制完整样本、同一完整样本无控制规格以及恢复 1,524 行后的无控制扩展样本。
7. 用独立实现重新估计冻结模型，并由 Benchmark Recompute Gate 校验全部关键数值。

## 八、实验设计（Experiments）

| 实验 | Baseline / Ablation | Metrics | 目的 |
|---|---|---|---|
| E1 主 DID | 城市 FE；月份 FE；六项控制；`id` 聚类 | \(\hat\beta\)、SE、p、95% CI、N | 估计冻结问题的目标系数 |
| E2 动态效应 | 省略政策前一个月的事件研究 | 各期系数、同时图形、提前项联合 p | 检查平行趋势与动态形态 |
| E3 小处理组推断 | 常规聚类 vs 999 次 wild bootstrap vs 999 次处理组置换 | 三种 p 值、置换分布分位数 | 避免 7 个处理组下的虚假精确性 |
| E4 处理组敏感性 | 逐一剔除 7 个处理 panel | 系数最小值、最大值、方向变化 | 检查单一试点城市驱动 |
| E5 样本流敏感性 | 六控制完整样本；同样本无控制；扩展无控制 | N、处理组数、系数变化 | 量化缺失控制变量造成的选择 |
| E6 假时点 | 2016-07 假政策起点；排除真实政策期 | placebo 系数与 p | 检查预先存在的差异走势 |
| E7 独立复算 | HypoWeaver 主实现 vs benchmark-owned 独立实现 | 最大绝对差、90 项复算指标 | 证明数值不是模型口述或手抄 |
| E8 Claim Gate | 无门禁写作 vs 识别门禁写作 | 因果准入状态、最大允许强度、矛盾数 | 阻止“p>0.05 即无效”等错误结论 |

## 九、实验结果（Results）

### 9.1 Qwen 与工程执行结果

- Qwen3.7-plus：7 次成功调用、0 次失败；输入 261,449 tokens，输出 12,278 tokens，模型阶段耗时 252.58 秒；
- 数据血缘、估计器语义、独立复算、诊断完整性、Claim 一致性、报告一致性、符号语义和虚假证据共 **8 个核心门全部通过**；
- 独立复算覆盖 90 个指标，核心估计最大绝对差为 \(1.82\times10^{-11}\)。

### 9.2 统计结果

| 指标 | 实际结果 | 科学含义 |
|---|---:|---|
| 主 DID 系数 | −0.135993 | 点估计接近 0 |
| 实体聚类 SE | 2.069367 | 不确定性远大于点估计 |
| 常规 p 值 | 0.947603 | 冻结规格下未检测到条件关联 |
| Wild cluster bootstrap p | 0.961 | 小处理组稳健推断同样不支持关联 |
| 处理组置换 p | 0.960080 | 观察值在置换分布中不异常 |
| 提前项联合 p | \(5.09\times10^{-6}\) | 平行趋势被显著拒绝，因果准入失败 |
| Leave-one-treated-out | [−1.8288, 1.1101] | 剔除不同试点后方向会改变 |
| 同样本无控制系数 | −0.5049 | 与主规格方向相同但仍不稳定 |
| 扩展无控制系数 | 1.9437 | 恢复缺失行后方向反转，提示样本选择敏感 |
| 假时点系数 / p | −0.7411 / 0.7021 | 未发现同型假时点效应，但不能修复前趋势失败 |

### 9.3 最终生成结论

系统最终没有输出“GFRI 改善空气质量”，也没有输出“GFRI 对空气质量没有影响”，而是生成如下可发表的识别结论：

> **在冻结的六控制共同起点 DID 规格中，未检测到 GFRI 与 AQI 的稳定条件关联；但显著的处理前趋势、仅 7 个完整样本处理实体以及样本缺失敏感性，使任何因果效应或因果零效应结论均不具备准入条件。**

从参赛展示角度，这不是“实验失败”，而是 AI Scientist 的关键能力证明：代码执行成功、模型调用成功、复算成功之后，系统仍能因为科学识别失败而拒绝一个更好看的政策结论。封存快照将输出模式自动切换为 `identification_failure_report`，目标 Claim 状态为 `rejected`。

## 十、参考论文（References）

1. Xu, X., Xie, Y., Obobisa, E. S., & Sun, H. (2023). Has the establishment of green finance reform and innovation pilot zones improved air quality? Evidence from China. *Humanities and Social Sciences Communications, 10*, 262. https://doi.org/10.1057/s41599-023-01773-0
2. Xu, X., Xie, Y., Obobisa, E. S., & Sun, H. (2023). Replication data for “Has the establishment of green finance reform and innovation pilot zones improved air quality? Evidence from China.” *Harvard Dataverse*. https://doi.org/10.7910/DVN/LEOXAK
3. Bertrand, M., Duflo, E., & Mullainathan, S. (2004). How much should we trust Differences-in-Differences estimates? *The Quarterly Journal of Economics, 119*(1), 249–275. https://doi.org/10.1162/003355304772839588
4. Conley, T. G., & Taber, C. R. (2011). Inference with “Difference in Differences” with a small number of policy changes. *The Review of Economics and Statistics, 93*(1), 113–125. https://doi.org/10.1162/REST_a_00049
5. MacKinnon, J. G., & Webb, M. D. (2017). Wild bootstrap inference for wildly different cluster sizes. *Journal of Applied Econometrics, 32*(2), 233–254. https://doi.org/10.1002/jae.2508
6. Roth, J. (2022). Pretest with caution: Event-study estimates after testing for parallel trends. *American Economic Review: Insights, 4*(3), 305–322. https://doi.org/10.1257/aeri.20210236

## 推荐放入技术方案的结果卡

> **真实问题集 / 真数据 / 真调用 / 真否决**：8,760 条城市—月记录进入冻结问题集，Qwen3.7-plus 完成 7 次调用，8 个科学门与独立复算全部通过；主 DID 为 −0.136（p=0.948），但前趋势联合检验 \(p=5.09\times10^{-6}\)。系统因此拒绝政策因果结论并自动生成识别失败报告，证明 HypoWeaver-Qwen 不会把“代码跑通”包装成“科学成立”。

