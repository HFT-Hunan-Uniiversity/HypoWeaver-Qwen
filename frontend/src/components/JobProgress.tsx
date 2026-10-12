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
  return (
    <div className="panel" role="status">
      <ErrorNote error={q.error} />
      {q.data ? (
        <>
          <strong>{q.data.status === 'failed' ? '执行失败' : q.data.progress_text}</strong>
          {q.data.error && <p className="error">{q.data.error}</p>}
        </>
      ) : (
        <p>正在读取进度…</p>
      )}
    </div>
  )
}
