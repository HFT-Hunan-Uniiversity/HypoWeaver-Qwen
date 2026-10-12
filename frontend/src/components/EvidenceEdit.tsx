import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, body } from '../api/client'
import type { Evidence } from '../pages/Literature'
import { ErrorNote } from './Shared'
export default function EvidenceEdit({ card, projectId }: { card: Evidence; projectId: string }) {
  const [open, setOpen] = useState(false),
    [title, setTitle] = useState(card.title),
    [year, setYear] = useState(card.year?.toString() || '')
  const cache = useQueryClient()
  const save = useMutation({
    mutationFn: () =>
      api(`/evidence/${card.id}`, body('PATCH', { title, year: year ? Number(year) : undefined })),
    onSuccess: () => {
      setOpen(false)
      cache.invalidateQueries({ queryKey: ['evidence', projectId] })
      cache.invalidateQueries({ queryKey: ['landscape', projectId] })
    },
  })
  return (
    <>
      {!open ? (
        <button className="quiet" onClick={() => setOpen(true)}>
          编辑元数据
        </button>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate()
          }}
        >
          <label>
            文献标题
            <input required value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          <label>
            发表年份
            <input
              type="number"
              min="1000"
              max="2200"
              value={year}
              onChange={(e) => setYear(e.target.value)}
            />
          </label>
          <ErrorNote error={save.error} />
          <div className="actions">
            <button className="quiet" type="button" onClick={() => setOpen(false)}>
              取消
            </button>
            <button disabled={save.isPending}>保存元数据</button>
          </div>
        </form>
      )}
    </>
  )
}
