import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { api, body, type Project } from '../api/client'
import { ErrorNote } from '../components/Shared'
import { AppSidebar, type ShellNav } from '../components/home/AppSidebar'
import { TaskComposer } from '../components/home/TaskComposer'
import { displayProjectTitle } from '../lib/displayTitle'
import { useLlm } from '../lib/llm'

type ThemeMode = 'day' | 'night'

function loadTheme(): ThemeMode {
  try {
    const v = localStorage.getItem('hw.ui.theme')
    if (v === 'night' || v === 'dark') return 'night'
    if (v === 'day' || v === 'light') return 'day'
  } catch {
    /* ignore */
  }
  return 'day'
}

function loadCollapsed(): boolean {
  try {
    return localStorage.getItem('hw-sidebar') === '1'
  } catch {
    return false
  }
}

export default function Projects() {
  const query = useQuery({ queryKey: ['projects'], queryFn: () => api<Project[]>('/projects') })
  const llm = useLlm()
  const [search, setSearch] = useSearchParams()
  const [nav, setNav] = useState<ShellNav>(() => {
    const v = search.get('view')
    if (v === 'projects') return 'projects'
    if (v === 'library') return 'library'
    return 'new'
  })
  const [theme, setTheme] = useState<ThemeMode>(loadTheme)
  const [collapsed, setCollapsed] = useState(loadCollapsed)
  const [deleting, setDeleting] = useState<Project | null>(null)
  const navigate = useNavigate()
  const cache = useQueryClient()

  useEffect(() => {
    try {
      localStorage.setItem('hw.ui.theme', theme === 'night' ? 'dark' : 'light')
      localStorage.setItem('hw-sidebar', collapsed ? '1' : '0')
    } catch {
      /* ignore */
    }
  }, [theme, collapsed])

  const create = useMutation({
    mutationFn: (title: string) =>
      api<Project>('/projects', body('POST', { title: title.trim().slice(0, 200) })),
    onSuccess: (p) => {
      cache.invalidateQueries({ queryKey: ['projects'] })
      navigate(`/p/${p.id}/direction`)
    },
  })
  const remove = useMutation({
    mutationFn: (id: string) => api(`/projects/${id}`, body('DELETE')),
    onSuccess: () => {
      setDeleting(null)
      cache.invalidateQueries({ queryKey: ['projects'] })
    },
  })

  const projects = query.data || []
  const sidebarProjects = useMemo(
    () =>
      projects.slice(0, 12).map((p) => ({
        id: p.id,
        title: displayProjectTitle(p.title, p.id),
        statusText: p.direction?.text ? '可继续' : '待开始',
      })),
    [projects],
  )
  const sidebarTasks = useMemo(
    () =>
      projects.slice(0, 8).map((p) => ({
        id: p.id,
        title: displayProjectTitle(p.title, p.id),
        statusText: p.direction?.text ? '进行中 · 分步向导' : '待开始 · 分步向导',
        tone: (p.direction?.text ? 'is-live' : 'is-wait') as 'is-live' | 'is-wait',
      })),
    [projects],
  )

  const goNav = (next: ShellNav) => {
    if (next === 'settings') {
      navigate('/settings')
      return
    }
    setNav(next)
    const sp = new URLSearchParams(search)
    if (next === 'new') sp.delete('view')
    else sp.set('view', next)
    setSearch(sp)
  }

  return (
    <div className={`shell ${collapsed ? 'is-collapsed' : ''} theme-${theme}`} data-theme={theme}>
      <AppSidebar
        nav={nav}
        projects={sidebarProjects}
        tasks={sidebarTasks}
        theme={theme}
        collapsed={collapsed}
        llmConfigured={!!llm.data?.configured}
        onToggleCollapse={() => setCollapsed((c) => !c)}
        onToggleTheme={() => setTheme((t) => (t === 'day' ? 'night' : 'day'))}
        onNavigate={goNav}
        onOpenProject={(id) => navigate(`/p/${id}?open=1`)}
      />
      <div className="shell-main">
        <div className="shell-view">
          {nav === 'new' && (
            <>
              <ErrorNote error={create.error || query.error} />
              <TaskComposer
                busy={create.isPending}
                onCreateProject={(prompt) => create.mutate(prompt)}
                onOpenSettings={() => navigate('/settings')}
              />
            </>
          )}
          {nav === 'projects' && (
            <div className="shell-view--scroll" style={{ padding: '20px 24px 40px' }}>
              <header
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  justifyContent: 'space-between',
                  gap: 12,
                  marginBottom: 16,
                }}
              >
                <div>
                  <h1
                    style={{
                      margin: 0,
                      fontFamily: 'var(--font-serif)',
                      fontSize: 24,
                      fontWeight: 550,
                    }}
                  >
                    我的项目
                  </h1>
                  <p className="muted" style={{ margin: '4px 0 0', fontSize: 12 }}>
                    展示名已隐藏验收编码；原始记录保留。
                  </p>
                </div>
                <button
                  type="button"
                  className="product-button is-primary"
                  onClick={() => goNav('new')}
                >
                  <Plus size={15} aria-hidden="true" /> 新建项目
                </button>
              </header>
              <ErrorNote error={query.error || remove.error} />
              {query.isPending ? (
                <p className="muted">正在读取项目…</p>
              ) : projects.length ? (
                <ul
                  style={{
                    listStyle: 'none',
                    margin: 0,
                    padding: 0,
                    borderTop: '1px solid var(--hairline)',
                  }}
                >
                  {projects.map((p) => (
                    <li
                      key={p.id}
                      style={{
                        display: 'flex',
                        gap: 12,
                        justifyContent: 'space-between',
                        padding: '14px 4px',
                        borderBottom: '1px solid var(--hairline)',
                      }}
                    >
                      <div>
                        <Link
                          to={`/p/${p.id}?open=1`}
                          style={{ color: 'var(--brand)', fontWeight: 650 }}
                        >
                          {displayProjectTitle(p.title, p.id)}
                        </Link>
                        <p className="muted" style={{ margin: '4px 0', fontSize: 12.5 }}>
                          {p.direction?.text || '尚未填写研究方向'}
                        </p>
                        <small className="muted">
                          更新于{' '}
                          {new Date(p.updated_at).toLocaleString('zh-CN', {
                            timeZone: 'Asia/Shanghai',
                          })}
                        </small>
                      </div>
                      <button
                        type="button"
                        className="product-button is-quiet"
                        disabled={remove.isPending}
                        onClick={() => setDeleting(p)}
                      >
                        删除
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                !query.error && (
                  <div style={{ textAlign: 'center', padding: 40 }}>
                    <h2 style={{ margin: '0 0 8px' }}>还没有项目</h2>
                    <button
                      type="button"
                      className="product-button is-primary"
                      onClick={() => goNav('new')}
                    >
                      从新研究开始
                    </button>
                  </div>
                )
              )}
            </div>
          )}
          {nav === 'library' && (
            <div className="shell-view--scroll" style={{ padding: '20px 24px 40px' }}>
              <h1
                style={{
                  margin: '0 0 8px',
                  fontFamily: 'var(--font-serif)',
                  fontSize: 24,
                  fontWeight: 550,
                }}
              >
                研究资源库
              </h1>
              <p className="muted" style={{ marginBottom: 16 }}>
                文献、数据与模型配置入口（复赛演示占位）。
              </p>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill,minmax(200px,1fr))',
                  gap: 12,
                }}
              >
                <Link
                  to="/settings"
                  style={{
                    display: 'block',
                    padding: 16,
                    border: '1px solid var(--hairline)',
                    borderRadius: 'var(--radius)',
                    background: 'var(--surface-2)',
                    color: 'inherit',
                    textDecoration: 'none',
                  }}
                >
                  <strong>模型与设置</strong>
                  <p className="muted" style={{ margin: '6px 0 0', fontSize: 12 }}>
                    配置千问等生成模型。
                  </p>
                </Link>
                <button
                  type="button"
                  onClick={() => goNav('projects')}
                  style={{
                    textAlign: 'left',
                    padding: 16,
                    border: '1px solid var(--hairline)',
                    borderRadius: 'var(--radius)',
                    background: 'var(--surface-2)',
                    cursor: 'pointer',
                  }}
                >
                  <strong>项目内文件</strong>
                  <p className="muted" style={{ margin: '6px 0 0', fontSize: 12 }}>
                    打开项目后在向导顶栏查看全部文件。
                  </p>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {deleting && (
        <div className="overlay">
          <section
            className="dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-title"
          >
            <h2 id="delete-title">删除项目</h2>
            <p>确认删除“{displayProjectTitle(deleting.title, deleting.id)}”？项目内容将被删除。</p>
            <ErrorNote error={remove.error} />
            <div className="actions">
              <button type="button" className="quiet" onClick={() => setDeleting(null)}>
                取消
              </button>
              <button
                type="button"
                disabled={remove.isPending}
                onClick={() => remove.mutate(deleting.id)}
              >
                确认删除
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
