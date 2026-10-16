/**
 * 统一工作台侧边栏：与分步向导共享品牌标识、陶土/炭黑设计 Token 与项目状态展示。
 */
import {
  FolderKanban,
  LibraryBig,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Settings2,
  Sparkles,
} from 'lucide-react'

export type ShellNav = 'new' | 'projects' | 'library' | 'settings'

export interface SidebarProjectItem {
  id: string
  title: string
  statusText: string
  tone: 'is-live' | 'is-wait' | 'is-done' | 'is-problem'
}

interface AppSidebarProps {
  nav: ShellNav
  projects: SidebarProjectItem[]
  projectCount?: number
  collapsed: boolean
  onToggleCollapse: () => void
  onNavigate: (nav: ShellNav) => void
  onOpenProject: (id: string) => void
  llmConfigured?: boolean
}

export function AppSidebar({
  nav,
  projects,
  projectCount = 0,
  collapsed,
  onToggleCollapse,
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
          title="HypoWeaver · 实证科研工作台"
        >
          <span className="sidebar__mark" aria-hidden="true">
            HW
          </span>
          {!collapsed && (
            <span className="sidebar__name">
              <strong>HypoWeaver</strong>
              <small>实证科研工作台</small>
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
          className={`sidebar__link ${nav === 'projects' ? 'is-active' : ''}`}
          title="我的项目"
          onClick={() => onNavigate('projects')}
        >
          <FolderKanban size={16} aria-hidden="true" />
          {!collapsed && (
            <>
              <span>我的项目</span>
              {projectCount > 0 && <em className="sidebar__count">{projectCount}</em>}
            </>
          )}
        </button>
        <button
          type="button"
          className={`sidebar__link ${nav === 'library' ? 'is-active' : ''}`}
          title="数据与资源库"
          onClick={() => onNavigate('library')}
        >
          <LibraryBig size={16} aria-hidden="true" />
          {!collapsed && <span>数据与资源</span>}
        </button>
      </nav>

      {!collapsed && (
        <div className="sidebar__collections">
          <section className="sidebar__projects" aria-labelledby="sidebar-projects-label">
            <div className="sidebar__group-row">
              <p className="sidebar__group" id="sidebar-projects-label">
                最近研究 · 分步向导
              </p>
              {projectCount > 0 && (
                <button
                  type="button"
                  className="sidebar__task-manage"
                  onClick={() => onNavigate('projects')}
                >
                  全部
                </button>
              )}
            </div>
            {projects.length === 0 && (
              <p className="sidebar__empty">从右侧输入研究想法后，项目会出现在这里。</p>
            )}
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
                  <span className={`sidebar__dot ${project.tone}`} aria-hidden="true" />
                  <span className="sidebar__task-copy">
                    <strong>{project.title}</strong>
                    <small>{project.statusText}</small>
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
          title="服务与用量设置"
          onClick={() => onNavigate('settings')}
        >
          <Settings2 size={16} aria-hidden="true" />
          {!collapsed && <span>服务与设置</span>}
          {!collapsed && (
            <span
              className={`sidebar__service ${llmConfigured ? 'is-ready' : ''}`}
              title={llmConfigured ? '千问模型已配置' : '模型未配置'}
              aria-hidden="true"
            />
          )}
        </button>
        {!collapsed && (
          <div className="sidebar__profile">
            <span className="sidebar__profile-icon" aria-hidden="true">
              <Sparkles size={13} />
            </span>
            <span>
              <strong>六步实证向导</strong>
              <small>
                {llmConfigured ? '千问模型就绪 · 本地存盘' : '检索与统计就绪 · 本地存盘'}
              </small>
            </span>
          </div>
        )}
      </div>
    </aside>
  )
}
