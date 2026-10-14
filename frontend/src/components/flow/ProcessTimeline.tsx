import { useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check, ChevronRight, Circle, Loader2, X } from 'lucide-react'
import { api } from '../../api/client'

export type StepState = 'done' | 'now' | 'todo' | 'failed'
export interface TimelineStep {
  key: string
  label: string
  state: StepState
  /** 展开后显示的明细（检索到的论文、各模型系数等） */
  detail?: ReactNode
  /** 只有后端给出该步开始/结束时间时才传，绝不估算 */
  seconds?: number
}
export interface StageJob {
  id: string
  kind: string
  status: string
  progress_text?: string
  created_at: string
  started_at: string | null
  finished_at: string | null
}

/** 某阶段最近一次后端任务（含 started_at / finished_at）。 */
export function useStageJob(projectId: string | undefined, kind: string, jobId?: string | null) {
  const q = useQuery({
    queryKey: ['jobs', projectId, kind],
    queryFn: () => api<StageJob[]>(`/projects/${projectId}/jobs?kind=${kind}`),
    enabled: !!projectId,
    staleTime: 5000,
  })
  const list = q.data || []
  return (jobId ? list.find((j) => j.id === jobId) : undefined) || list[0]
}

export function jobSeconds(job?: Pick<StageJob, 'started_at' | 'finished_at'> | null) {
  if (!job?.started_at || !job.finished_at) return undefined
  const s = (Date.parse(job.finished_at) - Date.parse(job.started_at)) / 1000
  return Number.isFinite(s) && s >= 0 ? s : undefined
}
export const fmtSeconds = (s: number) => (s < 10 ? `${s.toFixed(1)}s` : `${Math.round(s)}s`)

function Icon({ state }: { state: StepState }) {
  return (
    <span className="ptl__icon" aria-hidden="true">
      {state === 'now' ? (
        <Loader2 size={14} className="ptl-spin" />
      ) : state === 'done' ? (
        <Check size={14} />
      ) : state === 'failed' ? (
        <X size={14} />
      ) : (
        <Circle size={10} />
      )}
    </span>
  )
}

function Row({ step, index }: { step: TimelineStep; index: number }) {
  const [open, setOpen] = useState(false)
  const can = !!step.detail
  return (
    <li
      className={`ptl__row is-${step.state} ${open ? 'is-open' : ''}`}
      style={{ ['--i' as string]: index }}
    >
      <button
        type="button"
        className="ptl__head"
        aria-expanded={can ? open : undefined}
        disabled={!can}
        onClick={() => setOpen(!open)}
      >
        <Icon state={step.state} />
        <span className="ptl__title">{step.label}</span>
        {step.seconds !== undefined && (
          <span className="ptl__time">{fmtSeconds(step.seconds)}</span>
        )}
        {can && <ChevronRight size={14} className="ptl__chev" aria-hidden="true" />}
      </button>
      {open && can && <div className="ptl__detail">{step.detail}</div>}
    </li>
  )
}

/**
 * 过程时间线：每步一行（图标、标题、右侧用时、展开箭头）。
 * 进行中：展开显示，当前步加粗并转圈；全部完成：折叠为一行「用时 Xs · N 步」，可展开查看明细。
 * 用时只取后端任务的 started_at / finished_at。
 */
export default function ProcessTimeline({
  title,
  steps,
  seconds,
  defaultOpen,
}: {
  title?: string
  steps: TimelineStep[]
  seconds?: number
  defaultOpen?: boolean
}) {
  const running = steps.some((s) => s.state === 'now' || s.state === 'todo')
  const failed = steps.some((s) => s.state === 'failed')
  const [open, setOpen] = useState(!!defaultOpen)
  const expanded = running || open
  const summary = running
    ? `${title || '进行中'} · 第 ${Math.min(steps.length, steps.filter((s) => s.state === 'done').length + 1)} / ${steps.length} 步`
    : `${seconds !== undefined ? `用时 ${fmtSeconds(seconds)} · ` : ''}${steps.length} 步${failed ? ' · 有失败' : ''}`
  return (
    <section className={`ptl ${expanded ? 'is-open' : ''}`} aria-label={title || '处理过程'}>
      <button
        type="button"
        className="ptl__summary"
        aria-expanded={expanded}
        onClick={() => !running && setOpen(!open)}
      >
        {running ? <Loader2 size={14} className="ptl-spin" aria-hidden="true" /> : null}
        <span>
          {!running && title ? <strong>{title}</strong> : null}
          {!running && title ? ' · ' : ''}
          {summary}
        </span>
        {!running && <ChevronRight size={14} className="ptl__chev" aria-hidden="true" />}
      </button>
      {expanded && (
        <ol className="ptl__list">
          {steps.map((s, i) => (
            <Row key={s.key} step={s} index={i} />
          ))}
        </ol>
      )}
    </section>
  )
}
