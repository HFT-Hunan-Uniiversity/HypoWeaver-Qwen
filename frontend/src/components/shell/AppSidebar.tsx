import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { FolderKanban, PanelLeftClose, PanelLeftOpen, Plus, Settings2 } from 'lucide-react'
import { api, type Project } from '../../api/client'
import { useLlm } from '../../lib/llm'

export default function AppSidebar({
  collapsed,
  onToggle,
  activeProjectId,
}: {
  collapsed: boolean
  onToggle: () => void
  activeProjectId?: string
}) {
  const projects = useQuery({ queryKey: ['projects'], queryFn: () => api<Project[]>('/projects') })
  const llm = useLlm()
  const navigate = useNavigate()
  return (
    <aside
      className={`sidebar ${collapsed ? 'is-collapsed' : ''}`}
      onClick={(e) => e.stopPropagation()}
    >
      <div className="sidebar__brand">
        <Link to="/" className="sidebar__logo" title="HypoWeaver · 研究项目">
          <span className="sidebar__mark" aria-hidden="true">
            H
          </span>
          {!collapsed && (
            <span className="sidebar__name">
              <strong>HypoWeaver</strong>
              <small>实证科研工作台</small>
            </span>
          )}
        </Link>
        <button
          type="button"
          className="sidebar__fold"
          aria-label={collapsed ? '展开侧边栏' : '折叠侧边栏'}
          onClick={onToggle}
        >
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>
      </div>
      <nav className="sidebar__nav" aria-label="主导航">
        <button
          type="button"
          className="sidebar__link"
          title="新研究"
          onClick={() => navigate('/?new=1')}
        >
          <Plus size={16} aria-hidden="true" />
          {!collapsed && <span>新研究</span>}
        </button>
        <NavLink
          end
          to="/"
          className={({ isActive }) => `sidebar__link ${isActive ? 'is-active' : ''}`}
        >
          <FolderKanban size={16} aria-hidden="true" />
          {!collapsed && <span>项目</span>}
        </NavLink>
      </nav>
      {!collapsed && (
        <div className="sidebar__collections">
          <section className="sidebar__projects" aria-labelledby="sidebar-projects-label">
            <div className="sidebar__group-row">
              <p className="sidebar__group" id="sidebar-projects-label">
                项目
              </p>
            </div>
            {projects.data?.length === 0 && <p className="sidebar__empty">还没有项目。</p>}
            <div className="sidebar__list" role="list">
              {projects.data?.map((p) => (
                <Link
                  role="listitem"
                  key={p.id}
                  to={`/p/${p.id}`}
                  className={`sidebar__task ${p.id === activeProjectId ? 'is-active' : ''}`}
                  title={p.title}
                >
                  <span className="sidebar__dot is-project" aria-hidden="true" />
                  <span className="sidebar__task-copy">
                    <strong>{p.title}</strong>
                    <small>更新于 {new Date(p.updated_at).toLocaleDateString('zh-CN')}</small>
                  </span>
                </Link>
              ))}
            </div>
          </section>
        </div>
      )}
      <div className="sidebar__foot">
        <NavLink
          to="/settings"
          className={({ isActive }) => `sidebar__link ${isActive ? 'is-active' : ''}`}
          title="设置"
        >
          <Settings2 size={16} aria-hidden="true" />
          {!collapsed && <span>设置</span>}
          <span
            className={`sidebar__service ${llm.data?.configured ? 'is-ready' : ''}`}
            title={llm.data?.configured ? `模型已配置：${llm.data.llm_model}` : '模型未配置'}
          />
        </NavLink>
      </div>
    </aside>
  )
}
