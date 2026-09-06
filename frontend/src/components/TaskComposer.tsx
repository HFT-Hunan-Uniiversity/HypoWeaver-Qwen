/**
 * TaskComposer：ClawsGO /chat 形态的「新研究」页。
 * 问候语（逐字 blur 入场）→ 研究旅程 → 分类 chips → 模板卡片 → 底部居中输入框。
 * 提交文本 → 创建前端演示项目；导入案例文件夹 → 走真实链路（App 处理）。
 */
import { ArrowRight, ArrowUp, BookOpenText, ChartNoAxesCombined, ChevronDown, ClipboardList, Database, FileText, FlaskConical, FolderUp, Lightbulb, Link2, Network, Paperclip, Settings2, SlidersHorizontal, Sparkles } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import type { CaseImportReport, Group1VerifiedBundleStatus, RuntimeConfigStatus } from '../runtime/types'
import type { MockMode } from '../data/mockPipeline'

type LaunchTarget = 'hypoweaver' | 'agent-laboratory'

interface TemplateCard {
  id: string
  title: string
  description: string
  prompt: string
  mode: MockMode
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

/** 入口页只展示用户能理解的完整研究旅程，不把后台 Agent 名称暴露给用户。 */
const RESEARCH_JOURNEY: JourneyStage[] = [
  { title: '多源检索', description: '文献 · 政策 · 数据', owner: '系统自动', tone: 'auto', icon: Database },
  { title: '趋势与图谱', description: '主题演进 · 证据关系', owner: '系统自动', tone: 'auto', icon: Network },
  { title: '研究空白 H0', description: '证据边界 · 空白确认', owner: '你来确认', tone: 'confirm', icon: Lightbulb },
  { title: '候选假设', description: '机制 · 变量 · 证伪', owner: '共同选择', tone: 'collaborate', icon: Sparkles },
  { title: '科学十项', description: '方案草案 · 逐项审查', owner: '你来确认', tone: 'confirm', icon: ClipboardList },
  { title: '正式研究', description: 'H1–H4 · 结果交付', owner: '共同推进', tone: 'collaborate', icon: FlaskConical },
]

/** 首页任务建议：按科研意图组织，而不是让用户先理解系统流水线。 */
const TEMPLATE_CATEGORIES: TemplateCategory[] = [
  {
    id: 'literature', label: '文献与空白',
    cards: [
      { id: 'lit_progress', title: '看清一个领域的研究进展', description: '围绕主题梳理关键文献、方法演进和主要结论，形成可追溯的研究地图。', prompt: '梳理绿色金融政策与企业绿色技术创新领域的研究进展，识别主要理论、方法演进和关键证据。', mode: 'discovery_blind', icon: BookOpenText },
      { id: 'lit_gap', title: '从现有证据中定位研究空白', description: '对比已知结论与尚未回答的问题，给出有证据边界的空白清单。', prompt: '基于近五年文献与政策证据，识别绿色金融政策影响企业创新的研究空白，并说明每个空白的证据依据。', mode: 'discovery_blind', icon: Lightbulb },
      { id: 'lit_dispute', title: '比较一组相互矛盾的结论', description: '核对样本、口径和识别策略，解释为什么不同研究会得到不同结果。', prompt: '比较绿色金融政策促进与抑制企业创新的相互矛盾证据，重点核对样本、变量口径和识别策略。', mode: 'reproduction_aligned', icon: ChartNoAxesCombined },
      { id: 'lit_graph', title: '建立主题证据图谱', description: '把文献、政策、变量、方法与结论连接起来，便于后续提出假设。', prompt: '建立绿色金融政策、融资约束、研发投入与绿色专利质量之间的证据图谱。', mode: 'discovery_blind', icon: Sparkles },
    ],
  },
  {
    id: 'hypothesis', label: '研究假设',
    cards: [
      { id: 'hyp_generate', title: '从理论与证据提出可检验假设', description: '把研究空白转成变量明确、方向清楚且能够被证伪的假设。', prompt: '结合融资约束与创新补偿理论，为绿色金融政策对企业绿色创新的影响提出可检验假设。', mode: 'discovery_blind', icon: Lightbulb },
      { id: 'hyp_mechanism', title: '拆解一条作用机制', description: '明确中介变量、竞争机制和可观测证据，避免只写叙事链条。', prompt: '拆解绿色金融政策通过融资约束与研发投入影响绿色专利质量的作用机制。', mode: 'discovery_blind', icon: Sparkles },
      { id: 'hyp_boundary', title: '找出假设成立的边界条件', description: '比较行业、所有制与地区差异，形成异质性和调节效应假设。', prompt: '分析绿色金融政策创新效应在高碳行业、新兴绿色产业和不同所有制企业中的边界条件。', mode: 'reproduction_aligned', icon: ChartNoAxesCombined },
      { id: 'hyp_falsify', title: '为假设设计证伪路径', description: '列出会推翻假设的观察结果、替代解释和必要稳健性检验。', prompt: '为“绿色金融政策提升企业绿色专利质量”设计可证伪标准与替代解释排除方案。', mode: 'reproduction_aligned', icon: FlaskConical },
    ],
  },
  {
    id: 'design', label: '研究设计',
    cards: [
      { id: 'design_full', title: '把研究问题变成可执行方案', description: '定义样本、变量、估计量、识别策略和诊断，输出可冻结的研究合同。', prompt: '为绿色金融改革创新试验区政策与企业绿色创新设计一套可执行的实证研究方案。', mode: 'reproduction_aligned', icon: FlaskConical },
      { id: 'design_variable', title: '完善变量与测量方案', description: '比较代理变量、数据来源和测量误差，给出变量字典与替代口径。', prompt: '完善绿色金融政策、绿色研发强度和绿色专利质量的变量定义、数据来源与替代测量。', mode: 'reproduction_aligned', icon: ChartNoAxesCombined },
      { id: 'design_sample', title: '确定样本边界与数据结构', description: '明确分析单位、时间窗口、纳入排除标准以及可能的选择偏差。', prompt: '为企业—地区—年份面板确定样本边界、时间窗口、纳入排除规则和缺失值策略。', mode: 'reproduction_aligned', icon: BookOpenText },
      { id: 'design_diagnostics', title: '列出必须通过的诊断检验', description: '提前约定平行趋势、安慰剂、稳健性和敏感性分析，防止事后选择。', prompt: '为绿色金融政策的双重差分研究设计必须通过的诊断、安慰剂与敏感性检验。', mode: 'reproduction_aligned', icon: Sparkles },
    ],
  },
  {
    id: 'causal', label: '数据与因果',
    cards: [
      { id: 'causal_strategy', title: '比较可行的因果识别策略', description: '针对同一问题比较 DID、事件研究、工具变量等方案的假设与风险。', prompt: '比较识别绿色金融政策因果效应的 DID、事件研究与工具变量方案，并给出推荐条件。', mode: 'reproduction_aligned', icon: ChartNoAxesCombined },
      { id: 'causal_audit', title: '审计现有数据能否支撑结论', description: '检查处理组、时间、变量变异和缺失，明确能做什么、不能做什么。', prompt: '审计现有企业—地区—年份面板是否足以识别绿色金融政策对绿色创新的因果效应。', mode: 'reproduction_aligned', icon: FlaskConical },
      { id: 'causal_robust', title: '规划稳健性与敏感性分析', description: '把关键识别威胁转成可执行检查，并约定失败后的结论降级规则。', prompt: '为绿色金融政策研究规划稳健性、敏感性与结论降级规则。', mode: 'reproduction_aligned', icon: Sparkles },
      { id: 'causal_result', title: '解释模型结果而不过度推断', description: '区分统计事实、识别假设和可授权结论，生成证据支持的表述。', prompt: '审核一组绿色金融政策回归结果，区分统计相关、因果证据和不能发布的主张。', mode: 'reproduction_aligned', icon: FileText },
    ],
  },
  {
    id: 'writing', label: '论文写作',
    cards: [
      { id: 'write_outline', title: '从研究方案生成论文结构', description: '按问题、理论、设计、结果与限制组织章节，并绑定每节所需证据。', prompt: '根据绿色金融政策与企业创新的研究方案生成论文结构和各章节证据需求。', mode: 'reproduction_aligned', icon: FileText },
      { id: 'write_methods', title: '写清楚可复现的方法部分', description: '把样本、变量、模型、诊断和版本信息写成可复现的方法说明。', prompt: '为企业—地区—年份面板研究撰写可复现的方法与识别策略部分。', mode: 'reproduction_aligned', icon: FlaskConical },
      { id: 'write_results', title: '把证据转成审慎结论', description: '仅使用已通过审核的主张，主动说明边界、失败检验和替代解释。', prompt: '把已审核的绿色金融政策实证结果整理成审慎的结果与讨论部分。', mode: 'reproduction_aligned', icon: ChartNoAxesCombined },
      { id: 'write_review', title: '检查全文证据与引文一致性', description: '逐句核对结论来源、引用和图表，标出夸大或无法复现的内容。', prompt: '审查论文中每条结论的证据、引用与图表来源，并列出需要降级或重写的句子。', mode: 'reproduction_aligned', icon: BookOpenText },
    ],
  },
]

const directoryInputAttributes = { webkitdirectory: '', directory: '' }

interface TaskComposerProps {
  config: RuntimeConfigStatus | null
  group1Bundle: Group1VerifiedBundleStatus | null
  publicDemo: boolean
  importReport: CaseImportReport | null
  busy: boolean
  busyLabel: string
  onImportCaseFolder: (files: File[], target: LaunchTarget) => Promise<void>
  onImportGroup1Handoff: (path: string, mode: 'research' | 'fixture') => Promise<void>
  onStartVerifiedGroup1Bundle: () => Promise<void>
  onOpenAdvanced: () => void
  onOpenSettings: () => void
  onCreateProject: (prompt: string, mode: MockMode) => void
}

export function TaskComposer({ config, group1Bundle, publicDemo, importReport, busy, busyLabel, onImportCaseFolder, onImportGroup1Handoff, onStartVerifiedGroup1Bundle, onOpenAdvanced, onOpenSettings, onCreateProject }: TaskComposerProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [target, setTarget] = useState<LaunchTarget>('hypoweaver')
  const [category, setCategory] = useState(TEMPLATE_CATEGORIES[0].id)
  const [prompt, setPrompt] = useState('')
  const [mode, setMode] = useState<MockMode>('discovery_blind')
  const [moreOpen, setMoreOpen] = useState(false)
  const [manualGroup1Open, setManualGroup1Open] = useState(false)
  const [group1Path, setGroup1Path] = useState('')
  const [group1Mode, setGroup1Mode] = useState<'research' | 'fixture'>('research')
  const qwenReady = Boolean(config?.qwenApiKey.configured)
  const greeting = '你今天想研究什么？'
  const cards = TEMPLATE_CATEGORIES.find((item) => item.id === category)?.cards ?? []
  const group1Ready = group1Bundle?.status === 'ready'
  const group1VerifiedAt = useMemo(() => {
    if (!group1Bundle?.verifiedAt) return ''
    const date = new Date(group1Bundle.verifiedAt)
    return Number.isNaN(date.getTime())
      ? ''
      : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  }, [group1Bundle?.verifiedAt])

  function chooseFile(nextTarget: LaunchTarget) {
    setTarget(nextTarget)
    setMoreOpen(false)
    fileInputRef.current?.click()
  }

  function pickTemplate(card: TemplateCard) {
    setPrompt(card.prompt)
    setMode(card.mode)
  }

  function submit() {
    const text = prompt.trim()
    if (!text || busy) return
    onCreateProject(text, mode)
  }

  return (
    <div className="composer">
      <input
        ref={fileInputRef}
        className="file-input-hidden"
        type="file"
        multiple
        {...directoryInputAttributes}
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => {
          const files = Array.from(event.currentTarget.files ?? [])
          event.currentTarget.value = ''
          if (files.length) void onImportCaseFolder(files, target)
        }}
      />

      <div className="composer__scroll">
        <div className="composer__center">
          <h1 className="composer__greeting" aria-label={greeting}>
            {greeting.split('').map((char, index) => (
              <span key={`${char}-${index}`} style={{ animationDelay: `${index * 45}ms` }}>{char}</span>
            ))}
          </h1>
          <p className="composer__lead">从文献与证据出发，与你一起识别研究空白、提出假设并完成可审查的研究。</p>

          <section className="composer__journey" aria-labelledby="composer-journey-title">
            <header>
              <div>
                <span className="composer__journey-kicker"><ChartNoAxesCombined size={14} aria-hidden="true" />研究流程</span>
                <strong id="composer-journey-title">提交主题后，系统会沿这条路径推进</strong>
              </div>
              <small><i className="is-auto" />系统自动 <i className="is-confirm" />需要确认</small>
            </header>
            <ol>
              {RESEARCH_JOURNEY.map((stage, index) => {
                const Icon = stage.icon
                return (
                  <li key={stage.title}>
                    <span className={`composer__journey-icon is-${stage.tone}`} aria-hidden="true"><Icon size={16} /></span>
                    <span className="composer__journey-copy">
                      <b>{String(index + 1).padStart(2, '0')}</b>
                      <strong>{stage.title}</strong>
                      <small>{stage.description}</small>
                    </span>
                    <em className={`is-${stage.tone}`}>{stage.owner}</em>
                    {index < RESEARCH_JOURNEY.length - 1 && <ArrowRight className="composer__journey-arrow" size={13} aria-hidden="true" />}
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
              <button type="button" className="composer__card" key={card.id} onClick={() => pickTemplate(card)}>
                <span className="composer__card-icon" aria-hidden="true"><card.icon size={18} /></span>
                <span className="composer__card-copy"><h3>{card.title}</h3><p>{card.description}</p></span>
                <ArrowRight className="composer__card-arrow" size={17} aria-hidden="true" />
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="composer__dock">
        {importReport && (
          <p className="composer__import">
            已导入 {importReport.datasetFilename} · {importReport.rowCount.toLocaleString()} 行 × {importReport.columnCount} 列 · 隔离 {importReport.hiddenFileCount} 份隐藏材料
          </p>
        )}
        {!publicDemo && manualGroup1Open && (
          <section className="composer__handoff-panel" aria-label="接入已有研究包">
            <header><Link2 size={16} /><div><strong>从已有研究包继续</strong><small>{group1Ready ? `已验证执行包可用${group1VerifiedAt ? ` · ${group1VerifiedAt}` : ''}` : group1Bundle?.message || '尚未发现可直接启动的执行包'}</small></div></header>
            {group1Ready && (
              <button type="button" className="composer__handoff-primary" disabled={busy} onClick={() => void onStartVerifiedGroup1Bundle()}>
                {busy ? (busyLabel || '正在启动…') : '启动已验证链路'}
              </button>
            )}
            <p>也可以粘贴 Group 1 交接包路径；未绑定执行数据时，系统只完成研究设计并在执行前提示补充。</p>
            <div className="composer__handoff-fields">
              <input
                value={group1Path}
                placeholder="Group 1 pilot 或 I_group1_handoff 路径"
                aria-label="Group 1 冻结交接包路径"
                onChange={(event) => setGroup1Path(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && group1Path.trim() && !busy) {
                    event.preventDefault()
                    void onImportGroup1Handoff(group1Path, group1Mode)
                  }
                }}
              />
              <select value={group1Mode} onChange={(event) => setGroup1Mode(event.target.value as 'research' | 'fixture')} aria-label="Group 1 接入运行模式">
                <option value="research">正式研究</option>
                <option value="fixture">流程演示</option>
              </select>
              <button type="button" disabled={busy || !group1Path.trim()} onClick={() => void onImportGroup1Handoff(group1Path, group1Mode)}>
                {busy ? (busyLabel || '正在接入…') : '接入并进入边界确认'}
              </button>
            </div>
          </section>
        )}
        <form
          className="composer__box"
          onSubmit={(event) => { event.preventDefault(); submit() }}
        >
          <textarea
            value={prompt}
            rows={2}
            placeholder="描述你的研究任务，或导入案例数据包…"
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
                <button type="button" className="composer__tool" aria-haspopup="menu" aria-expanded={moreOpen} onClick={() => setMoreOpen((current) => !current)}>
                  <SlidersHorizontal size={14} />更多选项
                </button>
                {moreOpen && (
                  <div className="composer__menu" role="menu">
                    <button type="button" role="menuitem" onClick={() => { setMoreOpen(false); onOpenAdvanced() }}>手动填写研究输入</button>
                    {!publicDemo && <button type="button" role="menuitem" onClick={() => { setMoreOpen(false); setManualGroup1Open((current) => !current) }}><Link2 size={13} />从已有研究包继续</button>}
                    <button type="button" role="menuitem" disabled={busy || !qwenReady} onClick={() => chooseFile('agent-laboratory')}>{qwenReady ? '导入案例到 Agent Laboratory 基线' : '基线需先配置千问'}</button>
                    <button type="button" role="menuitem" onClick={() => { setMoreOpen(false); onOpenSettings() }}><Settings2 size={13} />模型与执行器配置</button>
                  </div>
                )}
              </div>
              <button type="button" className="composer__tool" disabled={busy} onClick={() => chooseFile('hypoweaver')}>
                {busy ? <FolderUp size={14} /> : <Paperclip size={14} />}{busy ? (busyLabel || '正在处理…') : '导入资料'}
              </button>
              <label className="composer__mode">
                <select value={mode} onChange={(event) => setMode(event.target.value as MockMode)} aria-label="研究模式">
                  <option value="discovery_blind">研究模式 · 严谨</option>
                  <option value="reproduction_aligned">研究模式 · 复现</option>
                </select>
                <ChevronDown size={13} aria-hidden="true" />
              </label>
            </div>
            <button type="submit" className="composer__send" disabled={busy || !prompt.trim()} aria-label="创建研究项目">
              <ArrowUp size={16} />
            </button>
          </div>
        </form>
        <p className="composer__hint">系统会先梳理证据和研究空白；涉及关键边界、研究方案、结论与交付时会请你确认。</p>
      </div>
    </div>
  )
}
