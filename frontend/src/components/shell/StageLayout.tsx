import { Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ArrowRight, PanelRight } from 'lucide-react'
import StageBar from './StageBar'
import { useShell, useViewportWide } from './ShellContext'
import {
  STAGE_HINTS,
  STAGE_ORDER,
  STAGE_TITLES,
  STATUS_LABELS,
  lockReason,
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
  const key = stageKeyFromPath(pathname) || 'direction'
  const stages = overview.data?.stages || []
  const status = stages.find((s) => s.key === key)?.status || 'not_started'
  const next = STAGE_ORDER[STAGE_ORDER.indexOf(key) + 1]
  const nextLock = next ? lockReason(stages, next) : null
  return (
    <div className="stage-page">
      <header className="page-bar no-print">
        <div className="page-bar__title" title={STAGE_HINTS[key]}>
          <h1>{STAGE_TITLES[key]}</h1>
          <span className={`status-badge is-${statusTone(status)}`}>
            {STATUS_LABELS[status] || status}
          </span>
        </div>
        <StageBar projectId={id!} stages={stages} current={key} />
        <div className="page-bar__actions">
          <span className="page-bar__slot" ref={setActionsEl} />
          {next && (
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
