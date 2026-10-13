import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, body, type Project } from '../api/client'
import { ErrorNote } from '../components/Shared'
import { ScrollRegion } from '../components/shell/ShellContext'
import Landscape from '../components/Landscape'
import PdfUpload from '../components/PdfUpload'
import EvidenceEdit from '../components/EvidenceEdit'
import { useFlow, useFlowStage, useStageUi } from '../components/flow/FlowContext'
import { EmptyState, ProgressView } from '../components/flow/FlowBits'
import { fromDirection, searchTerms } from '../lib/directionCard'
import { useLlm } from '../lib/llm'
export interface Evidence {
  id: string
  title: string
  authors: string[]
  year: number | null
  venue: string
  doi: string | null
  cited_by: number | null
  abstract: string | null
  fulltext_excerpt: string | null
  source: string
  sources: string[]
  included: boolean
  concepts: string[]
}
interface Search {
  id: string
  queries: { text: string }[]
  hit_count: number
  created_at: string
  status: string
  job_id: string
  per_source_status: Record<string, { status: string; reason: string; hits: number }>
}
const PAGE = 30
const norm = (s: string) =>
  s
    .replace(/[（(].*?[)）]/g, '')
    .trim()
    .toLowerCase()
const textOf = (c: Evidence) =>
  `${c.title} ${c.abstract || ''} ${c.concepts.join(' ')}`.toLowerCase()
/** 摘要首句作为"一句话结论"（后端暂无结论字段） */
const firstSentence = (s: string | null) => {
  if (!s) return '来源未提供摘要'
  const m = s.match(/^.{20,160}?[。.!?！？](\s|$)/)
  return (m ? m[0] : s.slice(0, 120) + (s.length > 120 ? '…' : '')).trim()
}

export default function Literature() {
  const { id } = useParams()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const { confirm } = useFlow()
  const stage = useFlowStage('literature')
  const llm = useLlm()
  const [page, setPage] = useState(0)
  const [queries, setQueries] = useState('')
  const [flash, setFlash] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const project = useQuery({
    queryKey: ['project', id],
    queryFn: () => api<Project>(`/projects/${id}`),
  })
  const cards = useQuery({
    queryKey: ['evidence', id],
    queryFn: () => api<Evidence[]>(`/projects/${id}/evidence`),
  })
  const searches = useQuery({
    queryKey: ['searches', id],
    queryFn: () => api<Search[]>(`/projects/${id}/searches`),
    refetchInterval: (q) => (q.state.data?.some((s) => s.status === 'running') ? 1500 : false),
  })
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['evidence', id] })
    qc.invalidateQueries({ queryKey: ['searches', id] })
    qc.invalidateQueries({ queryKey: ['landscape', id] })
    qc.invalidateQueries({ queryKey: ['overview', id] })
  }
  const card = project.data ? fromDirection(project.data.direction) : null
  // 方向卡有变量 / 关键词时用它们；旧项目回退到最近一次检索式里的词
  const cardTerms = card && (card.vars.length || card.keywords.length) ? searchTerms(card) : []
  const queryTerms = [
    ...new Set(
      (searches.data?.[0]?.queries || [])
        .flatMap((q) => q.text.split(/\s+|OR|AND/))
        .map((t) => t.replace(/["()]/g, '').trim())
        .filter((t) => t.length >= 2),
    ),
  ].slice(0, 6)
  const terms = cardTerms.length ? cardTerms : queryTerms
  const vars = (card?.vars || []).map(norm).filter(Boolean)
  const defaultQueries = () => {
    const t = terms.slice(0, 5)
    return [t.join(' '), ...t].filter(Boolean).slice(0, 6)
  }
  const search = useMutation({
    mutationFn: async (custom?: string[]) => {
      let qs = custom && custom.length ? custom : defaultQueries()
      if (!custom && llm.data?.configured) {
        try {
          const r = await api<{ queries: { text: string }[] }>(
            `/projects/${id}/queries:suggest`,
            body('POST'),
          )
          if (r.queries.length) qs = r.queries.map((q) => q.text)
        } catch {
          /* 模型建议失败时退回方向卡关键词 */
        }
      }
      if (!qs.length) qs = [project.data?.direction.text || '']
      return api<{ job_id: string }>(
        `/projects/${id}/searches`,
        body('POST', { queries: qs.map((text) => ({ text })) }),
      )
    },
    onSuccess: () => {
      setPage(0)
      refresh()
    },
  })
  const include = useMutation({
    mutationFn: (c: Evidence) => api(`/evidence/${c.id}`, body('PATCH', { included: !c.included })),
    onSuccess: refresh,
  })
  const running = searches.data?.find((s) => s.status === 'running')
  // 检索结束时刷新证据列表（自动切到结果）
  const wasRunning = useRef<string | undefined>(undefined)
  useEffect(() => {
    if (wasRunning.current && !running) refresh()
    wasRunning.current = running?.id
  }, [running?.id]) // eslint-disable-line react-hooks/exhaustive-deps
  const list = cards.data || []
  const included = list.filter((c) => c.included)
  const lastSearch = searches.data?.[0]
  const lastFailed =
    lastSearch?.status === 'failed'
      ? '上次检索失败：' +
        Object.values(lastSearch.per_source_status)
          .map((s) => s.reason)
          .filter(Boolean)
          .join('；')
      : null

  // 从方向阶段过来（?auto=1）且尚无证据：自动开始检索
  const autoDone = useRef(false)
  useEffect(() => {
    if (
      params.get('auto') &&
      !autoDone.current &&
      cards.data &&
      searches.data &&
      project.data &&
      stage.editable
    ) {
      autoDone.current = true
      const p = new URLSearchParams(params)
      p.delete('auto')
      setParams(p, { replace: true })
      if (!cards.data.length && !searches.data.some((s) => s.status === 'running'))
        search.mutate(undefined)
    }
  }, [params, cards.data, searches.data, project.data, stage.editable]) // eslint-disable-line react-hooks/exhaustive-deps

  // 相关度：方向卡关键词 / 变量在标题、摘要、主题词中的命中比例
  const scored = useMemo(() => {
    const ts = terms.map(norm).filter(Boolean)
    return list
      .map((c) => {
        const t = textOf(c)
        const hit = ts.filter((x) => t.includes(x)).length
        const rel = ts.length ? hit / ts.length : 0
        const vHit = card?.vars.filter((v) => norm(v) && t.includes(norm(v))) || []
        return { c, rel, vHit }
      })
      .sort((a, b) => Number(b.c.included) - Number(a.c.included) || b.rel - a.rel)
  }, [list, terms.join('|'), card?.vars.join('|')]) // eslint-disable-line react-hooks/exhaustive-deps

  const relations = useMemo(() => {
    const vs = card?.vars || []
    if (vs.length < 2) return []
    const y = vs[1]
    return [vs[0], ...vs.slice(2)].map((x) => ({ label: `${x} → ${y}`, a: norm(x), b: norm(y) }))
  }, [card?.vars.join('|')]) // eslint-disable-line react-hooks/exhaustive-deps
  const coverage = relations.map((r) => ({
    ...r,
    n: included.filter((c) => {
      const t = textOf(c)
      return t.includes(r.a) && t.includes(r.b)
    }).length,
  }))

  const goSelect = () => {
    listRef.current?.scrollTo({ top: 0 })
    setFlash(true)
    setTimeout(() => setFlash(false), 1200)
  }
  useStageUi({
    checklist: [
      { label: '检索文献', done: list.length > 0 },
      { label: '勾选证据', done: included.length > 0 },
    ],
    primary:
      running || search.isPending
        ? { label: '正在检索…', busy: true }
        : !list.length
          ? {
              label: '检索文献',
              onClick: () => search.mutate(undefined),
              error: search.error ? (search.error as Error).message : lastFailed,
            }
          : !included.length
            ? {
                label: '去勾选证据',
                onClick: goSelect,
                reason: `已找到 ${list.length} 篇，勾选认可的证据`,
              }
            : {
                label: '确认并进入下一阶段',
                reason: `已选 ${included.length} 篇证据`,
                onClick: () => {
                  if (!confirm('literature')) navigate(`/p/${id}/candidates`)
                },
              },
  })

  // —— 统计 ——
  const sources = new Map<string, number>()
  list.forEach((c) => c.sources.forEach((s) => sources.set(s, (sources.get(s) || 0) + 1)))
  const years = list.map((c) => c.year).filter((y): y is number => !!y)
  const ymin = Math.min(...years),
    ymax = Math.max(...years)
  const buckets = years.length ? Array.from({ length: Math.min(8, ymax - ymin + 1) }, () => 0) : []
  years.forEach((y) => {
    const i = Math.min(
      buckets.length - 1,
      Math.floor(((y - ymin) / Math.max(1, ymax - ymin + 1)) * buckets.length),
    )
    buckets[i]++
  })
  const bmax = Math.max(1, ...buckets)
  const kwHits = terms
    .slice(0, 4)
    .map((t) => ({ t, n: list.filter((c) => textOf(c).includes(norm(t))).length }))
  const offset = page * PAGE

  const reference = (
    <details className="flow-ref panel">
      <summary>参考与工具：检索式、检索记录、上传 PDF、文献图景</summary>
      <div className="lit-ref">
        <ScrollRegion label="检索式与记录">
          <label>
            自定义检索式（每行一条，最多 6 条）
            <textarea
              rows={3}
              value={queries}
              onChange={(e) => setQueries(e.target.value)}
              placeholder={defaultQueries().join('\n')}
            />
          </label>
          <button
            className="secondary"
            disabled={!!running || !queries.trim() || !stage.editable}
            onClick={() =>
              search.mutate(
                queries
                  .split('\n')
                  .map((s) => s.trim())
                  .filter(Boolean)
                  .slice(0, 6),
              )
            }
          >
            用这些检索式再检索
          </button>
          {searches.data?.map((s) => (
            <p key={s.id} className="muted">
              {new Date(s.created_at).toLocaleString('zh-CN')} ·{' '}
              {s.status === 'failed' ? '失败' : `${s.hit_count} 条`} ·{' '}
              {s.queries.map((q) => q.text).join('；')}
            </p>
          ))}
          <PdfUpload projectId={id!} />
        </ScrollRegion>
        <ScrollRegion label="文献图景">
          <Landscape projectId={id!} />
        </ScrollRegion>
      </div>
    </details>
  )

  if (cards.isPending || searches.isPending) return <p className="loading-line">正在读取文献…</p>
  if (running || search.isPending)
    return (
      <>
        <ProgressView
          title="正在检索文献"
          detail={
            running ? `检索式：${running.queries.map((q) => q.text).join('；')}` : '正在生成检索式…'
          }
          steps={
            running && !Object.keys(running.per_source_status).length
              ? running.queries.map((q) => ({ label: q.text, state: 'now' as const }))
              : running
                ? Object.entries(running.per_source_status).map(([k, v]) => ({
                    label: `${k}${v.hits ? ` · ${v.hits} 条` : ''}`,
                    state: v.status === 'ok' ? 'done' : v.status === 'failed' ? 'failed' : 'now',
                  }))
                : undefined
          }
        />
      </>
    )
  if (!list.length)
    return (
      <>
        <ErrorNote error={search.error || cards.error} />
        <EmptyState
          title="这里会列出与你的问题相关的论文"
          what={`系统会用方向卡的关键词（${terms.slice(0, 4).join('、') || '研究方向'}）检索多个文献库。每篇写明：与问题的相关度、一句话要点、涉及哪条变量关系。你只需要勾选认可的证据。`}
          example={{
            title: '碳排放权交易与企业绿色技术创新：来自试点政策的证据（2021 · 经济研究）',
            body: '相关度 92% · 要点：试点使企业绿色专利申请增加约 10% · 支持：碳交易试点 → 绿色专利',
          }}
          action={
            stage.editable
              ? { label: '检索文献', onClick: () => search.mutate(undefined) }
              : undefined
          }
        />
        {reference}
      </>
    )

  return (
    <>
      <ErrorNote error={include.error || search.error} />
      <div className="lit-strip" aria-label="检索摘要">
        <div>
          <b>{list.length}</b> 篇论文
          <small>
            {lastSearch ? `最近一次检索 ${lastSearch.hit_count} 条去重结果` : ''} · 已选{' '}
            {included.length}
          </small>
        </div>
        <div>
          来源
          {[...sources.entries()].slice(0, 4).map(([k, n]) => (
            <span key={k} className="lit-pill">
              {k} {n}
            </span>
          ))}
        </div>
        {buckets.length > 0 && (
          <div title="年份分布">
            年份
            <span className="lit-bars" aria-hidden="true">
              {buckets.map((b, i) => (
                <i key={i} style={{ height: 4 + (b / bmax) * 18 }} />
              ))}
            </span>
            <small>
              {ymin}–{ymax}
            </small>
          </div>
        )}
        {kwHits.length > 0 && (
          <div>
            关键词命中
            {kwHits.map((k) => (
              <span key={k.t} className="lit-pill">
                {k.t} {k.n}
              </span>
            ))}
          </div>
        )}
      </div>
      <div className="lit-main fill">
        <div className={`lit-list-wrap ${flash ? 'is-flash' : ''}`}>
          <ScrollRegion className="lit-list" label="论文列表">
            <div ref={listRef} />
            {scored.slice(offset, offset + PAGE).map(({ c, rel, vHit }) => (
              <article key={c.id} className={`lit-paper ${c.included ? 'is-on' : ''}`}>
                <input
                  type="checkbox"
                  aria-label={`选为证据：${c.title}`}
                  checked={c.included}
                  disabled={include.isPending || !stage.editable}
                  onChange={() => include.mutate(c)}
                />
                <div className="lit-paper__body">
                  <h3 title={c.title}>{c.title}</h3>
                  <div className="lit-paper__meta">
                    <span>
                      {c.year || '年份未知'} · {c.venue || c.source}
                    </span>
                    <span className="lit-rel" title="方向卡关键词在标题、摘要中的命中比例">
                      <i style={{ width: Math.max(4, rel * 56) }} />
                      相关度 {Math.round(rel * 100)}%
                    </span>
                    <span className="lit-tag">
                      {vHit.length >= 2
                        ? `支持：${vHit[0]} → ${vHit[1]}`
                        : vHit.length === 1
                          ? `涉及：${vHit[0]}`
                          : '未直接涉及方向卡变量'}
                    </span>
                    {c.cited_by !== null && <span>被引 {c.cited_by}</span>}
                  </div>
                  <p className="lit-paper__gist">
                    要点：{firstSentence(c.abstract || c.fulltext_excerpt)}
                  </p>
                  <details>
                    <summary>摘要与编辑</summary>
                    <p className="abstract">{c.abstract || '来源未提供摘要'}</p>
                    <EvidenceEdit card={c} projectId={id!} />
                  </details>
                </div>
              </article>
            ))}
          </ScrollRegion>
          {list.length > PAGE && (
            <div className="lit-pager">
              <button className="quiet" disabled={page === 0} onClick={() => setPage(page - 1)}>
                上一页
              </button>
              <span>
                第 {page + 1} / {Math.ceil(list.length / PAGE)} 页
              </span>
              <button
                className="quiet"
                disabled={offset + PAGE >= list.length}
                onClick={() => setPage(page + 1)}
              >
                下一页
              </button>
            </div>
          )}
        </div>
        <aside className="panel lit-side" aria-label="已选证据">
          <h2>已选证据 · {included.length} 篇</h2>
          {coverage.length ? (
            coverage.map((r) => (
              <div key={r.label} className={`lit-cov ${r.n ? 'is-ok' : 'is-miss'}`}>
                {r.n ? '✓' : '还缺'} {r.label}
                {r.n > 0 && <small> · {r.n} 篇</small>}
              </div>
            ))
          ) : (
            <p className="muted">方向卡里还没有变量，无法按变量关系统计。</p>
          )}
          <p className="muted">
            {coverage.some((r) => !r.n)
              ? '缺证据的关系不影响继续，但候选假设会更少。'
              : coverage.length
                ? '每条变量关系都有证据支持。'
                : ''}
            按关键词匹配估计。
          </p>
          <ScrollRegion className="lit-side__list" label="已选论文">
            {included.map((c) => (
              <p key={c.id} className="lit-side__item" title={c.title}>
                {c.title}
              </p>
            ))}
          </ScrollRegion>
        </aside>
      </div>
      {reference}
    </>
  )
}
