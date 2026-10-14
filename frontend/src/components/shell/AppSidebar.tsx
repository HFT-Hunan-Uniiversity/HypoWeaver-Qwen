import { useState } from 'react'
import { createPortal } from 'react-dom'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FolderKanban, PanelLeftClose, PanelLeftOpen, Plus, Settings2, Trash2 } from 'lucide-react'
import { api, ApiError, type Project } from '../../api/client'
import { useLlm } from '../../lib/llm'
import { CaseTag } from '../CaseToggle'

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
  const qc = useQueryClient()
  const [deleting, setDeleting] = useState<Project | null>(null)
  const remove = useMutation({
    mutationFn: async (id: string) => {
      try {
        await api(`/projects/${id}`, { method: 'DELETE' })
      } catch (e) {
        // 已不存在视为删除成功；接口不支持时给出明确提示
        if (e instanceof ApiError && e.status === 404) return
        if (e instanceof ApiError && (e.status === 405 || e.status === 501))
          throw new Error('当前后端不支持删除项目。')
        throw e
      }
    },
    onSuccess: (_, id) => {
      for (const k of ['hw.flow.', 'hw.dirdraft.']) localStorage.removeItem(k + id)
      qc.setQueryData<Project[]>(['projects'], (old) => old?.filter((p) => p.id !== id))
      qc.removeQueries({ queryKey: ['project', id] })
      qc.invalidateQueries({ queryKey: ['projects'] })
      setDeleting(null)
      if (id === activeProjectId) navigate('/', { replace: true })
    },
  })
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
            <div className="sidebar__list" role="list" data-scroll-region="" aria-label="项目列表">
              {projects.data?.map((p) => (
                <div
                  role="listitem"
                  key={p.id}
                  className={`sidebar__row ${p.id === activeProjectId ? 'is-active' : ''}`}
                >
                  <Link
                    to={`/p/${p.id}`}
                    className={`sidebar__task ${p.id === activeProjectId ? 'is-active' : ''}`}
                    title={p.title}
                  >
                    <span className="sidebar__dot is-project" aria-hidden="true" />
                    <span className="sidebar__task-copy">
                      <strong>{p.title}</strong>
                      <small>
                        <CaseTag project={p} /> 更新于{' '}
                        {new Date(p.updated_at).toLocaleDateString('zh-CN')}
                      </small>
                    </span>
                  </Link>
                  <button
                    type="button"
                    className="sidebar__del"
                    aria-label={`删除项目：${p.title}`}
                    title="删除项目"
                    onClick={() => {
                      remove.reset()
                      setDeleting(p)
                    }}
                  >
                    <Trash2 size={14} aria-hidden="true" />
                  </button>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}
      {deleting &&
        createPortal(
          <div className="overlay" onClick={() => !remove.isPending && setDeleting(null)}>
            <section
              className="dialog sidebar-del-dialog"
              role="dialog"
              aria-modal="true"
              aria-labelledby="sidebar-del-title"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 id="sidebar-del-title">删除项目？</h2>
              <p>
                将删除「<strong>{deleting.title}</strong>
                」及其文献、方案、数据绑定、检验结果和提案。
                <strong className="danger-text">删除后不可恢复。</strong>
              </p>
              {remove.error && <p className="danger-text">{(remove.error as Error).message}</p>}
              <div className="actions">
                <button
                  type="button"
                  className="quiet"
                  disabled={remove.isPending}
                  onClick={() => setDeleting(null)}
                >
                  取消
                </button>
                <button
                  type="button"
                  className="product-button is-danger"
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(deleting.id)}
                >
                  {remove.isPending ? '正在删除…' : '删除项目'}
                </button>
              </div>
            </section>
          </div>,
          document.body,
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
