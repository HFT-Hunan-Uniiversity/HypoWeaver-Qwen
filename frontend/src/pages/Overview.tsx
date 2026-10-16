import { useEffect } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { useFlow } from '../components/flow/FlowContext'
import { nextFlowStage } from '../lib/flow'
import { ErrorNote } from '../components/Shared'
import { ScrollRegion } from '../components/shell/ShellContext'
import CaseToggle, { CaseTag } from '../components/CaseToggle'
import { strengths } from '../components/Claims'
import { num } from '../components/ResultTable'
import { useProjectFacts } from '../lib/facts'
import { STAGE_TITLES, STAGE_TODO, useOverview } from '../lib/stages'
import { displayProjectTitle } from '../lib/displayTitle'

const FLOW_LABEL = { locked: '未解锁', active: '进行中', confirmed: '已确认', stale: '需要更新' }
const FLOW_TONE = { locked: 'gray', active: 'orange', confirmed: 'green', stale: 'yellow' }

/** 总览：与阶段页共用 StageLayout 外壳（一行页头 + 紧凑阶段条 + 继续按钮），下方网格填满一屏 */
export default function Overview() {
  const { id } = useParams()
  const q = useOverview(id)
  const f = useProjectFacts(id)
  const { flow } = useFlow()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = nextFlowStage(flow)
  // 打开项目时：若有阶段正等你确认（已有内容、尚未确认），直接进入该阶段
  useEffect(() => {
    if (params.get('open') && next && next.backend !== 'not_started')
      navigate(`/p/${id}/${next.key}`, { replace: true })
  }, [params, next, id, navigate])
  if (q.isPending) return <p className="loading-line">正在读取项目…</p>
  if (!q.data)
    return (
      <div className="page-body">
        <ErrorNote error={q.error} />
      </div>
    )
  const { project } = q.data
  const done = flow.filter((s) => s.status === 'confirmed').length
  const main = f.run?.result?.main
  const panel = f.dataset?.panel
  const period = panel?.time_min ? `${panel.time_min}–${panel.time_max}` : ''
  const strengthCell = f.strength ? (
    <span className={`status-badge is-${f.strength === 'causal_cautious' ? 'orange' : 'green'}`}>
      {strengths[f.strength] || f.strength}
      {f.strengthDecision === 'deferred' && '（已暂缓）'}
      {f.strengthDecision === 'rejected' && '（已拒绝）'}
    </span>
  ) : (
    '—'
  )
  const d = project.direction
  return (
    <>
      <section
        className={`overview-next ${next?.status === 'stale' ? 'is-stale' : ''}`}
        aria-label="下一步"
      >
        <div>
          <span className="eyebrow">下一步</span>
          <h2>
            {next
              ? `阶段 ${flow.indexOf(next) + 1} · ${STAGE_TITLES[next.key]}：${next.status === 'stale' ? '上游已修改，需要更新' : STAGE_TODO[next.key]}`
              : '六个阶段都已确认 · 可以导出研究提案'}
          </h2>
        </div>
        <button
          type="button"
          className="product-button is-primary flow-primary"
          onClick={() => navigate(`/p/${id}/${next?.key || 'proposal'}`)}
        >
          {next
            ? next.status === 'stale'
              ? '去更新'
              : `去${STAGE_TITLES[next.key]}`
            : '查看研究提案'}
          <ArrowRight size={14} aria-hidden="true" />
        </button>
      </section>
      <div className="overview-grid fill">
        <section className="panel overview-card overview-summary" style={{ gridArea: 'summary' }}>
          <div className="overview-card__head">
            <h2>{displayProjectTitle(project.title, project.id)}</h2>
            <CaseTag project={project} />
          </div>
          <ScrollRegion label="项目概要">
            <p className="overview-question">{d.question || d.text || '尚未填写研究方向。'}</p>
            {d.question && d.text && <p className="muted overview-direction-text">{d.text}</p>}
            <dl className="overview-dl">
              <div>
                <dt>领域</dt>
                <dd>{d.domain || '—'}</dd>
              </div>
              <div>
                <dt>研究约束</dt>
                <dd>{d.constraints.filter(Boolean).join('；') || '—'}</dd>
              </div>
            </dl>
            <Link to={`/p/${id}/direction`}>编辑研究方向 →</Link>
          </ScrollRegion>
          <div className="overview-settings">
            <CaseToggle project={project} />
          </div>
        </section>
        <section className="panel overview-card" style={{ gridArea: 'test' }}>
          <h2>最近一次检验</h2>
          {main ? (
            <>
              <dl className="overview-numbers">
                <div>
                  <dt>主系数</dt>
                  <dd>{num(main.coef)}</dd>
                </div>
                <div>
                  <dt>标准误</dt>
                  <dd>{num(main.se)}</dd>
                </div>
                <div>
                  <dt>p 值</dt>
                  <dd>{num(main.p)}</dd>
                </div>
                <div>
                  <dt>观测数</dt>
                  <dd>{main.n_obs.toLocaleString()}</dd>
                </div>
              </dl>
              <p className="overview-strength">主结论强度：{strengthCell}</p>
              <div className="actions overview-test-actions">
                <Link className="product-button" to={`/p/${id}/data?tab=results`}>
                  完整结果与图表
                </Link>
                <Link className="product-button" to={`/p/${id}/proposal`}>
                  研究提案
                </Link>
              </div>
            </>
          ) : (
            <p className="muted">尚未运行检验。完成方案与数据绑定后，在「数据与检验」中运行。</p>
          )}
        </section>
        <section className="panel overview-card overview-stages" style={{ gridArea: 'stages' }}>
          <h2>
            阶段进度 <small className="inline-meta">已完成 {done} / 6</small>
          </h2>
          <ol className="overview-stage-grid">
            {flow.map((s, i) => (
              <li key={s.key} className={`tone-${FLOW_TONE[s.status]}`}>
                <Link to={`/p/${id}/${s.key}`} aria-disabled={s.status === 'locked'}>
                  <span className="overview-stage-grid__idx">{i + 1}</span>
                  <span className="overview-stage-grid__body">
                    <strong>{STAGE_TITLES[s.key]}</strong>
                    <small title={s.summary || undefined}>
                      {s.summary || FLOW_LABEL[s.status]}
                    </small>
                  </span>
                  <span className={`status-badge is-${FLOW_TONE[s.status]}`}>
                    {FLOW_LABEL[s.status]}
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        </section>
        <section className="panel overview-card" style={{ gridArea: 'facts' }}>
          <h2>关键信息</h2>
          <dl
            className="overview-dl is-stacked scroll-region"
            data-scroll-region=""
            tabIndex={0}
            aria-label="关键信息"
          >
            <div>
              <dt>数据与样本期</dt>
              <dd>
                {f.dataset ? [f.dataset.name, period].filter(Boolean).join(' · ') : '尚未运行检验'}
              </dd>
            </div>
            <div>
              <dt>纳入证据</dt>
              <dd>{f.evidenceCount ?? '—'} 张</dd>
            </div>
            <div>
              <dt>当前方案</dt>
              <dd>
                {f.plan
                  ? `第 ${f.plan.version} 版 · ${f.plan.status === 'confirmed' ? '已确认' : '草稿'}`
                  : '—'}
              </dd>
            </div>
            <div className="overview-dl__extra">
              <dt>候选方向</dt>
              <dd>{f.candidateCount ?? '—'} 个</dd>
            </div>
            <div>
              <dt>检验运行</dt>
              <dd>{f.runCount ?? 0} 次</dd>
            </div>
            <div>
              <dt title="取主结论的强度">主结论强度</dt>
              <dd>{strengthCell}</dd>
            </div>
          </dl>
        </section>
      </div>
    </>
  )
}
