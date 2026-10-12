import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { api } from '../api/client'
import { ErrorNote } from './Shared'
export interface Job {
  id: string
  status: string
  progress_text: string
  error: string | null
  result: Record<string, unknown> | null
}
export default function JobProgress({
  id,
  onComplete,
}: {
  id: string
  onComplete?: (job: Job) => void
}) {
  const notified = useRef(''),
    cache = useQueryClient()
  const q = useQuery({
    queryKey: ['job', id],
    queryFn: () => api<Job>(`/jobs/${id}`),
    refetchInterval: (query) =>
      ['succeeded', 'failed'].includes(query.state.data?.status || '') ? false : 1000,
  })
  useEffect(() => {
    if (q.data && onComplete && ['succeeded', 'failed'].includes(q.data.status)) {
      const key = q.data.id + q.data.status
      if (notified.current !== key) {
        notified.current = key
        cache.invalidateQueries({ queryKey: ['overview'] })
        onComplete(q.data)
      }
    }
  }, [q.data, onComplete])
  // 已成功的任务不再单独占一张卡片（B5）；进行中 / 失败以一行状态显示
  if (q.data?.status === 'succeeded') return null
  return (
    <div className={`job-line ${q.data?.status === 'failed' ? 'is-failed' : ''}`} role="status">
      <ErrorNote error={q.error} />
      {q.data ? (
        <>
          <strong>
            {q.data.status === 'failed' ? '执行失败' : q.data.progress_text || '正在执行…'}
          </strong>
          {q.data.error && <span>{q.data.error}</span>}
        </>
      ) : (
        <span>正在读取进度…</span>
      )}
    </div>
  )
}
