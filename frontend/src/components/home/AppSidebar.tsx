/**
 * Ported from repo/frontend AppSidebar — class names / structure preserved.
 */
import {
  FolderKanban,
  LibraryBig,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Settings2,
  Sun,
  UserRound,
} from 'lucide-react'

export type ShellNav = 'new' | 'projects' | 'library' | 'settings'

export interface SidebarProjectItem {
  id: string
  title: string
  statusText: string
}

export interface SidebarTaskItem {
  id: string
  title: string
  statusText: string
  tone: 'is-live' | 'is-wait' | 'is-done' | 'is-problem'
}

interface AppSidebarProps {
  nav: ShellNav
  projects: SidebarProjectItem[]
  tasks: SidebarTaskItem[]
  theme: 'day' | 'night'
  collapsed: boolean
  onToggleCollapse: () => void
  onToggleTheme: () => void
  onNavigate: (nav: ShellNav) => void
  onOpenProject: (id: string) => void
  llmConfigured?: boolean
}

export function AppSidebar({
  nav,
  projects,
  tasks,
  theme,
  collapsed,
  onToggleCollapse,
  onToggleTheme,
  onNavigate,
  onOpenProject,
  llmConfigured,
}: AppSidebarProps) {
  return (
    <aside className={`sidebar ${collapsed ? 'is-collapsed' : ''}`}>
      <div className="sidebar__brand">
        <button
          type="button"
          className="sidebar__logo"
          onClick={() => onNavigate('new')}
          title="HypoWeaver · 回到新任务"
        >
          <span className="sidebar__mark" aria-hidden="true">
            H
          </span>
          {!collapsed && (
            <span className="sidebar__name">
              <strong>HypoWeaver</strong>
              <small>实证科研工作流</small>
            </span>
          )}
        </button>
        <button
          type="button"
          className="sidebar__fold"
          aria-label={collapsed ? '展开侧边栏' : '折叠侧边栏'}
          title={collapsed ? '展开侧边栏' : '折叠侧边栏'}
          onClick={onToggleCollapse}
        >
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>
      </div>

      <nav className="sidebar__nav" aria-label="主导航">
        <button
          type="button"
          className={`sidebar__link ${nav === 'new' ? 'is-active' : ''}`}
          title="新研究"
          onClick={() => onNavigate('new')}
        >
          <Plus size={16} aria-hidden="true" />
          {!collapsed && <span>新研究</span>}
        </button>
        <button
          type="button"
          className={`sidebar__link ${nav === 'library' ? 'is-active' : ''}`}
          title="研究资源库"
          onClick={() => onNavigate('library')}
        >
          <LibraryBig size={16} aria-hidden="true" />
          {!collapsed && <span>资源库</span>}
        </button>
        <button
          type="button"
          className={`sidebar__link ${nav === 'projects' ? 'is-active' : ''}`}
          title="项目"
          onClick={() => onNavigate('projects')}
        >
          <FolderKanban size={16} aria-hidden="true" />
          {!collapsed && <span>项目</span>}
        </button>
      </nav>

      {!collapsed && (
        <div className="sidebar__collections">
          <section className="sidebar__projects" aria-labelledby="sidebar-projects-label">
            <div className="sidebar__group-row">
              <p className="sidebar__group" id="sidebar-projects-label">
                项目
              </p>
            </div>
            {projects.length === 0 && <p className="sidebar__empty">还没有项目。</p>}
            <div className="sidebar__list" role="list">
              {projects.map((project) => (
                <button
                  type="button"
                  role="listitem"
                  key={project.id}
                  className="sidebar__task"
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
            <div className="sidebar__group-row">
              <p className="sidebar__group" id="sidebar-tasks-label">
                任务
              </p>
            </div>
            {tasks.length === 0 && <p className="sidebar__empty">创建项目后出现在此。</p>}
            <div className="sidebar__list" role="list">
              {tasks.map((task) => (
                <button
                  type="button"
                  role="listitem"
                  key={task.id}
                  className="sidebar__task"
                  title={task.title}
                  onClick={() => onOpenProject(task.id)}
                >
                  <span className={`sidebar__dot ${task.tone}`} aria-hidden="true" />
                  <span className="sidebar__task-copy">
                    <strong>{task.title}</strong>
                    <small>{task.statusText}</small>
                  </span>
                </button>
              ))}
            </div>
          </section>
        </div>
      )}

      <div className="sidebar__foot">
        <button
          type="button"
          className={`sidebar__link ${nav === 'settings' ? 'is-active' : ''}`}
          title="设置"
          onClick={() => onNavigate('settings')}
        >
          <Settings2 size={16} aria-hidden="true" />
          {!collapsed && <span>设置</span>}
          {!collapsed && (
            <span
              className={`sidebar__service ${llmConfigured ? 'is-ready' : ''}`}
              title={llmConfigured ? '模型已配置' : '模型未配置'}
              aria-hidden="true"
            />
          )}
        </button>
        <button
          type="button"
          className="sidebar__link"
          title={theme === 'day' ? '夜间模式' : '日间模式'}
          onClick={onToggleTheme}
        >
          {theme === 'day' ? (
            <Moon size={16} aria-hidden="true" />
          ) : (
            <Sun size={16} aria-hidden="true" />
          )}
          {!collapsed && <span>{theme === 'day' ? '夜间模式' : '日间模式'}</span>}
        </button>
        {!collapsed && (
          <div className="sidebar__profile">
            <span className="sidebar__profile-icon" aria-hidden="true">
              <UserRound size={14} />
            </span>
            <span>
              <strong>本地研究者</strong>
              <small>研究工作区</small>
            </span>
          </div>
        )}
      </div>
    </aside>
  )
}
