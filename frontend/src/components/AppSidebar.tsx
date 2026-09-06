/**
 * AppSidebar：ClawsGO 式左侧边栏。
 * 结构：品牌区 → 主导航（新研究/项目/研究资源库）→「项目」「任务」分组 →
 * 底部（设置 / 主题切换 / 后端状态）。
 * 可折叠为图标栏（localStorage: hw-sidebar），<768px 由 App 控制为抽屉。
 */
import { BellRing, CheckSquare2, ChevronRight, FolderKanban, LibraryBig, Moon, PanelLeftClose, PanelLeftOpen, Plus, Settings2, Square, Sun, Trash2, UserRound } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { RunStatus, RunSummary, RuntimeConfigStatus } from '../runtime/types'
import type { MockTaskSummary } from '../data/mockPipeline'
import type { ThemeMode } from '../runtime/theme'

export type ShellNav = 'new' | 'projects' | 'library' | 'settings'

const runStatusText: Record<RunStatus, string> = {
  created: '待启动',
  running: '运行中',
  waiting_human: '等待人工',
  blocked: '已阻塞',
  failed: '执行失败',
  completed: '已完成',
  stopped: '已终止',
  cancelled: '已取消',
}

const mockStatusText: Record<MockTaskSummary['status'], string> = {
  running: '运行中',
  waiting_human: '等待人工',
  completed: '已完成',
  rejected: '已终止',
}

function taskTone(status: string): string {
  if (status === 'completed') return 'is-done'
  if (status === 'waiting_human') return 'is-wait'
  if (status === 'failed' || status === 'blocked' || status === 'rejected') return 'is-problem'
  return 'is-live'
}

export interface SidebarTaskItem {
  id: string
  title: string
  meta: string
  status: string
  statusText: string
  gate?: string
}

export interface SidebarProjectItem {
  id: string
  title: string
  statusText: string
  updatedAt: string
}

export function sidebarTasks(mockTasks: MockTaskSummary[], runs: RunSummary[]): SidebarTaskItem[] {
  const fromMock: Array<SidebarTaskItem & { updatedAt: string }> = mockTasks.map((task) => ({
    id: task.id,
    title: task.title,
    meta: '示范研究',
    status: task.status,
    statusText: mockStatusText[task.status],
    gate: task.currentGate,
    updatedAt: task.updatedAt,
  }))
  const fromRuns: Array<SidebarTaskItem & { updatedAt: string }> = runs.map((run) => ({
    id: run.id,
    title: run.caseName,
    meta: run.mode === 'fixture' ? '流程演示' : '真实研究',
    status: run.status,
    statusText: runStatusText[run.status],
    gate: run.currentGate,
    updatedAt: run.updatedAt,
  }))
  return [...fromMock, ...fromRuns].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
}

interface AppSidebarProps {
  nav: ShellNav | null
  activeTaskId: string | null
  activeProjectId: string | null
  projects: SidebarProjectItem[]
  tasks: SidebarTaskItem[]
  pendingReviewCount: number
  config: RuntimeConfigStatus | null
  theme: ThemeMode
  collapsed: boolean
  onToggleCollapse: () => void
  onToggleTheme: () => void
  onNavigate: (nav: ShellNav) => void
  onOpenProject: (id: string) => void
  onOpenTask: (id: string) => void
  onDeleteProjects: (ids: string[]) => Promise<boolean>
  onDeleteTasks: (ids: string[]) => Promise<boolean>
  onOpenPendingReview: () => void
}

export function AppSidebar({ nav, activeTaskId, activeProjectId, projects, tasks, pendingReviewCount, config, theme, collapsed, onToggleCollapse, onToggleTheme, onNavigate, onOpenProject, onOpenTask, onDeleteProjects, onDeleteTasks, onOpenPendingReview }: AppSidebarProps) {
  const qwenReady = Boolean(config?.qwenApiKey.configured)
  const executorReady = Boolean(config?.researchEngineUrl.value)
  const serviceReady = qwenReady && executorReady
  const [selectingTasks, setSelectingTasks] = useState(false)
  const [selectedTaskIds, setSelectedTaskIds] = useState<Set<string>>(() => new Set())
  const [deletingTasks, setDeletingTasks] = useState(false)
  const allTasksSelected = tasks.length > 0 && selectedTaskIds.size === tasks.length
  const [selectingProjects, setSelectingProjects] = useState(false)
  const [selectedProjectIds, setSelectedProjectIds] = useState<Set<string>>(() => new Set())
  const [deletingProjects, setDeletingProjects] = useState(false)
  const allProjectsSelected = projects.length > 0 && selectedProjectIds.size === projects.length

  useEffect(() => {
    const availableIds = new Set(projects.map((project) => project.id))
    setSelectedProjectIds((current) => {
      const next = new Set([...current].filter((id) => availableIds.has(id)))
      return next.size === current.size ? current : next
    })
    if (!projects.length) setSelectingProjects(false)
  }, [projects])

  useEffect(() => {
    const availableIds = new Set(tasks.map((task) => task.id))
    setSelectedTaskIds((current) => {
      const next = new Set([...current].filter((id) => availableIds.has(id)))
      return next.size === current.size ? current : next
    })
    if (!tasks.length) setSelectingTasks(false)
  }, [tasks])

  function toggleTaskSelection(taskId: string) {
    setSelectedTaskIds((current) => {
      const next = new Set(current)
      if (next.has(taskId)) next.delete(taskId)
      else next.add(taskId)
      return next
    })
  }

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

  function exitTaskSelection() {
    setSelectingTasks(false)
    setSelectedTaskIds(new Set())
  }

  async function deleteSelectedTasks() {
    if (!selectedTaskIds.size || deletingTasks) return
    setDeletingTasks(true)
    try {
      const completed = await onDeleteTasks([...selectedTaskIds])
      if (completed) exitTaskSelection()
    } finally {
      setDeletingTasks(false)
    }
  }

  return (
    <aside className={`sidebar ${collapsed ? 'is-collapsed' : ''}`}>
      <div className="sidebar__brand">
        <button type="button" className="sidebar__logo" onClick={() => onNavigate('new')} title="HypoWeaver · 回到新任务">
          <span className="sidebar__mark" aria-hidden="true">H</span>
          {!collapsed && <span className="sidebar__name"><strong>HypoWeaver</strong><small>实证科研工作流</small></span>}
        </button>
        <button type="button" className="sidebar__fold" aria-label={collapsed ? '展开侧边栏' : '折叠侧边栏'} title={collapsed ? '展开侧边栏' : '折叠侧边栏'} onClick={onToggleCollapse}>
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>
      </div>

      <nav className="sidebar__nav" aria-label="主导航">
        <button type="button" className={`sidebar__link ${nav === 'new' ? 'is-active' : ''}`} title="新研究" onClick={() => onNavigate('new')}>
          <Plus size={16} aria-hidden="true" />{!collapsed && <span>新研究</span>}
        </button>
        <button type="button" className={`sidebar__link ${nav === 'library' ? 'is-active' : ''}`} title="研究资源库" onClick={() => onNavigate('library')}>
          <LibraryBig size={16} aria-hidden="true" />{!collapsed && <span>资源库</span>}
        </button>
        <button type="button" className={`sidebar__link ${nav === 'projects' ? 'is-active' : ''}`} title="项目" onClick={() => onNavigate('projects')}>
          <FolderKanban size={16} aria-hidden="true" />{!collapsed && <span>项目</span>}
        </button>
      </nav>

      {!collapsed && (
        <div className="sidebar__collections">
          <section className="sidebar__projects" aria-labelledby="sidebar-projects-label">
            <div className="sidebar__group-row">
              <p className="sidebar__group" id="sidebar-projects-label">项目</p>
              {projects.length > 0 ? (
                <button
                  type="button"
                  className={`sidebar__task-manage ${selectingProjects ? 'is-active' : ''}`}
                  onClick={() => selectingProjects ? exitProjectSelection() : setSelectingProjects(true)}
                >
                  {selectingProjects ? '取消' : '多选'}
                </button>
              ) : null}
            </div>
            {selectingProjects ? (
              <div className="sidebar__bulk-actions" aria-label="批量管理项目">
                <button
                  type="button"
                  onClick={() => setSelectedProjectIds(allProjectsSelected ? new Set() : new Set(projects.map((project) => project.id)))}
                >
                  {allProjectsSelected ? <CheckSquare2 size={13} aria-hidden="true" /> : <Square size={13} aria-hidden="true" />}
                  {allProjectsSelected ? '取消全选' : '全选'}
                </button>
                <button
                  type="button"
                  className="is-delete"
                  disabled={!selectedProjectIds.size || deletingProjects}
                  onClick={() => void deleteSelectedProjects()}
                >
                  <Trash2 size={13} aria-hidden="true" />
                  {deletingProjects ? '删除中…' : `删除已选 (${selectedProjectIds.size})`}
                </button>
              </div>
            ) : null}
            {projects.length === 0 && <p className="sidebar__empty">还没有项目。</p>}
            <div className="sidebar__list" role="list">
              {projects.map((project) => {
                const selected = selectedProjectIds.has(project.id)
                return selectingProjects ? (
                  <label
                    role="listitem"
                    key={project.id}
                    className={`sidebar__task is-selecting ${selected ? 'is-selected' : ''}`}
                    title={project.title}
                  >
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={() => toggleProjectSelection(project.id)}
                      aria-label={`选择项目：${project.title}`}
                    />
                    <span className="sidebar__dot is-project" aria-hidden="true" />
                    <span className="sidebar__task-copy">
                      <strong>{project.title}</strong>
                      <small>{project.statusText}</small>
                    </span>
                  </label>
                ) : (
                  <button
                    type="button"
                    role="listitem"
                    key={project.id}
                    className={`sidebar__task ${project.id === activeProjectId ? 'is-active' : ''}`}
                    title={project.title}
                    onClick={() => onOpenProject(project.id)}
                  >
                    <span className="sidebar__dot is-project" aria-hidden="true" />
                    <span className="sidebar__task-copy">
                      <strong>{project.title}</strong>
                      <small>{project.statusText}</small>
                    </span>
                  </button>
                )
              })}
            </div>
          </section>
          <section className="sidebar__tasks" aria-labelledby="sidebar-tasks-label">
            <div className="sidebar__group-row">
              <p className="sidebar__group" id="sidebar-tasks-label">任务</p>
              {tasks.length > 0 ? (
                <button
                  type="button"
                  className={`sidebar__task-manage ${selectingTasks ? 'is-active' : ''}`}
                  onClick={() => selectingTasks ? exitTaskSelection() : setSelectingTasks(true)}
                >
                  {selectingTasks ? '取消' : '多选'}
                </button>
              ) : null}
            </div>
            {selectingTasks ? (
              <div className="sidebar__bulk-actions" aria-label="批量管理任务">
                <button
                  type="button"
                  onClick={() => setSelectedTaskIds(allTasksSelected ? new Set() : new Set(tasks.map((task) => task.id)))}
                >
                  {allTasksSelected ? <CheckSquare2 size={13} aria-hidden="true" /> : <Square size={13} aria-hidden="true" />}
                  {allTasksSelected ? '取消全选' : '全选'}
                </button>
                <button
                  type="button"
                  className="is-delete"
                  disabled={!selectedTaskIds.size || deletingTasks}
                  onClick={() => void deleteSelectedTasks()}
                >
                  <Trash2 size={13} aria-hidden="true" />
                  {deletingTasks ? '删除中…' : `删除已选 (${selectedTaskIds.size})`}
                </button>
              </div>
            ) : null}
            {tasks.length === 0 && <p className="sidebar__empty">还没有正式或演示任务。</p>}
            <div className="sidebar__list" role="list">
              {tasks.map((task) => {
                const selected = selectedTaskIds.has(task.id)
                return selectingTasks ? (
                  <label
                    role="listitem"
                    key={task.id}
                    className={`sidebar__task is-selecting ${selected ? 'is-selected' : ''}`}
                    title={task.title}
                  >
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={() => toggleTaskSelection(task.id)}
                      aria-label={`选择任务：${task.title}`}
                    />
                    <span className={`sidebar__dot ${taskTone(task.status)}`} aria-hidden="true" />
                    <span className="sidebar__task-copy">
                      <strong>{task.title}</strong>
                      <small>{task.gate ? `${task.gate} · ` : ''}{task.statusText} · {task.meta}</small>
                    </span>
                  </label>
                ) : (
                  <button
                    type="button"
                    role="listitem"
                    key={task.id}
                    className={`sidebar__task ${task.id === activeTaskId ? 'is-active' : ''}`}
                    title={task.title}
                    onClick={() => onOpenTask(task.id)}
                  >
                    <span className={`sidebar__dot ${taskTone(task.status)}`} aria-hidden="true" />
                    <span className="sidebar__task-copy">
                      <strong>{task.title}</strong>
                      <small>{task.gate ? `${task.gate} · ` : ''}{task.statusText} · {task.meta}</small>
                    </span>
                  </button>
                )
              })}
            </div>
          </section>
        </div>
      )}
      {collapsed && <div className="sidebar__collections sidebar__tasks--collapsed" aria-hidden="true" />}

      {pendingReviewCount > 0 && (
        <button type="button" className="sidebar__review" title={`${pendingReviewCount} 项人工确认待处理`} onClick={onOpenPendingReview}>
          <BellRing size={15} aria-hidden="true" />
          {!collapsed && <span><strong>{pendingReviewCount} 项人工确认待处理</strong><small>研究已暂停，等待你决定</small></span>}
          {!collapsed && <ChevronRight size={14} aria-hidden="true" />}
        </button>
      )}

      <div className="sidebar__foot">
        <button type="button" className={`sidebar__link ${nav === 'settings' ? 'is-active' : ''}`} title="设置" onClick={() => onNavigate('settings')}>
          <Settings2 size={16} aria-hidden="true" />{!collapsed && <span>设置</span>}
          {!collapsed && <span className={`sidebar__service ${serviceReady ? 'is-ready' : ''}`} title={serviceReady ? '服务已就绪' : '需要配置'} />}
        </button>
        <button
          type="button"
          className="sidebar__link"
          aria-label={theme === 'night' ? '切换到日间模式' : '切换到夜间模式'}
          title={theme === 'night' ? '日间模式' : '夜间模式'}
          onClick={onToggleTheme}
        >
          {theme === 'night' ? <Sun size={16} aria-hidden="true" /> : <Moon size={16} aria-hidden="true" />}
          {!collapsed && <span>{theme === 'night' ? '日间模式' : '夜间模式'}</span>}
        </button>
        <div className="sidebar__profile" title="当前为本地研究工作区">
          <span className="sidebar__profile-icon"><UserRound size={15} /></span>
          {!collapsed && <span><strong>本地研究者</strong><small>研究工作区</small></span>}
        </div>
      </div>
    </aside>
  )
}
