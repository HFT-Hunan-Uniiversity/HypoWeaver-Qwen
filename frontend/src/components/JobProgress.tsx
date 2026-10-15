import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { ErrorNote } from './Shared'
export interface Job {
  id: string
  status: string
  progress_text: string
  error: string | null
  result: Record<string, unknown> | null
  started_at?: string | null
  created_at?: string | null
}

/** 后台任务块：转圈 + 不定进度条 + 已用秒数；轮询 GET /api/jobs/{id}；失败变红，只能手动重试 */
export default function JobProgress({
  id,
  onComplete,
  onRetry,
  label,
}: {
  id: string
  onComplete?: (job: Job) => void
  onRetry?: () => void
  label?: string
}) {
  const notified = useRef(''),
    cache = useQueryClient()
  const mounted = useRef(Date.now())
  const [now, setNow] = useState(Date.now())
  const q = useQuery({
    queryKey: ['job', id],
    queryFn: () => api<Job>(`/jobs/${id}`),
    refetchInterval: (query) =>
      ['succeeded', 'failed'].includes(query.state.data?.status || '') ? false : 1500,
  })
  useEffect(() => {
    cache.invalidateQueries({ queryKey: ['jobs'] })
  }, [id, cache])
  const finished = ['succeeded', 'failed'].includes(q.data?.status || '')
  useEffect(() => {
    if (finished) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [finished])
  useEffect(() => {
    if (q.data && ['succeeded', 'failed'].includes(q.data.status)) {
      const key = q.data.id + q.data.status
      if (notified.current !== key) {
        notified.current = key
        cache.invalidateQueries({ queryKey: ['overview'] })
        cache.invalidateQueries({ queryKey: ['jobs'] })
        onComplete?.(q.data)
      }
    }
  }, [q.data, onComplete, cache])
  if (q.data?.status === 'succeeded') return null
  const start = Date.parse(q.data?.started_at || q.data?.created_at || '') || mounted.current
  const secs = Math.max(0, Math.round((now - start) / 1000))
  if (q.data?.status === 'failed')
    return (
      <div className="job is-failed" role="alert">
        <div className="job__hd">任务失败</div>
        {q.data.error && <p className="job__err">{q.data.error}</p>}
        {onRetry ? (
          <button type="button" className="product-button" onClick={onRetry}>
            重试
          </button>
        ) : (
          <p className="muted">可点卡底的按钮重新提交，系统不会自动重试。</p>
        )}
      </div>
    )
  return (
    <div className="job" role="status" aria-live="polite">
      <ErrorNote error={q.error} />
      <div className="job__hd">
        <span className="job__spin" aria-hidden="true" />
        {q.data?.progress_text || label || '正在执行…'}
        <span className="job__secs">已用 {secs}s</span>
      </div>
      <div className="job__bar" aria-hidden="true">
        <i />
      </div>
      <p className="muted">通常约 2 分钟，完成后自动显示结果；按钮在此期间不可重复提交。</p>
    </div>
  )
}
