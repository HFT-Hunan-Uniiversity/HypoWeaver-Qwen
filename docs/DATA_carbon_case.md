# 碳市场主案例数据

来源为 Daihui Wei（2025）的公开数据集 [Industry Peer Effect of Corporate Green Innovation](https://data.mendeley.com/datasets/rrfwny7byp/1)，DOI `10.17632/rrfwny7byp.1`，版本 1，许可 CC BY 4.0。该数据集页面的文字是发布者说明，不能作为本产品已经验证的研究结论，也不能替代已发表论文。

从仓库根目录运行：

```bash
cd backend
uv run python -m hypoweaver.cases.carbon fetch
uv run python -m hypoweaver.cases.carbon prepare
```

`fetch` 从公开文件地址流式下载到 `DATA_DIR/raw/data.dta`，核验大小为 332,614,843 字节；中断片段保留为 `.partial`，下次仅在服务器接受 Range 时续传。已有完整文件不会覆盖。`prepare` 只读取 21 列、重命名，不筛行，将分析 CSV 放在 `DATA_DIR/datasets/` 并登记为全局可选资产。重复准备复用已登记的同配方资产，可选 `--project-id` 关联项目。原始文件、CSV 和 SQLite 都不进入 Git。

2026-10-12 实际下载与准备结果：14,208 行，1,184 个企业，2010–2021 年 12 期，平衡面板，个体—时间键没有重复或缺失。界面上传原始 `.dta` 时，先列出列名及 Stata 标签，再用 `usecols` 只读取勾选的字段。可复用已上传文件进行另一次列选择，避免重复保存 333 MB 原件。

| 原始字段 | 准备后的字段 | 含义 |
| --- | --- | --- |
| Symbol / year | firm_id / year | 企业 / 年份 |
| IndustryCode | industry_code | 当期行业代码 |
| PROVINCECODE / CITYCODE | province_code / city_code | 地区代码 |
| carbon_post | industry_peer_exposure | 行业同群暴露，非企业控排身份 |
| green_patent1 / 2 / 3 | green_all_independent / green_invention_independent / green_utility_independent | 独立申请的全部 / 发明 / 实用新型绿色专利 |
| green_patent4 / 5 / 6 | green_all_joint / green_invention_joint / green_utility_joint | 联合申请的全部 / 发明 / 实用新型绿色专利 |
| Size / Lev / ROA | total_assets / leverage / return_on_assets | 原始资产总计 / 杠杆 / 资产收益率 |
| SOE / HHI_A | state_ownership / industry_concentration | 股权性质编码 / 行业集中度 |
| FC_index / KZ_index / SA_index / WW_index | fc_index / kz_index / sa_index / ww_index | 融资约束指标 |

派生公式在绑定阶段定义：结果可用 `log1p(green_invention_independent + green_invention_joint)`，资产控制为 `log(total_assets)`，不能误把原始 `Size` 当成对数。`state_ownership` 原值是分类编码，未自动转成国企虚拟变量。

处理变量应定义为“行业层面同群暴露（发布者编码，行业×年份恒定）”，“真实处理分配”勾选为否。不能区分企业本身是否控排。方法可用政策 DID 框架，但最高只报告条件关联；事件研究限定单调暴露路径，机制指标仅用于机制线索。建议另外检查行业聚类。样本止于 2021 年，不支持将结果推广到全国碳市场的后续年份。

引用示例：Wei, Daihui (2025), “Industry Peer Effect of Corporate Green Innovation”, Mendeley Data, V1, https://doi.org/10.17632/rrfwny7byp.1，CC BY 4.0。本文使用其数据并作列选择、字段重命名；所有变换在研究方案与变量绑定中另行记录。
