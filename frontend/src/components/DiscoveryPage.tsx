import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Database,
  FileCheck2,
  FileText,
  GitBranch,
  Lightbulb,
  Link2,
  Network,
  PackageCheck,
  Scale,
  ShieldCheck,
  Sparkles,
  Target,
  Trash2,
  type LucideIcon,
} from 'lucide-react'
import {
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import {
  frontendDataSource,
  SHOWCASE_PROJECT_ID,
  type DiscoveryBrief,
  type DiscoveryHandoff,
  type DiscoveryStep as ProductDiscoveryStep,
  type EvidenceBundle,
  type GapCard,
  type IdeaCard,
  type Project,
  type ResourceKind,
} from '../product'
import type { DiscoveryStep as DiscoveryRouteStep } from '../runtime/router'
import { workflowApi } from '../runtime/api'
import type {
  DiscoveryPlanGeneration,
  DiscoveryReleasePreviewWire,
  RunSnapshot,
  VariableInput,
} from '../runtime/types'
import { ScientificTenPanel } from './ScientificTenPanel'
import '../projects.css'

interface DiscoveryStepMeta {
  number: ProductDiscoveryStep
  route: DiscoveryRouteStep
  label: string
  description: string
  icon: LucideIcon
}

const DISCOVERY_STEPS: DiscoveryStepMeta[] = [
  {
    number: 1,
    route: 'brief',
    label: '研究简报',
    description: '明确问题、对象、期间与边界',
    icon: Target,
  },
  {
    number: 2,
    route: 'resources',
    label: '数据中心检索',
    description: '汇集文献、政策、数据与方法',
    icon: BookOpen,
  },
  {
    number: 3,
    route: 'gaps',
    label: '趋势与空白',
    description: '分析主题演进、证据关系与研究空白',
    icon: Network,
  },
  {
    number: 4,
    route: 'ideas',
    label: '候选假设',
    description: '形成机制、变量与可证伪假设',
    icon: Lightbulb,
  },
  {
    number: 5,
    route: 'decision',
    label: '假设选择',
    description: '比较价值、可行性并人工选择',
    icon: Scale,
  },
  {
    number: 6,
    route: 'handoff',
    label: '方案输入',
    description: '检查科学十项与正式研究所需输入',
    icon: FileCheck2,
  },
]

const ROUTE_NUMBER = Object.fromEntries(
  DISCOVERY_STEPS.map((step) => [step.route, step.number]),
) as Record<DiscoveryRouteStep, ProductDiscoveryStep>

const NUMBER_ROUTE = Object.fromEntries(
  DISCOVERY_STEPS.map((step) => [step.number, step.route]),
) as Record<ProductDiscoveryStep, DiscoveryRouteStep>

const RESOURCE_META: Record<
  ResourceKind,
  { label: string; icon: LucideIcon }
> = {
  literature: { label: '文献', icon: BookOpen },
  policy: { label: '政策', icon: FileText },
  dataset: { label: '数据', icon: Database },
  method: { label: '方法', icon: Scale },
}

const DATA_STRUCTURE_LABEL: Record<DiscoveryBrief['dataStructureHint'], string> = {
  cross_section: '截面数据',
  panel: '面板数据',
  time_series: '时间序列',
  spatial_panel: '空间面板',
  event: '事件数据',
  unknown: '暂不确定',
}

const DIRECTION_LABEL: Record<IdeaCard['expectedDirection'], string> = {
  positive: '正向',
  negative: '负向',
  nonlinear: '非线性',
  heterogeneous: '异质性',
  unspecified: '待确定',
}

function createDemoGap(project: Project, bundle: EvidenceBundle): GapCard {
  const question = project.discovery.brief.researchQuestion.trim() || project.title
  return {
    id: `${project.id}-gap-demo`,
    title: '从总体关系到可识别机制的证据缺口',
    evidence: [
      `当前项目篮包含 ${bundle.counts.literature} 篇文献、${bundle.counts.policy} 条政策、`,
      `${bundle.counts.dataset} 个数据目录和 ${bundle.counts.method} 种方法。`,
      '这些资源建立了目录级证据关系，但尚未证明具体机制与识别条件。',
    ].join(''),
    opportunity: `围绕“${question}”，分别检验总体效应、作用机制与异质性边界，并明确每条命题所需的数据和诊断。`,
    resourceIds: bundle.links.map((link) => link.resourceId),
  }
}

function demoIdeaCandidates(project: Project): IdeaCard[] {
  const question = project.discovery.brief.researchQuestion.trim() || project.title
  const source = '待与真实导入的数据文件绑定'
  const sharedVariables: IdeaCard['variables'] = [
    {
      name: 'outcome',
      label: '目标结果变量',
      role: 'outcome',
      definition: '与研究问题对应的主要结果指标',
      source,
    },
    {
      name: 'treatment',
      label: '核心解释变量',
      role: 'treatment',
      definition: '研究问题中的主要处理、政策或暴露变量',
      source,
    },
    {
      name: 'unit_id',
      label: '观测单位标识',
      role: 'id',
      definition: '跨时期唯一识别观测对象的字段',
      source,
    },
    {
      name: 'period',
      label: '时期',
      role: 'time',
      definition: '记录观测发生时期的字段',
      source,
    },
  ]

  return [
    {
      id: `${project.id}-idea-baseline`,
      title: '基准效应：先验证核心关系',
      hypothesis: `围绕“${question}”，核心解释变量对目标结果产生方向明确且可复核的影响。`,
      expectedDirection: 'unspecified',
      mechanism: '核心解释变量变化 → 研究对象的约束或激励改变 → 目标结果响应',
      variables: sharedVariables.map((variable) => ({ ...variable })),
      pareto: {
        novelty: 3.6,
        feasibility: 4.7,
        identification: 3.5,
        dataReadiness: 4.5,
        policyValue: 3.8,
      },
    },
    {
      id: `${project.id}-idea-mechanism`,
      title: '机制路径：解释影响如何发生',
      hypothesis: `围绕“${question}”，核心效应通过可观测的中间机制传导。`,
      expectedDirection: 'positive',
      mechanism: '处理或政策冲击 → 中间约束缓解 / 激励增强 → 目标结果变化',
      variables: [
        ...sharedVariables.map((variable) => ({ ...variable })),
        {
          name: 'mechanism',
          label: '机制变量',
          role: 'mediator',
          definition: '用于区分候选传导路径的中间指标',
          source,
        },
      ],
      pareto: {
        novelty: 4.4,
        feasibility: 3.6,
        identification: 3.8,
        dataReadiness: 3.2,
        policyValue: 4.6,
      },
    },
    {
      id: `${project.id}-idea-heterogeneity`,
      title: '边界条件：识别谁的响应更强',
      hypothesis: `围绕“${question}”，核心效应随制度环境或对象特征呈现系统性异质性。`,
      expectedDirection: 'heterogeneous',
      mechanism: '制度或对象特征不同 → 约束与响应能力不同 → 核心效应出现分化',
      variables: [
        ...sharedVariables.map((variable) => ({ ...variable })),
        {
          name: 'moderator',
          label: '边界条件变量',
          role: 'moderator',
          definition: '用于刻画制度环境或对象差异的预先定义指标',
          source,
        },
      ],
      pareto: {
        novelty: 4.1,
        feasibility: 4,
        identification: 4.4,
        dataReadiness: 3.8,
        policyValue: 4.2,
      },
    },
  ]
}

function generateDemoGap(project: Project, bundle: EvidenceBundle): void {
  if (project.discovery.gapCards.length > 0) return
  frontendDataSource.updateDiscoveryDraft(project.id, {
    gapCards: [createDemoGap(project, bundle)],
  })
}

function generateDemoIdeas(project: Project): void {
  if (project.discovery.ideaCards.length >= 3) return
  const merged = project.discovery.ideaCards.map((idea) => ({ ...idea }))
  for (const candidate of demoIdeaCandidates(project)) {
    if (merged.length >= 3) break
    if (!merged.some((idea) => idea.id === candidate.id)) merged.push(candidate)
  }
  frontendDataSource.updateDiscoveryDraft(project.id, { ideaCards: merged })
}

function applyLiveGeneration(project: Project, generation: DiscoveryPlanGeneration): void {
  const plan = generation.plan
  const variableRoles: Record<string, VariableInput['role']> = {
    predictor: 'exposure',
    outcome: 'outcome',
    mediator: 'mediator',
    moderator: 'moderator',
    control: 'control',
  }
  const variables = plan.constructs.map((construct) => ({
    name: construct.key,
    label: construct.label,
    role: variableRoles[construct.role] ?? 'unknown',
    definition: construct.definition,
    source: construct.evidence_chunk_ids.join(', '),
  }))
  const predictor = plan.constructs.find((item) => item.role === 'predictor')
  const direction = predictor?.expected_direction ?? 'unspecified'
  frontendDataSource.updateDiscoveryDraft(project.id, {
    gapCards: [{
      id: 'research_gap:online_candidate',
      title: plan.gap_title,
      evidence: plan.current_state,
      opportunity: `${plan.missing_piece}\n\n${plan.why_important}`,
      resourceIds: generation.evidenceBundle.evidence_hits.map((item) => item.chunk_id),
    }],
    ideaCards: [{
      id: 'hypothesis:online_candidate',
      title: plan.hypothesis_title,
      hypothesis: plan.hypothesis_statement,
      expectedDirection: direction,
      mechanism: plan.mechanism_chain.map((item) => item.statement).join(' → '),
      variables,
      pareto: {
        novelty: plan.scores.novelty,
        feasibility: plan.scores.method,
        identification: plan.scores.theory,
        dataReadiness: plan.scores.data,
        policyValue: plan.scores.policy_value,
      },
    }],
    selectedIdeaId: undefined,
  })
}

export interface DiscoveryPageProps {
  projectId: string
  step: DiscoveryRouteStep
  onChangeStep: (projectId: string, step: DiscoveryRouteStep) => void
  onOpenOverview: (projectId: string) => void
  onOpenLibrary: (kind: ResourceKind) => void
  onCreateDemoTask: (handoff: DiscoveryHandoff) => void
  onLaunchRun: (run: RunSnapshot) => void
  publicDemo: boolean
}

function useProductRevision(): void {
  const [, setRevision] = useState(0)
  useEffect(
    () => frontendDataSource.subscribe(() => setRevision((current) => current + 1)),
    [],
  )
}

function ProductCallout({
  tone = 'neutral',
  icon,
  children,
}: {
  tone?: 'neutral' | 'attention' | 'positive'
  icon: ReactNode
  children: ReactNode
}) {
  return (
    <div className={`discovery-callout is-${tone}`}>
      <span aria-hidden="true">{icon}</span>
      <div>{children}</div>
    </div>
  )
}

function BriefStep({ project }: { project: Project }) {
  const brief = project.discovery.brief

  function updateBrief<K extends keyof DiscoveryBrief>(
    key: K,
    value: DiscoveryBrief[K],
  ): void {
    frontendDataSource.updateDiscoveryDraft(project.id, {
      brief: { ...brief, [key]: value },
    })
  }

  return (
    <div className="discovery-step-content">
      <div className="discovery-step-heading">
        <div>
          <span className="product-eyebrow">STEP 01</span>
          <h2>把研究意图写成清晰边界</h2>
          <p>这里记录的是研究发现输入，不会直接启动正式执行。</p>
        </div>
        <span className="discovery-save-state"><CheckCircle2 size={14} />自动保存</span>
      </div>

      <div className="discovery-form">
        <label className="is-wide">
          <span>研究问题</span>
          <textarea
            rows={3}
            value={brief.researchQuestion}
            onChange={(event) => updateBrief('researchQuestion', event.target.value)}
            placeholder="例如：绿色信贷政策如何影响重污染企业的绿色创新？"
          />
          <small>用一个可证伪、可落实到观测单位的问题开始。</small>
        </label>
        <label>
          <span>分析对象</span>
          <input
            value={brief.unitOfAnalysis}
            onChange={(event) => updateBrief('unitOfAnalysis', event.target.value)}
            placeholder="企业—年度"
          />
        </label>
        <label>
          <span>样本期间</span>
          <input
            value={brief.samplePeriod}
            onChange={(event) => updateBrief('samplePeriod', event.target.value)}
            placeholder="2012—2024"
          />
        </label>
        <label>
          <span>预期数据结构</span>
          <select
            value={brief.dataStructureHint}
            onChange={(event) => updateBrief(
              'dataStructureHint',
              event.target.value as DiscoveryBrief['dataStructureHint'],
            )}
          >
            {(Object.entries(DATA_STRUCTURE_LABEL) as Array<
              [DiscoveryBrief['dataStructureHint'], string]
            >).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        <label>
          <span>期望产出</span>
          <input
            value={brief.goal}
            onChange={(event) => updateBrief('goal', event.target.value)}
            placeholder="形成可执行的因果识别研究计划"
          />
        </label>
        <label className="is-wide">
          <span>研究约束</span>
          <textarea
            rows={4}
            value={brief.constraints.join('\n')}
            onChange={(event) => updateBrief(
              'constraints',
              event.target.value
                .split('\n')
                .map((item) => item.trim())
                .filter(Boolean),
            )}
            placeholder={'每行一条，例如：\n优先使用公开数据\n不读取隐藏参考结果'}
          />
          <small>每行一条。这些约束会进入科学十项与正式研究输入。</small>
        </label>
      </div>

      <ProductCallout tone="positive" icon={<ShieldCheck size={17} />}>
        <strong>发现区与正式执行区保持隔离</strong>
        <p>此处只整理研究意图与证据。正式任务仍需人工检查输入边界。</p>
      </ProductCallout>
    </div>
  )
}

function ResourcesStep({
  project,
  bundle,
  onOpenLibrary,
  replay = false,
}: {
  project: Project
  bundle: EvidenceBundle
  onOpenLibrary: (kind: ResourceKind) => void
  replay?: boolean
}) {
  return (
    <div className="discovery-step-content">
      <div className="discovery-step-heading">
        <div>
          <span className="product-eyebrow">STEP 02</span>
          <h2>建立项目资源篮</h2>
          <p>文献、政策、数据和方法先成为证据链接，不直接写入正式任务。</p>
        </div>
        <span className="discovery-counter">{bundle.links.length} 条资源</span>
      </div>

      <div className="resource-basket-summary">
        {(Object.keys(RESOURCE_META) as ResourceKind[]).map((kind) => {
          const meta = RESOURCE_META[kind]
          const Icon = meta.icon
          return (
            <button type="button" key={kind} onClick={() => onOpenLibrary(kind)}>
              <span><Icon size={17} aria-hidden="true" /></span>
              <strong>{meta.label}</strong>
              <b>{bundle.counts[kind]}</b>
              <small>打开资源库</small>
              <ChevronRight size={15} aria-hidden="true" />
            </button>
          )
        })}
      </div>

      {bundle.links.length > 0 ? (
        <div className="resource-basket-list" role="list" aria-label="已加入的项目资源">
          {(Object.keys(RESOURCE_META) as ResourceKind[]).flatMap((kind) => (
            bundle.resources[kind].map((resource) => (
              <article role="listitem" key={`${kind}-${resource.id}`}>
                <span className="resource-basket-list__kind">
                  {RESOURCE_META[kind].label}
                </span>
                <div>
                  <strong>{resource.title}</strong>
                  <small>{resource.source} · {resource.tags.slice(0, 2).join(' / ') || '未分类'}</small>
                </div>
                <span className={`resource-availability is-${resource.availability}`}>
                  {resource.availability === 'available'
                    ? '可用'
                    : resource.availability === 'metadata_only'
                      ? '仅元数据'
                      : '暂不可用'}
                </span>
                <button
                  type="button"
                  className="product-icon-button"
                  onClick={() => frontendDataSource.removeProjectResource(
                    project.id,
                    kind,
                    resource.id,
                  )}
                  aria-label={`从项目资源篮移除${resource.title}`}
                  title="移出资源篮"
                >
                  <Trash2 size={14} aria-hidden="true" />
                </button>
              </article>
            ))
          ))}
        </div>
      ) : (
        <section className="product-empty is-compact">
          <Link2 size={24} aria-hidden="true" />
          <h3>资源篮还是空的</h3>
          <p>从任意资源库加入条目，回到这里就会形成项目 EvidenceBundle。</p>
          <button
            type="button"
            className="product-button"
            onClick={() => onOpenLibrary('literature')}
          >
            浏览文献库
            <ArrowRight size={15} aria-hidden="true" />
          </button>
        </section>
      )}

      <section className="demo-generator">
        <span><Network size={18} aria-hidden="true" /></span>
        <div>
          <strong>
            {replay
              ? '证据检索已完成'
              : project.discovery.gapCards.length
              ? 'GapCard 已准备'
              : '根据简报与资源篮生成 GapCard'}
          </strong>
          <p>
            {replay
              ? '文献、政策、数据与方法已汇入项目；下一步分析研究趋势与研究空白。'
              : '根据当前项目内容整理；需要模型或研究服务的步骤会单独提示。'}
          </p>
        </div>
        <button
          type="button"
          className="product-button"
          disabled={replay || project.discovery.gapCards.length > 0}
          onClick={() => generateDemoGap(project, bundle)}
        >
          {replay || project.discovery.gapCards.length ? <Check size={15} /> : <Sparkles size={15} />}
          {replay
            ? '证据包已就绪'
            : project.discovery.gapCards.length
              ? '已生成'
              : '生成 1 张 GapCard'}
        </button>
      </section>

      <ProductCallout tone="attention" icon={<CircleAlert size={17} />}>
        <strong>数据目录不是本地文件</strong>
        <p>
          只有真实导入并具备文件名、SHA-256 与文件大小的文件，才会进入正式
          datasetRefs。
        </p>
      </ProductCallout>
    </div>
  )
}

function GapStep({
  project,
  bundle,
  replay = false,
}: {
  project: Project
  bundle: EvidenceBundle
  replay?: boolean
}) {
  const firstGapId = project.discovery.gapCards[0]?.id ?? ''
  const [activeGapId, setActiveGapId] = useState(firstGapId)
  const activeGap = project.discovery.gapCards.find((gap) => gap.id === activeGapId)
    ?? project.discovery.gapCards[0]

  function updateGap(key: keyof Pick<GapCard, 'title' | 'evidence' | 'opportunity'>, value: string) {
    if (!activeGap) return
    frontendDataSource.updateDiscoveryDraft(project.id, {
      gapCards: project.discovery.gapCards.map((gap) => (
        gap.id === activeGap.id ? { ...gap, [key]: value } : gap
      )),
    })
  }

  return (
    <div className="discovery-step-content">
      <div className="discovery-step-heading">
        <div>
          <span className="product-eyebrow">STEP 03</span>
          <h2>从证据关系中提炼研究缺口</h2>
          <p>GapCard 同时记录已有证据和仍可验证的机会，避免只写宽泛“研究不足”。</p>
        </div>
        <span className="discovery-counter">{project.discovery.gapCards.length} 张 GapCard</span>
      </div>

      {activeGap ? (
        <div className="gap-workspace">
          <nav className="gap-list" aria-label="研究缺口">
            {project.discovery.gapCards.map((gap, index) => (
              <button
                type="button"
                key={gap.id}
                className={gap.id === activeGap.id ? 'is-active' : ''}
                onClick={() => setActiveGapId(gap.id)}
              >
                <span>{String(index + 1).padStart(2, '0')}</span>
                <strong>{gap.title || '未命名缺口'}</strong>
                <small>{gap.resourceIds.length} 条关联证据</small>
                <ChevronRight size={14} aria-hidden="true" />
              </button>
            ))}
          </nav>
          <section className="gap-editor">
            <header>
              <span className="product-eyebrow">GAPCARD · 可编辑</span>
              <span><Network size={14} aria-hidden="true" />证据 → 机会</span>
            </header>
            <label>
              <span>缺口标题</span>
              <input
                value={activeGap.title}
                onChange={(event) => updateGap('title', event.target.value)}
              />
            </label>
            <label>
              <span>现有证据说明了什么</span>
              <textarea
                rows={5}
                value={activeGap.evidence}
                onChange={(event) => updateGap('evidence', event.target.value)}
              />
            </label>
            <label>
              <span>仍可验证的研究机会</span>
              <textarea
                rows={5}
                value={activeGap.opportunity}
                onChange={(event) => updateGap('opportunity', event.target.value)}
              />
            </label>
            <footer>
              <span><Link2 size={13} aria-hidden="true" />关联资源</span>
              <strong>{activeGap.resourceIds.length}</strong>
              <small>资源引用会随 GapCard 一起进入后续假设。</small>
            </footer>
          </section>
        </div>
      ) : (
        <section className="product-empty is-compact">
          <Network size={24} aria-hidden="true" />
          <h3>尚未生成 GapCard</h3>
          <p>先在资源篮加入证据，系统会将其整理为可审阅、可编辑的空白候选。</p>
          <button
            type="button"
            className="product-button"
            onClick={() => generateDemoGap(project, bundle)}
          >
            <Sparkles size={15} aria-hidden="true" />
            生成 GapCard
          </button>
        </section>
      )}

      {activeGap ? (
        <section className="demo-generator">
          <span><Lightbulb size={18} aria-hidden="true" /></span>
          <div>
            <strong>
              {replay
                ? '研究空白已形成可检验方向'
                : project.discovery.ideaCards.length >= 3
                ? '候选假设已准备'
                : '从 GapCard 生成 3 个候选假设'}
            </strong>
            <p>
              {replay
                ? '下一步将围绕基准效应、机制路径和边界条件生成并列候选假设。'
                : '候选会覆盖基准效应、机制路径和异质性边界，并保留独立 Pareto 维度。'}
            </p>
          </div>
          <button
            type="button"
            className="product-button"
            disabled={replay || project.discovery.ideaCards.length >= 3}
            onClick={() => generateDemoIdeas(project)}
          >
            {replay || project.discovery.ideaCards.length >= 3
              ? <Check size={15} aria-hidden="true" />
              : <Sparkles size={15} aria-hidden="true" />}
            {replay
              ? `${project.discovery.gapCards.length} 张 GapCard`
              : project.discovery.ideaCards.length >= 3
                ? '已生成'
                : '生成候选假设'}
          </button>
        </section>
      ) : null}
    </div>
  )
}

function policyValueOf(idea: IdeaCard): number {
  return idea.pareto.policyValue
}

function ScoreMeter({ label, value }: { label: string; value: number }) {
  const normalized = Math.max(0, Math.min(5, value))
  return (
    <span className="idea-score">
      <span><small>{label}</small><b>{normalized.toFixed(1)}</b></span>
      <i aria-hidden="true"><b style={{ width: `${normalized * 20}%` }} /></i>
    </span>
  )
}

function IdeasGrid({
  project,
  selectable,
}: {
  project: Project
  selectable: boolean
}) {
  const ideas = project.discovery.ideaCards
  const selectedIdeaId = project.discovery.selectedIdeaId
  const [activeIdeaId, setActiveIdeaId] = useState(
    selectedIdeaId && ideas.some((idea) => idea.id === selectedIdeaId)
      ? selectedIdeaId
      : ideas[0]?.id ?? '',
  )

  useEffect(() => {
    setActiveIdeaId((current) => {
      if (selectable && selectedIdeaId && ideas.some((idea) => idea.id === selectedIdeaId)) {
        return selectedIdeaId
      }
      if (ideas.some((idea) => idea.id === current)) return current
      return selectedIdeaId && ideas.some((idea) => idea.id === selectedIdeaId)
        ? selectedIdeaId
        : ideas[0]?.id ?? ''
    })
  }, [ideas, selectable, selectedIdeaId])

  const activeIdeaIndex = Math.max(0, ideas.findIndex((idea) => idea.id === activeIdeaId))
  const activeIdea = ideas[activeIdeaIndex]

  if (!activeIdea) return null

  const selected = selectedIdeaId === activeIdea.id

  return (
    <div className={`idea-browser ${selectable ? 'is-selectable' : ''}`}>
      {ideas.length > 1 ? (
        <div className="idea-tabs" role="tablist" aria-label="切换候选假设">
          {ideas.map((idea, index) => {
            const active = idea.id === activeIdea.id
            const isSelected = idea.id === selectedIdeaId
            return (
              <button
                key={idea.id}
                type="button"
                role="tab"
                aria-selected={active}
                className={`idea-tab ${active ? 'is-active' : ''}`}
                onClick={() => setActiveIdeaId(idea.id)}
              >
                <span>假设 {index + 1}</span>
                {isSelected ? <b><Check size={12} aria-hidden="true" />已选择</b> : null}
              </button>
            )
          })}
        </div>
      ) : null}

      <div className="idea-grid">
        <article key={activeIdea.id} className={selected ? 'is-selected' : ''}>
          <header>
            <span>假设 {activeIdeaIndex + 1} / {ideas.length}</span>
            {selected ? <b><Check size={12} aria-hidden="true" />已选择</b> : null}
          </header>
          <h3>{activeIdea.title}</h3>
          <p className="idea-grid__hypothesis">{activeIdea.hypothesis}</p>
          <dl>
            <div>
              <dt>预期方向</dt>
              <dd>{DIRECTION_LABEL[activeIdea.expectedDirection]}</dd>
            </div>
            <div>
              <dt>机制链</dt>
              <dd>{activeIdea.mechanism}</dd>
            </div>
            <div>
              <dt>变量</dt>
              <dd>{activeIdea.variables.map((variable) => variable.label).join('、') || '待补充'}</dd>
            </div>
          </dl>
          {selectable ? (
            <>
              <div className="idea-scores" aria-label={`${activeIdea.title}的 Pareto 维度`}>
                <ScoreMeter label="新颖性" value={activeIdea.pareto.novelty} />
                <ScoreMeter label="数据基础" value={activeIdea.pareto.dataReadiness} />
                <ScoreMeter label="识别强度" value={activeIdea.pareto.identification} />
                <ScoreMeter label="政策价值" value={policyValueOf(activeIdea)} />
              </div>
              <button
                type="button"
                className={`product-button ${selected ? 'is-selected' : ''}`}
                disabled={selected}
                onClick={() => frontendDataSource.selectDiscoveryIdea(project.id, activeIdea.id)}
              >
                {selected ? <Check size={15} aria-hidden="true" /> : <Scale size={15} aria-hidden="true" />}
                {selected ? '当前选择' : '选择此假设'}
              </button>
            </>
          ) : null}
        </article>
      </div>
    </div>
  )
}

function IdeasStep({ project }: { project: Project }) {
  return (
    <div className="discovery-step-content">
      <div className="discovery-step-heading">
        <div>
          <span className="product-eyebrow">STEP 04</span>
          <h2>把研究空白转成可检验的候选假设</h2>
          <p>每张 IdeaCard 同时给出命题、方向、机制和变量，不在这里提前冻结方法。</p>
        </div>
        <span className="discovery-counter">{project.discovery.ideaCards.length} 个候选</span>
      </div>
      {project.discovery.ideaCards.length > 0 ? (
        <IdeasGrid project={project} selectable={false} />
      ) : (
        <section className="product-empty is-compact">
          <Lightbulb size={24} aria-hidden="true" />
          <h3>尚未生成候选假设</h3>
          <p>可以先返回编辑 GapCard，也可以根据当前项目内容生成候选。</p>
        </section>
      )}
      {project.discovery.ideaCards.length < 3 ? (
        <section className="demo-generator">
          <span><Sparkles size={18} aria-hidden="true" /></span>
          <div>
            <strong>补齐 3 个候选假设</strong>
            <p>当前根据项目内已有信息生成，后续可再用研究服务补充证据。</p>
          </div>
          <button
            type="button"
            className="product-button"
            onClick={() => generateDemoIdeas(project)}
          >
            生成候选假设
          </button>
        </section>
      ) : null}
      <ProductCallout tone="neutral" icon={<GitBranch size={17} />}>
        <strong>候选保持并列</strong>
        <p>下一步会分维度比较这些构想；系统不会用一个总分替代人工判断。</p>
      </ProductCallout>
    </div>
  )
}

function DecisionStep({ project }: { project: Project }) {
  const selected = project.discovery.ideaCards.find(
    (idea) => idea.id === project.discovery.selectedIdeaId,
  )

  return (
    <div className="discovery-step-content">
      <div className="discovery-step-heading">
        <div>
          <span className="product-eyebrow">STEP 05</span>
          <h2>按 Pareto 维度比较并人工选择</h2>
          <p>新颖性、数据基础、识别强度与政策价值分别保留，不计算综合总分。</p>
        </div>
        <span className={`discovery-counter ${selected ? 'is-positive' : ''}`}>
          {selected ? '已选择 1 个构想' : '等待选择'}
        </span>
      </div>
      <div className="pareto-notice">
        <Scale size={18} aria-hidden="true" />
        <div>
          <strong>没有“第一名”</strong>
          <p>较弱的单一维度可能是需要补证据的风险，也可能是值得保留的研究取舍。</p>
        </div>
      </div>
      <IdeasGrid project={project} selectable />
      {project.discovery.ideaCards.length < 3 ? (
        <section className="demo-generator">
          <span><Sparkles size={18} aria-hidden="true" /></span>
          <div>
            <strong>比较前先补齐候选</strong>
            <p>当前只有 {project.discovery.ideaCards.length} 个构想，前端可补齐到 3 个。</p>
          </div>
          <button
            type="button"
            className="product-button"
            onClick={() => generateDemoIdeas(project)}
          >
            补齐候选
          </button>
        </section>
      ) : null}
      {selected ? (
        <ProductCallout tone="positive" icon={<CheckCircle2 size={17} />}>
          <strong>已选择：{selected.title}</strong>
          <p>在进入正式任务前仍可修改；系统不会替你自动冻结研究方案。</p>
        </ProductCallout>
      ) : (
        <ProductCallout tone="attention" icon={<CircleAlert size={17} />}>
          <strong>请选择一个候选假设</strong>
          <p>选定后，系统才能准备包含假设、机制与变量的科学十项输入。</p>
        </ProductCallout>
      )}
    </div>
  )
}

function PreviewValue({
  label,
  children,
}: {
  label: string
  children: ReactNode
}) {
  return (
    <div className="handoff-preview__value">
      <span>{label}</span>
      <strong>{children}</strong>
    </div>
  )
}

function HandoffStep({
  project,
  handoff,
  onCreateDemoTask,
}: {
  project: Project
  handoff: DiscoveryHandoff | null
  onCreateDemoTask: (handoff: DiscoveryHandoff) => void
}) {
  if (!handoff) {
    return (
      <section className="product-empty is-compact">
        <FileCheck2 size={24} aria-hidden="true" />
        <h3>尚未完成 H0 审阅</h3>
        <p>请先选择一个候选假设，再准备科学十项所需的研究输入。</p>
      </section>
    )
  }

  const input = handoff.caseInput
  const selectedIdea = project.discovery.ideaCards.find(
    (idea) => idea.id === project.discovery.selectedIdeaId,
  )
  const proposalConfirmed = project.discovery.scientificTen?.status === 'confirmed'

  return (
    <div className="discovery-step-content">
      <div className="discovery-step-heading">
        <div>
          <span className="product-eyebrow">STEP 06</span>
          <h2>确认科学十项输入</h2>
          <p>先核对研究问题、假设、变量、数据与证据边界，再进入后续任务。</p>
        </div>
        <span className={`discovery-counter ${handoff.readyForFormalTask ? 'is-positive' : ''}`}>
          {handoff.readyForFormalTask ? '正式字段已齐备' : `${handoff.missingFields.length} 项待补充`}
        </span>
      </div>

      <ScientificTenPanel project={project} />

      <section className="handoff-preview">
        <header>
          <span><PackageCheck size={18} aria-hidden="true" /></span>
          <div>
            <strong>研究输入草稿</strong>
            <small>{input.caseId} · 当前项目</small>
          </div>
          <span className="product-status is-demo">待确认</span>
        </header>
        <div className="handoff-preview__grid">
          <PreviewValue label="标题">{input.title || '待补充'}</PreviewValue>
          <PreviewValue label="分析对象">{input.unitOfAnalysis || '待补充'}</PreviewValue>
          <PreviewValue label="样本期间">{input.samplePeriod || '待补充'}</PreviewValue>
          <PreviewValue label="数据结构">{DATA_STRUCTURE_LABEL[input.dataStructureHint]}</PreviewValue>
          <PreviewValue label="研究问题">{input.researchQuestion || '待补充'}</PreviewValue>
          <PreviewValue label="选定构想">{selectedIdea?.title || '尚未选择'}</PreviewValue>
        </div>
        <div className="handoff-preview__collections">
          <div>
            <span>假设</span>
            <strong>{input.hypotheses.length}</strong>
            <small>{input.hypotheses[0]?.statement || '待补充'}</small>
          </div>
          <div>
            <span>变量定义</span>
            <strong>{input.variables.length}</strong>
            <small>{input.variables.map((variable) => variable.label).slice(0, 3).join('、') || '待补充'}</small>
          </div>
          <div>
            <span>已导入数据文件</span>
            <strong>{input.datasetRefs.length}</strong>
            <small>必须同时具备文件名、哈希和大小</small>
          </div>
          <div>
            <span>已确认政策事实</span>
            <strong>{input.knownPolicyFacts.length}</strong>
            <small>政策摘要不会自动转为事实</small>
          </div>
        </div>
      </section>

      <section className={`handoff-requirements ${handoff.missingFields.length ? 'has-missing' : ''}`}>
        <header>
          {handoff.missingFields.length
            ? <CircleAlert size={18} aria-hidden="true" />
            : <CheckCircle2 size={18} aria-hidden="true" />}
          <div>
            <strong>
              {handoff.missingFields.length ? '正式任务仍缺少以下输入' : '正式任务的必要输入已齐备'}
            </strong>
            <p>缺失项需由用户确认或补充后，才会进入方案生成。</p>
          </div>
        </header>
        {handoff.missingFields.length ? (
          <ul>
            {handoff.missingFields.map((field) => (
              <li key={field}><CircleAlert size={13} aria-hidden="true" />{field}</li>
            ))}
          </ul>
        ) : null}
      </section>

      <ProductCallout tone="attention" icon={<ShieldCheck size={17} />}>
        <strong>边界检查</strong>
        <p>
          EvidenceBundle 含 {handoff.evidenceBundle.links.length} 条资源链接；
          datasetRefs 含 {input.datasetRefs.length} 个真实文件；knownPolicyFacts 含{' '}
          {input.knownPolicyFacts.length} 条人工确认事实。三类材料分别记录，避免来源混用。
        </p>
      </ProductCallout>

      <section className="handoff-action">
        <span><Sparkles size={20} aria-hidden="true" /></span>
        <div>
          <strong>进入后续研究任务</strong>
          <p>当前入口用于查看 H1–H4 流程；正式执行仍以数据、方法与人工确认状态为准。</p>
        </div>
        <button
          type="button"
          className="product-button is-primary"
          disabled={!selectedIdea || !proposalConfirmed}
          onClick={() => {
            if (!selectedIdea || !proposalConfirmed) return
            frontendDataSource.updateDiscoveryStep(project.id, 6, {
              completedSteps: [1, 2, 3, 4, 5, 6],
            })
            frontendDataSource.updateProject(project.id, { status: 'handoff_ready' })
            onCreateDemoTask(handoff)
          }}
        >
          {!selectedIdea
            ? '请先选择候选假设'
            : proposalConfirmed
              ? '进入流程预览'
              : '请先确认科学十项'}
          <ArrowRight size={15} aria-hidden="true" />
        </button>
      </section>
    </div>
  )
}

function sourceLocatorLabel(hit: DiscoveryPlanGeneration['evidenceBundle']['evidence_hits'][number]): string {
  const locator = hit.source_locator
  if (locator.page_start) {
    return locator.page_end && locator.page_end !== locator.page_start
      ? `第 ${locator.page_start}–${locator.page_end} 页`
      : `第 ${locator.page_start} 页`
  }
  if (locator.section) return locator.section
  if (locator.paragraph) return `第 ${locator.paragraph} 段`
  return '已绑定原文位置'
}

function LiveResourcesStep({
  project,
  generation,
  busy,
  error,
  onGenerate,
}: {
  project: Project
  generation: DiscoveryPlanGeneration | null
  busy: boolean
  error: string | null
  onGenerate: () => void
}) {
  const hits = generation?.evidenceBundle.evidence_hits ?? []
  const diagnostics = generation?.evidenceBundle.retrieval_diagnostics
  return (
    <div className="discovery-step-content">
      <div className="discovery-step-heading">
        <div>
          <span className="product-eyebrow">STEP 02 · KNOWLEDGE SERVICE</span>
          <h2>检索可定位原文并生成证据约束草案</h2>
          <p>向量检索负责召回，图谱关系只作候选提示；Qwen 的每项判断必须引用真实 chunk_id。</p>
        </div>
        <span className={`discovery-counter ${hits.length ? 'is-positive' : ''}`}>
          {hits.length ? `${hits.length} 条原文证据` : '等待检索'}
        </span>
      </div>

      <section className="demo-generator">
        <span><Network size={18} aria-hidden="true" /></span>
        <div>
          <strong>{generation ? 'EvidenceBundle 与 DiscoveryPlan 已生成' : '启动真实发现链路'}</strong>
          <p>{project.discovery.brief.researchQuestion || '请先在步骤 1 填写研究问题。'}</p>
        </div>
        <button
          type="button"
          className="product-button is-primary"
          disabled={busy || project.discovery.brief.researchQuestion.trim().length < 2}
          onClick={onGenerate}
        >
          {busy ? '检索与规划中…' : generation ? '重新检索并生成' : '检索并生成候选'}
          {!busy && <ArrowRight size={15} aria-hidden="true" />}
        </button>
      </section>

      {error ? (
        <ProductCallout tone="attention" icon={<CircleAlert size={17} />}>
          <strong>发现链路未完成</strong>
          <p>{error}</p>
        </ProductCallout>
      ) : null}

      {generation ? (
        <>
          <ProductCallout tone="positive" icon={<ShieldCheck size={17} />}>
            <strong>{generation.evidenceBundle.bundle_id}</strong>
            <p>
              语料快照 {generation.evidenceBundle.corpus_snapshot_id}；图谱返回的{' '}
              {generation.evidenceBundle.graph_edges.length} 条关系尚未被当作独立科学证据。
            </p>
          </ProductCallout>
          {diagnostics ? (
            <section className="handoff-preview" aria-label="检索多样性门诊断">
              <header>
                <span><ShieldCheck size={18} aria-hidden="true" /></span>
                <div>
                  <strong>检索多样性门</strong>
                  <small>top-k 后按文档限流，避免单篇文献垄断规划上下文</small>
                </div>
                <span className={`product-status ${diagnostics.diversity_gate_passed ? 'is-ready' : 'is-demo'}`}>
                  {diagnostics.diversity_gate_passed ? 'PASSED' : 'BLOCKED'}
                </span>
              </header>
              <div className="handoff-preview__grid">
                <PreviewValue label="返回证据">{diagnostics.returned_hits}/{diagnostics.requested_top_k}</PreviewValue>
                <PreviewValue label="不同文献">{diagnostics.unique_document_count} 篇</PreviewValue>
                <PreviewValue label="单篇最高命中">{diagnostics.max_hits_from_one_document}/{diagnostics.max_hits_per_document}</PreviewValue>
                <PreviewValue label="去重跳过">{diagnostics.skipped_by_document_cap} 个候选块</PreviewValue>
              </div>
            </section>
          ) : null}
          <div className="resource-basket-list" role="list" aria-label="知识服务返回的可追溯证据">
            {hits.map((hit) => (
              <article role="listitem" key={hit.chunk_id}>
                <span className="resource-basket-list__kind">{hit.source_type}</span>
                <div>
                  <strong>{hit.title}</strong>
                  <small>
                    {hit.publication_year ?? '年份未知'} · {sourceLocatorLabel(hit)} · {hit.chunk_id}
                  </small>
                </div>
                <span className="resource-availability is-available">{hit.evidence_status}</span>
              </article>
            ))}
          </div>
          {[...generation.evidenceBundle.warnings, ...generation.warnings].length ? (
            <ProductCallout tone="attention" icon={<CircleAlert size={17} />}>
              <strong>语料边界提示</strong>
              <p>{[...new Set([...generation.evidenceBundle.warnings, ...generation.warnings])].join('；')}</p>
            </ProductCallout>
          ) : null}
        </>
      ) : null}
    </div>
  )
}

function LiveGapStep({ generation }: { generation: DiscoveryPlanGeneration | null }) {
  if (!generation) {
    return (
      <section className="product-empty is-compact">
        <Network size={24} aria-hidden="true" />
        <h3>尚无可审阅的研究缺口</h3>
        <p>请先在数据中心检索步骤运行知识检索与研究发现规划。</p>
      </section>
    )
  }
  const plan = generation.plan
  return (
    <div className="discovery-step-content">
      <div className="discovery-step-heading">
        <div>
          <span className="product-eyebrow">STEP 03 · CORPUS-BOUNDED GAP</span>
          <h2>{plan.gap_title}</h2>
          <p>这是受当前语料快照约束的候选缺口，不是“全球文献从未研究”的断言。</p>
        </div>
        <span className="discovery-counter">{plan.gap_type}</span>
      </div>
      <section className="gap-editor">
        <label><span>缺口陈述</span><textarea rows={4} value={plan.gap_statement} readOnly /></label>
        <label><span>当前证据状态</span><textarea rows={4} value={plan.current_state} readOnly /></label>
        <label><span>缺失环节</span><textarea rows={4} value={plan.missing_piece} readOnly /></label>
        <label><span>研究价值</span><textarea rows={4} value={plan.why_important} readOnly /></label>
        <footer>
          <span><Link2 size={13} aria-hidden="true" />支持证据块</span>
          <strong>{generation.evidenceBundle.evidence_hits.length}</strong>
          <small>所有解释节点会在 H0 审阅后才标记为 human_verified。</small>
        </footer>
      </section>
    </div>
  )
}

function LiveIdeasStep({
  project,
  generation,
  selectable = false,
}: {
  project: Project
  generation: DiscoveryPlanGeneration | null
  selectable?: boolean
}) {
  if (!generation) {
    if (project.discovery.ideaCards.length) {
      return (
        <div className="discovery-step-content">
          <div className="discovery-step-heading">
            <div>
              <span className="product-eyebrow">{selectable ? 'STEP 05 · SAVED CANDIDATES' : 'STEP 04 · SAVED CANDIDATES'}</span>
              <h2>{selectable ? '从已保存候选中选择假设' : '查看项目中已保存的候选假设'}</h2>
              <p>这些候选保存在当前项目中，可用于生成科学十项；进入 H1 前仍需完成 H0 证据审阅。</p>
            </div>
            <span className="discovery-counter">{project.discovery.ideaCards.length} 个候选</span>
          </div>
          <IdeasGrid project={project} selectable={selectable} />
          <ProductCallout tone="attention" icon={<CircleAlert size={17} />}>
            <strong>当前使用已保存候选</strong>
            <p>本次会话尚无可提交的 Group1 发布包；科学十项可以继续编辑，但 H1 入口保持锁定。</p>
          </ProductCallout>
        </div>
      )
    }
    return (
      <section className="product-empty is-compact">
        <Lightbulb size={24} aria-hidden="true" />
        <h3>尚无候选假设</h3>
        <p>真实链路一次只生成一个内部一致、可证伪的候选方案。</p>
      </section>
    )
  }
  const plan = generation.plan
  return (
    <div className="discovery-step-content">
      <div className="discovery-step-heading">
        <div>
          <span className="product-eyebrow">{selectable ? 'STEP 05 · H0 REVIEW' : 'STEP 04 · DISCOVERY PLAN'}</span>
          <h2>{selectable ? '审阅并选择唯一候选' : '检查可证伪命题与机制链'}</h2>
          <p>Qwen 只负责起草；候选在 H0 前不具有科学批准状态。</p>
        </div>
        <span className="discovery-counter">1 个候选</span>
      </div>
      <IdeasGrid project={project} selectable={selectable} />
      <ProductCallout tone="neutral" icon={<GitBranch size={17} />}>
        <strong>证伪条件</strong>
        <p>{plan.falsifiable_form}</p>
      </ProductCallout>
      <ProductCallout tone="attention" icon={<CircleAlert size={17} />}>
        <strong>主要威胁与未解决冲突</strong>
        <p>{[...plan.major_threats, ...plan.unresolved_conflicts].join('；') || '模型未列出。'}</p>
      </ProductCallout>
    </div>
  )
}

function LiveDecisionStep({
  project,
  generation,
  release,
  reviewNote,
  busy,
  error,
  onReviewNoteChange,
  onReview,
}: {
  project: Project
  generation: DiscoveryPlanGeneration | null
  release: DiscoveryReleasePreviewWire | null
  reviewNote: string
  busy: boolean
  error: string | null
  onReviewNoteChange: (value: string) => void
  onReview: () => void
}) {
  if (!generation) return <LiveIdeasStep project={project} generation={null} selectable />
  const selected = project.discovery.selectedIdeaId === 'hypothesis:online_candidate'
  const consistency = generation.consistencyReview
  const consistencyPassed = generation.finalConsistencyPassed && consistency?.decision === 'pass'
  const preservation = consistency
    ? [
        `暴露${consistency.exposure_preserved ? '✓' : '✗'}`,
        `结果${consistency.outcome_preserved ? '✓' : '✗'}`,
        `限定语${consistency.qualifiers_preserved ? '✓' : '✗'}`,
      ].join(' · ')
    : '尚无 Reviewer 回执'
  return (
    <>
      <LiveIdeasStep project={project} generation={generation} selectable />
      <ProductCallout
        tone={consistencyPassed ? 'positive' : 'attention'}
        icon={consistencyPassed ? <CheckCircle2 size={17} /> : <CircleAlert size={17} />}
      >
        <strong>问题—计划一致性 Reviewer：{consistencyPassed ? '通过' : '阻断'}</strong>
        <p>
          {preservation}；检索/规划 {generation.retrievalRounds.length || 1} 轮，定向修复 {generation.repairCount} 次。
          {consistency?.missing_concepts.length ? ` 缺失概念：${consistency.missing_concepts.join('、')}。` : ''}
          {consistency?.rationale ? ` ${consistency.rationale}` : ''}
        </p>
      </ProductCallout>
      <section className={`handoff-requirements ${consistencyPassed ? '' : 'has-missing'}`}>
        <header>
          {release
            ? <CheckCircle2 size={18} aria-hidden="true" />
            : consistencyPassed
              ? <ShieldCheck size={18} aria-hidden="true" />
              : <CircleAlert size={18} aria-hidden="true" />}
          <div>
            <strong>{release ? 'H0 审阅已形成可验证发布预览' : consistencyPassed ? 'H0 人工科学审阅' : 'H0 入口已由一致性门锁定'}</strong>
            <p>{consistencyPassed
              ? '请核对原文位置、语料边界、变量定义、机制链和证伪条件，并留下具体说明。'
              : '系统在一次定向修复后仍未完整保留原问题；请重新检索或修改问题边界，不能人工直接放行该草案。'}</p>
          </div>
        </header>
        <label>
          <span>审阅记录</span>
          <textarea
            rows={4}
            value={reviewNote}
            onChange={(event) => onReviewNoteChange(event.target.value)}
            placeholder="例如：已逐条核对引用 chunk；缺口仅限当前语料；机制仍需在 H1/H2 设计阶段验证。"
          />
        </label>
        <button
          type="button"
          className="product-button is-primary"
          disabled={!selected || !consistencyPassed || reviewNote.trim().length < 10 || busy}
          onClick={onReview}
        >
          {busy ? '正在运行 Group1 校验…' : release ? '重新生成审阅预览' : '完成 H0 审阅'}
          {!busy && <ArrowRight size={15} aria-hidden="true" />}
        </button>
      </section>
      {error ? (
        <ProductCallout tone="attention" icon={<CircleAlert size={17} />}>
          <strong>H0 校验未通过</strong><p>{error}</p>
        </ProductCallout>
      ) : null}
      {release ? (
        <ProductCallout tone="positive" icon={<CheckCircle2 size={17} />}>
          <strong>Group1 发布包校验通过</strong>
          <p>
            {release.gap_cards.length} 张 GapCard、{release.hypothesis_cards.length} 张 HypothesisCard；
            审阅者 {release.reviewer}。下一步可批准进入 H1。
          </p>
        </ProductCallout>
      ) : null}
    </>
  )
}

function LiveHandoffStep({
  project,
  generation,
  release,
  reviewNote,
  approvalReason,
  busy,
  error,
  onApprovalReasonChange,
  onLaunch,
}: {
  project: Project
  generation: DiscoveryPlanGeneration | null
  release: DiscoveryReleasePreviewWire | null
  reviewNote: string
  approvalReason: string
  busy: boolean
  error: string | null
  onApprovalReasonChange: (value: string) => void
  onLaunch: () => void
}) {
  const proposalConfirmed = project.discovery.scientificTen?.status === 'confirmed'
  if (!generation || !release) {
    return (
      <div className="discovery-step-content">
        <ScientificTenPanel project={project} />
        <section className="product-empty is-compact">
          <FileCheck2 size={24} aria-hidden="true" />
          <h3>尚未完成 H0 审阅</h3>
          <p>请先在假设选择中完成 H0 审阅，再准备科学十项与 H1 所需输入。</p>
        </section>
      </div>
    )
  }
  const hypothesis = release.hypothesis_cards[0] ?? {}
  const readiness = generation.executionReadiness
  const readyDatasetCount = readiness?.dataset_candidates.filter((item) => item.status === 'ready').length ?? 0
  const boundVariableCount = readiness?.variable_dictionary.filter((item) => item.status === 'bound').length ?? 0
  const readyStrategyCount = readiness?.identification_strategies.filter((item) => item.status === 'candidate_ready_for_h1_review').length ?? 0
  return (
    <div className="discovery-step-content">
      <div className="discovery-step-heading">
        <div>
          <span className="product-eyebrow">STEP 06 · H0 → H1</span>
          <h2>批准候选进入现有 H1 研究边界门</h2>
          <p>这一步创建真实后端 run；H0 批准不授权统计执行，也不授权任何结论。</p>
        </div>
        <span className="discovery-counter is-positive">发布包已校验</span>
      </div>
      <ScientificTenPanel project={project} />
      <section className="handoff-preview">
        <header>
          <span><PackageCheck size={18} aria-hidden="true" /></span>
          <div>
            <strong>{String(hypothesis.title ?? generation.plan.hypothesis_title)}</strong>
            <small>{generation.evidenceBundle.bundle_id}</small>
          </div>
          <span className="product-status is-ready">H0 REVIEWED</span>
        </header>
        <div className="handoff-preview__grid">
          <PreviewValue label="研究问题">{generation.originalQuestion}</PreviewValue>
          <PreviewValue label="图谱快照">{String(release.final_research_graph.snapshot_id ?? '已生成')}</PreviewValue>
          <PreviewValue label="证据块">{generation.evidenceBundle.evidence_hits.length}</PreviewValue>
          <PreviewValue label="数据执行">
            {readiness?.can_execute
              ? '合同完整；仍须 H1 人工批准后执行'
              : `BLOCKED · ${readiness?.blockers.length ?? 1} 项硬条件未满足`}
          </PreviewValue>
        </div>
      </section>
      <section className={`handoff-requirements ${readiness?.can_execute ? '' : 'has-missing'}`}>
        <header>
          {readiness?.can_execute
            ? <CheckCircle2 size={18} aria-hidden="true" />
            : <CircleAlert size={18} aria-hidden="true" />}
          <div>
            <strong>执行就绪编译器：{readiness?.can_execute ? 'READY FOR H1 REVIEW' : 'FAIL-CLOSED'}</strong>
            <p>
              数据资产 {readyDatasetCount}/{readiness?.dataset_candidates.length ?? 0}；
              字段绑定 {boundVariableCount}/{readiness?.variable_dictionary.length ?? 0}；
              识别策略 {readyStrategyCount}/{readiness?.identification_strategies.length ?? 0}。
              {!readiness?.can_execute ? ' 创建 H1 任务只用于补齐输入，不会启动统计执行。' : ''}
            </p>
          </div>
        </header>
        {!readiness?.can_execute && readiness?.blockers.length ? (
          <ul aria-label="执行阻断项">
            {readiness.blockers.slice(0, 6).map((blocker) => <li key={blocker}>{blocker}</li>)}
          </ul>
        ) : null}
      </section>
      <section className="handoff-action">
        <span><ShieldCheck size={20} aria-hidden="true" /></span>
        <div>
          <strong>记录 H0 批准并创建 H1 任务</strong>
          <p>批准理由会和发布包哈希、证据引用、图谱快照一起写入上游 provenance。</p>
          <textarea
            rows={3}
            value={approvalReason}
            onChange={(event) => onApprovalReasonChange(event.target.value)}
            placeholder="说明为何该候选足以进入 H1 设计审阅，以及仍需补充哪些数据或识别条件。"
          />
        </div>
        <button
          type="button"
          className="product-button is-primary"
          disabled={busy || !proposalConfirmed || reviewNote.trim().length < 10 || approvalReason.trim().length < 10}
          onClick={onLaunch}
        >
          {busy ? '正在创建 H1 任务…' : proposalConfirmed ? '批准并进入 H1' : '请先确认科学十项'}
          {!busy && <ArrowRight size={15} aria-hidden="true" />}
        </button>
      </section>
      {error ? (
        <ProductCallout tone="attention" icon={<CircleAlert size={17} />}>
          <strong>方案输入未完成</strong><p>{error}</p>
        </ProductCallout>
      ) : null}
    </div>
  )
}

export function DiscoveryPage({
  projectId,
  step,
  onChangeStep,
  onOpenOverview,
  onOpenLibrary,
  onCreateDemoTask,
  onLaunchRun,
  publicDemo,
}: DiscoveryPageProps) {
  useProductRevision()
  const project = frontendDataSource.getProject(projectId)
  const currentNumber = ROUTE_NUMBER[step]
  const [generation, setGeneration] = useState<DiscoveryPlanGeneration | null>(null)
  const [release, setRelease] = useState<DiscoveryReleasePreviewWire | null>(null)
  const [reviewNote, setReviewNote] = useState('')
  const [approvalReason, setApprovalReason] = useState('')
  const [liveBusy, setLiveBusy] = useState(false)
  const [liveError, setLiveError] = useState<string | null>(null)

  useEffect(() => {
    setGeneration(null)
    setRelease(null)
    setReviewNote('')
    setApprovalReason('')
    setLiveError(null)
  }, [projectId])

  useEffect(() => {
    if (project && project.discovery.currentStep !== currentNumber) {
      frontendDataSource.updateDiscoveryDraft(project.id, { currentStep: currentNumber })
    }
  }, [currentNumber, project?.discovery.currentStep, project?.id])

  if (!project) {
    return (
      <main className="product-page">
        <section className="product-empty">
          <FileCheck2 size={28} aria-hidden="true" />
          <h1>无法恢复研究发现草稿</h1>
          <p>项目可能已被删除，或当前浏览器里没有这条记录。</p>
          <button type="button" className="product-button" onClick={() => onOpenOverview(projectId)}>
            <ArrowLeft size={16} aria-hidden="true" />
            返回项目
          </button>
        </section>
      </main>
    )
  }

  const activeProject: Project = project
  const bundle = frontendDataSource.getEvidenceBundle(activeProject.id)
  const handoff = frontendDataSource.buildDiscoveryHandoff(activeProject.id)
  const completed = new Set(activeProject.discovery.completedSteps)
  const currentMeta = DISCOVERY_STEPS[currentNumber - 1]
  const useSnapshotDiscovery = publicDemo || activeProject.id === SHOWCASE_PROJECT_ID
  const isShowcaseReplay = activeProject.id === SHOWCASE_PROJECT_ID
    && activeProject.status !== 'handoff_ready'

  async function generateLivePlan(): Promise<void> {
    setLiveBusy(true)
    setLiveError(null)
    try {
      const next = await workflowApi.generateDiscoveryPlan({
        question: activeProject.discovery.brief.researchQuestion,
        goal: activeProject.discovery.brief.goal,
        unitOfAnalysis: activeProject.discovery.brief.unitOfAnalysis,
        samplePeriod: activeProject.discovery.brief.samplePeriod,
        constraints: activeProject.discovery.brief.constraints,
      })
      applyLiveGeneration(activeProject, next)
      setGeneration(next)
      setRelease(null)
      setReviewNote('')
      setApprovalReason('')
    } catch (reason) {
      setLiveError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setLiveBusy(false)
    }
  }

  async function reviewLivePlan(): Promise<void> {
    if (!generation) return
    setLiveBusy(true)
    setLiveError(null)
    try {
      setRelease(await workflowApi.reviewDiscoveryPlan(generation, reviewNote))
    } catch (reason) {
      setRelease(null)
      setLiveError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setLiveBusy(false)
    }
  }

  async function launchLivePlan(): Promise<void> {
    if (!generation || !release || activeProject.discovery.scientificTen?.status !== 'confirmed') return
    setLiveBusy(true)
    setLiveError(null)
    try {
      const result = await workflowApi.launchDiscoveryPlan(
        generation,
        reviewNote,
        approvalReason,
      )
      frontendDataSource.updateDiscoveryStep(activeProject.id, 6, {
        completedSteps: [1, 2, 3, 4, 5, 6],
      })
      frontendDataSource.updateProject(activeProject.id, {
        status: 'handoff_ready',
        taskIds: Array.from(new Set([...activeProject.taskIds, result.run.id])),
      })
      onLaunchRun(result.run)
    } catch (reason) {
      setLiveError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setLiveBusy(false)
    }
  }

  function goTo(target: ProductDiscoveryStep, markCurrentComplete = false): void {
    const completedSteps = markCurrentComplete
      ? Array.from(new Set([...activeProject.discovery.completedSteps, currentNumber]))
        .sort((a, b) => a - b) as ProductDiscoveryStep[]
      : activeProject.discovery.completedSteps
    if (markCurrentComplete) {
      frontendDataSource.updateDiscoveryStep(activeProject.id, target, { completedSteps })
    } else {
      frontendDataSource.updateDiscoveryDraft(activeProject.id, {
        currentStep: target,
        completedSteps,
      })
    }
    if (activeProject.status === 'draft' && target > 1) {
      frontendDataSource.updateProject(activeProject.id, { status: 'active' })
    }
    onChangeStep(activeProject.id, NUMBER_ROUTE[target])
  }

  const content = (() => {
    switch (step) {
      case 'brief':
        return <BriefStep project={activeProject} />
      case 'resources':
        return useSnapshotDiscovery
          ? (
            <ResourcesStep
              project={activeProject}
              bundle={bundle}
              onOpenLibrary={onOpenLibrary}
              replay={isShowcaseReplay}
            />
          )
          : (
            <LiveResourcesStep
              project={activeProject}
              generation={generation}
              busy={liveBusy}
              error={liveError}
              onGenerate={() => void generateLivePlan()}
            />
          )
      case 'gaps':
        return useSnapshotDiscovery
          ? <GapStep project={activeProject} bundle={bundle} replay={isShowcaseReplay} />
          : <LiveGapStep generation={generation} />
      case 'ideas':
        return useSnapshotDiscovery
          ? <IdeasStep project={activeProject} />
          : <LiveIdeasStep project={activeProject} generation={generation} />
      case 'decision':
        return useSnapshotDiscovery
          ? <DecisionStep project={activeProject} />
          : (
            <LiveDecisionStep
              project={activeProject}
              generation={generation}
              release={release}
              reviewNote={reviewNote}
              busy={liveBusy}
              error={liveError}
              onReviewNoteChange={(value) => {
                setReviewNote(value)
                setRelease(null)
              }}
              onReview={() => void reviewLivePlan()}
            />
          )
      case 'handoff':
        return useSnapshotDiscovery ? (
          <HandoffStep
            project={activeProject}
            handoff={handoff}
            onCreateDemoTask={onCreateDemoTask}
          />
        ) : (
          <LiveHandoffStep
            project={activeProject}
            generation={generation}
            release={release}
            reviewNote={reviewNote}
            approvalReason={approvalReason}
            busy={liveBusy}
            error={liveError}
            onApprovalReasonChange={setApprovalReason}
            onLaunch={() => void launchLivePlan()}
          />
        )
    }
  })()
  const canContinue = useSnapshotDiscovery
    || (currentNumber === 1
      ? activeProject.discovery.brief.researchQuestion.trim().length >= 2
      : currentNumber < 5
        ? Boolean(generation)
        : currentNumber === 5
          ? Boolean(release || activeProject.discovery.selectedIdeaId)
          : true)

  return (
    <main className="product-page discovery-page">
      <button
        type="button"
        className="product-back"
        onClick={() => onOpenOverview(activeProject.id)}
      >
        <ArrowLeft size={15} aria-hidden="true" />
        {activeProject.title}
      </button>

      <header className="discovery-page__header">
        <div>
          <span className="product-eyebrow">
            {isShowcaseReplay
              ? 'RESEARCH DISCOVERY · 知识服务 + QWEN'
              : useSnapshotDiscovery
                ? 'RESEARCH DISCOVERY · 已封存执行快照'
                : 'RESEARCH DISCOVERY · 知识服务 + GROUP1'}
          </span>
          <h1>{currentMeta.label}</h1>
          <p>{currentMeta.description}</p>
        </div>
        <span className="discovery-page__progress">
          <span>{currentNumber} / 6</span>
          <i aria-hidden="true"><b style={{ width: `${(currentNumber / 6) * 100}%` }} /></i>
        </span>
      </header>

      <div className="discovery-layout">
        <nav className="discovery-steps" aria-label="研究发现步骤">
          {DISCOVERY_STEPS.map((item) => {
            const Icon = item.icon
            const isCurrent = item.number === currentNumber
            const isComplete = completed.has(item.number)
              || (!isShowcaseReplay && activeProject.status === 'handoff_ready' && item.number <= 6)
            return (
              <button
                type="button"
                key={item.number}
                className={`${isCurrent ? 'is-current' : ''} ${isComplete ? 'is-complete' : ''}`}
                aria-current={isCurrent ? 'step' : undefined}
                onClick={() => goTo(item.number)}
              >
                <span className="discovery-steps__node" aria-hidden="true">
                  {isComplete ? <Check size={13} /> : <Icon size={15} />}
                </span>
                <span>
                  <small>步骤 {item.number}</small>
                  <strong>{item.label}</strong>
                  <em>{item.description}</em>
                </span>
                <ChevronRight size={14} aria-hidden="true" />
              </button>
            )
          })}
        </nav>

        <section className="discovery-workspace">
          {content}
          <footer className="discovery-navigation">
            <button
              type="button"
              className="product-button"
              disabled={currentNumber === 1}
              onClick={() => goTo((currentNumber - 1) as ProductDiscoveryStep)}
            >
              <ArrowLeft size={15} aria-hidden="true" />
              上一步
            </button>
            <span>
              <strong>{currentMeta.label}</strong>
              <small>
                {useSnapshotDiscovery
                  ? isShowcaseReplay
                    ? '研究进度与证据已保存到当前项目'
                    : '已封存案例快照保存在当前浏览器'
                  : '证据包仅保留在当前会话；H0/H1 状态写入后端'}
              </small>
            </span>
            {currentNumber < 6 ? (
              <button
                type="button"
                className="product-button is-primary"
                disabled={!canContinue}
                onClick={() => goTo(
                  (currentNumber + 1) as ProductDiscoveryStep,
                  true,
                )}
              >
                保存并继续
                <ArrowRight size={15} aria-hidden="true" />
              </button>
            ) : (
              <button
                type="button"
                className="product-button"
                onClick={() => onOpenOverview(activeProject.id)}
              >
                返回项目总览
                <ArrowRight size={15} aria-hidden="true" />
              </button>
            )}
          </footer>
        </section>
      </div>
    </main>
  )
}
