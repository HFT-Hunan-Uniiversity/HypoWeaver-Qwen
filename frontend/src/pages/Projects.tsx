import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Database, FolderKanban, Menu, Plus, Settings2, Trash2 } from 'lucide-react'
import { api, body, type Project } from '../api/client'
import type { Dataset } from '../api/datasets'
import { ErrorNote } from '../components/Shared'
import { AppSidebar, type ShellNav } from '../components/home/AppSidebar'
import { TaskComposer } from '../components/home/TaskComposer'
import { ModelBanner } from '../components/shell/AppShell'
import { fromDirection } from '../lib/directionCard'
import { displayProjectTitle } from '../lib/displayTitle'
import { useLlm } from '../lib/llm'

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
  const [collapsed, setCollapsed] = useState(loadCollapsed)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [deleting, setDeleting] = useState<Project | null>(null)
  const navigate = useNavigate()
  const cache = useQueryClient()

  const datasetsQuery = useQuery({
    queryKey: ['datasets'],
    queryFn: () => api<Dataset[]>('/datasets'),
    enabled: nav === 'library',
  })

  useEffect(() => {
    const v = search.get('view')
    if (v === 'projects') setNav('projects')
    else if (v === 'library') setNav('library')
    else setNav('new')
  }, [search])

  useEffect(() => {
    try {
      localStorage.setItem('hw.ui.theme', 'light')
      localStorage.setItem('hw-sidebar', collapsed ? '1' : '0')
    } catch {
      /* ignore */
    }
  }, [collapsed])

  const create = useMutation({
    mutationFn: (rawPrompt: string) => {
      const clean = rawPrompt.trim()
      const title = (clean || '新研究项目').slice(0, 200)
      return api<Project>('/projects', body('POST', { title }))
    },
    onSuccess: (p, rawPrompt) => {
      const clean = rawPrompt.trim()
      if (clean) {
        try {
          const question = clean.replace(/[。；！？!?]+$/, '') + '？'
          const card = {
            ...fromDirection(p.direction),
            idea: clean,
            question,
          }
          localStorage.setItem(`hw.dirdraft.${p.id}`, JSON.stringify({ card }))
        } catch {
          /* ignore */
        }
      }
      cache.invalidateQueries({ queryKey: ['projects'] })
      navigate(clean ? `/p/${p.id}/direction` : `/p/${p.id}/direction?direct=1`)
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
      projects.slice(0, 12).map((p) => {
        const hasDir = !!p.direction?.text?.trim()
        return {
          id: p.id,
          title: displayProjectTitle(p.title, p.id),
          statusText: hasDir ? '进行中 · 分步向导' : '第 1 步 · 待明确方向',
          tone: (hasDir ? 'is-live' : 'is-wait') as 'is-live' | 'is-wait',
        }
      }),
    [projects],
  )

  const goNav = (next: ShellNav) => {
    setDrawerOpen(false)
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

  const datasets = datasetsQuery.data || []

  return (
    <div
      className={`shell ${collapsed ? 'is-collapsed' : ''} ${drawerOpen ? 'is-drawer-open' : ''} theme-day`}
      data-theme="day"
    >
      <AppSidebar
        nav={nav}
        projects={sidebarProjects}
        projectCount={projects.length}
        collapsed={collapsed}
        llmConfigured={!!llm.data?.configured}
        onToggleCollapse={() => setCollapsed((c) => !c)}
        onNavigate={goNav}
        onOpenProject={(id) => {
          setDrawerOpen(false)
          navigate(`/p/${id}?open=1`)
        }}
      />
      {drawerOpen && (
        <button
          type="button"
          className="shell__scrim"
          aria-label="关闭侧边栏"
          onClick={() => setDrawerOpen(false)}
        />
      )}
      <div className="shell-main">
        <header className="main-toolbar">
          <button
            type="button"
            className="main-toolbar__menu"
            aria-label="打开导航菜单"
            onClick={() => setDrawerOpen(true)}
          >
            <Menu size={16} aria-hidden="true" />
          </button>
          <span className="main-toolbar__sep" aria-hidden="true" />
          <div className="main-toolbar__title">
            <strong>
              {nav === 'new'
                ? '新研究 · 分步向导起点'
                : nav === 'projects'
                  ? '我的研究项目'
                  : '数据与资源库'}
            </strong>
            <small>
              {nav === 'new'
                ? '1 研究方向 → 2 文献 → 3 候选假设 → 4 研究方案 → 5 数据与检验 → 6 研究提案'
                : nav === 'projects'
                  ? `共 ${projects.length} 个项目 · 点击进入六步向导`
                  : '全局共享数据资产与模型服务状态'}
            </small>
          </div>
          <div className="main-toolbar__actions">
            {nav !== 'new' && (
              <button
                type="button"
                className="product-button is-primary home-top-btn"
                onClick={() => goNav('new')}
              >
                <Plus size={14} aria-hidden="true" /> 新建研究
              </button>
            )}
            <Link to="/settings" className="nb-small" title="服务与用量设置">
              <Settings2 size={13} aria-hidden="true" />
              <span>{llm.data?.configured ? '千问已就绪' : '配置模型'}</span>
            </Link>
          </div>
        </header>
        <ModelBanner />
        <div className="shell-view">
          {nav === 'new' && (
            <>
              <ErrorNote error={create.error || query.error} />
              <TaskComposer
                busy={create.isPending}
                llmConfigured={!!llm.data?.configured}
                onCreateProject={(prompt) => create.mutate(prompt)}
                onOpenSettings={() => navigate('/settings')}
              />
            </>
          )}
          {nav === 'projects' && (
            <div className="shell-view--scroll home-subview">
              <div className="home-subview__inner">
                <section className="wz-card">
                  <header className="wz-card__hd">
                    <div>
                      <h2>我的研究项目</h2>
                      <p className="wz-card__sub">
                        每个项目沿六步向导独立保存状态与版本；点击即可回到当前阶段继续推进。
                      </p>
                    </div>
                    <button
                      type="button"
                      className="product-button is-primary"
                      onClick={() => goNav('new')}
                    >
                      <Plus size={14} aria-hidden="true" /> 新建研究项目
                    </button>
                  </header>
                  <ErrorNote error={query.error || remove.error} />
                  {query.isPending ? (
                    <p className="muted" style={{ marginTop: 12 }}>
                      正在读取项目…
                    </p>
                  ) : projects.length ? (
                    <ul className="home-proj-list">
                      {projects.map((p) => {
                        const hasDir = !!p.direction?.text?.trim()
                        return (
                          <li key={p.id} className="home-proj-item">
                            <div className="home-proj-item__main">
                              <div className="home-proj-item__head">
                                <Link to={`/p/${p.id}?open=1`} className="home-proj-item__title">
                                  {displayProjectTitle(p.title, p.id)}
                                </Link>
                                <span className={`wz-badge ${hasDir ? 'is-active' : 'is-stale'}`}>
                                  {hasDir ? '进行中 · 分步向导' : '第 1 步 · 待明确方向'}
                                </span>
                              </div>
                              <p className="home-proj-item__desc">
                                {p.direction?.text ||
                                  '尚未填写研究方向，进入向导第 1 步即可明确研究问题、变量与范围。'}
                              </p>
                              <small className="home-proj-item__meta">
                                更新于{' '}
                                {new Date(p.updated_at).toLocaleString('zh-CN', {
                                  timeZone: 'Asia/Shanghai',
                                })}
                              </small>
                            </div>
                            <div className="home-proj-item__acts">
                              <Link to={`/p/${p.id}?open=1`} className="product-button is-primary">
                                进入向导 <ArrowRight size={13} aria-hidden="true" />
                              </Link>
                              <button
                                type="button"
                                className="product-button is-quiet"
                                disabled={remove.isPending}
                                onClick={() => setDeleting(p)}
                                title="删除项目"
                              >
                                <Trash2 size={13} aria-hidden="true" /> 删除
                              </button>
                            </div>
                          </li>
                        )
                      })}
                    </ul>
                  ) : (
                    !query.error && (
                      <div className="home-empty-card">
                        <FolderKanban size={28} aria-hidden="true" />
                        <h3>还没有研究项目</h3>
                        <p>
                          从一个研究想法或启发模板开始，系统会带你逐步完成文献、方案与实证检验。
                        </p>
                        <button
                          type="button"
                          className="product-button is-primary"
                          onClick={() => goNav('new')}
                        >
                          开始第一个研究 <ArrowRight size={14} aria-hidden="true" />
                        </button>
                      </div>
                    )
                  )}
                </section>
              </div>
            </div>
          )}
          {nav === 'library' && (
            <div className="shell-view--scroll home-subview">
              <div className="home-subview__inner">
                <section className="wz-card">
                  <header className="wz-card__hd">
                    <div>
                      <h2>全局数据资产</h2>
                      <p className="wz-card__sub">
                        已导入的数据集可在任意项目的「5. 数据与检验」阶段直接选择并绑定变量。
                      </p>
                    </div>
                    <span className="wz-badge is-confirmed">共 {datasets.length} 份数据集</span>
                  </header>
                  {datasetsQuery.isPending ? (
                    <p className="muted" style={{ marginTop: 12 }}>
                      正在读取数据资产…
                    </p>
                  ) : datasets.length ? (
                    <div className="home-lib-grid">
                      {datasets.map((d) => (
                        <article key={d.id} className="home-lib-card">
                          <div className="home-lib-card__hd">
                            <span className="home-lib-card__icon" aria-hidden="true">
                              <Database size={15} />
                            </span>
                            <div>
                              <strong>{d.name}</strong>
                              <small>
                                {d.format.toUpperCase()} · {d.n_rows.toLocaleString()} 行 ×{' '}
                                {d.n_cols} 列
                              </small>
                            </div>
                          </div>
                          {d.panel?.detected && (
                            <p className="home-lib-card__meta">
                              面板结构：{d.panel.unit || '个体'} × {d.panel.time || '时间'}
                              {d.panel.n_units ? `（${d.panel.n_units} 个体）` : ''}
                            </p>
                          )}
                          {d.source?.citation && (
                            <p className="home-lib-card__cite">{d.source.citation}</p>
                          )}
                        </article>
                      ))}
                    </div>
                  ) : (
                    <p className="nb-hint" style={{ marginTop: 12 }}>
                      当前尚未导入全局数据集。进入任意项目的「5. 数据与检验」阶段即可上传
                      .csv、.xlsx 或 .dta 文件。
                    </p>
                  )}
                </section>

                <section className="wz-card" style={{ marginTop: 14 }}>
                  <header className="wz-card__hd">
                    <div>
                      <h2>模型与外部检索服务</h2>
                      <p className="wz-card__sub">
                        管理千问生成模型连接、查看 OpenAlex / Crossref 检索可用性与 Token 调用统计。
                      </p>
                    </div>
                    <span
                      className={`wz-badge ${llm.data?.configured ? 'is-confirmed' : 'is-stale'}`}
                    >
                      {llm.data?.configured ? '千问模型已配置' : '待配置密钥'}
                    </span>
                  </header>
                  <div className="home-lib-actions">
                    <Link to="/settings" className="product-button is-primary">
                      <Settings2 size={14} aria-hidden="true" /> 打开服务与用量设置
                    </Link>
                    <button
                      type="button"
                      className="product-button is-quiet"
                      onClick={() => goNav('projects')}
                    >
                      查看全部研究项目
                    </button>
                  </div>
                </section>
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
