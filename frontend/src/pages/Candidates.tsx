import CandidateActions from '../components/CandidateActions'
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, body } from '../api/client'
import { ErrorNote, ProjectBack } from '../components/Shared'
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
    [job, setJob] = useState('')
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
  const cited = new Set(current?.candidates.flatMap((c) => c.evidence_ids) || []),
    unused = cards.data?.filter((c) => c.included && !cited.has(c.id)) || []
  return (
    <>
      <ProjectBack />
      <div className="page-heading">
        <div>
          <p className="eyebrow">第三阶段 / 从证据到问题</p>
          <h1>缺口与候选</h1>
          <p className="muted">比较研究增量、数据可得性与识别边界，再选择值得推进的问题。</p>
        </div>
        <button
          disabled={generate.isPending || current?.status === 'generating'}
          onClick={() => generate.mutate()}
        >
          {sets.data?.length ? '重新生成候选' : '生成研究候选'}
        </button>
      </div>
      <ErrorNote error={sets.error || cards.error || generate.error} />
      {activeJob && (
        <JobProgress
          id={activeJob}
          onComplete={() => qc.invalidateQueries({ queryKey: ['candidate-sets', id] })}
        />
      )}
      {sets.isPending ? (
        <p>正在读取候选…</p>
      ) : !current ? (
        <section className="panel">
          <h2>让候选从文献中生长</h2>
          <p>
            先在文献调研中纳入至少两篇相关文献，再生成 2–4 个候选。生成和自审需要在设置中配置模型。
          </p>
        </section>
      ) : (
        <>
          <label>
            候选版本
            <select value={current.id} onChange={(e) => setVersion(e.target.value)}>
              {sets.data?.map((s) => (
                <option key={s.id} value={s.id}>
                  第 {s.version} 版 ·{' '}
                  {s.status === 'ready' ? '已完成' : s.status === 'failed' ? '生成失败' : '生成中'}
                  {s.stale ? ' · 已过期' : ''}
                </option>
              ))}
            </select>
          </label>
          {current.stale && (
            <p className="notice" role="status">
              上游证据已变更，此版本已过期。旧内容保留，可重新生成。
            </p>
          )}
          {current.error && <p className="error">{current.error}</p>}
          {current.status === 'ready' && (
            <>
              <section className="panel">
                <h2>推荐与取舍</h2>
                <p>{current.recommendation_text}</p>
                <p className="muted">
                  已移除无效引用 {current.removed_references} 处 · 自审
                  {current.review.revised ? '提出修订，已修订一次' : '通过'}
                </p>
                {current.evidence_ids.length <
                  (cards.data?.filter((c) => c.included).length || 0) && (
                  <p className="muted">
                    本次最多使用按年份排序的 80 张证据卡，每张摘要截取 1,200
                    字；未输入模型的文献仍保留。
                  </p>
                )}
                {current.review.issues?.map((r, i) => (
                  <p key={i}>
                    {r.problem} · 建议：{r.suggestion}
                  </p>
                ))}
              </section>
              <div className="candidate-grid">
                {current.candidates.map((c, i) => (
                  <article className="panel candidate-card" key={c.id}>
                    <span className="eyebrow">
                      候选 {i + 1} · {positioning[c.positioning]}
                    </span>
                    <h2>{c.title}</h2>
                    <h3>研究缺口</h3>
                    <p>{c.gap}</p>
                    <h3>待检验假设</h3>
                    <p>{c.hypothesis}</p>
                    <h3>可能机制</h3>
                    <ul>
                      {c.mechanism.map((s, j) => (
                        <li key={j}>{s}</li>
                      ))}
                    </ul>
                    <h3>所需数据</h3>
                    <ul>
                      {c.required_data.map((s, j) => (
                        <li key={j}>{s}</li>
                      ))}
                    </ul>
                    <h3>识别思路</h3>
                    <p>{c.identification}</p>
                    <h3>风险与边界</h3>
                    <ul>
                      {c.risks.map((s, j) => (
                        <li key={j}>{s}</li>
                      ))}
                    </ul>
                    <h3>支持文献</h3>
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
                    <CandidateActions
                      candidate={c}
                      projectId={id!}
                      cards={cards.data || []}
                      stale={current.stale}
                    />
                  </article>
                ))}
              </div>
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
