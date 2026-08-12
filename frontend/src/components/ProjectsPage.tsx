import {
  ArrowRight,
  CircleAlert,
  Clock3,
  FolderKanban,
  Plus,
  Sparkles,
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
  2: '资源收集',
  3: '图谱与缺口',
  4: '候选构想',
  5: '比较与选择',
  6: '交接预览',
}

export interface ProjectsPageProps {
  onCreateProject: () => void
  onOpenProject: (projectId: string) => void
  onOpenDiscovery: (projectId: string, step: DiscoveryRouteStep) => void
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
}: {
  project: Project
  onOpenProject: (projectId: string) => void
  onOpenDiscovery: (projectId: string, step: DiscoveryRouteStep) => void
}) {
  const status = STATUS_COPY[project.status]
  const progress = progressOf(project)
  const nextStep = project.discovery.currentStep

  return (
    <article className="project-card">
      <button
        type="button"
        className="project-card__main"
        onClick={() => onOpenProject(project.id)}
        aria-label={`打开项目：${project.title}`}
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
      <div className="project-card__action">
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
      </div>
    </article>
  )
}

export function ProjectsPage({
  onCreateProject,
  onOpenProject,
  onOpenDiscovery,
}: ProjectsPageProps) {
  useProductRevision()
  const projects = frontendDataSource.listProjects()

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
          <span className="product-eyebrow">PROJECTS · 前端演示</span>
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
          <small>继续发现流程或完成交接</small>
        </div>
        <div>
          <span>等待交接</span>
          <strong>{summary.handoffReady}</strong>
          <small>已生成案例草稿，尚未建任务</small>
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
                    ? '创建本地演示任务'
                    : `继续${STEP_LABEL[project.discovery.currentStep]}`}
                </strong>
                <ArrowRight size={14} aria-hidden="true" />
              </button>
            ))}
          </div>
        </section>
      ) : null}

      <section className="product-section-heading">
        <div>
          <span className="product-eyebrow">全部项目</span>
          <h2>从问题到可执行任务</h2>
        </div>
        <span>{projects.length} 个项目</span>
      </section>

      {projects.length > 0 ? (
        <div className="projects-grid">
          {projects.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              onOpenProject={onOpenProject}
              onOpenDiscovery={onOpenDiscovery}
            />
          ))}
        </div>
      ) : (
        <section className="product-empty">
          <FolderKanban size={28} aria-hidden="true" />
          <h2>还没有研究项目</h2>
          <p>先用一句研究问题创建项目，再逐步补齐资源、缺口与候选构想。</p>
          <button type="button" className="product-button is-primary" onClick={onCreateProject}>
            <Plus size={16} aria-hidden="true" />
            创建第一个项目
          </button>
        </section>
      )}
    </main>
  )
}
