import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, body, type Project } from '../api/client'
import { ErrorNote } from './Shared'

/** 碳市场案例开关：PATCH /api/projects/{id} { case: 'carbon' | null }。变更会让下游阶段过期。 */
export default function CaseToggle({ project }: { project: Project }) {
  const qc = useQueryClient()
  const on = project.case === 'carbon'
  const save = useMutation({
    mutationFn: (next: 'carbon' | null) =>
      api<Project>(`/projects/${project.id}`, body('PATCH', { case: next })),
    onSuccess: () => {
      for (const k of ['overview', 'projects', 'plans', 'runs', 'proposals', 'candidate-sets'])
        qc.invalidateQueries({ queryKey: [k] })
    },
  })
  return (
    <div className="case-toggle">
      <label className="switch">
        <input
          type="checkbox"
          role="switch"
          checked={on}
          disabled={save.isPending}
          onChange={(e) => {
            const next = e.target.checked ? 'carbon' : null
            const msg = '切换案例标记会让候选、方案、检验和提案标记为过期（旧内容保留）。确定切换？'
            if (window.confirm(msg)) save.mutate(next)
          }}
        />
        <span aria-hidden="true" />
        碳市场案例
      </label>
      <small>开启后按碳市场数据约束起草方案（至少 4 项稳健性，处理为同群暴露）。</small>
      <ErrorNote error={save.error} />
    </div>
  )
}

export function CaseTag({ project }: { project?: Pick<Project, 'case'> | null }) {
  return project?.case === 'carbon' ? <span className="case-tag">碳市场案例</span> : null
}
