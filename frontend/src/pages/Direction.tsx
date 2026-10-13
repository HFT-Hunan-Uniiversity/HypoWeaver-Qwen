import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, body, type Direction as DirectionType, type Project } from '../api/client'
import { ErrorNote } from '../components/Shared'
function Editor({ project }: { project: Project }) {
  const [draft, setDraft] = useState<DirectionType>(project.direction),
    [saved, setSaved] = useState(false),
    [confirm, setConfirm] = useState(false)
  const cache = useQueryClient()
  const overview = useQuery({
    queryKey: ['overview', project.id],
    queryFn: () =>
      api<{ stages: { key: string; status: string }[] }>(`/projects/${project.id}/overview`),
  })
  const mutation = useMutation({
    mutationFn: () => api(`/projects/${project.id}`, body('PATCH', { direction: draft })),
    onSuccess: () => {
      setSaved(true)
      setConfirm(false)
      cache.invalidateQueries()
      cache.invalidateQueries({ queryKey: ['projects'] })
      cache.invalidateQueries({ queryKey: ['overview', project.id] })
      cache.invalidateQueries({ queryKey: ['project', project.id] })
    },
  })
  const field = (key: keyof DirectionType, value: string | string[]) => {
    setSaved(false)
    setDraft({ ...draft, [key]: value })
  }
  return (
    <form
      className="panel form direction-form fill"
      onSubmit={(e) => {
        e.preventDefault()
        if (
          JSON.stringify(draft) !== JSON.stringify(project.direction) &&
          (project.direction.text ||
            overview.data?.stages.some(
              (s) => !['direction', 'literature'].includes(s.key) && s.status !== 'not_started',
            ))
        )
          setConfirm(true)
        else mutation.mutate()
      }}
    >
      <div className="direction-grid">
        <div className="col-stack">
          <label>
            研究方向
            <textarea
              required
              rows={5}
              value={draft.text}
              onChange={(e) => field('text', e.target.value)}
              placeholder="你希望研究什么现象？"
            />
          </label>
          <label>
            具体问题（可选）
            <textarea
              rows={5}
              value={draft.question}
              onChange={(e) => field('question', e.target.value)}
            />
          </label>
        </div>
        <div className="col-stack">
          <label>
            研究约束（每行一项）
            <textarea
              rows={5}
              value={draft.constraints.join('\n')}
              onChange={(e) => field('constraints', e.target.value.split('\n'))}
            />
          </label>
          <label>
            领域
            <input
              value={draft.domain}
              onChange={(e) => field('domain', e.target.value)}
              placeholder="例如：绿色金融"
            />
          </label>
          <aside className="direction-tips" aria-label="填写提示">
            <strong>怎样写一个好方向</strong>
            <ul>
              <li>研究方向写现象与对象，例如“碳市场对企业绿色创新的影响”。</li>
              <li>具体问题写可检验的关系：谁、在什么条件下、与什么相关。</li>
              <li>约束写数据、样本期、方法或口径上的硬限制，后续候选与方案会遵守。</li>
              <li>领域用于文献检索与候选生成的语境。</li>
            </ul>
          </aside>
        </div>
      </div>
      <ErrorNote error={mutation.error} />
      <div className="actions">
        <span role="status">{saved ? '已保存' : ''}</span>
        <button disabled={mutation.isPending}>
          {mutation.isPending ? '正在保存…' : '保存研究方向'}
        </button>
      </div>
      {confirm && (
        <div className="overlay">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="impact-title"
            className="dialog"
          >
            <h2 id="impact-title">修改方向会影响后续研究</h2>
            <p>
              已有候选、研究方案、检验运行和提案会标记为过期，历史内容仍然保留。请按新方向重新审阅后续工作。
            </p>
            <div className="actions">
              <button type="button" className="quiet" onClick={() => setConfirm(false)}>
                继续编辑
              </button>
              <button type="button" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
                保存并标记过期
              </button>
            </div>
          </section>
        </div>
      )}
    </form>
  )
}
export default function Direction() {
  const { id } = useParams()
  const q = useQuery({ queryKey: ['project', id], queryFn: () => api<Project>(`/projects/${id}`) })
  return (
    <>
      <ErrorNote error={q.error} />
      {q.data ? <Editor project={q.data} /> : q.isPending && <p>正在读取…</p>}
    </>
  )
}
