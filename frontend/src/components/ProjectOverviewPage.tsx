import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  ChevronDown,
  Circle,
  Database,
  Download,
  FileCheck2,
  FileText,
  FlaskConical,
  Layers3,
  ListChecks,
  Library,
  Printer,
  Scale,
  ScrollText,
  Target,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import {
  frontendDataSource,
  SHOWCASE_PROJECT_ID,
  type DiscoveryStep,
  type Project,
  type ResourceKind,
} from '../product'
import {
  SHOWCASE_CLAIMS,
  SHOWCASE_PAPER,
  SHOWCASE_PAPER_FIGURES,
  SHOWCASE_PAPER_TABLES,
  SHOWCASE_RESULT_METRICS,
  type ShowcasePaperBlock,
  type ShowcasePaperFigure,
  type ShowcasePaperTable,
} from '../data/showcaseResearch'
import type { DiscoveryStep as DiscoveryRouteStep } from '../runtime/router'
import '../projects.css'

const STATUS_COPY: Record<Project['status'], { label: string; tone: string }> = {
  draft: { label: '草稿', tone: 'is-muted' },
  active: { label: '研究发现中', tone: 'is-active' },
  handoff_ready: { label: '可交接', tone: 'is-ready' },
  archived: { label: '已归档', tone: 'is-muted' },
}

const STEP_ROUTE: Record<DiscoveryStep, DiscoveryRouteStep> = {
  1: 'brief',
  2: 'resources',
  3: 'gaps',
  4: 'ideas',
  5: 'decision',
  6: 'handoff',
}

const DISCOVERY_STAGES: Array<{
  step: DiscoveryStep
  title: string
  short: string
}> = [
  { step: 1, title: '定义研究问题、对象与证据边界', short: '研究简报' },
  { step: 2, title: '检索文献、政策、数据与方法资源', short: '数据中心检索' },
  { step: 3, title: '分析主题趋势、证据关系与研究空白', short: '趋势与空白' },
  { step: 4, title: '生成机制、变量和可证伪假设', short: '候选假设' },
  { step: 5, title: '比较价值、可行性并人工选择', short: '假设选择' },
  { step: 6, title: '检查科学十项生成所需的正式输入', short: '方案输入' },
]

const SCIENTIFIC_TEN = [
  '问题与定位',
  '空白与贡献',
  '核心假设',
  '机制路径',
  '对象与边界',
  '变量与测量',
  '数据与授权',
  '识别与方法',
  '诊断与停止',
  '产物与主张',
] as const

const FORMAL_STAGES = [
  { gate: 'H1', title: '研究边界确认' },
  { gate: 'H2', title: '方法选择与冻结' },
  { gate: 'H3', title: '证据审计与结论授权' },
  { gate: 'H4', title: '终稿审核与封存' },
] as const

const RESOURCE_META: Record<
  ResourceKind,
  { label: string; note: string; icon: LucideIcon }
> = {
  literature: { label: '文献', note: '研究结论与相邻证据', icon: BookOpen },
  policy: { label: '政策', note: '制度背景与政策节点', icon: FileText },
  dataset: { label: '数据', note: '外部数据目录与字段线索', icon: Database },
  method: { label: '方法', note: '识别策略与诊断要求', icon: Scale },
}

type OutcomeTab = 'hypotheses' | 'scientific' | 'results' | 'paper'

const OUTCOME_TABS: Array<{
  id: OutcomeTab
  label: string
  note: string
  icon: LucideIcon
}> = [
  { id: 'hypotheses', label: '研究假设', note: '机制、变量与选择依据', icon: Target },
  { id: 'scientific', label: '科学十项', note: '完整研究方案', icon: ListChecks },
  { id: 'results', label: '关键结果', note: '估计、诊断与主张', icon: FileCheck2 },
  { id: 'paper', label: '论文初稿', note: '完整正文与导出', icon: ScrollText },
]

const VARIABLE_ROLE_LABELS: Record<string, string> = {
  treatment: '处理变量',
  exposure: '解释变量',
  outcome: '结果变量',
  mediator: '机制变量',
  moderator: '调节变量',
  control: '控制变量',
  id: '实体键',
  time: '时间键',
  event_date: '事件时间',
}

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

function getShowcaseFigure(id: string): ShowcasePaperFigure | undefined {
  return SHOWCASE_PAPER_FIGURES.find((figure) => figure.id === id)
}

function getShowcaseTable(id: string): ShowcasePaperTable | undefined {
  return SHOWCASE_PAPER_TABLES.find((table) => table.id === id)
}

function ShowcaseFigure({ figure }: { figure: ShowcasePaperFigure }) {
  return (
    <figure className={`showcase-paper__figure ${figure.demo ? 'is-demo' : ''}`}>
      <img src={figure.src} alt={figure.alt} loading="lazy" />
      <figcaption><strong>{figure.title}</strong><span>{figure.note}</span></figcaption>
    </figure>
  )
}

function ShowcaseTable({ table }: { table: ShowcasePaperTable }) {
  return (
    <figure className={`showcase-paper__table ${table.demo ? 'is-demo' : ''}`}>
      <figcaption>{table.title}</figcaption>
      <div className="showcase-paper__table-scroll">
        <table>
          <thead><tr>{table.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
          <tbody>
            {table.rows.map((row, rowIndex) => (
              <tr key={`${table.id}-${rowIndex}`}>
                {row.map((cell, cellIndex) => <td key={`${table.id}-${rowIndex}-${cellIndex}`}>{cell}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>{table.note}</p>
    </figure>
  )
}

function renderShowcaseBlock(block: ShowcasePaperBlock, index: number) {
  if (block.kind === 'paragraph') return <p key={`paragraph-${index}`}>{block.text}</p>
  if (block.kind === 'subheading') return <h5 key={`subheading-${index}`}>{block.text}</h5>
  if (block.kind === 'hypothesis') {
    return <div className="showcase-paper__hypothesis" key={`hypothesis-${index}`}><strong>{block.label}</strong><p>{block.text}</p></div>
  }
  if (block.kind === 'equation') {
    return (
      <div className="showcase-paper__equation" key={`equation-${index}`}>
        <div><span>{block.formula}</span><b>{block.label}</b></div>
        {block.note && <p>{block.note}</p>}
      </div>
    )
  }
  if (block.kind === 'figure') {
    const figure = getShowcaseFigure(block.id)
    return figure ? <ShowcaseFigure figure={figure} key={`figure-${block.id}-${index}`} /> : null
  }
  const table = getShowcaseTable(block.id)
  return table ? <ShowcaseTable table={table} key={`table-${block.id}-${index}`} /> : null
}

function scrollToShowcasePaperSection(id: string): void {
  const target = document.getElementById(id)
  const article = target?.closest<HTMLElement>('.showcase-paper__article')
  if (!target || !article) return
  const top = article.scrollTop + target.getBoundingClientRect().top - article.getBoundingClientRect().top - 8
  article.scrollTo({ top, behavior: 'smooth' })
}

function escapeHtmlWithBreaks(value: string): string {
  return escapeHtml(value).replaceAll('\n', '<br>')
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(blob)
  })
}

async function downloadShowcasePaper(): Promise<void> {
  const embeddedFigures = new Map<string, string>()
  await Promise.all(SHOWCASE_PAPER_FIGURES.map(async (figure) => {
    try {
      const response = await fetch(figure.wordSrc)
      if (!response.ok) throw new Error(`Figure fetch failed: ${response.status}`)
      embeddedFigures.set(figure.id, await blobToDataUrl(await response.blob()))
    } catch {
      embeddedFigures.set(figure.id, figure.wordSrc)
    }
  }))

  const tableHtml = (table: ShowcasePaperTable): string => `
    <div class="table-wrap">
      <div class="table-title">${escapeHtml(table.title)}</div>
      <table>
        <thead><tr>${table.columns.map((column) => `<th>${escapeHtml(column)}</th>`).join('')}</tr></thead>
        <tbody>${table.rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtmlWithBreaks(cell)}</td>`).join('')}</tr>`).join('')}</tbody>
      </table>
      <p class="figure-note">${escapeHtml(table.note)}</p>
    </div>`

  const figureHtml = (figure: ShowcasePaperFigure): string => `
    <div class="figure-wrap">
      <img src="${embeddedFigures.get(figure.id) ?? figure.wordSrc}" alt="${escapeHtml(figure.alt)}">
      <div class="figure-title">${escapeHtml(figure.title)}</div>
      <p class="figure-note">${escapeHtml(figure.note)}</p>
    </div>`

  const blockHtml = (block: ShowcasePaperBlock): string => {
    if (block.kind === 'paragraph') return `<p>${escapeHtml(block.text)}</p>`
    if (block.kind === 'subheading') return `<h3>${escapeHtml(block.text)}</h3>`
    if (block.kind === 'hypothesis') return `<div class="hypothesis"><strong>${escapeHtml(block.label)}</strong><p>${escapeHtml(block.text)}</p></div>`
    if (block.kind === 'equation') return `<div class="equation"><span>${escapeHtml(block.formula)}</span><b>${escapeHtml(block.label)}</b></div>${block.note ? `<p class="equation-note">${escapeHtml(block.note)}</p>` : ''}`
    if (block.kind === 'figure') {
      const figure = getShowcaseFigure(block.id)
      return figure ? figureHtml(figure) : ''
    }
    const table = getShowcaseTable(block.id)
    return table ? tableHtml(table) : ''
  }

  const sections = SHOWCASE_PAPER.sections.map((section) => `
    <h2>${escapeHtml(section.title)}</h2>
    ${section.blocks.map(blockHtml).join('')}
  `).join('')
  const references = SHOWCASE_PAPER.references.map((reference) => `<p class="reference">${escapeHtml(reference)}</p>`).join('')
  const html = `<!doctype html><html><head><meta charset="utf-8"><style>
    body{font-family:"SimSun",serif;font-size:10.5pt;line-height:1.75;color:#111;margin:2.35cm 2.5cm;background:#fff}
    h1{font-family:"SimHei",sans-serif;font-size:20pt;text-align:center;line-height:1.45;margin:0 0 12pt}
    .authors,.affiliation,.subtitle{text-align:center;text-indent:0}.authors{font-size:12pt}.affiliation,.subtitle{font-size:9.5pt;color:#555}
    .abstract{margin:20pt 0 8pt}.abstract p{text-indent:0}.keywords,.jel{text-indent:0;margin:3pt 0}
    h2{font-family:"SimHei",sans-serif;font-size:14pt;text-align:center;margin:22pt 0 10pt}
    h3{font-family:"SimHei",sans-serif;font-size:11pt;margin:14pt 0 4pt}
    p{text-indent:2em;margin:5pt 0;text-align:justify}.hypothesis{margin:10pt 2em;border-left:2pt solid #333;padding:6pt 10pt}.hypothesis p{display:inline;text-indent:0}
    .equation{display:flex;align-items:center;justify-content:center;position:relative;margin:12pt 0;font-family:"Times New Roman",serif;font-size:11pt;font-style:italic}.equation b{position:absolute;right:0;font-style:normal;font-weight:normal}.equation-note{text-indent:0;font-size:9.5pt}
    .table-wrap,.figure-wrap{margin:16pt 0;page-break-inside:avoid}.table-title,.figure-title{text-align:center;font-weight:bold;margin:5pt 0}
    table{width:100%;border-collapse:collapse;border-top:1.2pt solid #111;border-bottom:1.2pt solid #111;font-size:9pt}th{border-bottom:.6pt solid #111;padding:5pt 3pt;font-weight:normal}td{padding:4pt 3pt;text-align:center;vertical-align:middle}tbody tr:first-child td{border-top:.4pt solid #777}
    .figure-wrap img{display:block;max-width:100%;max-height:16cm;margin:0 auto}.figure-note{font-size:8.5pt;line-height:1.5;text-indent:0;margin-top:4pt}
    .reference{text-indent:-2em;padding-left:2em;font-size:9.5pt}.note{margin-top:24pt;padding-top:10pt;border-top:.6pt solid #777;color:#444;font-size:9pt;text-indent:0}
  </style></head><body>
    <h1>${escapeHtml(SHOWCASE_PAPER.title)}</h1>
    <p class="authors">${SHOWCASE_PAPER.authors.map(escapeHtml).join('，')}</p>
    <p class="affiliation">${escapeHtml(SHOWCASE_PAPER.affiliation)}</p>
    <p class="subtitle">${escapeHtml(SHOWCASE_PAPER.subtitle)}</p>
    <div class="abstract"><strong>摘　要：</strong><p>${escapeHtml(SHOWCASE_PAPER.abstract)}</p></div>
    <p class="keywords"><strong>关键词：</strong>${SHOWCASE_PAPER.keywords.map(escapeHtml).join('；')}</p>
    <p class="jel"><strong>JEL分类号：</strong>${SHOWCASE_PAPER.jel.map(escapeHtml).join('、')}</p>
    ${sections}
    <h2>参考文献</h2>${references}
    <p class="note">${escapeHtml(SHOWCASE_PAPER.dataStatement)}</p>
  </body></html>`
  const blob = new Blob(['\ufeff', html], { type: 'application/msword;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = '碳市场与企业高质量绿色创新_公开数据复现初稿.doc'
  document.body.append(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

export interface ProjectOverviewPageProps {
  projectId: string
  onOpenProjects: () => void
  onOpenDiscovery: (projectId: string, step: DiscoveryRouteStep) => void
  onOpenLibrary: (kind: ResourceKind) => void
  onOpenTask: (taskId: string) => void
}

function useProductRevision(): void {
  const [, setRevision] = useState(0)
  useEffect(
    () => frontendDataSource.subscribe(() => setRevision((current) => current + 1)),
    [],
  )
}

function dateLabel(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '刚刚'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export function ProjectOverviewPage({
  projectId,
  onOpenProjects,
  onOpenDiscovery,
  onOpenLibrary,
  onOpenTask,
}: ProjectOverviewPageProps) {
  useProductRevision()
  const [activeOutcomeTab, setActiveOutcomeTab] = useState<OutcomeTab>('hypotheses')
  const outcomesRef = useRef<HTMLElement | null>(null)
  const project = frontendDataSource.getProject(projectId)

  if (!project) {
    return (
      <main className="product-page">
        <section className="product-empty">
          <Layers3 size={28} aria-hidden="true" />
          <h1>没有找到这个项目</h1>
          <p>项目可能已被删除，或当前浏览器里尚未保存这条记录。</p>
          <button type="button" className="product-button" onClick={onOpenProjects}>
            <ArrowLeft size={16} aria-hidden="true" />
            返回项目
          </button>
        </section>
      </main>
    )
  }

  const bundle = frontendDataSource.getEvidenceBundle(project.id)
  const handoff = frontendDataSource.buildDiscoveryHandoff(project.id)
  const completedSteps = new Set(project.discovery.completedSteps)
  const discoveryPercent = project.status === 'handoff_ready' || completedSteps.has(6)
    ? 100
    : Math.round((completedSteps.size / 6) * 100)
  const status = STATUS_COPY[project.status]
  const latestTaskId = project.taskIds.at(-1)
  const nextStep = project.discovery.currentStep
  const scientificTen = project.discovery.scientificTen
  const scientificTenConfirmedCount = scientificTen?.items.filter((item) => item.confirmed).length ?? 0
  const selectedIdea = project.discovery.ideaCards.find((idea) => (
    idea.id === project.discovery.selectedIdeaId
  )) ?? project.discovery.ideaCards[0]
  const alternativeIdeas = project.discovery.ideaCards.filter((idea) => idea.id !== selectedIdea?.id)
  const isShowcaseProject = project.id === SHOWCASE_PROJECT_ID
  const projectSummary = project.summary.startsWith('前端演示项目：')
    ? '围绕研究问题组织证据、假设、方案与正式验证。'
    : project.summary || project.discovery.brief.researchQuestion || '尚未填写项目摘要'

  const focusOutcome = (tab: OutcomeTab): void => {
    setActiveOutcomeTab(tab)
    window.requestAnimationFrame(() => {
      outcomesRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }

  return (
    <main className="product-page project-overview">
      <button type="button" className="product-back" onClick={onOpenProjects}>
        <ArrowLeft size={15} aria-hidden="true" />
        全部项目
      </button>

      <header className="product-page__header project-overview__header">
        <div>
          <span className="product-eyebrow">{isShowcaseProject ? 'RESEARCH SHOWCASE' : 'PROJECT OVERVIEW'}</span>
          <div className="project-overview__titleline">
            <h1>{project.title}</h1>
            <span className={`product-status ${status.tone}`}>{status.label}</span>
          </div>
          <p>{projectSummary}</p>
        </div>
        <button
          type="button"
          className="product-button is-primary"
          onClick={() => focusOutcome('hypotheses')}
        >
          <FileCheck2 size={15} aria-hidden="true" />
          查看研究成果
        </button>
      </header>

      <section className="project-overview__facts" aria-label="项目元数据">
        <div>
          <span>研究问题</span>
          <strong>{project.discovery.brief.researchQuestion || '待补充'}</strong>
        </div>
        <div>
          <span>分析对象</span>
          <strong>{project.discovery.brief.unitOfAnalysis || '待补充'}</strong>
        </div>
        <div>
          <span>样本期间</span>
          <strong>{project.discovery.brief.samplePeriod || '待补充'}</strong>
        </div>
        <div>
          <span>最近更新</span>
          <strong>{dateLabel(project.updatedAt)}</strong>
        </div>
      </section>

      <section ref={outcomesRef} className="project-outcomes" aria-labelledby="project-outcomes-title">
        <div className="product-section-heading project-outcomes__heading">
          <div>
            <span className="product-eyebrow">DELIVERABLES</span>
            <h2 id="project-outcomes-title">研究成果直达</h2>
            <p>从核心假设到论文正文，集中查看系统生成并经研究流程核对的阶段成果。</p>
          </div>
          <span className={isShowcaseProject ? 'is-showcase' : ''}>
            {isShowcaseProject ? '真实执行案例' : '当前项目成果'}
          </span>
        </div>

        <div className="project-outcomes__shell">
          <div className="project-outcomes__tabs" role="tablist" aria-label="研究成果类型">
            {OUTCOME_TABS.map((tab) => {
              const Icon = tab.icon
              const selected = activeOutcomeTab === tab.id
              return (
                <button
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  aria-controls={`outcome-panel-${tab.id}`}
                  className={selected ? 'is-active' : ''}
                  key={tab.id}
                  onClick={() => setActiveOutcomeTab(tab.id)}
                >
                  <span><Icon size={17} aria-hidden="true" /></span>
                  <span><strong>{tab.label}</strong><small>{tab.note}</small></span>
                </button>
              )
            })}
          </div>

          {activeOutcomeTab === 'hypotheses' && (
            <div className="project-outcomes__panel outcome-hypotheses" role="tabpanel" id="outcome-panel-hypotheses">
              {selectedIdea ? (
                <>
                  <header className="outcome-panel__header">
                    <div>
                      <span className="outcome-kicker"><Check size={12} aria-hidden="true" />最终选择</span>
                      <h3>{selectedIdea.title}</h3>
                      <p>{selectedIdea.hypothesis}</p>
                    </div>
                    <span className="outcome-score">综合评价 <strong>{(Object.values(selectedIdea.pareto).reduce((sum, value) => sum + value, 0) / 5).toFixed(1)}</strong>/5</span>
                  </header>

                  <div className="outcome-hypotheses__body">
                    <section className="outcome-mechanism">
                      <span>理论机制</span>
                      <p>{selectedIdea.mechanism}</p>
                      {isShowcaseProject && (
                        <div className="outcome-mechanism__paths" aria-label="双机制路径">
                          <article><b>路径 A</b><strong>碳价信号</strong><p>履约成本进入生产决策，提高绿色研发与低碳技术的相对收益。</p></article>
                          <ArrowRight size={17} aria-hidden="true" />
                          <article><b>路径 B</b><strong>信息约束</strong><p>核算与履约披露提高环境行为可见度，强化声誉与融资压力。</p></article>
                        </div>
                      )}
                    </section>

                    <section className="outcome-variables">
                      <div className="outcome-subheading"><span>变量设计</span><small>{selectedIdea.variables.length} 个核心变量</small></div>
                      <div className="outcome-variables__table" role="table" aria-label="核心变量设计">
                        <div className="is-heading" role="row"><span>角色</span><span>变量</span><span>操作化定义</span><span>来源</span></div>
                        {selectedIdea.variables.map((variable) => (
                          <div role="row" key={`${variable.role}-${variable.name}`}>
                            <span>{VARIABLE_ROLE_LABELS[variable.role] ?? variable.role}</span>
                            <span><strong>{variable.label}</strong><small>{variable.name}</small></span>
                            <span>{variable.definition}</span>
                            <span>{variable.source}</span>
                          </div>
                        ))}
                      </div>
                    </section>
                  </div>

                  {alternativeIdeas.length > 0 && (
                    <footer className="outcome-alternatives">
                      <span>同步保留的候选方向</span>
                      <div>{alternativeIdeas.map((idea, index) => <span key={idea.id}><b>候选 {index + 2}</b>{idea.title}</span>)}</div>
                    </footer>
                  )}
                </>
              ) : (
                <div className="outcome-empty"><Target size={24} /><strong>尚未形成研究假设</strong><p>完成候选假设生成与人工选择后，这里会自动汇总最终假设。</p></div>
              )}
            </div>
          )}

          {activeOutcomeTab === 'scientific' && (
            <div className="project-outcomes__panel outcome-scientific" role="tabpanel" id="outcome-panel-scientific">
              {scientificTen ? (
                <>
                  <header className="outcome-panel__header is-compact">
                    <div><span className="outcome-kicker"><Check size={12} aria-hidden="true" />{scientificTen.status === 'confirmed' ? '10/10 已确认' : `${scientificTenConfirmedCount}/10 已核对`}</span><h3>科学十项研究方案</h3><p>把研究构想编译为可以审查、执行和复现的完整方案。</p></div>
                    <button type="button" className="product-button" onClick={() => onOpenDiscovery(project.id, 'handoff')}>进入方案工作台<ArrowRight size={14} /></button>
                  </header>
                  <div className="outcome-scientific__list">
                    {scientificTen.items.map((item, index) => (
                      <details key={item.itemNo} open={index < 2 ? true : undefined}>
                        <summary>
                          <span className="outcome-scientific__number">{item.confirmed ? <Check size={13} /> : item.itemNo}</span>
                          <span><strong>{item.title}</strong><small>{item.status === 'evidence_bound' ? '证据已绑定' : item.status === 'conditional' ? '条件性结论' : '等待补充'}</small></span>
                          <ChevronDown size={15} aria-hidden="true" />
                        </summary>
                        <div className="outcome-scientific__content">
                          <p>{item.content}</p>
                          <span>证据引用：{item.evidenceRefs.join(' · ') || '待补充'}</span>
                        </div>
                      </details>
                    ))}
                  </div>
                </>
              ) : (
                <div className="outcome-empty"><ListChecks size={24} /><strong>尚未生成科学十项</strong><p>选择假设后进入方案输入，系统会生成并逐项等待人工确认。</p></div>
              )}
            </div>
          )}

          {activeOutcomeTab === 'results' && (
            <div className="project-outcomes__panel outcome-results" role="tabpanel" id="outcome-panel-results">
              {isShowcaseProject ? (
                <>
                  <header className="outcome-panel__header is-compact">
                    <div><span className="outcome-kicker">公开数据真实执行</span><h3>关键估计与结论台账</h3><p>数值、诊断和文字主张一一对应，未通过审计的结论不会进入正文。</p></div>
                    {latestTaskId && <button type="button" className="product-button" onClick={() => onOpenTask(latestTaskId)}>查看完整任务<ArrowRight size={14} /></button>}
                  </header>
                  <div className="outcome-results__metrics">
                    {SHOWCASE_RESULT_METRICS.map((metric) => <article key={metric.label}><strong>{metric.value}</strong><span>{metric.label}</span><small>{metric.note}</small></article>)}
                  </div>
                  <section className="outcome-claims">
                    <div className="outcome-subheading"><span>结论台账</span><small>4 条经过分级的研究主张</small></div>
                    {SHOWCASE_CLAIMS.map((item, index) => (
                      <article key={item.claim}>
                        <span className={item.status === '公开复现支持' || item.status === '识别诊断通过' ? 'is-approved' : 'is-qualified'}>{item.status}</span>
                        <div><strong>{index + 1}. {item.claim}</strong><small>证据：{item.evidence}</small></div>
                      </article>
                    ))}
                  </section>
                  <p className="outcome-demo-note">本页数值来自公开许可数据的真实执行快照：两轮协议、原始数据、结果表、图形规格与独立复算均已封存。录屏时加载快照，不重复发起外部模型调用。</p>
                </>
              ) : (
                <div className="outcome-empty"><FileCheck2 size={24} /><strong>当前项目尚无可展示结果</strong><p>正式任务通过执行、诊断与 H3 结论授权后，关键结果会汇总到这里。</p></div>
              )}
            </div>
          )}

          {activeOutcomeTab === 'paper' && (
            <div className="project-outcomes__panel outcome-paper" role="tabpanel" id="outcome-panel-paper">
              {isShowcaseProject ? (
                <article className="showcase-paper">
                  <header>
                    <span className="outcome-kicker">期刊规范化初稿 · 真实估计</span>
                    <h3>{SHOWCASE_PAPER.title}</h3>
                    <p className="showcase-paper__authors">{SHOWCASE_PAPER.authors.join('，')}</p>
                    <p className="showcase-paper__affiliation">{SHOWCASE_PAPER.affiliation}</p>
                    <p className="showcase-paper__subtitle">{SHOWCASE_PAPER.subtitle}</p>
                    <div className="showcase-paper__actions">
                      <button type="button" className="product-button" onClick={() => void downloadShowcasePaper()}><Download size={14} />下载 Word</button>
                      <button type="button" className="product-button" onClick={() => window.print()}><Printer size={14} />打印 / 存为 PDF</button>
                    </div>
                  </header>
                  <div className="showcase-paper__layout">
                    <nav aria-label="论文目录">
                      <strong>正文目录</strong>
                      <button type="button" onClick={() => scrollToShowcasePaperSection('paper-abstract')}>摘要</button>
                      {SHOWCASE_PAPER.sections.map((section) => <button type="button" onClick={() => scrollToShowcasePaperSection(`paper-${section.id}`)} key={section.id}>{section.title}</button>)}
                      <button type="button" onClick={() => scrollToShowcasePaperSection('paper-references')}>参考文献</button>
                    </nav>
                    <div className="showcase-paper__article">
                      <section id="paper-abstract" className="showcase-paper__abstract">
                        <h4>内容摘要</h4>
                        <p>{SHOWCASE_PAPER.abstract}</p>
                        <p className="showcase-paper__keywords"><strong>关键词：</strong>{SHOWCASE_PAPER.keywords.join('；')}</p>
                        <p className="showcase-paper__keywords"><strong>JEL分类号：</strong>{SHOWCASE_PAPER.jel.join('、')}</p>
                      </section>
                      {SHOWCASE_PAPER.sections.map((section) => (
                        <section id={`paper-${section.id}`} key={section.id}>
                          <h4>{section.title}</h4>
                          {section.blocks.map(renderShowcaseBlock)}
                        </section>
                      ))}
                      <section id="paper-references" className="showcase-paper__references">
                        <h4>参考文献</h4>
                        {SHOWCASE_PAPER.references.map((reference) => <p key={reference}>{reference}</p>)}
                      </section>
                      <aside className="showcase-paper__data-statement">{SHOWCASE_PAPER.dataStatement}</aside>
                    </div>
                  </div>
                </article>
              ) : (
                <div className="outcome-empty"><ScrollText size={24} /><strong>当前项目尚未生成论文初稿</strong><p>完成结果审计与 H3 结论授权后，系统将按获准主张自动组织论文正文。</p></div>
              )}
            </div>
          )}
        </div>
      </section>

      <section className="project-journey" aria-labelledby="project-journey-title">
        <div className="product-section-heading">
          <div>
            <span className="product-eyebrow">完整研究旅程</span>
            <h2 id="project-journey-title">从研究发现到可审查交付</h2>
          </div>
          <span>{discoveryPercent}% 发现进度</span>
        </div>

        <div className="project-journey__zones">
          <section className="project-zone is-discovery">
            <header>
              <span className="project-zone__number">01</span>
              <div>
                <h3>研究发现区</h3>
                <p>自动检索、趋势图谱、研究空白与候选假设</p>
              </div>
              <span className="project-zone__progress">{discoveryPercent}%</span>
            </header>
            <ol className="project-zone__stages">
              {DISCOVERY_STAGES.map((stage) => {
                const complete = completedSteps.has(stage.step)
                  || project.status === 'handoff_ready'
                const active = stage.step === project.discovery.currentStep && !complete
                return (
                  <li key={stage.step} className={`${complete ? 'is-complete' : ''} ${active ? 'is-active' : ''}`}>
                    <button
                      type="button"
                      onClick={() => onOpenDiscovery(project.id, STEP_ROUTE[stage.step])}
                    >
                      <span className="project-zone__node" aria-hidden="true">
                        {complete ? <Check size={13} /> : stage.step}
                      </span>
                      <span>
                        <strong>{stage.short}</strong>
                        <small>{stage.title}</small>
                      </span>
                      <ArrowRight size={14} aria-hidden="true" />
                    </button>
                  </li>
                )
              })}
            </ol>
          </section>

          <section className="project-journey__bridge" aria-label="科学十项研究方案">
            <span className="project-journey__bridge-number">02</span>
            <span className="project-journey__bridge-copy">
              <small>研究方案</small>
              <strong>科学十项</strong>
              <em>
                {scientificTen?.status === 'confirmed'
                  ? '10/10 已确认'
                  : scientificTen
                    ? `${scientificTenConfirmedCount}/10 已核对`
                    : completedSteps.has(5) || project.status === 'handoff_ready'
                      ? '可生成方案草案'
                      : '选择假设后准备'}
              </em>
            </span>
            <ol className="project-journey__proposal-items" aria-label="科学十项内容">
              {SCIENTIFIC_TEN.map((item, index) => (
                <li className={scientificTen?.items[index]?.confirmed ? 'is-confirmed' : ''} key={item}>
                  <b>{scientificTen?.items[index]?.confirmed ? <Check size={9} aria-hidden="true" /> : index + 1}</b>
                  <span>{item}</span>
                </li>
              ))}
            </ol>
            <button
              type="button"
              className="project-journey__proposal-action"
              onClick={() => scientificTen ? focusOutcome('scientific') : onOpenDiscovery(project.id, 'handoff')}
            >
              {scientificTen ? '查看科学十项' : '准备科学十项'}
              <ArrowRight size={13} aria-hidden="true" />
            </button>
          </section>

          <section className={`project-zone is-formal ${project.taskIds.length ? 'is-started' : ''}`}>
            <header>
              <span className="project-zone__number">03</span>
              <div>
                <h3>实证任务区</h3>
                <p>正式 H1–H4 · 执行状态与科学结论分别记录</p>
              </div>
              <span className="product-status is-formal">
                {project.taskIds.length ? `${project.taskIds.length} 个任务` : '尚未创建'}
              </span>
            </header>
            <ol className="formal-gates">
              {FORMAL_STAGES.map((stage, index) => (
                <li key={stage.gate}>
                  <span className="formal-gates__node">
                    {project.taskIds.length ? stage.gate : <Circle size={10} aria-hidden="true" />}
                  </span>
                  <div>
                    <strong>{stage.gate}</strong>
                    <small>{stage.title}</small>
                  </div>
                  <span>{project.taskIds.length && index === 0 ? '查看任务' : '正式流程'}</span>
                </li>
              ))}
            </ol>
            {latestTaskId ? (
              <button
                type="button"
                className="product-button project-zone__task-button"
                onClick={() => onOpenTask(latestTaskId)}
              >
                <FlaskConical size={15} aria-hidden="true" />
                打开正式任务
              </button>
            ) : (
              <p className="project-zone__note">
                科学十项方案不会绕过人工确认直接进入执行；请先检查研究边界、数据与方法。
              </p>
            )}
          </section>
        </div>
      </section>

      <section className="project-resources" aria-labelledby="project-resources-title">
        <div className="product-section-heading">
          <div>
            <span className="product-eyebrow">EVIDENCE BUNDLE</span>
            <h2 id="project-resources-title">项目资源篮</h2>
          </div>
          <span>{bundle.links.length} 条资源</span>
        </div>
        <div className="project-resources__grid">
          {(Object.keys(RESOURCE_META) as ResourceKind[]).map((kind) => {
            const item = RESOURCE_META[kind]
            const Icon = item.icon
            return (
              <button type="button" key={kind} onClick={() => onOpenLibrary(kind)}>
                <span className="project-resources__icon"><Icon size={17} aria-hidden="true" /></span>
                <span>
                  <strong>{item.label}</strong>
                  <small>{item.note}</small>
                </span>
                <b>{bundle.counts[kind]}</b>
                <ArrowRight size={14} aria-hidden="true" />
              </button>
            )
          })}
        </div>
        <p className="project-resources__boundary">
          <Library size={15} aria-hidden="true" />
          资源篮中的内容会作为项目证据输入；外部目录与政策摘要需在正式使用前核验来源与权限。
        </p>
      </section>

      <section className="project-next-action">
        <span className="project-next-action__icon">
          {latestTaskId ? <FlaskConical size={20} aria-hidden="true" /> : <ArrowRight size={20} aria-hidden="true" />}
        </span>
        <div>
          <span className="product-eyebrow">建议下一步</span>
          <h2>
            {latestTaskId
              ? '继续正式任务，处理当前人工闸门'
              : handoff?.readyForFormalTask
                ? '方案输入已完整，可以进入科学十项与正式任务'
                : `继续${DISCOVERY_STAGES[nextStep - 1].short}`}
          </h2>
          <p>
            {latestTaskId
              ? '正式任务严格沿用 H1–H4 语义，并分开展示执行成功与科学有效性。'
              : handoff?.missingFields.length
                ? `交接前仍有 ${handoff.missingFields.length} 项正式字段需要补齐。`
                : '在方案输入中复核研究边界，再进入科学十项与正式任务。'}
          </p>
        </div>
        <button
          type="button"
          className="product-button is-primary"
          onClick={() => (
            latestTaskId
              ? onOpenTask(latestTaskId)
              : onOpenDiscovery(project.id, STEP_ROUTE[nextStep])
          )}
        >
          {latestTaskId ? '打开任务' : '继续研究发现'}
          <ArrowRight size={15} aria-hidden="true" />
        </button>
      </section>
    </main>
  )
}
