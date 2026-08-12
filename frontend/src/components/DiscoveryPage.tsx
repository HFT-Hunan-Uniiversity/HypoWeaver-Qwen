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
    label: '资源收集',
    description: '建立项目 EvidenceBundle',
    icon: BookOpen,
  },
  {
    number: 3,
    route: 'gaps',
    label: '图谱与缺口',
    description: '把证据关系转成 GapCard',
    icon: Network,
  },
  {
    number: 4,
    route: 'ideas',
    label: '候选构想',
    description: '形成机制、变量与可检验命题',
    icon: Lightbulb,
  },
  {
    number: 5,
    route: 'decision',
    label: '比较与选择',
    description: '分维度比较，不合成总分',
    icon: Scale,
  },
  {
    number: 6,
    route: 'handoff',
    label: '交接预览',
    description: '检查 CaseSubmission 草稿',
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

export interface DiscoveryPageProps {
  projectId: string
  step: DiscoveryRouteStep
  onChangeStep: (projectId: string, step: DiscoveryRouteStep) => void
  onOpenOverview: (projectId: string) => void
  onOpenLibrary: (kind: ResourceKind) => void
  onCreateDemoTask: (handoff: DiscoveryHandoff) => void
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
          <small>每行一条。正式交接时这些约束会进入 CaseSubmission 草稿。</small>
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
}: {
  project: Project
  bundle: EvidenceBundle
  onOpenLibrary: (kind: ResourceKind) => void
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
            {project.discovery.gapCards.length
              ? 'GapCard 已准备'
              : '根据简报与资源篮生成 GapCard'}
          </strong>
          <p>确定性前端演示：只整理当前页面已有内容，不调用模型或后端。</p>
        </div>
        <button
          type="button"
          className="product-button"
          disabled={project.discovery.gapCards.length > 0}
          onClick={() => generateDemoGap(project, bundle)}
        >
          {project.discovery.gapCards.length ? <Check size={15} /> : <Sparkles size={15} />}
          {project.discovery.gapCards.length ? '已生成' : '生成 1 张 GapCard'}
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
}: {
  project: Project
  bundle: EvidenceBundle
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
              <small>资源引用会随 GapCard 一起进入后续构想。</small>
            </footer>
          </section>
        </div>
      ) : (
        <section className="product-empty is-compact">
          <Network size={24} aria-hidden="true" />
          <h3>尚未生成 GapCard</h3>
          <p>先在资源篮加入证据，前端演示数据会在这里形成可编辑缺口。</p>
          <button
            type="button"
            className="product-button"
            onClick={() => generateDemoGap(project, bundle)}
          >
            <Sparkles size={15} aria-hidden="true" />
            生成演示 GapCard
          </button>
        </section>
      )}

      {activeGap ? (
        <section className="demo-generator">
          <span><Lightbulb size={18} aria-hidden="true" /></span>
          <div>
            <strong>
              {project.discovery.ideaCards.length >= 3
                ? '候选构想已准备'
                : '从 GapCard 生成 3 个候选构想'}
            </strong>
            <p>候选会覆盖基准效应、机制路径和异质性边界，并保留独立 Pareto 维度。</p>
          </div>
          <button
            type="button"
            className="product-button"
            disabled={project.discovery.ideaCards.length >= 3}
            onClick={() => generateDemoIdeas(project)}
          >
            {project.discovery.ideaCards.length >= 3
              ? <Check size={15} aria-hidden="true" />
              : <Sparkles size={15} aria-hidden="true" />}
            {project.discovery.ideaCards.length >= 3 ? '已生成' : '生成候选构想'}
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
  return (
    <div className={`idea-grid ${selectable ? 'is-selectable' : ''}`}>
      {project.discovery.ideaCards.map((idea, index) => {
        const selected = project.discovery.selectedIdeaId === idea.id
        return (
          <article key={idea.id} className={selected ? 'is-selected' : ''}>
            <header>
              <span>IDEA {String(index + 1).padStart(2, '0')}</span>
              {selected ? <b><Check size={12} aria-hidden="true" />已选择</b> : null}
            </header>
            <h3>{idea.title}</h3>
            <p className="idea-grid__hypothesis">{idea.hypothesis}</p>
            <dl>
              <div>
                <dt>预期方向</dt>
                <dd>{DIRECTION_LABEL[idea.expectedDirection]}</dd>
              </div>
              <div>
                <dt>机制链</dt>
                <dd>{idea.mechanism}</dd>
              </div>
              <div>
                <dt>变量</dt>
                <dd>{idea.variables.map((variable) => variable.label).join('、') || '待补充'}</dd>
              </div>
            </dl>
            {selectable ? (
              <>
                <div className="idea-scores" aria-label={`${idea.title}的 Pareto 维度`}>
                  <ScoreMeter label="新颖性" value={idea.pareto.novelty} />
                  <ScoreMeter label="数据基础" value={idea.pareto.dataReadiness} />
                  <ScoreMeter label="识别强度" value={idea.pareto.identification} />
                  <ScoreMeter label="政策价值" value={policyValueOf(idea)} />
                </div>
                <button
                  type="button"
                  className={`product-button ${selected ? 'is-selected' : ''}`}
                  onClick={() => frontendDataSource.selectDiscoveryIdea(project.id, idea.id)}
                >
                  {selected ? <Check size={15} aria-hidden="true" /> : <Scale size={15} aria-hidden="true" />}
                  {selected ? '当前选择' : '选择此构想'}
                </button>
              </>
            ) : null}
          </article>
        )
      })}
    </div>
  )
}

function IdeasStep({ project }: { project: Project }) {
  return (
    <div className="discovery-step-content">
      <div className="discovery-step-heading">
        <div>
          <span className="product-eyebrow">STEP 04</span>
          <h2>把缺口转成可检验的候选构想</h2>
          <p>每张 IdeaCard 同时给出命题、方向、机制和变量，不在这里提前冻结方法。</p>
        </div>
        <span className="discovery-counter">{project.discovery.ideaCards.length} 个候选</span>
      </div>
      {project.discovery.ideaCards.length > 0 ? (
        <IdeasGrid project={project} selectable={false} />
      ) : (
        <section className="product-empty is-compact">
          <Lightbulb size={24} aria-hidden="true" />
          <h3>尚未生成候选构想</h3>
          <p>可以先返回编辑 GapCard，也可以直接生成确定性的前端演示候选。</p>
        </section>
      )}
      {project.discovery.ideaCards.length < 3 ? (
        <section className="demo-generator">
          <span><Sparkles size={18} aria-hidden="true" /></span>
          <div>
            <strong>补齐 3 个候选构想</strong>
            <p>生成动作完全在浏览器中完成，不调用模型或后端。</p>
          </div>
          <button
            type="button"
            className="product-button"
            onClick={() => generateDemoIdeas(project)}
          >
            生成前端演示候选
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
          <p>选择仍可在创建演示任务前修改，不会自动冻结正式研究合同。</p>
        </ProductCallout>
      ) : (
        <ProductCallout tone="attention" icon={<CircleAlert size={17} />}>
          <strong>请选择一个候选构想</strong>
          <p>选定后，系统才能生成包含假设、机制与变量的交接草稿。</p>
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
        <h3>暂时无法生成交接草稿</h3>
        <p>返回比较页选择一个候选构想后再试。</p>
      </section>
    )
  }

  const input = handoff.caseInput
  const selectedIdea = project.discovery.ideaCards.find(
    (idea) => idea.id === project.discovery.selectedIdeaId,
  )

  return (
    <div className="discovery-step-content">
      <div className="discovery-step-heading">
        <div>
          <span className="product-eyebrow">STEP 06</span>
          <h2>预览 CaseSubmission 草稿</h2>
          <p>这是前端生成的交接对象；创建演示任务不会连接新后端。</p>
        </div>
        <span className={`discovery-counter ${handoff.readyForFormalTask ? 'is-positive' : ''}`}>
          {handoff.readyForFormalTask ? '正式字段已齐备' : `${handoff.missingFields.length} 项待补充`}
        </span>
      </div>

      <section className="handoff-preview">
        <header>
          <span><PackageCheck size={18} aria-hidden="true" /></span>
          <div>
            <strong>CaseSubmissionInput</strong>
            <small>{input.caseId} · 生成于本地浏览器</small>
          </div>
          <span className="product-status is-demo">前端演示</span>
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
            <p>缺失字段不会被演示数据或资源目录悄悄补齐。</p>
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
          {input.knownPolicyFacts.length} 条人工确认事实。三者不会互相冒充。
        </p>
      </ProductCallout>

      <section className="handoff-action">
        <span><Sparkles size={20} aria-hidden="true" /></span>
        <div>
          <strong>创建本地演示任务</strong>
          <p>使用这份草稿演示后半段流程；不发起真实 API 请求，也不修改数据库。</p>
        </div>
        <button
          type="button"
          className="product-button is-primary"
          disabled={!selectedIdea}
          onClick={() => {
            if (!selectedIdea) return
            frontendDataSource.updateDiscoveryStep(project.id, 6, {
              completedSteps: [1, 2, 3, 4, 5, 6],
            })
            frontendDataSource.updateProject(project.id, { status: 'handoff_ready' })
            onCreateDemoTask(handoff)
          }}
        >
          {selectedIdea ? '创建演示任务' : '请先选择候选构想'}
          <ArrowRight size={15} aria-hidden="true" />
        </button>
      </section>
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
}: DiscoveryPageProps) {
  useProductRevision()
  const project = frontendDataSource.getProject(projectId)
  const currentNumber = ROUTE_NUMBER[step]

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
    if (target === 6 && activeProject.discovery.selectedIdeaId) {
      frontendDataSource.updateProject(activeProject.id, { status: 'handoff_ready' })
    }
    onChangeStep(activeProject.id, NUMBER_ROUTE[target])
  }

  const content = (() => {
    switch (step) {
      case 'brief':
        return <BriefStep project={activeProject} />
      case 'resources':
        return <ResourcesStep project={activeProject} bundle={bundle} onOpenLibrary={onOpenLibrary} />
      case 'gaps':
        return <GapStep project={activeProject} bundle={bundle} />
      case 'ideas':
        return <IdeasStep project={activeProject} />
      case 'decision':
        return <DecisionStep project={activeProject} />
      case 'handoff':
        return (
          <HandoffStep
            project={activeProject}
            handoff={handoff}
            onCreateDemoTask={onCreateDemoTask}
          />
        )
    }
  })()

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
          <span className="product-eyebrow">RESEARCH DISCOVERY · 前端演示</span>
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
              || (activeProject.status === 'handoff_ready' && item.number <= 6)
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
              <small>更改会自动保存在当前浏览器</small>
            </span>
            {currentNumber < 6 ? (
              <button
                type="button"
                className="product-button is-primary"
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
