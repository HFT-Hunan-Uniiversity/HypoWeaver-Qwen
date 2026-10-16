/**
 * Ported from repo/frontend TaskComposer — visual structure + class names preserved.
 * Submit / examples → onCreateProject (real v2 project).
 */
import {
  ArrowRight,
  ArrowUp,
  BookOpenText,
  ChartNoAxesCombined,
  ChevronDown,
  ClipboardList,
  Database,
  FileText,
  FlaskConical,
  Lightbulb,
  Network,
  Paperclip,
  Settings2,
  SlidersHorizontal,
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
    title: '多源检索',
    description: '文献 · 政策 · 数据',
    owner: '系统自动',
    tone: 'auto',
    icon: Database,
  },
  {
    title: '趋势与图谱',
    description: '主题演进 · 证据关系',
    owner: '系统自动',
    tone: 'auto',
    icon: Network,
  },
  {
    title: '研究空白 H0',
    description: '证据边界 · 空白确认',
    owner: '你来确认',
    tone: 'confirm',
    icon: Lightbulb,
  },
  {
    title: '候选假设',
    description: '机制 · 变量 · 证伪',
    owner: '共同选择',
    tone: 'collaborate',
    icon: Sparkles,
  },
  {
    title: '科学十项',
    description: '方案草案 · 逐项审查',
    owner: '你来确认',
    tone: 'confirm',
    icon: ClipboardList,
  },
  {
    title: '正式研究',
    description: '六步向导 · 结果交付',
    owner: '共同推进',
    tone: 'collaborate',
    icon: FlaskConical,
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
        title: '建立主题证据图谱',
        description: '把文献、政策、变量、方法与结论连接起来，便于后续提出假设。',
        prompt: '建立绿色金融政策、融资约束、研发投入与绿色专利质量之间的证据图谱。',
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
        description: '定义样本、变量、估计量、识别策略和诊断，输出可冻结的研究合同。',
        prompt: '为绿色金融改革创新试验区政策与企业绿色创新设计一套可执行的实证研究方案。',
        icon: FlaskConical,
      },
      {
        id: 'design_variable',
        title: '完善变量与测量方案',
        description: '比较代理变量、数据来源和测量误差，给出变量字典与替代口径。',
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
        description: '提前约定平行趋势、安慰剂、稳健性和敏感性分析，防止事后选择。',
        prompt: '为绿色金融政策的双重差分研究设计必须通过的诊断、安慰剂与敏感性检验。',
        icon: Sparkles,
      },
    ],
  },
  {
    id: 'causal',
    label: '数据与因果',
    cards: [
      {
        id: 'causal_strategy',
        title: '比较可行的因果识别策略',
        description: '针对同一问题比较 DID、事件研究、工具变量等方案的假设与风险。',
        prompt: '比较识别绿色金融政策因果效应的 DID、事件研究与工具变量方案，并给出推荐条件。',
        icon: ChartNoAxesCombined,
      },
      {
        id: 'causal_audit',
        title: '审计现有数据能否支撑结论',
        description: '检查处理组、时间、变量变异和缺失，明确能做什么、不能做什么。',
        prompt: '审计现有企业—地区—年份面板是否足以识别绿色金融政策对绿色创新的因果效应。',
        icon: FlaskConical,
      },
      {
        id: 'causal_robust',
        title: '规划稳健性与敏感性分析',
        description: '把关键识别威胁转成可执行检查，并约定失败后的结论降级规则。',
        prompt: '为绿色金融政策研究规划稳健性、敏感性与结论降级规则。',
        icon: Sparkles,
      },
      {
        id: 'causal_result',
        title: '解释模型结果而不过度推断',
        description: '区分统计事实、识别假设和可授权结论，生成证据支持的表述。',
        prompt: '审核一组绿色金融政策回归结果，区分统计相关、因果证据和不能发布的主张。',
        icon: FileText,
      },
    ],
  },
  {
    id: 'writing',
    label: '论文写作',
    cards: [
      {
        id: 'write_outline',
        title: '从研究方案生成论文结构',
        description: '按问题、理论、设计、结果与限制组织章节，并绑定每节所需证据。',
        prompt: '根据绿色金融政策与企业创新的研究方案生成论文结构和各章节证据需求。',
        icon: FileText,
      },
      {
        id: 'write_methods',
        title: '写清楚可复现的方法部分',
        description: '把样本、变量、模型、诊断和版本信息写成可复现的方法说明。',
        prompt: '为企业—地区—年份面板研究撰写可复现的方法与识别策略部分。',
        icon: FlaskConical,
      },
      {
        id: 'write_results',
        title: '把证据转成审慎结论',
        description: '仅使用已通过审核的主张，主动说明边界、失败检验和替代解释。',
        prompt: '把已审核的绿色金融政策实证结果整理成审慎的结果与讨论部分。',
        icon: ChartNoAxesCombined,
      },
      {
        id: 'write_review',
        title: '检查全文证据与引文一致性',
        description: '逐句核对结论来源、引用和图表，标出夸大或无法复现的内容。',
        prompt: '审查论文中每条结论的证据、引用与图表来源，并列出需要降级或重写的句子。',
        icon: BookOpenText,
      },
    ],
  },
]

export function TaskComposer({
  busy,
  onCreateProject,
  onOpenSettings,
}: {
  busy?: boolean
  onCreateProject: (prompt: string) => void
  onOpenSettings: () => void
}) {
  const [category, setCategory] = useState(TEMPLATE_CATEGORIES[0].id)
  const [prompt, setPrompt] = useState('')
  const [moreOpen, setMoreOpen] = useState(false)
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
          <h1 className="composer__greeting" aria-label={greeting}>
            {greeting.split('').map((char, index) => (
              <span key={`${char}-${index}`} style={{ animationDelay: `${index * 45}ms` }}>
                {char === ' ' ? '\u00a0' : char}
              </span>
            ))}
          </h1>
          <p className="composer__lead">
            从文献与证据出发，与你一起识别研究空白、提出假设并完成可审查的研究。
          </p>

          <section className="composer__journey" aria-labelledby="composer-journey-title">
            <header>
              <div>
                <span className="composer__journey-kicker">
                  <ChartNoAxesCombined size={14} aria-hidden="true" />
                  研究流程
                </span>
                <strong id="composer-journey-title">提交主题后，系统会沿这条路径推进</strong>
              </div>
              <small>
                <i className="is-auto" />
                系统自动 <i className="is-confirm" />
                需要确认
              </small>
            </header>
            <ol>
              {RESEARCH_JOURNEY.map((stage, index) => {
                const Icon = stage.icon
                return (
                  <li key={stage.title}>
                    <span className={`composer__journey-icon is-${stage.tone}`} aria-hidden="true">
                      <Icon size={16} />
                    </span>
                    <span className="composer__journey-copy">
                      <b>{String(index + 1).padStart(2, '0')}</b>
                      <strong>{stage.title}</strong>
                      <small>{stage.description}</small>
                    </span>
                    <em className={`is-${stage.tone}`}>{stage.owner}</em>
                    {index < RESEARCH_JOURNEY.length - 1 && (
                      <ArrowRight
                        className="composer__journey-arrow"
                        size={13}
                        aria-hidden="true"
                      />
                    )}
                  </li>
                )
              })}
            </ol>
          </section>

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

          <div className="composer__cards" key={category}>
            {cards.map((card) => (
              <button
                type="button"
                className="composer__card"
                key={card.id}
                onClick={() => pickTemplate(card)}
              >
                <span className="composer__card-icon" aria-hidden="true">
                  <card.icon size={18} />
                </span>
                <span className="composer__card-copy">
                  <h3>{card.title}</h3>
                  <p>{card.description}</p>
                </span>
                <ArrowRight className="composer__card-arrow" size={17} aria-hidden="true" />
              </button>
            ))}
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
            placeholder="描述你的研究任务，或从上方模板开始…"
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
              <div className="composer__more">
                <button
                  type="button"
                  className="composer__tool"
                  aria-haspopup="menu"
                  aria-expanded={moreOpen}
                  onClick={() => setMoreOpen((c) => !c)}
                >
                  <SlidersHorizontal size={14} />
                  更多选项
                </button>
                {moreOpen && (
                  <div className="composer__menu" role="menu">
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setMoreOpen(false)
                        onOpenSettings()
                      }}
                    >
                      <Settings2 size={13} />
                      模型与执行器配置
                    </button>
                  </div>
                )}
              </div>
              <button type="button" className="composer__tool" onClick={() => onOpenSettings()}>
                <Paperclip size={14} />
                导入资料
              </button>
              <label className="composer__mode">
                <select defaultValue="rigorous" aria-label="研究模式">
                  <option value="rigorous">研究模式 · 严谨</option>
                  <option value="reproduce">研究模式 · 复现</option>
                </select>
                <ChevronDown size={13} aria-hidden="true" />
              </label>
            </div>
            <button
              type="submit"
              className="composer__send"
              disabled={busy || !prompt.trim()}
              aria-label="创建研究项目"
            >
              <ArrowUp size={16} />
            </button>
          </div>
        </form>
        <p className="composer__hint">发送后将创建真实项目并进入研究方向；每一步可确认、可回溯。</p>
      </div>
    </div>
  )
}
