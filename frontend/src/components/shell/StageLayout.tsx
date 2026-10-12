import { Link, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Check, ChevronRight } from 'lucide-react'
import {
  STAGE_HINTS,
  STAGE_ORDER,
  STAGE_TITLES,
  STATUS_LABELS,
  completedCount,
  stageKeyFromPath,
  statusTone,
  useOverview,
} from '../../lib/stages'

/** 项目内阶段页：旧版 DiscoveryPage 的头部 n/6 进度 + 左侧竖向 stepper + 底部上一步/下一步 */
export default function StageLayout() {
  const { id } = useParams()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const overview = useOverview(id)
  const key = stageKeyFromPath(pathname) || 'direction'
  const index = STAGE_ORDER.indexOf(key)
  const stages = overview.data?.stages || []
  const status = stages.find((s) => s.key === key)?.status || 'not_started'
  const done = completedCount(stages)
  const prev = STAGE_ORDER[index - 1],
    next = STAGE_ORDER[index + 1]
  return (
    <div className="product-page discovery-page">
      <Link className="product-back no-print" to={`/p/${id}`}>
        <ArrowLeft size={15} aria-hidden="true" />
        {overview.data?.project.title || '项目总览'}
      </Link>
      <header className="discovery-page__header no-print">
        <div>
          <span className="product-eyebrow">
            研究阶段 {index + 1} / 6 ·{' '}
            <span className={`status-badge is-${statusTone(status)}`}>
              {STATUS_LABELS[status] || status}
            </span>
          </span>
          <h1>{STAGE_TITLES[key]}</h1>
          <p>{STAGE_HINTS[key]}</p>
        </div>
        <span className="discovery-page__progress" title="已完成阶段数">
          <span>
            已完成 {done} / 6 · 当前第 {index + 1} 步
          </span>
          <i aria-hidden="true">
            <b style={{ width: `${(done / 6) * 100}%` }} />
          </i>
        </span>
      </header>
      <div className="discovery-layout">
        <nav className="discovery-steps no-print" aria-label="研究阶段">
          {STAGE_ORDER.map((k, i) => {
            const st = stages.find((s) => s.key === k)
            const tone = statusTone(st?.status || 'not_started')
            return (
              <Link
                key={k}
                to={`/p/${id}/${k}`}
                className={`${k === key ? 'is-current' : ''} ${tone === 'green' ? 'is-complete' : ''} tone-${tone}`}
                aria-current={k === key ? 'step' : undefined}
              >
                <span className="discovery-steps__node" aria-hidden="true">
                  {tone === 'green' ? <Check size={13} /> : i + 1}
                </span>
                <span>
                  <small>
                    步骤 {i + 1} · {STATUS_LABELS[st?.status || 'not_started']}
                  </small>
                  <strong>{STAGE_TITLES[k]}</strong>
                  <em>{st?.summary || STAGE_HINTS[k]}</em>
                </span>
                <ChevronRight size={14} aria-hidden="true" />
              </Link>
            )
          })}
        </nav>
        <section className="discovery-workspace">
          <div className="discovery-step-content">
            <Outlet />
          </div>
          <footer className="discovery-navigation no-print">
            <button
              type="button"
              className="product-button"
              disabled={!prev}
              onClick={() => navigate(`/p/${id}/${prev}`)}
            >
              <ArrowLeft size={15} aria-hidden="true" />
              上一阶段
            </button>
            <span>
              <strong>{STAGE_TITLES[key]}</strong>
              <small>所有内容已保存到当前项目；上游变更会让下游标记为过期</small>
            </span>
            {next ? (
              <button
                type="button"
                className="product-button is-primary"
                onClick={() => navigate(`/p/${id}/${next}`)}
              >
                下一阶段：{STAGE_TITLES[next]}
                <ArrowRight size={15} aria-hidden="true" />
              </button>
            ) : (
              <button type="button" className="product-button" onClick={() => navigate(`/p/${id}`)}>
                返回项目总览
                <ArrowRight size={15} aria-hidden="true" />
              </button>
            )}
          </footer>
        </section>
      </div>
    </div>
  )
}
