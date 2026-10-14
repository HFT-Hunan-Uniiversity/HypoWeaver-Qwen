import { useState, type ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown } from 'lucide-react'
import { api } from '../../api/client'
import { STAGE_TITLES, STATUS_LABELS, statusTone, useOverview } from '../../lib/stages'
import { useProjectFacts } from '../../lib/facts'
import { strengths } from '../Claims'
import { num } from '../ResultTable'

interface Status {
  configured: boolean
  model?: string | null
  llm_model?: string | null
  usage?: { calls: number; input_tokens: number; output_tokens: number }
}

function Sec({
  title,
  children,
  open0 = true,
}: {
  title: string
  children: ReactNode
  open0?: boolean
}) {
  const [open, setOpen] = useState(open0)
  return (
    <section className={`rpanel__sec${open ? '' : ' is-closed'}`}>
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
        {title}
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {open && <div className="rpanel__body">{children}</div>}
    </section>
  )
}

export default function ResearchRail({ projectId }: { projectId: string }) {
  const overview = useOverview(projectId)
  const f = useProjectFacts(projectId)
  const loc = useLocation()
  const status = useQuery({
    queryKey: ['settings'],
    queryFn: () => api<Status>('/settings/status'),
    staleTime: 60000,
  })
  const stages = overview.data?.stages || []
  const u = status.data?.usage
  return (
    <aside className="task-context rpanel no-print" aria-label="研究进度与产出">
      <Sec title="阶段进度">
        <ol>
          {stages.map((s) => {
            const tone = statusTone(s.status)
            const dot =
              tone === 'green'
                ? 'is-done'
                : tone === 'gray'
                  ? ''
                  : s.status === 'stale'
                    ? 'is-stale'
                    : 'is-active'
            const cur = loc.pathname.startsWith(`/p/${projectId}/${s.key}`)
            return (
              <li key={s.key} className={`rpanel__stage${cur ? ' is-current' : ''}`}>
                <span className={`rpanel__dot ${dot}`} aria-hidden="true" />
                <span>
                  <Link to={`/p/${projectId}/${s.key}`}>{STAGE_TITLES[s.key] || s.label}</Link>{' '}
                  <small>{STATUS_LABELS[s.status] || s.status}</small>
                </span>
              </li>
            )
          })}
        </ol>
      </Sec>
      <Sec title="产出物">
        <ul>
          <li>
            <span>数据</span>
            <small>{f.dataset ? f.dataset.name : '尚未绑定'}</small>
          </li>
          <li>
            <Link to={`/p/${projectId}/plan`}>研究方案</Link>
            <small>{f.plan ? `v${f.plan.version}` : '—'}</small>
          </li>
          <li>
            <Link to={`/p/${projectId}/data`}>运行记录</Link>
            <small>
              {f.runCount ?? '—'} 次{f.run?.result ? ` · coef ${num(f.run.result.main.coef)}` : ''}
            </small>
          </li>
          <li>
            <span>结论强度</span>
            <small>{f.strength ? strengths[f.strength] : '—'}</small>
          </li>
          <li>
            <Link to={`/p/${projectId}/proposal`}>研究提案</Link>
          </li>
        </ul>
      </Sec>
      <Sec title="模型与用量">
        <ul>
          <li>
            <span>模型</span>
            <small>
              {status.data
                ? status.data.configured
                  ? status.data.llm_model || status.data.model || '已配置'
                  : '未配置'
                : '—'}
            </small>
          </li>
          <li>
            <span>调用</span>
            <small>{u ? `${u.calls} 次` : '—'}</small>
          </li>
          <li>
            <span>Token</span>
            <small>
              {u
                ? `入 ${u.input_tokens.toLocaleString()} · 出 ${u.output_tokens.toLocaleString()}`
                : '—'}
            </small>
          </li>
        </ul>
      </Sec>
    </aside>
  )
}
