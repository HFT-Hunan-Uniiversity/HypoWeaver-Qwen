export type ShowcasePaperBlock =
  | { kind: 'paragraph'; text: string }
  | { kind: 'subheading'; text: string }
  | { kind: 'hypothesis'; label: string; text: string }
  | { kind: 'equation'; formula: string; label: string; note?: string }
  | { kind: 'figure'; id: string }
  | { kind: 'table'; id: string }

export interface ShowcasePaperSection {
  id: string
  title: string
  blocks: ShowcasePaperBlock[]
}

export interface ShowcasePaperFigure {
  id: string
  title: string
  src: string
  wordSrc: string
  alt: string
  note: string
  demo?: boolean
}

export interface ShowcasePaperTable {
  id: string
  title: string
  columns: string[]
  rows: string[][]
  note: string
  demo?: boolean
}

export const SHOWCASE_RESULT_METRICS = [
  { value: '0.0717', label: '政策暴露系数', note: '约对应7.4%的对数指标增幅' },
  { value: '0.00043', label: '企业聚类 p 值', note: '14,196条企业—年份观测' },
  { value: '0.494', label: '处理前联合检验 p 值', note: '未拒绝平行趋势' },
  { value: '16/16', label: '独立复算核验', note: '最大系数差小于5×10⁻¹¹' },
] as const

export const SHOWCASE_CLAIMS = [
  {
    status: '公开复现支持',
    claim: '在2010—2021年公开上市公司样本及原数据政策暴露编码下，碳政策暴露与企业绿色发明专利申请呈稳定正向关系。',
    evidence: '基准系数0.0717，p=0.00043；四项核心稳健性方向一致',
  },
  {
    status: '识别诊断通过',
    claim: '处理前动态系数整体不显著，政策后绿色发明响应逐步释放并趋于稳定。',
    evidence: '提前项联合检验p=0.494；499次企业轨迹置换p=0.004',
  },
  {
    status: '机制方向一致',
    claim: '政策暴露与融资约束代理值下降相伴，但本结果定位为机制一致性证据。',
    evidence: 'SA指数绝对值系数−0.0079，p=0.0199',
  },
  {
    status: '后续确认研究',
    claim: '全国碳市场效应将在补齐2022年以后结果与官方履约企业名单后单独检验。',
    evidence: '数据执行门保留全国命题，同时将当前估计范围收敛至区域公开复现',
  },
] as const

export const SHOWCASE_PAPER_FIGURES: ShowcasePaperFigure[] = [
  {
    id: 'mechanism',
    title: '图1  碳市场影响企业高质量绿色创新的理论机制',
    src: '/showcase-paper/backend_skill_figure_1_mechanism.svg',
    wordSrc: '/showcase-paper/backend_skill_figure_1_mechanism.png',
    alt: '碳市场通过融资条件、合规压力和价格信号影响高质量绿色创新的理论机制图',
    note: '注：该图为理论框架，不是统计估计结果。融资约束与市场竞争分别作为机制一致性和探索性异质性诊断。由后端中文经济学期刊图表 Skill 生成。',
  },
  {
    id: 'event-study',
    title: '图2  政策暴露前后的绿色发明专利动态',
    src: '/showcase-paper/backend_skill_figure_2_event_study.svg',
    wordSrc: '/showcase-paper/backend_skill_figure_2_event_study.png',
    alt: '区域碳政策暴露前后企业绿色发明专利的事件研究估计图',
    note: '注：点为企业和年份固定效应估计，线段为企业层面聚类的95%置信区间；−1期为基期。仅使用政策路径单调的企业，作为趋势与动态模式诊断。数据来源：Mendeley Data公开复现样本（CC BY 4.0）。',
  },
  {
    id: 'robustness',
    title: '图3  不同模型设定下的政策暴露系数',
    src: '/showcase-paper/backend_skill_figure_3_robustness.svg',
    wordSrc: '/showcase-paper/backend_skill_figure_3_robustness.png',
    alt: '八种模型设定下碳政策暴露系数及95%置信区间',
    note: '注：点为估计系数，横线为企业层面聚类的95%置信区间。不同结果变量用于稳健性和创新质量区分，不比较系数绝对大小。图中数值均为真实公开数据估计。',
  },
]

export const SHOWCASE_PAPER_TABLES: ShowcasePaperTable[] = [
  {
    id: 'variables',
    title: '表1  主要变量定义',
    columns: ['变量', '符号', '定义', '预期方向', '数据来源'],
    rows: [
      ['高质量绿色创新', 'LnGreenInv', 'ln（1＋绿色发明专利独立申请＋联合申请）', '—', '公开数据中的绿色专利字段'],
      ['碳政策暴露', 'Exposure', '数据发布者提供的企业—年份碳政策暴露编码', '＋', 'Mendeley Data原数据'],
      ['企业规模', 'Size', '企业总资产的自然对数', '待定', '公开企业财务字段'],
      ['资产负债率', 'Lev', '总负债与总资产之比', '待定', '公开企业财务字段'],
      ['资产收益率', 'ROA', '企业资产收益率', '＋', '公开企业财务字段'],
      ['融资约束', 'AbsSA', 'SA融资约束指数的绝对值', '－', '公开企业财务字段'],
      ['行业集中度', 'HHI', '企业所在行业年度HHI', '待定', '公开行业竞争字段'],
    ],
    note: '注：Exposure为公开数据发布者提供的源定义编码，未改写为全国碳市场官方履约名单；变量口径、样本规则和估计方法均在读取结果前冻结。',
  },
  {
    id: 'descriptive',
    title: '表2  主要变量的描述性统计',
    columns: ['变量', '观测值', '均值', '标准差', '最小值', '最大值'],
    rows: [
      ['LnGreenInv', '14196', '0.3880', '0.9084', '0.0000', '7.2598'],
      ['Exposure', '14196', '0.4801', '0.4996', '0.0000', '1.0000'],
      ['Size', '14196', '6.4763', '1.3281', '3.0263', '12.5184'],
      ['Lev', '14196', '0.4603', '0.1956', '0.0080', '1.0564'],
      ['ROA', '14196', '0.0393', '0.0559', '−0.9652', '0.5262'],
      ['AbsSA', '14196', '3.8153', '0.2742', '2.1196', '4.7566'],
    ],
    note: '注：主样本为2010—2021年12期齐全且主结果、政策暴露和三项控制变量无缺失的企业平衡面板；主模型不因显著性剔除样本，也不事后缩尾。',
  },
  {
    id: 'baseline',
    title: '表3  碳政策暴露与企业绿色发明专利：基准结果',
    columns: ['变量', '(1)', '(2)', '(3)', '(4)'],
    rows: [
      ['Exposure', '0.0729***\n(0.0204)', '0.0717***\n(0.0204)', '0.0805***\n(0.0223)', '0.0722***\n(0.0205)'],
      ['企业控制变量', '否', '是', '是', '是'],
      ['仅单调暴露路径', '否', '否', '是', '否'],
      ['行业集中度', '否', '否', '否', '是'],
      ['企业固定效应', '是', '是', '是', '是'],
      ['年份固定效应', '是', '是', '是', '是'],
      ['观测值', '14196', '14196', '13296', '14089'],
      ['R²', '0.6901', '0.6905', '0.6977', '0.6909'],
    ],
    note: '注：被解释变量为LnGreenInv。括号内为企业层面聚类稳健标准误；***表示在1%的水平上显著。第（2）列为预先冻结的主规格。',
  },
  {
    id: 'robustness',
    title: '表4  稳健性、创新质量与机制诊断',
    columns: ['检验', '系数', '标准误', 'p值', '观测值', '判断'],
    rows: [
      ['基准模型', '0.0717***', '0.0204', '0.00043', '14196', '支持'],
      ['剔除2021年', '0.0737***', '0.0196', '0.00017', '13013', '支持'],
      ['仅单调暴露路径', '0.0805***', '0.0223', '0.00031', '13296', '支持'],
      ['仅独立绿色发明', '0.0627***', '0.0152', '<0.0001', '14196', '支持'],
      ['全部绿色专利', '0.0602**', '0.0240', '0.0123', '14196', '支持'],
      ['绿色实用新型对照', '0.0229', '0.0182', '0.2083', '14196', '未显著'],
      ['融资约束代理值', '−0.0079**', '0.0034', '0.0199', '14196', '机制方向一致'],
      ['高竞争行业交互项', '−0.0485', '0.0309', '0.1169', '14089', '未支持'],
    ],
    note: '注：每行来自单独回归，固定效应和聚类层级与主模型一致。融资约束与竞争结果用于机制一致性和探索性异质性判断，不替代完整因果机制识别。',
  },
]

export const SHOWCASE_PAPER = {
  title: '碳市场能否激励企业高质量绿色创新？——基于公开上市公司面板的复现证据',
  subtitle: '真实公开数据执行｜双轮冻结协议｜独立复算',
  authors: ['HypoWeaver-Qwen 研究团队'],
  affiliation: '面向社会科学实证研究的证据驱动型 AI Scientist 示范研究',
  abstract: '碳市场能否将环境约束转化为企业持续创新动力，是理解市场型环境规制长期效应的关键。本文借助证据驱动型AI Scientist，围绕全国碳市场与企业高质量绿色技术创新提出研究假设，并在数据执行门发现全国市场结果期不足后，将本轮估计对象收敛为区域碳政策公开复现。基于2010—2021年1,183家上市公司的14,196条企业—年份观测，本文以绿色发明专利申请衡量高质量绿色创新，估计企业和年份双向固定效应模型，并执行事件研究、七项稳健性检验、融资约束与竞争异质性诊断以及499次企业政策轨迹置换。结果显示，政策暴露系数为0.0717（企业聚类标准误0.0204，p=0.00043）；剔除2021年、排除非单调暴露路径、改用独立绿色发明或全部绿色专利后，主要判断保持稳定。三个处理前系数的联合检验不能拒绝平行趋势（p=0.494），企业轨迹置换检验的双侧p值为0.004。融资约束代理值的估计方向与理论预期一致，市场竞争交互项未达到统计显著。独立估计器完成16项核验，核心系数最大绝对差小于5×10⁻¹¹。研究为区域碳政策暴露与高质量绿色创新之间的稳定正向关系提供了公开复现证据，也展示了AI Scientist从问题发现、范围自适应到统计执行和结论准入的完整科研能力。',
  keywords: ['碳市场', '高质量绿色创新', '绿色发明专利', '融资约束', 'AI Scientist'],
  jel: ['Q58', 'O32', 'G32'],
  sections: [
    {
      id: 'introduction',
      title: '一、问题提出',
      blocks: [
        { kind: 'paragraph', text: '碳排放权交易通过配额、交易与履约把环境外部成本转化为企业可观察的经营约束。制度能否进一步改变企业的长期技术选择，关系到碳市场能否在控制排放之外形成绿色增长动力。相较于购买配额或压缩产出，绿色发明具有降低跨期合规成本、形成知识积累和创造新产品的潜力，但其投入高、周期长、不确定性大，新增合规成本也可能挤出研发。碳市场究竟激励还是抑制高质量绿色创新，需要由企业层面的数据回答。' },
        { kind: 'paragraph', text: '围绕环境规制与创新，Porter and van der Linde（1995）强调合理规制可能诱发创新补偿，Popp（2002）和Calel and Dechezleprêtre（2016）则分别从能源价格与碳交易制度提供经验支持。中国地方碳交易试点形成了丰富的政策实践，但全国市场自2021年启动，现有公开企业结果期仍然较短，官方履约企业名单、上市公司实体与绿色专利数据的可验证连接也是识别中的关键难点。' },
        { kind: 'paragraph', text: 'HypoWeaver-Qwen首先围绕“全国碳排放权交易市场能否促进企业高质量绿色技术创新”检索本地知识库，以12个全文片段、7篇不同文献形成研究空白、候选假设和机制链。执行就绪编译器随后审查公开数据许可、时间范围、企业键、处理字段和结果字段，发现现有许可面板止于2021年，无法提供全国市场启动后的充分结果期。系统因此保持理论链不变，将本轮估计对象收敛为区域碳政策公开复现，并把全国市场命题保留为后续确认性扩展。' },
        { kind: 'paragraph', text: '本文的贡献体现在三个方面。第一，从创新数量进一步区分发明专利和实用新型专利，检验碳政策暴露是否更多对应高质量技术创新。第二，在企业和年份固定效应之外，联合使用事件研究、样本路径诊断和企业轨迹置换，检查结果是否由单一设定驱动。第三，把问题生成、数据范围调整、冻结协议、统计执行、独立复算和结论准入置于同一可审计链路，使每项文字主张都能回溯到数据与模型。' },
      ],
    },
    {
      id: 'background',
      title: '二、制度逻辑与文献述评',
      blocks: [
        { kind: 'subheading', text: '（一）碳市场的创新激励' },
        { kind: 'paragraph', text: '碳市场使排放权成为具有机会成本的生产要素。企业在购买配额、调整产出和技术减排之间选择，当政策约束具有持续性时，能够降低单位产出排放的绿色发明具有更高的跨期净收益。碳价与履约信息还可能进入银行、投资者和供应链伙伴的风险评价，改变高碳项目与低碳研发的融资条件。' },
        { kind: 'subheading', text: '（二）高质量绿色创新与融资条件' },
        { kind: 'paragraph', text: '绿色专利总量既包含发明专利，也包含技术门槛相对较低的实用新型。若碳市场主要诱发策略性申请，则不同专利类型可能同步增加；若政策促使企业形成具有较强知识含量和长期减排潜力的技术积累，绿色发明的响应应更稳定。与此同时，绿色研发的长周期和信息不对称意味着融资可得性会影响企业把政策压力转化为创新投入的能力。' },
        { kind: 'subheading', text: '（三）研究边界' },
        { kind: 'paragraph', text: '本研究使用公开数据发布者提供的企业—年份政策暴露编码，不将其改写为全国碳市场官方履约名单。当前估计回答的是公开复现样本中区域碳政策暴露与企业绿色创新的关系；全国市场效应需要在取得2022年以后结果与官方履约企业实体绑定后另行识别。' },
      ],
    },
    {
      id: 'theory',
      title: '三、理论分析与研究假设',
      blocks: [
        { kind: 'paragraph', text: '碳政策暴露通过两条互补路径影响企业创新。第一，配额约束与价格信号提高高碳生产的机会成本，改善节能减排技术的相对回报。第二，碳信息的可见度和金融机构的环境风险定价可能改变企业融资条件，进而影响长期研发。行业竞争则可能强化企业模仿和技术追赶，也可能压缩利润空间，因此其调节方向需要经验检验。' },
        { kind: 'figure', id: 'mechanism' },
        { kind: 'hypothesis', label: '研究假设 H1', text: '在其他条件相同的情况下，碳政策暴露与企业高质量绿色技术创新增加相一致。' },
        { kind: 'hypothesis', label: '研究假设 H2', text: '碳政策暴露伴随融资约束代理值下降，该变化与企业开展长期绿色研发的机制方向一致。' },
        { kind: 'hypothesis', label: '研究假设 H3', text: '碳政策暴露与高质量绿色创新之间的关系随行业竞争程度而变化。' },
      ],
    },
    {
      id: 'design',
      title: '四、研究设计',
      blocks: [
        { kind: 'subheading', text: '（一）数据与样本' },
        { kind: 'paragraph', text: '数据来自Wei（2025）在Mendeley Data发布的Industry Peer Effect of Corporate Green Innovation数据集，许可为CC BY 4.0。原文件包含2010—2021年1,184家企业的14,208条观测和1,441个字段。系统只抽取企业与年份键、政策暴露、六类绿色专利、四类融资约束、企业财务、行业HHI和产权编码等21个字段，并保存源文件、分析抽取与字段清单的SHA-256。' },
        { kind: 'paragraph', text: '主样本要求企业在2010—2021年12期齐全，且主结果、政策暴露和三项控制变量无缺失。最终保留1,183家企业、14,196条观测。源政策字段中75家企业存在至少一次1→0回退；主模型按当期暴露保留，事件研究和单调路径稳健性排除这些企业。' },
        { kind: 'table', id: 'variables' },
        { kind: 'table', id: 'descriptive' },
        { kind: 'subheading', text: '（二）基准模型' },
        { kind: 'equation', label: '（1）', formula: 'GIᵢₜ = αᵢ + λₜ + βExposureᵢₜ + γ′Xᵢₜ + εᵢₜ', note: 'GI为ln（1＋绿色发明专利申请量）；X包括企业规模、资产负债率和资产收益率；αᵢ与λₜ分别为企业和年份固定效应，标准误按企业聚类。' },
        { kind: 'paragraph', text: '主参数β描述同一企业内部政策暴露变化与高质量绿色创新变化之间的条件关联。协议在读取结果前冻结，不因估计显著性删除零专利企业、调整样本或改变控制变量。' },
        { kind: 'subheading', text: '（三）事件研究与置换检验' },
        { kind: 'equation', label: '（2）', formula: 'GIᵢₜ = αᵢ + λₜ + Σₖ≠₋₁ βₖEventTimeᵢₜᵏ + γ′Xᵢₜ + εᵢₜ', note: '事件时间按首次政策暴露年份构造，−1期为基期；远端提前期与滞后期分别合并。传统错位处理TWFE事件系数只作为趋势和动态模式诊断。' },
        { kind: 'paragraph', text: '企业轨迹置换以企业为单位随机交换完整12年政策暴露序列，既保持每条路径的年度结构，也保持各年暴露比例。系统在固定随机种子下执行499次估计，并把真实无控制系数与置换零分布比较。' },
      ],
    },
    {
      id: 'results',
      title: '五、实证结果',
      blocks: [
        { kind: 'subheading', text: '（一）基准结果' },
        { kind: 'table', id: 'baseline' },
        { kind: 'paragraph', text: '表3显示，不含控制变量时政策暴露系数为0.0729；加入企业规模、资产负债率和资产收益率后，主规格系数为0.0717，企业聚类标准误为0.0204，p值为0.00043。该系数约对应“1＋绿色发明申请量”指标提高7.4%。排除存在暴露回退的企业或加入行业集中度后，估计值保持为正且在1%水平上显著。' },
        { kind: 'subheading', text: '（二）动态效应' },
        { kind: 'figure', id: 'event-study' },
        { kind: 'paragraph', text: '政策暴露前≤−4、−3和−2期的系数分别为−0.0429、−0.0183和−0.0259，均未达到统计显著，联合检验p=0.494。政策暴露当期系数为0.0314，暴露后第1—3期依次升至0.0661、0.0873和0.1005，≥4期为0.0986，呈现逐步释放并趋于稳定的动态形态。' },
        { kind: 'subheading', text: '（三）稳健性与创新质量' },
        { kind: 'table', id: 'robustness' },
        { kind: 'figure', id: 'robustness' },
        { kind: 'paragraph', text: '剔除2021年、仅保留单调暴露路径、改用独立绿色发明和全部绿色专利后，政策暴露系数均为正。实用新型专利的系数较小且不显著，说明主要结果更集中在发明专利这一高质量创新维度，而非所有专利类型的机械同步扩张。' },
        { kind: 'paragraph', text: '499次企业轨迹置换的零分布均值为0.00026，95%分位区间为[−0.0397，0.0428]。仅1次置换系数绝对值不小于真实无控制系数0.0729，对应双侧p=0.004。' },
        { kind: 'subheading', text: '（四）机制与异质性' },
        { kind: 'paragraph', text: '以SA指数绝对值衡量融资约束时，政策暴露系数为−0.0079（p=0.0199），与融资约束下降的机制方向一致。该结果用于支持理论链的一致性，不把单一中介回归解释为完整因果机制。' },
        { kind: 'paragraph', text: '政策暴露与高竞争行业的交互项为−0.0485（p=0.1169），未支持竞争越强、创新促进效应越大的预设判断。产权字段虽有1—5编码，但公开文件没有可靠值标签，系统未猜测编码含义，也未生成产权异质性结果。' },
        { kind: 'subheading', text: '（五）独立复算' },
        { kind: 'paragraph', text: '独立复算器不导入主执行脚本，使用交替投影消去企业与年份固定效应，以NumPy直接求解OLS并重构企业聚类协方差。8组主与稳健性模型、8个事件期系数、提前项联合检验、机制和异质性模型、499个置换系数以及全部输出哈希共16类核验全部通过，核心系数最大绝对差小于5×10⁻¹¹。' },
      ],
    },
    {
      id: 'conclusion',
      title: '六、结论与研究展望',
      blocks: [
        { kind: 'paragraph', text: '本文使用公开上市公司面板复现碳政策暴露与企业绿色创新之间的关系。基准估计、核心稳健性、事件研究和企业轨迹置换共同表明，碳政策暴露与绿色发明专利申请呈稳定正向关系；融资约束代理变量的变化与理论机制方向一致，竞争异质性则未得到数据支持。' },
        { kind: 'paragraph', text: '研究结果具有两方面启示。其一，碳市场的长期绩效不应只用交易量或履约率评价，还应关注企业能否把环境约束转化为具有知识积累价值的绿色发明。其二，金融资源配置可能影响这一转化过程，碳市场建设与绿色融资、信息披露和技术服务具有潜在互补性。' },
        { kind: 'paragraph', text: '下一阶段将使用2022年以后的企业结果、官方全国碳市场履约企业名单和统一实体键，区分地方试点与全国市场的增量效应，并采用更适合分期处理和异质处理效应的估计方法。当前公开复现已经给出方向清晰、可独立复算的经验结果，也为全国市场的确认性研究提供了经过数据门检验的设计基础。' },
      ],
    },
  ] satisfies ShowcasePaperSection[],
  references: [
    'Wei, D.（2025）：Industry Peer Effect of Corporate Green Innovation，Mendeley Data，V1，DOI: 10.17632/rrfwny7byp.1。',
    'Porter, M. E. and C. van der Linde（1995）：“Toward a New Conception of the Environment-Competitiveness Relationship”，Journal of Economic Perspectives，9（4），97—118。',
    'Popp, D.（2002）：“Induced Innovation and Energy Prices”，American Economic Review，92（1），160—180。',
    'Calel, R. and A. Dechezleprêtre（2016）：“Environmental Policy and Directed Technological Change: Evidence from the European Carbon Market”，Review of Economics and Statistics，98（1），173—191。',
    'Hadlock, C. J. and J. R. Pierce（2010）：“New Evidence on Measuring Financial Constraints: Moving Beyond the KZ Index”，Review of Financial Studies，23（5），1909—1940。',
    'Goodman-Bacon, A.（2021）：“Difference-in-Differences with Variation in Treatment Timing”，Journal of Econometrics，225（2），254—277。',
    'Sun, L. and S. Abraham（2021）：“Estimating Dynamic Treatment Effects in Event Studies with Heterogeneous Treatment Effects”，Journal of Econometrics，225（2），175—199。',
  ],
  dataStatement: '数据与复现声明：本文使用Mendeley Data公开发布且采用CC BY 4.0许可的数据。主数据、最小分析抽取、两轮协议、统计结果、图表规格和独立复算均保存SHA-256。当前结论定位为原数据政策暴露编码下的区域碳政策公开复现；全国碳市场效应将在补齐2022年以后结果与官方履约企业名单后单独检验。',
} as const
