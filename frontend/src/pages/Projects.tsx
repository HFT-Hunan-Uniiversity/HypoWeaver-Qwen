import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowUp,
  BarChart3,
  FolderOpen,
  Library,
  Moon,
  PanelLeft,
  Plus,
  Settings2,
  Sun,
  Map,
} from 'lucide-react'
import { api, body, type Project } from '../api/client'
import { ErrorNote } from '../components/Shared'
import { displayProjectTitle, timeGreeting } from '../lib/displayTitle'
import { ModelBanner } from '../components/shell/AppShell'

type View = 'home' | 'projects' | 'library'
type ThemeMode = 'light' | 'dark'

const THEMES = ['政策评估', '企业行为', '区域发展', '市场反应'] as const

const EXAMPLES: Record<(typeof THEMES)[number], { title: string; body: string; tag: string }[]> = {
  政策评估: [
    {
      title: '绿色信贷与高污染企业',
      body: '绿色信贷约束是否抑制高污染企业的扩张与排放强度？',
      tag: '分步向导 · 示例',
    },
    {
      title: '绿改试验区与空气质量',
      body: '绿色金融改革试验区对城市空气质量的处理效应如何识别？',
      tag: '分步向导 · 示例',
    },
  ],
  企业行为: [
    {
      title: '碳市场同群与绿色创新',
      body: '同行业控排企业出现后，上市公司绿色发明专利如何变化？',
      tag: '分步向导 · 示例',
    },
    {
      title: '数字化与全要素生产率',
      body: '企业数字化转型是否提升全要素生产率，机制何在？',
      tag: '分步向导 · 示例',
    },
  ],
  区域发展: [
    {
      title: '城市群协同与产业升级',
      body: '城市群一体化政策是否推动制造业向高技术环节升级？',
      tag: '分步向导 · 示例',
    },
    {
      title: '供应链韧性与出口',
      body: '供应链冲击下，韧性更高的企业出口表现是否更稳？',
      tag: '分步向导 · 示例',
    },
  ],
  市场反应: [
    {
      title: '环境规制与企业研发',
      body: '更严环境规制是挤出还是倒逼企业研发投入？',
      tag: '分步向导 · 示例',
    },
    {
      title: '税收激励与人力资本',
      body: '研发加计扣除是否改善企业人力资本结构？',
      tag: '分步向导 · 示例',
    },
  ],
}

function loadTheme(): ThemeMode {
  try {
    const v = localStorage.getItem('hw.ui.theme')
    if (v === 'dark' || v === 'light') return v
  } catch {
    /* ignore */
  }
  return 'light'
}

export default function Projects() {
  const query = useQuery({ queryKey: ['projects'], queryFn: () => api<Project[]>('/projects') })
  const [search, setSearch] = useSearchParams()
  const [view, setView] = useState<View>(() =>
    search.get('view') === 'projects' ? 'projects' : 'home',
  )
  const [theme, setTheme] = useState<ThemeMode>(loadTheme)
  const [topic, setTopic] = useState<(typeof THEMES)[number]>('政策评估')
  const [draft, setDraft] = useState('')
  const [open, setOpenState] = useState(search.get('new') === '1')
  const [title, setTitle] = useState('')
  const [deleting, setDeleting] = useState<Project | null>(null)
  const [sideCollapsed, setSideCollapsed] = useState(false)
  const greet = useMemo(() => timeGreeting(), [])
  const navigate = useNavigate()
  const cache = useQueryClient()

  const setOpen = (v: boolean) => {
    setOpenState(v)
    if (!v && search.get('new')) {
      const next = new URLSearchParams(search)
      next.delete('new')
      setSearch(next)
    }
  }
  if (search.get('new') === '1' && !open) setOpenState(true)

  useEffect(() => {
    document.documentElement.dataset.cxTheme = theme
    try {
      localStorage.setItem('hw.ui.theme', theme)
    } catch {
      /* ignore */
    }
  }, [theme])

  const create = useMutation({
    mutationFn: (t: string) => api<Project>('/projects', body('POST', { title: t.trim() })),
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
  const recent = projects.slice(0, 8)
  const examples = EXAMPLES[topic]

  const startNew = (preset?: string) => {
    const t = (preset ?? draft).trim()
    if (t) {
      create.mutate(t.slice(0, 200))
      return
    }
    setTitle('')
    setOpen(true)
  }

  const goView = (v: View) => {
    setView(v)
    const next = new URLSearchParams(search)
    if (v === 'projects') next.set('view', 'projects')
    else next.delete('view')
    setSearch(next)
  }

  return (
    <div className={`cx ${sideCollapsed ? 'is-collapsed' : ''}`} data-theme={theme}>
      <aside className="cx-side" aria-label="主导航">
        <div className="cx-side__top">
          <Link to="/" className="cx-brand" onClick={() => goView('home')}>
            <span className="cx-brand__mark" aria-hidden="true">
              H
            </span>
            {!sideCollapsed && (
              <span className="cx-brand__txt">
                <strong>HypoWeaver</strong>
                <small>实证科研工作流</small>
              </span>
            )}
          </Link>
          <button
            type="button"
            className="cx-iconbtn"
            aria-label={sideCollapsed ? '展开侧栏' : '收起侧栏'}
            onClick={() => setSideCollapsed((c) => !c)}
          >
            <PanelLeft size={15} />
          </button>
        </div>

        <nav className="cx-nav">
          <button
            type="button"
            className={`cx-nav__item is-accent ${view === 'home' ? 'is-on' : ''}`}
            onClick={() => {
              goView('home')
              startNew()
            }}
          >
            <Plus size={15} aria-hidden="true" />
            {!sideCollapsed && <span>新研究</span>}
          </button>
          <button
            type="button"
            className={`cx-nav__item ${view === 'projects' ? 'is-on' : ''}`}
            onClick={() => goView('projects')}
          >
            <Map size={15} aria-hidden="true" />
            {!sideCollapsed && <span>项目</span>}
          </button>
          <button
            type="button"
            className={`cx-nav__item ${view === 'library' ? 'is-on' : ''}`}
            onClick={() => goView('library')}
          >
            <Library size={15} aria-hidden="true" />
            {!sideCollapsed && <span>研究资源库</span>}
          </button>
        </nav>

        {!sideCollapsed && (
          <>
            <div className="cx-sec">
              <h3>项目</h3>
              <ul className="cx-sec__list">
                {query.isPending && <li className="cx-muted">读取中…</li>}
                {!query.isPending && recent.length === 0 && <li className="cx-muted">暂无项目</li>}
                {recent.map((p) => (
                  <li key={p.id}>
                    <Link
                      to={`/p/${p.id}?open=1`}
                      className="cx-sec__link"
                      title={displayProjectTitle(p.title, p.id)}
                    >
                      <span className="cx-sec__title">{displayProjectTitle(p.title, p.id)}</span>
                      <small>{p.direction?.text ? '可继续' : '待开始'}</small>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
            <div className="cx-sec">
              <h3>任务</h3>
              <ul className="cx-sec__list">
                {recent.slice(0, 5).map((p) => (
                  <li key={'t-' + p.id}>
                    <Link to={`/p/${p.id}?open=1`} className="cx-sec__link">
                      <span className="cx-sec__title">{displayProjectTitle(p.title, p.id)}</span>
                      <small>
                        <i className={`cx-dot ${p.direction?.text ? 'is-ok' : 'is-wait'}`} />
                        {p.direction?.text ? '进行中 · 分步向导' : '待开始 · 分步向导'}
                      </small>
                    </Link>
                  </li>
                ))}
                {!recent.length && !query.isPending && (
                  <li className="cx-muted">创建项目后出现在此</li>
                )}
              </ul>
            </div>
          </>
        )}

        <div className="cx-side__foot">
          <Link to="/settings" className="cx-nav__item">
            <Settings2 size={15} aria-hidden="true" />
            {!sideCollapsed && <span>设置</span>}
          </Link>
          <button
            type="button"
            className="cx-nav__item"
            onClick={() => setTheme((t) => (t === 'light' ? 'dark' : 'light'))}
            aria-pressed={theme === 'dark'}
          >
            {theme === 'light' ? (
              <Moon size={15} aria-hidden="true" />
            ) : (
              <Sun size={15} aria-hidden="true" />
            )}
            {!sideCollapsed && <span>{theme === 'light' ? '夜间模式' : '日间模式'}</span>}
          </button>
        </div>
      </aside>

      <div className="cx-main">
        <ModelBanner />
        {view === 'home' && (
          <div className="cx-home">
            <header className="cx-home__bar">
              <span>新研究</span>
            </header>
            <div className="cx-home__center">
              <h1 className="cx-greet">
                {greet}，<em>研究者</em>
              </h1>
              <p className="cx-badge">分步向导 · 六步流程</p>
              <p className="cx-blurb">
                描述研究目标，创建项目后按文献、选题、方案、数据与检验、提案逐步推进；每一步可确认、可回溯。
              </p>
              <div className="cx-pills" role="tablist" aria-label="研究主题">
                {THEMES.map((t) => (
                  <button
                    key={t}
                    type="button"
                    role="tab"
                    aria-selected={topic === t}
                    className={topic === t ? 'is-on' : ''}
                    onClick={() => setTopic(t)}
                  >
                    {t}
                  </button>
                ))}
              </div>
              <div className="cx-examples">
                {examples.map((ex) => (
                  <button
                    key={ex.title}
                    type="button"
                    className="cx-ex"
                    onClick={() => {
                      setDraft(ex.title)
                      startNew(ex.title)
                    }}
                  >
                    <strong>{ex.title}</strong>
                    <span>{ex.body}</span>
                    <small>{ex.tag}</small>
                  </button>
                ))}
              </div>
            </div>
            <div className="cx-composer">
              <label className="cx-composer__box">
                <textarea
                  rows={3}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder="描述你的研究任务，或从上方示例开始…"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                      e.preventDefault()
                      startNew()
                    }
                  }}
                />
                <div className="cx-composer__bar">
                  <div className="cx-composer__acts">
                    <button type="button" className="cx-chip" onClick={() => setOpen(true)}>
                      <Settings2 size={13} aria-hidden="true" /> 更多选项
                    </button>
                    <button
                      type="button"
                      className="cx-chip"
                      onClick={() => goView('library')}
                      title="导入与资源入口"
                    >
                      <FolderOpen size={13} aria-hidden="true" /> 导入资料
                    </button>
                    <span className="cx-chip is-static">
                      <BarChart3 size={13} aria-hidden="true" /> 研究模式 · 分步向导
                    </span>
                  </div>
                  <button
                    type="button"
                    className="cx-send"
                    aria-label="开始研究"
                    disabled={create.isPending}
                    onClick={() => startNew()}
                  >
                    <ArrowUp size={18} />
                  </button>
                </div>
              </label>
              <p className="cx-composer__hint">
                发送后将创建真实项目并进入研究方向；不会假装连接不存在的后端能力。
              </p>
              <ErrorNote error={create.error || query.error} />
            </div>
          </div>
        )}

        {view === 'projects' && (
          <div className="cx-list">
            <header className="cx-list__hd">
              <div>
                <h1>我的项目</h1>
                <p className="muted">展示名已隐藏验收编码；原始记录保留在后端。</p>
              </div>
              <button
                type="button"
                className="product-button is-primary"
                onClick={() => startNew()}
              >
                <Plus size={15} aria-hidden="true" /> 新建项目
              </button>
            </header>
            <ErrorNote error={query.error || remove.error} />
            {query.isPending ? (
              <p className="cx-muted">正在读取项目…</p>
            ) : projects.length ? (
              <ul className="cx-list__ul">
                {projects.map((p) => (
                  <li key={p.id}>
                    <div>
                      <Link to={`/p/${p.id}?open=1`}>{displayProjectTitle(p.title, p.id)}</Link>
                      <p className="muted">{p.direction?.text || '尚未填写研究方向'}</p>
                      <small>
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
                <div className="cx-empty">
                  <h2>还没有项目</h2>
                  <p className="muted">从「新研究」或下方输入框开始。</p>
                  <button
                    type="button"
                    className="product-button is-primary"
                    onClick={() => startNew()}
                  >
                    新建研究项目
                  </button>
                </div>
              )
            )}
          </div>
        )}

        {view === 'library' && (
          <div className="cx-lib">
            <header className="cx-list__hd">
              <div>
                <h1>研究资源库</h1>
                <p className="muted">文献、数据与模型配置的入口（复赛演示占位）。</p>
              </div>
            </header>
            <div className="cx-lib__grid">
              <Link to="/settings" className="cx-lib__card">
                <Settings2 size={18} aria-hidden="true" />
                <strong>模型与设置</strong>
                <span>配置千问等生成模型，生成类步骤可用。</span>
              </Link>
              <button type="button" className="cx-lib__card" onClick={() => goView('projects')}>
                <FolderOpen size={18} aria-hidden="true" />
                <strong>项目内文件</strong>
                <span>打开任一项目后，在向导顶栏查看「全部文件」。</span>
              </button>
              <button type="button" className="cx-lib__card" onClick={() => goView('home')}>
                <Plus size={18} aria-hidden="true" />
                <strong>从新研究开始</strong>
                <span>创建项目后按六步向导推进，再沉淀文献与数据。</span>
              </button>
            </div>
          </div>
        )}
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
      {open && (
        <div className="overlay">
          <section role="dialog" aria-modal="true" aria-labelledby="new-title" className="dialog">
            <h2 id="new-title">新建研究项目</h2>
            <form
              onSubmit={(e) => {
                e.preventDefault()
                create.mutate(title.trim().slice(0, 200))
              }}
            >
              <label>
                项目标题
                <input
                  autoFocus
                  required
                  maxLength={200}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="例如：碳市场与企业绿色创新"
                />
              </label>
              <ErrorNote error={create.error} />
              <div className="actions">
                <button type="button" className="quiet" onClick={() => setOpen(false)}>
                  取消
                </button>
                <button type="submit" disabled={create.isPending || !title.trim()}>
                  {create.isPending ? '正在创建…' : '创建项目'}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  )
}
