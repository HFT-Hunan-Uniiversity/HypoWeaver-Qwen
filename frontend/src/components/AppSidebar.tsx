/**
 * AppSidebar：ClawsGO 式左侧边栏。
 * 结构：品牌区 → 主导航（新研究/项目/研究资源库）→「项目」「任务」分组 →
 * 底部（设置 / 主题切换 / 后端状态）。
 * 可折叠为图标栏（localStorage: hw-sidebar），<768px 由 App 控制为抽屉。
 */
import { FolderKanban, LibraryBig, Moon, PanelLeftClose, PanelLeftOpen, Plus, Settings2, Sun } from 'lucide-react'
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
    meta: '演示流程',
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
  config: RuntimeConfigStatus | null
  theme: ThemeMode
  collapsed: boolean
  onToggleCollapse: () => void
  onToggleTheme: () => void
  onNavigate: (nav: ShellNav) => void
  onOpenProject: (id: string) => void
  onOpenTask: (id: string) => void
}

export function AppSidebar({ nav, activeTaskId, activeProjectId, projects, tasks, config, theme, collapsed, onToggleCollapse, onToggleTheme, onNavigate, onOpenProject, onOpenTask }: AppSidebarProps) {
  const qwenReady = Boolean(config?.qwenApiKey.configured)
  const executorReady = Boolean(config?.researchEngineUrl.value)
  const serviceReady = qwenReady && executorReady

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
        <button type="button" className={`sidebar__link ${nav === 'projects' ? 'is-active' : ''}`} title="项目" onClick={() => onNavigate('projects')}>
          <FolderKanban size={16} aria-hidden="true" />{!collapsed && <span>项目</span>}
        </button>
        <button type="button" className={`sidebar__link ${nav === 'library' ? 'is-active' : ''}`} title="研究资源库" onClick={() => onNavigate('library')}>
          <LibraryBig size={16} aria-hidden="true" />{!collapsed && <span>研究资源库</span>}
        </button>
      </nav>

      {!collapsed && (
        <div className="sidebar__collections">
          <section className="sidebar__projects" aria-labelledby="sidebar-projects-label">
            <p className="sidebar__group" id="sidebar-projects-label">项目</p>
            {projects.length === 0 && <p className="sidebar__empty">还没有项目。</p>}
            <div className="sidebar__list" role="list">
              {projects.map((project) => (
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
              ))}
            </div>
          </section>
          <section className="sidebar__tasks" aria-labelledby="sidebar-tasks-label">
            <p className="sidebar__group" id="sidebar-tasks-label">任务</p>
            {tasks.length === 0 && <p className="sidebar__empty">还没有正式或演示任务。</p>}
            <div className="sidebar__list" role="list">
              {tasks.map((task) => (
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
              ))}
            </div>
          </section>
        </div>
      )}
      {collapsed && <div className="sidebar__collections sidebar__tasks--collapsed" aria-hidden="true" />}

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
      </div>
    </aside>
  )
}
