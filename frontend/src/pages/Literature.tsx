import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, body } from '../api/client'
import { ErrorNote } from '../components/Shared'
import Landscape from '../components/Landscape'
import PdfUpload from '../components/PdfUpload'
import EvidenceEdit from '../components/EvidenceEdit'
import JobProgress from '../components/JobProgress'
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
export default function Literature() {
  const { id } = useParams(),
    cache = useQueryClient()
  const [queries, setQueries] = useState(''),
    [job, setJob] = useState(''),
    [page, setPage] = useState(0)
  const cards = useQuery({
    queryKey: ['evidence', id],
    queryFn: () => api<Evidence[]>(`/projects/${id}/evidence`),
  })
  const searches = useQuery({
    queryKey: ['searches', id],
    queryFn: () => api<Search[]>(`/projects/${id}/searches`),
  })
  const refresh = () => {
    cache.invalidateQueries({ queryKey: ['evidence', id] })
    cache.invalidateQueries({ queryKey: ['searches', id] })
    cache.invalidateQueries({ queryKey: ['landscape', id] })
  }
  const suggest = useMutation({
    mutationFn: () =>
      api<{ queries: { text: string }[] }>(`/projects/${id}/queries:suggest`, body('POST')),
    onSuccess: (r) => setQueries(r.queries.map((q) => q.text).join('\n')),
  })
  const search = useMutation({
    mutationFn: () =>
      api<{ job_id: string }>(
        `/projects/${id}/searches`,
        body('POST', {
          queries: queries
            .split('\n')
            .map((s) => s.trim())
            .filter(Boolean)
            .map((text) => ({ text })),
        }),
      ),
    onSuccess: (r) => {
      setJob(r.job_id)
      setPage(0)
      refresh()
    },
  })
  const include = useMutation({
    mutationFn: (card: Evidence) =>
      api(`/evidence/${card.id}`, body('PATCH', { included: !card.included })),
    onSuccess: refresh,
  })
  const activeJob = job || searches.data?.find((s) => s.status === 'running')?.job_id
  const offset = page * 20
  return (
    <>
      <h1>文献联合调研</h1>
      <p className="muted">检索并筛选证据，后续候选只使用你纳入的文献。</p>
      <section className="panel">
        <div className="heading compact">
          <h2>检索式</h2>
          <button className="quiet" disabled={suggest.isPending} onClick={() => suggest.mutate()}>
            {suggest.isPending ? '正在生成…' : '根据方向生成'}
          </button>
        </div>
        <label>
          中英文检索式（每行一条，最多 6 条）
          <textarea
            rows={4}
            value={queries}
            onChange={(e) => setQueries(e.target.value)}
            placeholder="输入关键词，或让模型根据研究方向生成"
          />
        </label>
        <ErrorNote error={suggest.error || search.error} />
        <button
          disabled={
            search.isPending ||
            searches.data?.some((s) => s.status === 'running') ||
            !queries.trim()
          }
          onClick={() => search.mutate()}
        >
          开始联合检索
        </button>
      </section>
      {activeJob && <JobProgress id={activeJob} onComplete={() => refresh()} />}
      <Landscape projectId={id!} />
      <PdfUpload projectId={id!} />
      <ErrorNote error={cards.error || searches.error || include.error} />
      <section className="panel">
        <h2>
          证据卡{' '}
          <small>
            {cards.data?.length || 0} 条 · 纳入 {cards.data?.filter((c) => c.included).length || 0}{' '}
            条
          </small>
        </h2>
        {cards.isPending ? (
          <p>正在读取证据…</p>
        ) : !cards.data?.length ? (
          <p className="muted">还没有证据卡。输入检索式开始调研。</p>
        ) : (
          <>
            <div className="evidence-list">
              {cards.data.slice(offset, offset + 20).map((card) => (
                <article className="evidence-card" key={card.id}>
                  <div className="evidence-heading">
                    <label className="check">
                      <input
                        type="checkbox"
                        checked={card.included}
                        disabled={include.isPending}
                        onChange={() => include.mutate(card)}
                      />
                      纳入
                    </label>
                    <div>
                      <h3>{card.title}</h3>
                      <p className="muted">
                        {card.authors.join('、') || '作者未提供'} · {card.year || '年份未提供'} ·{' '}
                        {card.venue || '期刊未提供'}
                      </p>
                    </div>
                  </div>
                  <div className="tags">
                    {card.sources.map((source) => (
                      <span key={source}>{source}</span>
                    ))}
                    {card.cited_by !== null && <span>被引 {card.cited_by}</span>}
                    {card.doi && (
                      <a
                        href={`https://doi.org/${encodeURIComponent(card.doi)}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        DOI: {card.doi}
                      </a>
                    )}
                  </div>
                  <details>
                    <summary>查看摘要与证据</summary>
                    <p className="abstract">{card.abstract || '来源未提供摘要'}</p>
                    {card.fulltext_excerpt && <p className="abstract">{card.fulltext_excerpt}</p>}
                    <small>证据编号：{card.id}</small>
                    <EvidenceEdit card={card} projectId={id!} />
                  </details>
                </article>
              ))}
            </div>
            <div className="actions">
              <button className="quiet" disabled={page === 0} onClick={() => setPage(page - 1)}>
                上一页
              </button>
              <span>
                第 {page + 1} / {Math.ceil(cards.data.length / 20)} 页
              </span>
              <button
                className="quiet"
                disabled={offset + 20 >= cards.data.length}
                onClick={() => setPage(page + 1)}
              >
                下一页
              </button>
            </div>
          </>
        )}
      </section>
      <section className="panel">
        <h2>检索记录</h2>
        {!searches.data?.length ? (
          <p className="muted">尚未执行检索</p>
        ) : (
          searches.data.map((s) => (
            <details key={s.id} open={s.id === searches.data?.[0]?.id}>
              <summary>
                {new Date(s.created_at).toLocaleString('zh-CN')} ·{' '}
                {s.status === 'running'
                  ? '检索中'
                  : s.status === 'failed'
                    ? '检索失败'
                    : `${s.hit_count} 条去重结果`}
              </summary>
              <p>{s.queries.map((q) => q.text).join('；')}</p>
              {Object.entries(s.per_source_status).map(([source, status]) => (
                <p key={source} className={status.status === 'failed' ? 'error' : ''}>
                  {source}：{status.status === 'ok' ? '成功' : '存在失败'} · {status.hits} 条{' '}
                  {status.reason}
                </p>
              ))}
            </details>
          ))
        )}
      </section>
    </>
  )
}
