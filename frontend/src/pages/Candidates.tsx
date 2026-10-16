import ProcessTimeline, { jobSeconds, useStageJob } from '../components/flow/ProcessTimeline'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, body, type Project } from '../api/client'
import { ErrorNote } from '../components/Shared'
import { ScrollRegion } from '../components/shell/ShellContext'
import { GeneratedBy, VersionPills } from '../components/ui/Bits'
import JobProgress from '../components/JobProgress'
import EvidenceChip from '../components/EvidenceChip'
import type { Evidence } from '../components/EvidenceChip'
import CandidateActions from '../components/CandidateActions'
import { useFlow, useFlowStage, useStageUi } from '../components/flow/FlowContext'
import { EmptyState, ProgressView } from '../components/flow/FlowBits'
import { useLlm } from '../lib/llm'
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
/** 可检验性（前端估算，后端暂无评分字段）：证据越多、识别思路越明确、风险越少越高 */
export function testability(c: Candidate) {
  const s =
    45 +
    Math.min(4, c.evidence_ids.length) * 8 +
    (c.identification ? 12 : 0) +
    (c.positioning === 'feasible_limited_increment' ? 8 : c.positioning === 'balanced' ? 4 : 0) -
    Math.min(4, c.risks.length) * 4
  return Math.max(10, Math.min(98, s))
}
/** 推荐：推荐说明中点名的候选，否则取可检验性最高者 */
function recommended(set: CandidateSet) {
  const named = set.candidates.find(
    (c) => c.title && set.recommendation_text.includes(c.title.slice(0, 8)),
  )
  if (named) return named.id
  return [...set.candidates].sort((a, b) => testability(b) - testability(a))[0]?.id
}

export default function Candidates() {
  const { id } = useParams()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const { confirm } = useFlow()
  const stage = useFlowStage('candidates')
  const llmOk = useLlm().data?.configured !== false
  const [version, setVersion] = useState('')
  const [job, setJob] = useState('')
  const [jobEnd, setJobEnd] = useState<'' | 'succeeded' | 'failed'>('')
  const [jobErr, setJobErr] = useState<string | null>(null)
  const sets = useQuery({
    queryKey: ['candidate-sets', id],
    queryFn: () => api<CandidateSet[]>(`/projects/${id}/candidate-sets`),
  })
  const cards = useQuery({
    queryKey: ['evidence', id],
    queryFn: () => api<Evidence[]>(`/projects/${id}/evidence`),
  })
  const project = useQuery({
    queryKey: ['project', id],
    queryFn: () => api<Project>(`/projects/${id}`),
  })
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['candidate-sets', id] })
    qc.invalidateQueries({ queryKey: ['overview', id] })
  }
  const generate = useMutation({
    mutationFn: () => api<{ job_id: string }>(`/projects/${id}/candidate-sets`, body('POST')),
    onSuccess: (d) => {
      setJob(d.job_id)
      setJobEnd('')
      setJobErr(null)
      setVersion('')
      refresh()
    },
  })
  const choose = useMutation({
    mutationFn: (cid: string) => api(`/candidates/${cid}:select`, body('POST')),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['project', id] })
      qc.invalidateQueries({ queryKey: ['plans', id] })
      qc.invalidateQueries({ queryKey: ['overview', id] })
    },
  })
  const current = sets.data?.find((s) => s.id === version) || sets.data?.[0]
  const generating = generate.isPending || current?.status === 'generating' || (!!job && !jobEnd)
  const onJobDone = (j: { status: string; error: string | null }) => {
    setJobEnd(j.status === 'failed' ? 'failed' : 'succeeded')
    if (j.status === 'failed') setJobErr(j.error || '候选生成失败')
    refresh()
  }
  const included = cards.data?.filter((c) => c.included).length ?? 0
  const selectedId = project.data?.selected_candidate_id
  const ready = current?.status === 'ready' ? current : undefined
  const chosen = ready?.candidates.find((c) => c.id === selectedId)
  const rec = ready ? recommended(ready) : undefined
  const failed = jobErr || (current?.status === 'failed' ? current.error || '候选生成失败' : null)
  const candJob = useStageJob(id, 'candidates', current?.job_id)

  useStageUi({
    checklist: [
      { label: '生成候选', done: !!ready },
      { label: '选一条假设', done: !!chosen },
    ],
    primary: generating
      ? { label: '正在生成…', busy: true }
      : !ready || (stage.status === 'stale' && current?.stale)
        ? included < 2
          ? {
              label: '生成候选假设',
              disabled: true,
              reason: `需先在文献阶段选至少 2 篇证据（当前 ${included}）`,
            }
          : {
              label: ready ? '重新生成候选' : '生成候选假设',
              needsLlm: true,
              onClick: () => generate.mutate(),
              error: generate.error ? (generate.error as Error).message : failed,
            }
        : !chosen
          ? { label: '选择一个候选', disabled: true, reason: '在下方选一条假设' }
          : {
              label: '确认并进入下一阶段',
              reason: `已选：${chosen.title.slice(0, 18)}${chosen.title.length > 18 ? '…' : ''}`,
              onClick: () => {
                if (!confirm('candidates')) navigate(`/p/${id}/plan`)
              },
            },
  })

  if (sets.isPending) return <p className="loading-line">正在读取候选…</p>
  if (generating)
    return (
      <>
        {(job || current?.job_id) && (
          <JobProgress
            id={job || current!.job_id!}
            label="正在生成候选假设…"
            onComplete={onJobDone}
            onRetry={() => generate.mutate()}
          />
        )}
        <ProgressView
          title="正在生成候选假设"
          detail={`基于已选的 ${included} 篇证据生成 2–4 条候选，并自审引用。完成后自动显示。`}
        />
      </>
    )
  if (!ready)
    return (
      <>
        {job && jobEnd === 'failed' && <JobProgress id={job} onRetry={() => generate.mutate()} />}
        <ErrorNote error={sets.error || generate.error} />
        <EmptyState
          title="这里会出现几条可以比较的候选假设"
          what="每条写明：假设表述、涉及变量与机制、有几篇证据支持、需要什么数据、可检验性评分。系统会推荐一条并说明理由。"
          example={{
            title: '碳交易试点提升了企业绿色专利数量',
            body: '可检验性 86 · 证据 3 篇 · 需要：上市公司面板 2008–2020',
          }}
          blocked={
            included < 2 ? `先在文献阶段选至少 2 篇证据（当前 ${included} 篇）。` : undefined
          }
          action={
            stage.editable ? { label: '生成候选假设', onClick: () => generate.mutate() } : undefined
          }
        />
      </>
    )

  return (
    <>
      <ErrorNote error={sets.error || choose.error || generate.error} />
      <ProcessTimeline
        title="候选生成"
        seconds={jobSeconds(candJob)}
        steps={[
          {
            key: 'gen',
            label: `依据 ${ready.evidence_ids.length} 条纳入证据生成 ${ready.candidates.length} 条候选`,
            state: 'done',
            detail: (
              <ul>
                {ready.candidates.map((c) => (
                  <li key={c.id}>{c.title}</li>
                ))}
              </ul>
            ),
          },
          {
            key: 'review',
            label: `自动审查 · ${ready.review.decision === 'pass' ? '通过' : ready.review.decision}${ready.review.issues?.length ? ` · ${ready.review.issues.length} 条意见` : ''}`,
            state: 'done',
            detail: ready.review.issues?.length ? (
              <ul>
                {ready.review.issues.map((x, i) => (
                  <li key={i}>
                    {x.problem}；{x.suggestion}
                  </li>
                ))}
              </ul>
            ) : undefined,
          },
        ]}
      />
      <div className="cand-toolbar">
        {(sets.data?.length || 0) > 1 && (
          <VersionPills
            label="候选版本"
            value={current!.id}
            onChange={setVersion}
            items={(sets.data || []).map((s) => ({
              id: s.id,
              label: `第 ${s.version} 版`,
              note: (s.status === 'failed' ? '生成失败' : '') + (s.stale ? '需要更新' : ''),
              tone: s.stale ? 'stale' : s.status === 'failed' ? 'failed' : undefined,
            }))}
          />
        )}
        <p className="cand-reco" title={ready.recommendation_text}>
          <strong>推荐理由</strong> {ready.recommendation_text}
        </p>
        <GeneratedBy of={ready} />
        {stage.editable && llmOk && (
          <button className="product-button is-quiet" onClick={() => generate.mutate()}>
            重新生成
          </button>
        )}
      </div>
      {ready.stale && (
        <p className="notice">上游证据已变更，这一版候选需要更新：可重新生成，或确认后继续沿用。</p>
      )}
      <div className="cand-grid fill" role="radiogroup" aria-label="候选假设">
        {ready.candidates.map((c, i) => {
          const score = testability(c)
          const isRec = c.id === rec
          const on = c.id === selectedId
          const posLabel = positioning[c.positioning] || c.positioning
          const dataText = c.required_data.slice(0, 2).join('；')
          return (
            <article
              key={c.id}
              className={`cand-card ${on ? 'is-on' : ''} ${isRec ? 'is-rec' : ''}`}
            >
              <div className="cand-card__top">
                <span className={`cand-card__rec ${isRec ? '' : 'is-none'}`}>
                  {isRec ? '系统推荐' : `候选 ${i + 1}`}
                </span>
                <span
                  className="cand-card__metrics"
                  title={`${posLabel} · 支持证据 ${c.evidence_ids.length} 篇 · 可检验性 ${score}`}
                >
                  <span>证据 {c.evidence_ids.length} 篇</span>
                  <span aria-hidden="true">·</span>
                  <span>
                    可检验{' '}
                    <span className="cand-score" title="前端按证据数、识别思路、风险估算">
                      <i style={{ width: score + '%' }} />
                    </span>{' '}
                    <b>{score}</b>
                  </span>
                  <span aria-hidden="true">·</span>
                  <span>{posLabel}</span>
                </span>
              </div>
              <label className="cand-card__head">
                <input
                  type="radio"
                  name="candidate"
                  checked={on}
                  disabled={!stage.editable || choose.isPending}
                  onChange={() => choose.mutate(c.id)}
                />
                <span title={c.title}>{c.title}</span>
              </label>
              <ScrollRegion className="cand-card__body" label={`候选 ${i + 1} 详情`}>
                <dl>
                  <dt>假设</dt>
                  <dd className="cand-clamp-3" title={c.hypothesis}>
                    {c.hypothesis}
                  </dd>
                  <dt>机制</dt>
                  <dd className="cand-tags">
                    {c.mechanism.map((m) => (
                      <i key={m} title={m}>
                        {m}
                      </i>
                    ))}
                  </dd>
                  <dt>数据</dt>
                  <dd className="cand-clamp-2" title={c.required_data.join('；')}>
                    {dataText}
                  </dd>
                </dl>
                <details>
                  <summary>缺口、识别思路、风险与证据</summary>
                  <p>
                    <strong>研究缺口：</strong>
                    {c.gap}
                  </p>
                  <p>
                    <strong>识别思路：</strong>
                    {c.identification}
                  </p>
                  <ul>
                    {c.risks.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                  <div className="evidence-chips">
                    {c.evidence_ids.map((ref) => {
                      const card = cards.data?.find((x) => x.id === ref)
                      return card ? <EvidenceChip key={ref} card={card} /> : null
                    })}
                  </div>
                  {stage.editable && (
                    <CandidateActions
                      candidate={c}
                      projectId={id!}
                      cards={cards.data || []}
                      stale={ready.stale}
                      editOnly
                    />
                  )}
                </details>
              </ScrollRegion>
            </article>
          )
        })}
      </div>
    </>
  )
}
