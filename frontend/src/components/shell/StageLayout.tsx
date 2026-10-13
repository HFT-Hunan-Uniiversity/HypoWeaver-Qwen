import { Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ArrowRight, PanelRight } from 'lucide-react'
import StageBar from './StageBar'
import { useShell, useViewportWide } from './ShellContext'
import {
  STAGE_HINTS,
  STAGE_ORDER,
  STAGE_TITLES,
  STATUS_LABELS,
  completedCount,
  lockReason,
  nextStage,
  stageKeyFromPath,
  statusTone,
  useOverview,
} from '../../lib/stages'

/** 阶段页：一行页头（左 阶段名+状态，中 横向六阶段条，右 主操作+下一阶段）+ 全宽内容区 */
export default function StageLayout() {
  const { id } = useParams()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const overview = useOverview(id)
  const { setActionsEl, toggleRail, railOpen } = useShell()
  const wide = useViewportWide(1600)
  const stageKey = stageKeyFromPath(pathname)
  // 总览与阶段页共用同一外壳：/p/:id 无阶段段时为总览
  const isOverview = !stageKey
  const key = stageKey || 'direction'
  const stages = overview.data?.stages || []
  const status = stages.find((s) => s.key === key)?.status || 'not_started'
  const next = isOverview
    ? nextStage(stages)?.key || 'proposal'
    : STAGE_ORDER[STAGE_ORDER.indexOf(key) + 1]
  const nextLock = next && !isOverview ? lockReason(stages, next) : null
  const done = completedCount(stages)
  const overall: [string, string] =
    done === 6
      ? ['green', '可交接']
      : stages.some((s) => s.status === 'stale')
        ? ['yellow', '有过期阶段']
        : ['orange', `进行中 · ${done}/6`]
  return (
    <div className="stage-page">
      <header className="page-bar no-print">
        {isOverview ? (
          <div className="page-bar__title" title="项目总览">
            <h1>项目总览</h1>
            <span className={`status-badge is-${overall[0]}`}>{overall[1]}</span>
          </div>
        ) : (
          <div className="page-bar__title" title={STAGE_HINTS[key]}>
            <h1>{STAGE_TITLES[key]}</h1>
            <span className={`status-badge is-${statusTone(status)}`}>
              {STATUS_LABELS[status] || status}
            </span>
          </div>
        )}
        <StageBar projectId={id!} stages={stages} current={isOverview ? undefined : key} />
        <div className="page-bar__actions">
          <span className="page-bar__slot" ref={setActionsEl} />
          {isOverview && next && (
            <button
              type="button"
              className="product-button is-primary"
              onClick={() => navigate(`/p/${id}/${next}`)}
            >
              {done === 6 ? '查看研究提案' : `继续：${STAGE_TITLES[next]}`}
              <ArrowRight size={14} aria-hidden="true" />
            </button>
          )}
          {!isOverview && next && (
            <button
              type="button"
              className={`product-button ${status === 'completed' ? 'is-primary' : ''}`}
              disabled={!!nextLock}
              title={nextLock || `进入「${STAGE_TITLES[next]}」`}
              onClick={() => navigate(`/p/${id}/${next}`)}
            >
              下一阶段
              <ArrowRight size={14} aria-hidden="true" />
            </button>
          )}
          {!wide && (
            <button
              type="button"
              className="icon-button"
              aria-pressed={railOpen}
              title="进度与证据"
              aria-label="进度与证据"
              onClick={toggleRail}
            >
              <PanelRight size={15} />
            </button>
          )}
        </div>
      </header>
      <div className="stage-body">
        <Outlet />
      </div>
    </div>
  )
}
