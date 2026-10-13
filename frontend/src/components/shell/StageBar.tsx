import { Link } from 'react-router-dom'
import { Check, Lock } from 'lucide-react'
import { STAGE_TITLES } from '../../lib/stages'
import type { FlowStage } from '../../lib/flow'

const LABEL = { locked: '未解锁', active: '进行中', confirmed: '已确认', stale: '需要更新' }

/** 横向六阶段条：已确认 ✓、进行中高亮、需要更新黄点、未解锁锁定不可点 */
export default function StageBar({
  projectId,
  flow,
  current,
}: {
  projectId: string
  flow: FlowStage[]
  current?: string
}) {
  return (
    <nav className="stage-bar is-sm flow-bar" aria-label="研究阶段">
      <Link className={`flow-bar__overview ${!current ? 'is-current' : ''}`} to={`/p/${projectId}`}>
        总览
      </Link>
      <ol>
        {flow.map((s, i) => {
          const label = STAGE_TITLES[s.key]
          const tip = `${label} · ${LABEL[s.status]}${s.summary ? ' · ' + s.summary : ''}`
          const inner = (
            <>
              <span className="stage-bar__node" aria-hidden="true">
                {s.status === 'confirmed' ? (
                  <Check size={12} />
                ) : s.status === 'locked' ? (
                  <Lock size={10} />
                ) : (
                  i + 1
                )}
              </span>
              <span className="stage-bar__text">
                <strong>{label}</strong>
              </span>
              {s.status === 'stale' && <span className="flow-dot" title="需要更新" />}
            </>
          )
          const cls = `flow-${s.status} ${s.key === current ? 'is-current' : ''} ${s.status === 'locked' ? 'is-locked' : ''}`
          return (
            <li key={s.key} className={cls}>
              {s.status === 'locked' ? (
                <span className="stage-bar__item" title="完成前面的阶段后解锁" aria-disabled="true">
                  {inner}
                  <span className="sr-only">（未解锁）</span>
                </span>
              ) : (
                <Link
                  className="stage-bar__item"
                  to={`/p/${projectId}/${s.key}`}
                  title={tip}
                  aria-current={s.key === current ? 'step' : undefined}
                >
                  {inner}
                  <span className="sr-only">（{LABEL[s.status]}）</span>
                </Link>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
