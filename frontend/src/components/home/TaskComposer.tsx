/**
 * 新研究入口（与分步向导统一设计语言）：
 * 时段问候 → 六步向导路径预览 → 分类启发模板 → 底部研究方向输入台。
 */
import {
  ArrowRight,
  BookOpenText,
  ChartNoAxesCombined,
  ClipboardList,
  Database,
  FileText,
  FlaskConical,
  Lightbulb,
  RotateCcw,
  Settings2,
  Sparkles,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useMemo, useState } from 'react'
import { timeGreeting } from '../../lib/displayTitle'

interface TemplateCard {
  id: string
  title: string
  description: string
  prompt: string
  icon: LucideIcon
}

interface TemplateCategory {
  id: string
  label: string
  cards: TemplateCard[]
}

interface JourneyStage {
  title: string
  description: string
  owner: string
  tone: 'auto' | 'confirm' | 'collaborate'
  icon: LucideIcon
}

const RESEARCH_JOURNEY: JourneyStage[] = [
  {
    title: '研究方向',
    description: '问题 · 变量 · 范围',
    owner: '你来明确',
    tone: 'confirm',
    icon: Lightbulb,
  },
  {
    title: '文献',
    description: '多源检索 · 勾选证据',
    owner: '检索与勾选',
    tone: 'collaborate',
    icon: BookOpenText,
  },
  {
    title: '候选假设',
    description: '缺口 · 机制 · 引用校验',
    owner: '生成与选择',
    tone: 'collaborate',
    icon: Sparkles,
  },
  {
    title: '研究方案',
    description: '识别策略 · 锁定规则',
    owner: '起草与确认',
    tone: 'confirm',
    icon: ClipboardList,
  },
  {
    title: '数据与检验',
    description: '变量绑定 · 回归与复算',
    owner: '执行与评估',
    tone: 'auto',
    icon: Database,
  },
  {
    title: '研究提案',
    description: '数字注入 · 结论边界',
    owner: '审阅与导出',
    tone: 'collaborate',
    icon: FileText,
  },
]

const TEMPLATE_CATEGORIES: TemplateCategory[] = [
  {
    id: 'literature',
    label: '文献与空白',
    cards: [
      {
        id: 'lit_progress',
        title: '看清一个领域的研究进展',
        description: '围绕主题梳理关键文献、方法演进和主要结论，形成可追溯的研究地图。',
        prompt:
          '梳理绿色金融政策与企业绿色技术创新领域的研究进展，识别主要理论、方法演进和关键证据。',
        icon: BookOpenText,
      },
      {
        id: 'lit_gap',
        title: '从现有证据中定位研究空白',
        description: '对比已知结论与尚未回答的问题，给出有证据边界的空白清单。',
        prompt:
          '基于近五年文献与政策证据，识别绿色金融政策影响企业创新的研究空白，并说明每个空白的证据依据。',
        icon: Lightbulb,
      },
      {
        id: 'lit_dispute',
        title: '比较一组相互矛盾的结论',
        description: '核对样本、口径和识别策略，解释为什么不同研究会得到不同结果。',
        prompt:
          '比较绿色金融政策促进与抑制企业创新的相互矛盾证据，重点核对样本、变量口径和识别策略。',
        icon: ChartNoAxesCombined,
      },
      {
        id: 'lit_graph',
        title: '碳市场同群暴露与企业绿色创新',
        description: '围绕行业同群暴露与企业绿色发明专利申请，梳理文献依据并检验条件关联。',
        prompt: '同行业出现碳交易控排企业后，行业内上市公司的绿色发明专利申请是否发生变化？',
        icon: Sparkles,
      },
    ],
  },
  {
    id: 'hypothesis',
    label: '研究假设',
    cards: [
      {
        id: 'hyp_generate',
        title: '从理论与证据提出可检验假设',
        description: '把研究空白转成变量明确、方向清楚且能够被证伪的假设。',
        prompt: '结合融资约束与创新补偿理论，为绿色金融政策对企业绿色创新的影响提出可检验假设。',
        icon: Lightbulb,
      },
      {
        id: 'hyp_mechanism',
        title: '拆解一条作用机制',
        description: '明确中介变量、竞争机制和可观测证据，避免只写叙事链条。',
        prompt: '拆解绿色金融政策通过融资约束与研发投入影响绿色专利质量的作用机制。',
        icon: Sparkles,
      },
      {
        id: 'hyp_boundary',
        title: '找出假设成立的边界条件',
        description: '比较行业、所有制与地区差异，形成异质性和调节效应假设。',
        prompt: '分析绿色金融政策创新效应在高碳行业、新兴绿色产业和不同所有制企业中的边界条件。',
        icon: ChartNoAxesCombined,
      },
      {
        id: 'hyp_falsify',
        title: '为假设设计证伪路径',
        description: '列出会推翻假设的观察结果、替代解释和必要稳健性检验。',
        prompt: '为“绿色金融政策提升企业绿色专利质量”设计可证伪标准与替代解释排除方案。',
        icon: FlaskConical,
      },
    ],
  },
  {
    id: 'design',
    label: '研究设计',
    cards: [
      {
        id: 'design_full',
        title: '把研究问题变成可执行方案',
        description: '定义样本、变量、估计量、识别策略和诊断，输出可锁定的研究方案。',
        prompt: '为绿色金融改革创新试验区政策与企业绿色创新设计一套可执行的实证研究方案。',
        icon: FlaskConical,
      },
      {
        id: 'design_variable',
        title: '完善变量与测量方案',
        description: '比较代理变量、数据来源和测量误差，给出变量角色与派生口径。',
        prompt: '完善绿色金融政策、绿色研发强度和绿色专利质量的变量定义、数据来源与替代测量。',
        icon: ChartNoAxesCombined,
      },
      {
        id: 'design_sample',
        title: '确定样本边界与数据结构',
        description: '明确分析单位、时间窗口、纳入排除标准以及可能的选择偏差。',
        prompt: '为企业—地区—年份面板确定样本边界、时间窗口、纳入排除规则和缺失值策略。',
        icon: BookOpenText,
      },
      {
        id: 'design_diagnostics',
        title: '列出必须通过的诊断检验',
        description: '提前约定平行趋势、置换检验、稳健性和独立复算，防止事后挑结果。',
        prompt: '为绿色金融政策的双重差分研究设计必须通过的诊断、置换检验与稳健性方案。',
        icon: Sparkles,
      },
    ],
  },
  {
    id: 'causal',
    label: '数据与因果边界',
    cards: [
      {
        id: 'causal_strategy',
        title: '比较可行的识别策略',
        description: '针对同一问题比较政策 DID、面板关联与机制边界方案的假设与风险。',
        prompt: '比较识别绿色金融政策效应的政策 DID、面板关联与机制检验方案，并明确适用条件。',
        icon: ChartNoAxesCombined,
      },
      {
        id: 'causal_audit',
        title: '审计现有数据能否支撑结论',
        description: '检查处理组、时间、变量变异和缺失，明确结论强度上限。',
        prompt: '审计现有企业—行业—年份面板是否足以识别碳市场暴露对绿色创新的效应。',
        icon: FlaskConical,
      },
      {
        id: 'causal_robust',
        title: '规划稳健性与结论降级规则',
        description: '把关键识别威胁转成可执行检查，并约定未通过时的结论降级规则。',
        prompt: '为绿色金融政策研究规划稳健性、置换检验与结论强度降级规则。',
        icon: Sparkles,
      },
      {
        id: 'causal_result',
        title: '解释模型结果而不过度宣称',
        description: '区分条件关联与因果识别，按决策规则生成不越界的学术表述。',
        prompt: '围绕行业层面政策暴露与企业绿色创新，设计审慎的实证检验与结论边界表述。',
        icon: FileText,
      },
    ],
  },
]

export function TaskComposer({
  busy,
  llmConfigured,
  onCreateProject,
  onOpenSettings,
}: {
  busy?: boolean
  llmConfigured?: boolean
  onCreateProject: (prompt: string) => void
  onOpenSettings: () => void
}) {
  const [category, setCategory] = useState(TEMPLATE_CATEGORIES[0].id)
  const [prompt, setPrompt] = useState('')
  const greeting = useMemo(() => `${timeGreeting()}，研究者`, [])
  const cards = TEMPLATE_CATEGORIES.find((item) => item.id === category)?.cards ?? []

  function pickTemplate(card: TemplateCard) {
    setPrompt(card.prompt)
  }

  function submit() {
    const text = prompt.trim()
    if (!text || busy) return
    onCreateProject(text)
  }

  return (
    <div className="composer">
      <div className="composer__scroll">
        <div className="composer__center">
          <div className="composer__hero">
            <h1 className="composer__greeting" aria-label={greeting}>
              {greeting}
            </h1>
            <p className="composer__lead">
              从一个研究问题出发，沿「研究方向 → 文献 → 候选假设 → 研究方案 → 数据与检验 →
              研究提案」六步向导推进可核查的实证研究。
            </p>
          </div>

          <section className="composer__journey" aria-labelledby="composer-journey-title">
            <header>
              <div>
                <span className="composer__journey-kicker">
                  <ChartNoAxesCombined size={13} aria-hidden="true" />
                  六步分步向导
                </span>
                <strong id="composer-journey-title">
                  提交研究想法后，将进入同一套六步向导逐步核查与确认
                </strong>
              </div>
              <small>
                <i className="is-auto" />
                系统执行 <i className="is-confirm" />
                你来确认
              </small>
            </header>
            <ol>
              {RESEARCH_JOURNEY.map((stage, index) => {
                const Icon = stage.icon
                return (
                  <li key={stage.title}>
                    <div className="composer__journey-top">
                      <span className="composer__journey-num">{index + 1}</span>
                      <span
                        className={`composer__journey-icon is-${stage.tone}`}
                        aria-hidden="true"
                      >
                        <Icon size={14} />
                      </span>
                    </div>
                    <span className="composer__journey-copy">
                      <strong>{stage.title}</strong>
                      <small>{stage.description}</small>
                    </span>
                    <em className={`is-${stage.tone}`}>{stage.owner}</em>
                    {index < RESEARCH_JOURNEY.length - 1 && (
                      <ArrowRight
                        className="composer__journey-arrow"
                        size={12}
                        aria-hidden="true"
                      />
                    )}
                  </li>
                )
              })}
            </ol>
          </section>

          <div className="composer__templates-hd">
            <span className="composer__templates-label">启发模板 · 点击填入下方方向输入框</span>
            <div className="composer__chips" role="tablist" aria-label="任务模板分类">
              {TEMPLATE_CATEGORIES.map((item) => (
                <button
                  type="button"
                  role="tab"
                  key={item.id}
                  aria-selected={category === item.id}
                  className={`composer__chip ${category === item.id ? 'is-active' : ''}`}
                  onClick={() => setCategory(item.id)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          <div className="composer__cards" key={category}>
            {cards.map((card) => {
              const selected = prompt.trim() === card.prompt.trim()
              return (
                <button
                  type="button"
                  className={`composer__card ${selected ? 'is-selected' : ''}`}
                  key={card.id}
                  onClick={() => pickTemplate(card)}
                >
                  <span className="composer__card-icon" aria-hidden="true">
                    <card.icon size={17} />
                  </span>
                  <span className="composer__card-copy">
                    <h3>{card.title}</h3>
                    <p>{card.description}</p>
                  </span>
                  <ArrowRight className="composer__card-arrow" size={16} aria-hidden="true" />
                </button>
              )
            })}
          </div>
        </div>
      </div>

      <div className="composer__dock">
        <form
          className="composer__box"
          onSubmit={(event) => {
            event.preventDefault()
            submit()
          }}
        >
          <textarea
            value={prompt}
            rows={2}
            aria-label="研究方向或一句话想法"
            placeholder="用一句话描述你想研究的问题（例如：碳交易试点是否提升了行业内企业绿色发明专利？），或点选上方模板…"
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault()
                submit()
              }
            }}
          />
          <div className="composer__box-row">
            <div className="composer__box-left">
              <button type="button" className="composer__tool" onClick={() => onOpenSettings()}>
                <span
                  className={`composer__status-dot ${llmConfigured ? 'is-ready' : ''}`}
                  aria-hidden="true"
                />
                <Settings2 size={13} aria-hidden="true" />
                {llmConfigured ? '千问模型已就绪' : '配置千问模型'}
              </button>
              <button
                type="button"
                className="composer__tool"
                disabled={busy}
                onClick={() => onCreateProject('')}
              >
                直接填空白方向卡 →
              </button>
              {prompt.trim() && (
                <button
                  type="button"
                  className="composer__tool"
                  onClick={() => setPrompt('')}
                  title="清空输入"
                >
                  <RotateCcw size={13} aria-hidden="true" />
                  清空
                </button>
              )}
            </div>
            <button
              type="submit"
              className="composer__send"
              disabled={busy || !prompt.trim()}
              aria-label="创建研究项目并进入第一步"
            >
              <span>{busy ? '正在创建…' : '进入向导'}</span>
              <ArrowRight size={15} aria-hidden="true" />
            </button>
          </div>
        </form>
        <p className="composer__hint">
          创建后将自动带入「1. 研究方向」卡片，每一步自动保存草稿，确认后依次解锁下一阶段。
        </p>
      </div>
    </div>
  )
}
