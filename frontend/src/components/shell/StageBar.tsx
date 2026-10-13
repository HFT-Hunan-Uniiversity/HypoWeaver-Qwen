import { Link } from 'react-router-dom'
import { Check } from 'lucide-react'
import type { Stage } from '../../api/client'
import { STAGE_ORDER, STAGE_TITLES, STATUS_LABELS, lockReason, statusTone } from '../../lib/stages'

/** 横向六阶段条：唯一的流程导航。已解锁阶段可点击（含回退），未解锁置灰并提示原因 */
export default function StageBar({
  projectId,
  stages,
  current,
  size = 'sm',
}: {
  projectId: string
  stages: Stage[]
  current?: string
  size?: 'sm' | 'lg'
}) {
  return (
    <nav className={`stage-bar is-${size}`} aria-label="研究阶段">
      <ol>
        {STAGE_ORDER.map((k, i) => {
          const st = stages.find((s) => s.key === k)
          const status = st?.status || 'not_started'
          const tone = statusTone(status)
          const lock = lockReason(stages, k)
          const label = STAGE_TITLES[k]
          const tip =
            lock ||
            `${label} · ${STATUS_LABELS[status] || status}${st?.summary ? ' · ' + st.summary : ''}`
          const inner = (
            <>
              <span className="stage-bar__node" aria-hidden="true">
                {tone === 'green' ? <Check size={12} /> : i + 1}
              </span>
              <span className="stage-bar__text">
                <strong>{label}</strong>
                {size === 'lg' && <small>{st?.summary || STATUS_LABELS[status]}</small>}
              </span>
            </>
          )
          const cls = `tone-${tone} ${k === current ? 'is-current' : ''} ${lock ? 'is-locked' : ''}`
          return (
            <li key={k} className={cls}>
              {lock ? (
                <span className="stage-bar__item" title={tip} aria-disabled="true" tabIndex={0}>
                  {inner}
                  <span className="sr-only">（未解锁：{lock}）</span>
                </span>
              ) : (
                <Link
                  className="stage-bar__item"
                  to={`/p/${projectId}/${k}`}
                  title={tip}
                  aria-current={k === current ? 'step' : undefined}
                >
                  {inner}
                </Link>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
