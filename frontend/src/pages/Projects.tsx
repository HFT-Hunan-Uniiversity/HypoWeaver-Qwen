import { ScrollRegion } from '../components/shell/ShellContext'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { api, body, type Project } from '../api/client'
import { ErrorNote } from '../components/Shared'
import { displayProjectTitle, timeGreeting } from '../lib/displayTitle'
import { STAGE_ORDER, STAGE_TITLES } from '../lib/stages'

const BLURB =
  '从问题出发，走完文献、选题、方案、数据与检验，最后生成可审查的研究提案。每一步可确认、可回溯。'

export default function Projects() {
  const query = useQuery({ queryKey: ['projects'], queryFn: () => api<Project[]>('/projects') })
  const [search, setSearch] = useSearchParams()
  const [open, setOpenState] = useState(search.get('new') === '1')
  const [title, setTitle] = useState('')
  const [deleting, setDeleting] = useState<Project | null>(null)
  const setOpen = (v: boolean) => {
    setOpenState(v)
    if (!v && search.get('new')) setSearch({})
  }
  if (search.get('new') === '1' && !open) setOpenState(true)
  const navigate = useNavigate()
  const cache = useQueryClient()
  const greet = useMemo(() => timeGreeting(), [])
  const create = useMutation({
    mutationFn: () => api<Project>('/projects', body('POST', { title })),
    onSuccess: (p) => {
      cache.invalidateQueries({ queryKey: ['projects'] })
      navigate(`/p/${p.id}`)
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

  return (
    <div className="home">
      <div className="home__grid">
        <aside className="home__intro" aria-label="欢迎">
          <p className="home__eyebrow">HypoWeaver · 文献·数据·判断</p>
          <h1 className="home__greet">
            {greet}，<span className="home__greet-em">研究者</span>
          </h1>
          <p className="home__blurb">{BLURB}</p>
          <ol className="home__steps" aria-label="六步研究流程">
            {STAGE_ORDER.map((k, i) => (
              <li key={k}>
                <span className="home__step-n">{i + 1}</span>
                <span className="home__step-lab">{STAGE_TITLES[k]}</span>
              </li>
            ))}
          </ol>
          <button
            type="button"
            className="product-button is-primary home__new"
            onClick={() => setOpen(true)}
          >
            <Plus size={16} aria-hidden="true" /> 新建项目
          </button>
        </aside>

        <section className="home__panel" aria-label="研究项目">
          <header className="home__panel-hd">
            <div>
              <h2>我的项目</h2>
              <p className="muted">点开继续；标题仅作展示，不改动原始记录。</p>
            </div>
            <button
              type="button"
              className="product-button is-quiet home__new-quiet"
              onClick={() => setOpen(true)}
            >
              <Plus size={14} aria-hidden="true" /> 新建
            </button>
          </header>
          <ErrorNote error={query.error || remove.error} />
          {query.isPending ? (
            <p className="home__loading">正在读取项目…</p>
          ) : projects.length ? (
            <ScrollRegion className="home__list" label="项目列表">
              {projects.map((p, i) => (
                <article key={p.id} className="home__card" style={{ ['--i' as string]: i }}>
                  <div className="home__card-main">
                    <Link className="home__card-title" to={`/p/${p.id}?open=1`}>
                      {displayProjectTitle(p.title, p.id)}
                    </Link>
                    <p className="home__card-dir">{p.direction?.text || '尚未填写研究方向'}</p>
                    <small className="home__card-meta">
                      更新于{' '}
                      {new Date(p.updated_at).toLocaleString('zh-CN', {
                        timeZone: 'Asia/Shanghai',
                      })}
                    </small>
                  </div>
                  <button
                    type="button"
                    className="product-button is-quiet home__card-del"
                    disabled={remove.isPending}
                    onClick={() => setDeleting(p)}
                  >
                    删除
                  </button>
                </article>
              ))}
            </ScrollRegion>
          ) : (
            !query.error && (
              <div className="home__empty">
                <h3>把第一个研究问题放在这里</h3>
                <p className="muted">创建后按六步向导推进：文献 → 选题 → 方案 → 数据 → 提案。</p>
                <button
                  type="button"
                  className="product-button is-primary"
                  onClick={() => setOpen(true)}
                >
                  <Plus size={16} aria-hidden="true" /> 新建研究项目
                </button>
              </div>
            )
          )}
        </section>
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
                create.mutate()
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
