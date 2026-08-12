import type { ResourceDetail, ResourceKind } from './types'

function fixture(
  kind: ResourceKind,
  id: string,
  title: string,
  summary: string | undefined,
  source: string,
  tags: string[],
  availability: ResourceDetail['availability'],
  attributes: ResourceDetail['attributes'],
): ResourceDetail {
  return { id, kind, title, summary, source, tags, availability, attributes }
}

export const LITERATURE_FIXTURES: ResourceDetail[] = [
  fixture('literature', 'lit-001', '绿色金融改革与企业绿色创新', '基于地区政策差异讨论绿色金融与企业创新之间的关系。', '公开文献元数据快照', ['绿色金融', '企业创新', '政策评估'], 'available', { scope: '企业', conclusion: '促进创新', topics: ['绿色金融', '绿色创新'], year: 2024, journal: '金融研究' }),
  fixture('literature', 'lit-002', '绿色信贷政策的资源配置效应', '考察信贷约束如何改变高污染行业的融资与投资。', '公开文献元数据快照', ['绿色信贷', '融资约束'], 'available', { scope: '企业', conclusion: '调整资源配置', topics: ['绿色信贷', '融资约束'], year: 2023, journal: '经济研究' }),
  fixture('literature', 'lit-003', '环境规制与企业技术升级', '比较不同环境规制工具对技术升级的影响。', '公开文献元数据快照', ['环境规制', '技术升级'], 'available', { scope: '企业', conclusion: '异质性影响', topics: ['环境规制', '技术升级'], year: 2022, journal: '管理世界' }),
  fixture('literature', 'lit-004', '绿色金融试验区的区域溢出', '从城市层面评估试验区政策的空间关联。', '公开文献元数据快照', ['试验区', '空间溢出'], 'available', { scope: '城市', conclusion: '存在区域溢出', topics: ['绿色金融', '空间效应'], year: 2024, journal: '中国工业经济' }),
  fixture('literature', 'lit-005', '金融科技与绿色信贷可得性', '研究数字化风控与绿色项目融资可得性的关联。', '公开文献元数据快照', ['金融科技', '绿色信贷'], 'available', { scope: '企业', conclusion: '改善信贷可得性', topics: ['金融科技', '绿色信贷'], year: 2021, journal: '金融论坛' }),
  fixture('literature', 'lit-006', '企业环境信息披露与资本成本', '整理披露质量、投资者关注与融资成本的经验关系。', '公开文献元数据快照', ['信息披露', '资本成本'], 'available', { scope: '企业', conclusion: '降低资本成本', topics: ['环境信息', '资本市场'], year: 2020, journal: '会计研究' }),
  fixture('literature', 'lit-007', '碳交易政策与企业减排行为', '使用政策分期实施信息考察企业减排行为。', '公开文献元数据快照', ['碳交易', '减排'], 'available', { scope: '企业', conclusion: '促进减排', topics: ['碳交易', '环境绩效'], year: 2023, journal: '数量经济技术经济研究' }),
  fixture('literature', 'lit-008', '绿色债券发行与企业投资', '分析绿色债券发行前后的投资结构变化。', '公开文献元数据快照', ['绿色债券', '企业投资'], 'available', { scope: '企业', conclusion: '优化投资结构', topics: ['绿色债券', '企业投资'], year: 2022, journal: '证券市场导报' }),
  fixture('literature', 'lit-009', '环境政策不确定性与创新决策', undefined, '公开文献元数据快照', ['政策不确定性', '创新'], 'metadata_only', { scope: '企业', conclusion: '抑制长期创新', topics: ['政策不确定性', '创新'], year: 2019, journal: '产业经济评论' }),
  fixture('literature', 'lit-010', '地方绿色财政支出的绩效评估', '从城市层面讨论绿色财政支出与污染治理绩效。', '公开文献元数据快照', ['绿色财政', '污染治理'], 'available', { scope: '城市', conclusion: '改善治理绩效', topics: ['绿色财政', '污染治理'], year: 2021, journal: '财政研究' }),
  fixture('literature', 'lit-011', '绿色供应链与企业环境绩效', '考察核心企业绿色采购要求的供应链传导。', '公开文献元数据快照', ['绿色供应链', '环境绩效'], 'available', { scope: '供应链', conclusion: '产生链式传导', topics: ['供应链', '环境绩效'], year: 2024, journal: '南开管理评论' }),
  fixture('literature', 'lit-012', '银行竞争与绿色项目融资', '研究银行竞争程度与绿色项目贷款条件之间的关系。', '公开文献元数据快照', ['银行竞争', '项目融资'], 'unavailable', { scope: '项目', conclusion: '关系依赖市场结构', topics: ['银行竞争', '绿色融资'], year: 2018, journal: '经济管理' }),
]

export const POLICY_FIXTURES: ResourceDetail[] = [
  fixture('policy', 'policy-001', '绿色金融改革创新试验区总体方案', '明确试验区建设目标、地区安排与重点任务。', '国务院公开政策', ['绿色金融', '试验区'], 'available', { issuer: '国务院', administrativeLevel: '国家', region: '多地区', topic: '绿色金融', effectiveDate: '2017-06-14', status: '现行' }),
  fixture('policy', 'policy-002', '关于构建绿色金融体系的指导意见', '提出绿色信贷、绿色债券和环境信息披露等制度方向。', '中央部门公开政策', ['绿色金融体系'], 'available', { issuer: '中国人民银行等部门', administrativeLevel: '国家', region: '全国', topic: '绿色金融', effectiveDate: '2016-08-31', status: '现行' }),
  fixture('policy', 'policy-003', '绿色信贷指引', '规定银行业金融机构绿色信贷管理要求。', '金融监管公开政策', ['绿色信贷', '银行'], 'available', { issuer: '原银监会', administrativeLevel: '国家', region: '全国', topic: '绿色信贷', effectiveDate: '2012-02-24', status: '现行' }),
  fixture('policy', 'policy-004', '银行业保险业绿色金融指引', '完善银行保险机构绿色金融治理和风险管理要求。', '金融监管公开政策', ['绿色金融', '风险管理'], 'available', { issuer: '原银保监会', administrativeLevel: '国家', region: '全国', topic: '绿色金融', effectiveDate: '2022-06-01', status: '现行' }),
  fixture('policy', 'policy-005', '绿色产业指导目录（2019年版）', '界定绿色产业、项目与服务的分类范围。', '中央部门公开目录', ['绿色产业', '分类目录'], 'available', { issuer: '国家发展改革委等部门', administrativeLevel: '国家', region: '全国', topic: '绿色产业', effectiveDate: '2019-02-14', status: '已更新' }),
  fixture('policy', 'policy-006', '绿色债券支持项目目录（2021年版）', '统一绿色债券支持项目的认定边界。', '中央部门公开目录', ['绿色债券', '项目目录'], 'available', { issuer: '中国人民银行等部门', administrativeLevel: '国家', region: '全国', topic: '绿色债券', effectiveDate: '2021-07-01', status: '现行' }),
  fixture('policy', 'policy-007', '碳排放权交易管理办法（试行）', '规范全国碳排放权登记、交易与履约。', '生态环境部公开政策', ['碳交易', '减排'], 'available', { issuer: '生态环境部', administrativeLevel: '国家', region: '全国', topic: '碳交易', effectiveDate: '2021-02-01', status: '现行' }),
  fixture('policy', 'policy-008', '环境信息依法披露制度改革方案', '推进企业环境信息强制披露制度建设。', '生态环境公开政策', ['信息披露', '环境治理'], 'available', { issuer: '生态环境部', administrativeLevel: '国家', region: '全国', topic: '环境信息', effectiveDate: '2021-05-24', status: '现行' }),
  fixture('policy', 'policy-009', '湖州市绿色金融改革实施方案', '提出地方绿色金融产品、标准和激励机制。', '地方政府公开政策', ['湖州', '绿色金融'], 'available', { issuer: '湖州市人民政府', administrativeLevel: '市级', region: '浙江湖州', topic: '绿色金融', effectiveDate: '2017-12-01', status: '现行' }),
  fixture('policy', 'policy-010', '广州市绿色金融改革行动计划', '部署绿色金融服务体系与重点项目建设。', '地方政府公开政策', ['广州', '绿色金融'], 'available', { issuer: '广州市人民政府', administrativeLevel: '市级', region: '广东广州', topic: '绿色金融', effectiveDate: '2018-03-01', status: '已到期' }),
  fixture('policy', 'policy-011', '重庆市建设绿色金融改革创新试验区实施细则', undefined, '地方政府公开政策', ['重庆', '试验区'], 'metadata_only', { issuer: '重庆市人民政府', administrativeLevel: '省级', region: '重庆', topic: '绿色金融', effectiveDate: '2022-10-01', status: '现行' }),
  fixture('policy', 'policy-012', '绿色低碳转型产业指导目录（2024年版）', '更新绿色低碳转型产业的支持范围。', '中央部门公开目录', ['低碳转型', '产业目录'], 'unavailable', { issuer: '国家发展改革委等部门', administrativeLevel: '国家', region: '全国', topic: '低碳转型', effectiveDate: '2024-02-02', status: '现行' }),
]

export const DATASET_FIXTURES: ResourceDetail[] = [
  fixture('dataset', 'dataset-001', '中国城市统计年鉴指标', '城市经济、人口、产业与公共服务年度指标目录。', '国家统计公开资料', ['城市', '年度'], 'metadata_only', { region: '全国城市', frequency: '年度', coverage: '2000–2023', access: '需自行获取', variables: ['GDP', '人口', '产业结构'], license: '依来源条款', qualityStatus: '待核验' }),
  fixture('dataset', 'dataset-002', '中国工业企业基础指标', '企业规模、行业、资产与经营状况字段说明。', '公共数据目录', ['企业', '工业'], 'unavailable', { region: '全国', frequency: '年度', coverage: '1998–2013', access: '受控申请', variables: ['资产', '就业', '行业'], license: '受控使用', qualityStatus: '需清洗' }),
  fixture('dataset', 'dataset-003', '上市公司财务指标目录', '上市公司资产负债表、利润表与现金流量表字段目录。', '商业数据库元数据', ['上市公司', '财务'], 'metadata_only', { region: '中国A股', frequency: '季度/年度', coverage: '1990–至今', access: '机构订阅', variables: ['总资产', '营业收入', '负债率'], license: '订阅许可', qualityStatus: '结构化' }),
  fixture('dataset', 'dataset-004', '企业绿色专利指标目录', '绿色专利申请、授权与分类口径说明。', '专利公开数据元数据', ['专利', '绿色创新'], 'metadata_only', { region: '全国', frequency: '年度', coverage: '1985–至今', access: '公开检索', variables: ['申请量', '授权量', 'IPC'], license: '依来源条款', qualityStatus: '需实体匹配' }),
  fixture('dataset', 'dataset-005', '全国空气质量城市日度指标', '城市空气质量指数及主要污染物日度观测。', '生态环境公开数据', ['空气质量', '城市'], 'available', { region: '全国城市', frequency: '日度', coverage: '2014–至今', access: '公开下载', variables: ['AQI', 'PM2.5', 'SO2'], license: '公开使用需注明来源', qualityStatus: '结构化' }),
  fixture('dataset', 'dataset-006', '全国碳市场成交信息', '全国碳市场成交量、成交额与收盘价信息。', '交易机构公开数据', ['碳市场', '交易'], 'available', { region: '全国', frequency: '交易日', coverage: '2021–至今', access: '公开查询', variables: ['成交量', '成交额', '收盘价'], license: '依来源条款', qualityStatus: '结构化' }),
  fixture('dataset', 'dataset-007', '绿色金融试验区政策时间表', '试验区批次、地区与公开实施日期的元数据清单。', '公开政策整理', ['绿色金融', '政策时点'], 'available', { region: '试验区', frequency: '事件', coverage: '2017–至今', access: '公开整理', variables: ['地区', '批次', '日期'], license: '开放事实数据', qualityStatus: '需人工复核' }),
  fixture('dataset', 'dataset-008', '银行网点地理分布目录', '银行网点名称、机构类型与地理位置字段目录。', '金融机构公开名录', ['银行', '地理'], 'metadata_only', { region: '全国', frequency: '不定期', coverage: '存量', access: '公开查询', variables: ['机构名', '地址', '机构类型'], license: '依来源条款', qualityStatus: '需地理编码' }),
  fixture('dataset', 'dataset-009', '城市绿色财政支出指标', '地方财政节能环保相关支出科目元数据。', '财政公开资料', ['财政', '环境支出'], 'metadata_only', { region: '全国城市', frequency: '年度', coverage: '2007–2023', access: '年鉴整理', variables: ['节能环保支出', '一般预算支出'], license: '依来源条款', qualityStatus: '口径需对齐' }),
  fixture('dataset', 'dataset-010', '企业环境处罚公开记录', '企业环境行政处罚决定的公开字段目录。', '政府公开信息', ['环境处罚', '企业'], 'available', { region: '全国', frequency: '事件', coverage: '动态更新', access: '公开查询', variables: ['企业名', '处罚日期', '处罚金额'], license: '公开信息合理使用', qualityStatus: '需实体匹配' }),
  fixture('dataset', 'dataset-011', '地级市气象观测指标', undefined, '气象公开数据目录', ['气象', '城市'], 'metadata_only', { region: '全国站点', frequency: '日度', coverage: '1951–至今', access: '注册申请', variables: ['温度', '降水', '风速'], license: '依申请条款', qualityStatus: '待核验' }),
  fixture('dataset', 'dataset-012', '省级能源消费平衡表', '省级能源生产、调入、消费与损失指标。', '能源统计公开资料', ['能源', '省级'], 'unavailable', { region: '全国省级', frequency: '年度', coverage: '2000–2022', access: '年鉴获取', variables: ['能源消费', '能源结构', '碳强度'], license: '依来源条款', qualityStatus: '口径需对齐' }),
]

export const METHOD_FIXTURES: ResourceDetail[] = [
  fixture('method', 'method-001', '双重差分（DID）', '比较处理组与对照组在政策前后的变化差异。', '方法卡片', ['因果识别', '面板数据'], 'available', { family: '政策评估', researchGoal: '因果', dataStructure: '面板', identificationAssumptions: ['平行趋势', '无同期差异冲击'], diagnostics: ['事件研究', '安慰剂检验'] }),
  fixture('method', 'method-002', '多期双重差分', '处理不同单位在不同时点进入政策的情形。', '方法卡片', ['因果识别', '分期处理'], 'available', { family: '政策评估', researchGoal: '因果', dataStructure: '面板', identificationAssumptions: ['分期平行趋势', '处理时点可观测'], diagnostics: ['组别-时点效应', '权重诊断'] }),
  fixture('method', 'method-003', '三重差分（DDD）', '引入第三个差异维度以隔离替代解释。', '方法卡片', ['因果识别', '三重差分'], 'available', { family: '政策评估', researchGoal: '因果', dataStructure: '面板', identificationAssumptions: ['三重平行趋势'], diagnostics: ['分组趋势', '替代分组'] }),
  fixture('method', 'method-004', '断点回归（RDD）', '利用阈值附近处理概率的跳跃识别局部效应。', '方法卡片', ['阈值', '局部效应'], 'available', { family: '准实验', researchGoal: '因果', dataStructure: '截面', identificationAssumptions: ['阈值不可精确操纵', '潜在结果连续'], diagnostics: ['密度检验', '协变量连续性'] }),
  fixture('method', 'method-005', '合成控制法', '以对照单位加权组合构造反事实路径。', '方法卡片', ['合成控制', '政策评估'], 'available', { family: '准实验', researchGoal: '因果', dataStructure: '时间序列面板', identificationAssumptions: ['政策前拟合充分'], diagnostics: ['安慰剂地区', '拟合误差比'] }),
  fixture('method', 'method-006', '倾向得分匹配', '按观测协变量估计处理概率并构造可比样本。', '方法卡片', ['匹配', '选择偏差'], 'available', { family: '匹配', researchGoal: '因果', dataStructure: '截面/面板', identificationAssumptions: ['条件独立', '共同支撑'], diagnostics: ['平衡性', '共同支撑区间'] }),
  fixture('method', 'method-007', '工具变量法（IV）', '使用满足相关性和排除限制的工具识别内生解释变量。', '方法卡片', ['内生性', '工具变量'], 'available', { family: '内生性处理', researchGoal: '因果', dataStructure: '截面/面板', identificationAssumptions: ['工具相关性', '排除限制'], diagnostics: ['弱工具检验', '过度识别检验'] }),
  fixture('method', 'method-008', '回归不连续时间序列', '识别明确时间节点前后的水平或趋势变化。', '方法卡片', ['时间序列', '政策冲击'], 'available', { family: '时间序列', researchGoal: '因果', dataStructure: '时间序列', identificationAssumptions: ['无同期结构突变'], diagnostics: ['序列相关', '带宽敏感性'] }),
  fixture('method', 'method-009', '空间面板模型', '刻画地区间空间依赖与溢出效应。', '方法卡片', ['空间效应', '面板'], 'available', { family: '空间计量', researchGoal: '机制', dataStructure: '空间面板', identificationAssumptions: ['空间权重合理'], diagnostics: ['Moran I', '权重矩阵敏感性'] }),
  fixture('method', 'method-010', '中介机制分析', '分解解释变量通过候选机制影响结果的路径。', '方法卡片', ['机制', '中介'], 'metadata_only', { family: '机制检验', researchGoal: '机制', dataStructure: '截面/面板', identificationAssumptions: ['机制顺序可辩护'], diagnostics: ['替代机制', '时序检验'] }),
  fixture('method', 'method-011', '异质性效应分析', '按预设分组或连续调节变量比较效应差异。', '方法卡片', ['异质性', '分组'], 'available', { family: '效应分解', researchGoal: '异质性', dataStructure: '截面/面板', identificationAssumptions: ['分组预先指定'], diagnostics: ['交互项', '多重检验校正'] }),
  fixture('method', 'method-012', '双重机器学习（DML）', undefined, '方法卡片', ['机器学习', '因果估计'], 'unavailable', { family: '半参数方法', researchGoal: '因果', dataStructure: '截面/面板', identificationAssumptions: ['正交得分', '交叉拟合'], diagnostics: ['重叠性', '学习器敏感性'] }),
]

export const RESOURCE_FIXTURES: Record<ResourceKind, ResourceDetail[]> = {
  literature: LITERATURE_FIXTURES,
  policy: POLICY_FIXTURES,
  dataset: DATASET_FIXTURES,
  method: METHOD_FIXTURES,
}
