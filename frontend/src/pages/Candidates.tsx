import { StageActions } from '../components/shell/ShellContext'
import CandidateActions from '../components/CandidateActions'
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, body } from '../api/client'
import { ErrorNote } from '../components/Shared'
import { GeneratedBy, NeedsModel, VersionPills } from '../components/ui/Bits'
import { useLlm } from '../lib/llm'
import { useOverview } from '../lib/stages'
import { Link } from 'react-router-dom'
import JobProgress from '../components/JobProgress'
import EvidenceChip from '../components/EvidenceChip'
import type { Evidence } from '../components/EvidenceChip'
export interface Candidate {
  id: string
  title: string
  gap: string
  hypothesis: string
  mechanism: string[]
  required_data: string[]
  identification: string
  risks: string[]
  positioning: string
  evidence_ids: string[]
  user_edited: boolean
}
interface CandidateSet {
  id: string
  version: number
  status: string
  stale: boolean
  removed_references: number
  recommendation_text: string
  review: {
    decision: string
    revised?: boolean
    issues?: { candidate_id: string; problem: string; suggestion: string }[]
  }
  candidates: Candidate[]
  error: string | null
  job_id: string | null
  evidence_ids: string[]
  llm_model?: string | null
}
const positioning: Record<string, string> = {
  high_increment_data_gap: '增量较高 · 数据有缺口',
  feasible_limited_increment: '可行性较高 · 增量有限',
  balanced: '增量与可行性平衡',
}
export default function Candidates() {
  const { id } = useParams(),
    qc = useQueryClient(),
    [version, setVersion] = useState(''),
    [job, setJob] = useState(''),
    [view, setView] = useState<'detail' | 'compare'>('detail'),
    [focus, setFocus] = useState('')
  const sets = useQuery({
    queryKey: ['candidate-sets', id],
    queryFn: () => api<CandidateSet[]>(`/projects/${id}/candidate-sets`),
  })
  const cards = useQuery({
    queryKey: ['evidence', id],
    queryFn: () => api<Evidence[]>(`/projects/${id}/evidence`),
  })
  const generate = useMutation({
    mutationFn: () => api<{ job_id: string }>(`/projects/${id}/candidate-sets`, body('POST')),
    onSuccess: (d) => {
      setJob(d.job_id)
      setVersion('')
      qc.invalidateQueries({ queryKey: ['candidate-sets', id] })
    },
  })
  const current = sets.data?.find((s) => s.id === version) || sets.data?.[0],
    activeJob = job || (current?.status === 'generating' ? current.job_id : '')
  const llm = useLlm()
  const included = cards.data?.filter((c) => c.included).length ?? 0
  const configured = llm.data?.configured ?? true
  const selectedId = useOverview(id).data?.project.selected_candidate_id
  const cand = current?.candidates.find((c) => c.id === focus) || current?.candidates[0]
  const cited = new Set(current?.candidates.flatMap((c) => c.evidence_ids) || []),
    unused = cards.data?.filter((c) => c.included && !cited.has(c.id)) || []
  const list = (xs: string[]) => (
    <ul>
      {xs.map((x, j) => (
        <li key={j}>{x}</li>
      ))}
    </ul>
  )
  const chips = (c: Candidate) => (
    <div className="evidence-chips">
      {c.evidence_ids.map((ref) => {
        const card = cards.data?.find((x) => x.id === ref)
        return card ? (
          <EvidenceChip key={ref} card={card} />
        ) : (
          <span key={ref}>引用文献已不可用</span>
        )
      })}
    </div>
  )
  const empty = () => {
    if (cards.isPending || llm.isPending) return <p className="loading-line">正在检查证据与模型…</p>
    if (included < 2)
      return (
        <section className="empty-state">
          <h2>先纳入至少两篇文献</h2>
          <p>当前已纳入 {included} 张证据卡。候选的每条主张都需引用已纳入的文献。</p>
          <Link className="product-button is-primary" to={`/p/${id}/literature`}>
            前往文献调研
          </Link>
        </section>
      )
    if (!configured)
      return (
        <section className="empty-state">
          <h2>证据已就绪，等待配置模型</h2>
          <p>
            已纳入 {included} 张证据卡，足以生成 2–4 个候选。生成与自审需要千问模型，当前尚未配置。
          </p>
          <Link className="product-button is-primary" to="/settings">
            前往设置配置模型
          </Link>
        </section>
      )
    return (
      <section className="empty-state">
        <h2>可以生成研究候选了</h2>
        <p>已纳入 {included} 张证据卡。模型将生成 2–4 个实质不同的候选并自审引用。</p>
        <button className="product-button is-primary" onClick={() => generate.mutate()}>
          生成研究候选
        </button>
      </section>
    )
  }
  const rows: [string, (c: Candidate) => React.ReactNode][] = [
    ['定位', (c) => positioning[c.positioning]],
    ['研究缺口', (c) => c.gap],
    ['待检验假设', (c) => c.hypothesis],
    ['可能机制', (c) => list(c.mechanism)],
    ['所需数据', (c) => list(c.required_data)],
    ['识别思路', (c) => c.identification],
    ['风险与边界', (c) => list(c.risks)],
    ['支持文献', (c) => `${c.evidence_ids.length} 篇`],
  ]
  return (
    <>
      <StageActions>
        <div className="action-cluster">
          <NeedsModel />
          <button
            disabled={generate.isPending || current?.status === 'generating' || !configured}
            title={configured ? undefined : '需要先配置模型'}
            onClick={() => generate.mutate()}
          >
            {sets.data?.length ? '重新生成候选' : '生成研究候选'}
          </button>
        </div>
      </StageActions>
      <ErrorNote error={sets.error || cards.error || generate.error} />
      {activeJob && (
        <JobProgress
          id={activeJob}
          onComplete={() => qc.invalidateQueries({ queryKey: ['candidate-sets', id] })}
        />
      )}
      {sets.isPending ? (
        <p className="loading-line">正在读取候选…</p>
      ) : !current ? (
        empty()
      ) : (
        <>
          <div className="candidate-toolbar">
            <VersionPills
              label="候选版本"
              value={current.id}
              onChange={(v) => {
                setVersion(v)
                setFocus('')
              }}
              items={(sets.data || []).map((s) => ({
                id: s.id,
                label: `第 ${s.version} 版`,
                note:
                  (s.status === 'ready' ? '' : s.status === 'failed' ? '生成失败' : '生成中') +
                  (s.stale ? '已过期' : ''),
                tone: s.stale ? 'stale' : s.status === 'failed' ? 'failed' : undefined,
              }))}
            />
            <div className="action-cluster">
              <GeneratedBy of={current} />
              {current.status === 'ready' && (
                <div className="view-switch" role="tablist" aria-label="视图">
                  <button
                    role="tab"
                    aria-selected={view === 'detail'}
                    className={view === 'detail' ? 'is-active' : ''}
                    onClick={() => setView('detail')}
                  >
                    逐个审阅
                  </button>
                  <button
                    role="tab"
                    aria-selected={view === 'compare'}
                    className={view === 'compare' ? 'is-active' : ''}
                    onClick={() => setView('compare')}
                  >
                    对比视图
                  </button>
                </div>
              )}
            </div>
          </div>
          {current.stale && (
            <p className="notice" role="status">
              上游证据已变更，此版本已过期。旧内容保留，可重新生成。
            </p>
          )}
          {current.error &&
            (/模型|API_KEY|llm_not_configured/i.test(current.error) ? (
              <p className="notice">
                {current.error} <Link to="/settings">前往设置 →</Link>
              </p>
            ) : (
              <p className="error">{current.error}</p>
            ))}
          {current.status === 'ready' && (
            <>
              <section className="panel">
                <h2>推荐与取舍</h2>
                <p>{current.recommendation_text}</p>
                <p className="muted">
                  已移除无效引用 {current.removed_references} 处 · 自审
                  {current.review.revised ? '提出修订，已修订一次' : '通过'}
                  {current.evidence_ids.length < included &&
                    ' · 本次最多使用按年份排序的 80 张证据卡，每张摘要截取 1,200 字'}
                </p>
                {current.review.issues?.map((r, i) => (
                  <p key={i}>
                    {r.problem} · 建议：{r.suggestion}
                  </p>
                ))}
              </section>
              {view === 'compare' ? (
                <div className="table-scroll">
                  <table className="compare-table">
                    <thead>
                      <tr>
                        <th>字段</th>
                        {current.candidates.map((c, i) => (
                          <th key={c.id} className={c.id === selectedId ? 'is-chosen' : ''}>
                            候选 {i + 1}
                            {c.id === selectedId ? ' · 当前已选' : ''}
                            <div>{c.title}</div>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map(([label, f]) => (
                        <tr key={label}>
                          <th>{label}</th>
                          {current.candidates.map((c) => (
                            <td key={c.id} className={c.id === selectedId ? 'is-chosen' : ''}>
                              {f(c)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                cand && (
                  <div className="master-detail">
                    <div className="master-list" role="tablist" aria-label="候选列表">
                      {current.candidates.map((c, i) => (
                        <button
                          key={c.id}
                          role="tab"
                          aria-selected={c.id === cand.id}
                          className={c.id === cand.id ? 'is-active' : ''}
                          onClick={() => setFocus(c.id)}
                        >
                          <b>0{i + 1}</b>
                          <span>
                            <strong>{c.title}</strong>
                            <small>
                              {positioning[c.positioning]} · {c.evidence_ids.length} 篇文献
                              {c.id === selectedId && <span className="chosen"> · 已选</span>}
                            </small>
                          </span>
                        </button>
                      ))}
                    </div>
                    <article className="panel candidate-card" key={cand.id}>
                      <span className="eyebrow">{positioning[cand.positioning]}</span>
                      <h2>{cand.title}</h2>
                      <div className="two-columns">
                        <div>
                          <h3>研究缺口</h3>
                          <p>{cand.gap}</p>
                          <h3>待检验假设</h3>
                          <p>{cand.hypothesis}</p>
                          <h3>识别思路</h3>
                          <p>{cand.identification}</p>
                        </div>
                        <div>
                          <h3>可能机制</h3>
                          {list(cand.mechanism)}
                          <h3>所需数据</h3>
                          {list(cand.required_data)}
                          <h3>风险与边界</h3>
                          {list(cand.risks)}
                        </div>
                      </div>
                      <h3>支持文献</h3>
                      {chips(cand)}
                      <CandidateActions
                        candidate={cand}
                        projectId={id!}
                        cards={cards.data || []}
                        stale={current.stale}
                      />
                    </article>
                  </div>
                )
              )}
              <details className="panel">
                <summary>未被本版候选引用的已纳入文献（{unused.length}）</summary>
                <div className="evidence-chips">
                  {unused.map((c) => (
                    <EvidenceChip key={c.id} card={c} />
                  ))}
                </div>
              </details>
            </>
          )}
        </>
      )}
    </>
  )
}
