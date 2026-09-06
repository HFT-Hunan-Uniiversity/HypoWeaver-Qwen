import {
  ArrowRight,
  CheckSquare2,
  CircleAlert,
  Clock3,
  FolderKanban,
  Plus,
  Square,
  Sparkles,
  Trash2,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import {
  frontendDataSource,
  type DiscoveryStep,
  type Project,
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

const STEP_LABEL: Record<DiscoveryStep, string> = {
  1: '研究简报',
  2: '数据中心检索',
  3: '趋势与空白',
  4: '候选假设',
  5: '假设选择',
  6: '方案输入',
}

export interface ProjectsPageProps {
  onCreateProject: () => void
  onOpenProject: (projectId: string) => void
  onOpenDiscovery: (projectId: string, step: DiscoveryRouteStep) => void
  onDeleteProjects: (projectIds: string[]) => Promise<boolean>
}

function useProductRevision(): void {
  const [, setRevision] = useState(0)
  useEffect(
    () => frontendDataSource.subscribe(() => setRevision((current) => current + 1)),
    [],
  )
}

function progressOf(project: Project): number {
  const completed = new Set(project.discovery.completedSteps)
  if (project.status === 'handoff_ready' || completed.has(6)) return 100
  return Math.round((completed.size / 6) * 100)
}

function dateLabel(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '刚刚更新'
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function ProjectCard({
  project,
  onOpenProject,
  onOpenDiscovery,
  selecting,
  selected,
  onToggleSelection,
}: {
  project: Project
  onOpenProject: (projectId: string) => void
  onOpenDiscovery: (projectId: string, step: DiscoveryRouteStep) => void
  selecting: boolean
  selected: boolean
  onToggleSelection: (projectId: string) => void
}) {
  const status = STATUS_COPY[project.status]
  const progress = progressOf(project)
  const nextStep = project.discovery.currentStep

  return (
    <article className={`project-card ${selecting ? 'is-selecting' : ''} ${selected ? 'is-selected' : ''}`}>
      {selecting ? (
        <label className="project-card__selector">
          <input
            type="checkbox"
            checked={selected}
            onChange={() => onToggleSelection(project.id)}
            aria-label={`选择项目：${project.title}`}
          />
          {selected ? <CheckSquare2 size={16} aria-hidden="true" /> : <Square size={16} aria-hidden="true" />}
        </label>
      ) : null}
      <button
        type="button"
        className="project-card__main"
        onClick={() => selecting ? onToggleSelection(project.id) : onOpenProject(project.id)}
        aria-label={selecting ? `选择项目：${project.title}` : `打开项目：${project.title}`}
      >
        <span className="project-card__topline">
          <span className={`product-status ${status.tone}`}>{status.label}</span>
          <span className="project-card__updated">
            <Clock3 size={12} aria-hidden="true" />
            {dateLabel(project.updatedAt)}
          </span>
        </span>
        <strong className="project-card__title">{project.title}</strong>
        <span className="project-card__summary">
          {project.summary || project.discovery.brief.researchQuestion || '尚未填写项目摘要'}
        </span>
        <span className="project-card__meta">
          <span>{project.resources.length} 条研究资源</span>
          <i aria-hidden="true" />
          <span>{project.taskIds.length} 个正式任务</span>
        </span>
        <span className="project-card__progress" aria-label={`研究发现完成 ${progress}%`}>
          <span><b>研究发现</b><em>{progress}%</em></span>
          <i><b style={{ width: `${progress}%` }} /></i>
        </span>
      </button>
      {!selecting ? <div className="project-card__action">
        <span>
          下一步
          <strong>{STEP_LABEL[nextStep]}</strong>
        </span>
        <button
          type="button"
          className="product-icon-button"
          onClick={() => onOpenDiscovery(project.id, STEP_ROUTE[nextStep])}
          aria-label={`继续${project.title}的${STEP_LABEL[nextStep]}`}
        >
          <ArrowRight size={16} aria-hidden="true" />
        </button>
      </div> : null}
    </article>
  )
}

export function ProjectsPage({
  onCreateProject,
  onOpenProject,
  onOpenDiscovery,
  onDeleteProjects,
}: ProjectsPageProps) {
  useProductRevision()
  const projects = frontendDataSource.listProjects()
  const [selectingProjects, setSelectingProjects] = useState(false)
  const [selectedProjectIds, setSelectedProjectIds] = useState<Set<string>>(() => new Set())
  const [deletingProjects, setDeletingProjects] = useState(false)
  const projectIdKey = projects.map((project) => project.id).join('|')
  const allProjectsSelected = projects.length > 0 && selectedProjectIds.size === projects.length

  useEffect(() => {
    const availableIds = new Set(projects.map((project) => project.id))
    setSelectedProjectIds((current) => {
      const next = new Set([...current].filter((id) => availableIds.has(id)))
      return next.size === current.size ? current : next
    })
    if (!projects.length) setSelectingProjects(false)
    // projectIdKey is a stable membership signature; project metadata updates do not reset selection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectIdKey])

  function toggleProjectSelection(projectId: string) {
    setSelectedProjectIds((current) => {
      const next = new Set(current)
      if (next.has(projectId)) next.delete(projectId)
      else next.add(projectId)
      return next
    })
  }

  function exitProjectSelection() {
    setSelectingProjects(false)
    setSelectedProjectIds(new Set())
  }

  async function deleteSelectedProjects() {
    if (!selectedProjectIds.size || deletingProjects) return
    setDeletingProjects(true)
    try {
      const completed = await onDeleteProjects([...selectedProjectIds])
      if (completed) exitProjectSelection()
    } finally {
      setDeletingProjects(false)
    }
  }

  const summary = useMemo(() => {
    let needsAttention = 0
    let handoffReady = 0
    let formalTasks = 0
    for (const project of projects) {
      if (project.status === 'handoff_ready' && project.taskIds.length === 0) {
        handoffReady += 1
        needsAttention += 1
      } else if (
        project.status === 'active'
        && !project.discovery.completedSteps.includes(project.discovery.currentStep)
      ) {
        needsAttention += 1
      }
      formalTasks += project.taskIds.length
    }
    return { needsAttention, handoffReady, formalTasks }
  }, [projects])

  const attentionProjects = projects
    .filter((project) => (
      (project.status === 'handoff_ready' && project.taskIds.length === 0)
      || (project.status === 'active'
        && !project.discovery.completedSteps.includes(project.discovery.currentStep))
    ))
    .slice(0, 3)

  return (
    <main className="product-page projects-page">
      <header className="product-page__header">
        <div>
          <span className="product-eyebrow">PROJECTS</span>
          <h1>研究项目</h1>
          <p>在一个项目里连接研究发现、资源证据与正式 H1–H4 任务。</p>
        </div>
        <button type="button" className="product-button is-primary" onClick={onCreateProject}>
          <Plus size={16} aria-hidden="true" />
          新建研究
        </button>
      </header>

      <section className="project-summary-grid" aria-label="项目概览">
        <div className="project-summary-grid__lead">
          <span className="project-summary-grid__icon"><Sparkles size={18} aria-hidden="true" /></span>
          <div>
            <span>当前项目</span>
            <strong>{projects.length}</strong>
            <small>所有进度保存在此浏览器</small>
          </div>
        </div>
        <div>
          <span>需要处理</span>
          <strong>{summary.needsAttention}</strong>
          <small>继续研究发现或补齐方案输入</small>
        </div>
        <div>
          <span>等待方案</span>
          <strong>{summary.handoffReady}</strong>
          <small>输入已齐备，尚未进入正式任务</small>
        </div>
        <div>
          <span>正式任务</span>
          <strong>{summary.formalTasks}</strong>
          <small>独立执行 H1–H4 工作流</small>
        </div>
      </section>

      {attentionProjects.length > 0 ? (
        <section className="project-attention" aria-labelledby="project-attention-title">
          <div className="project-attention__heading">
            <CircleAlert size={17} aria-hidden="true" />
            <div>
              <strong id="project-attention-title">待处理事项</strong>
              <span>这些项目有清晰的下一步，可直接继续。</span>
            </div>
          </div>
          <div className="project-attention__items">
            {attentionProjects.map((project) => (
              <button
                type="button"
                key={project.id}
                onClick={() => onOpenDiscovery(
                  project.id,
                  STEP_ROUTE[project.discovery.currentStep],
                )}
              >
                <span>{project.title}</span>
                <strong>
                  {project.status === 'handoff_ready'
                    ? '进入后续研究任务'
                    : `继续${STEP_LABEL[project.discovery.currentStep]}`}
                </strong>
                <ArrowRight size={14} aria-hidden="true" />
              </button>
            ))}
          </div>
        </section>
      ) : null}

      <section className="product-section-heading projects-heading">
        <div>
          <span className="product-eyebrow">全部项目</span>
          <h2>从问题到可执行任务</h2>
        </div>
        <div className="projects-heading__actions">
          {selectingProjects ? (
            <>
              <button
                type="button"
                className="product-button"
                onClick={() => setSelectedProjectIds(allProjectsSelected ? new Set() : new Set(projects.map((project) => project.id)))}
              >
                {allProjectsSelected ? <CheckSquare2 size={15} aria-hidden="true" /> : <Square size={15} aria-hidden="true" />}
                {allProjectsSelected ? '取消全选' : '全选'}
              </button>
              <button
                type="button"
                className="product-button is-danger"
                disabled={!selectedProjectIds.size || deletingProjects}
                onClick={() => void deleteSelectedProjects()}
              >
                <Trash2 size={15} aria-hidden="true" />
                {deletingProjects ? '删除中…' : `删除已选 (${selectedProjectIds.size})`}
              </button>
            </>
          ) : <span>{projects.length} 个项目</span>}
          {projects.length ? (
            <button type="button" className="product-button" onClick={() => selectingProjects ? exitProjectSelection() : setSelectingProjects(true)}>
              {selectingProjects ? '取消' : '多选管理'}
            </button>
          ) : null}
        </div>
      </section>

      {projects.length > 0 ? (
        <div className="projects-grid">
          {projects.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              onOpenProject={onOpenProject}
              onOpenDiscovery={onOpenDiscovery}
              selecting={selectingProjects}
              selected={selectedProjectIds.has(project.id)}
              onToggleSelection={toggleProjectSelection}
            />
          ))}
        </div>
      ) : (
        <section className="product-empty">
          <FolderKanban size={28} aria-hidden="true" />
          <h2>还没有研究项目</h2>
          <p>先用一句研究问题创建项目，再逐步完成检索、研究空白、候选假设与科学十项。</p>
          <button type="button" className="product-button is-primary" onClick={onCreateProject}>
            <Plus size={16} aria-hidden="true" />
            创建第一个项目
          </button>
        </section>
      )}
    </main>
  )
}
