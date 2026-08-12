import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  Circle,
  Database,
  FileText,
  FlaskConical,
  Layers3,
  Library,
  Play,
  Scale,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import {
  frontendDataSource,
  type DiscoveryStep,
  type Project,
  type ResourceKind,
} from '../product'
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
  { step: 1, title: '定义研究问题、对象与约束', short: '研究简报' },
  { step: 2, title: '把文献、政策、数据与方法放入项目篮', short: '资源收集' },
  { step: 3, title: '提炼证据关系与可验证缺口', short: '图谱与缺口' },
  { step: 4, title: '生成机制、变量和可检验构想', short: '候选构想' },
  { step: 5, title: '按 Pareto 维度进行人工选择', short: '比较与选择' },
  { step: 6, title: '生成 CaseSubmission 草稿', short: '交接预览' },
]

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

  return (
    <main className="product-page project-overview">
      <button type="button" className="product-back" onClick={onOpenProjects}>
        <ArrowLeft size={15} aria-hidden="true" />
        全部项目
      </button>

      <header className="product-page__header project-overview__header">
        <div>
          <span className="product-eyebrow">PROJECT OVERVIEW · 前端演示</span>
          <div className="project-overview__titleline">
            <h1>{project.title}</h1>
            <span className={`product-status ${status.tone}`}>{status.label}</span>
          </div>
          <p>{project.summary || project.discovery.brief.researchQuestion || '尚未填写项目摘要'}</p>
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
          {latestTaskId ? <Play size={15} aria-hidden="true" /> : <ArrowRight size={15} aria-hidden="true" />}
          {latestTaskId ? '打开最新任务' : `继续${DISCOVERY_STAGES[nextStep - 1].short}`}
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

      <section className="project-journey" aria-labelledby="project-journey-title">
        <div className="product-section-heading">
          <div>
            <span className="product-eyebrow">双区流程</span>
            <h2 id="project-journey-title">先发现，再进入正式验证</h2>
          </div>
          <span>{discoveryPercent}% 发现进度</span>
        </div>

        <div className="project-journey__zones">
          <section className="project-zone is-discovery">
            <header>
              <span className="project-zone__number">01</span>
              <div>
                <h3>研究发现区</h3>
                <p>前端原型 · 形成可审阅的 CaseSubmission 草稿</p>
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

          <div className="project-journey__bridge" aria-hidden="true">
            <span>人工交接</span>
            <ArrowRight size={18} />
          </div>

          <section className={`project-zone is-formal ${project.taskIds.length ? 'is-started' : ''}`}>
            <header>
              <span className="project-zone__number">02</span>
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
                研究发现不会绕过人工确认直接写入正式任务；请先在交接页检查缺失字段。
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
          资源只进入项目 EvidenceBundle。外部数据目录不会冒充已上传文件，政策摘要也不会自动成为已确认事实。
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
                ? '交接草稿已完整，可以创建本地演示任务'
                : `继续${DISCOVERY_STAGES[nextStep - 1].short}`}
          </h2>
          <p>
            {latestTaskId
              ? '正式任务严格沿用 H1–H4 语义，并分开展示执行成功与科学有效性。'
              : handoff?.missingFields.length
                ? `交接前仍有 ${handoff.missingFields.length} 项正式字段需要补齐。`
                : '在交接预览中复核输入边界，再进入后半段流程。'}
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
