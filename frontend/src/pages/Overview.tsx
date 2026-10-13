import { Link, useParams } from 'react-router-dom'
import { ErrorNote } from '../components/Shared'
import { ScrollRegion } from '../components/shell/ShellContext'
import CaseToggle, { CaseTag } from '../components/CaseToggle'
import { strengths } from '../components/Claims'
import { num } from '../components/ResultTable'
import { useProjectFacts } from '../lib/facts'
import {
  STAGE_TITLES,
  STATUS_LABELS,
  completedCount,
  nextStage,
  statusTone,
  useOverview,
} from '../lib/stages'

/** 总览：与阶段页共用 StageLayout 外壳（一行页头 + 紧凑阶段条 + 继续按钮），下方网格填满一屏 */
export default function Overview() {
  const { id } = useParams()
  const q = useOverview(id)
  const f = useProjectFacts(id)
  if (q.isPending) return <p className="loading-line">正在读取项目…</p>
  if (!q.data)
    return (
      <div className="page-body">
        <ErrorNote error={q.error} />
      </div>
    )
  const { project, stages } = q.data
  const next = nextStage(stages)
  const done = completedCount(stages)
  const stale = stages.filter((s) => s.status === 'stale')
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
      {stale.length > 0 && (
        <p className="notice" role="status">
          {stale.map((s) => STAGE_TITLES[s.key]).join('、')}
          已过期：上游信息已变化，旧内容保留，可在对应阶段重新生成或运行。
        </p>
      )}
      <div className="overview-grid fill">
        <section className="panel overview-card overview-summary">
          <div className="overview-card__head">
            <h2>{project.title}</h2>
            <CaseTag project={project} />
          </div>
          <ScrollRegion label="项目概要">
            <p className="overview-question">{d.question || d.text || '尚未填写研究方向。'}</p>
            {d.question && d.text && <p className="muted">{d.text}</p>}
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
        </section>
        <section className="panel overview-card">
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
              <div className="actions">
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
        <section className="panel overview-card">
          <h2>项目设置</h2>
          <CaseToggle project={project} />
        </section>
        <section className="panel overview-card overview-stages">
          <h2>
            阶段进度 <small className="inline-meta">已完成 {done} / 6</small>
          </h2>
          <ol className="overview-stage-grid">
            {stages.map((s, i) => (
              <li key={s.key} className={`tone-${statusTone(s.status)}`}>
                <Link to={`/p/${id}/${s.key}`}>
                  <span className="overview-stage-grid__idx">{i + 1}</span>
                  <span className="overview-stage-grid__body">
                    <strong>{STAGE_TITLES[s.key] || s.label}</strong>
                    <small>{s.summary || STATUS_LABELS[s.status] || s.status}</small>
                  </span>
                  <span className={`status-badge is-${statusTone(s.status)}`}>
                    {STATUS_LABELS[s.status] || s.status}
                  </span>
                </Link>
              </li>
            ))}
          </ol>
          {next && (
            <p className="muted">
              下一步：
              <Link to={`/p/${id}/${next.key}`}>{STAGE_TITLES[next.key]} →</Link>
            </p>
          )}
        </section>
        <section className="panel overview-card">
          <h2>关键信息</h2>
          <dl className="overview-dl">
            <div>
              <dt>数据资产与样本期</dt>
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
            <div>
              <dt>检验运行</dt>
              <dd>{f.runCount ?? 0} 次</dd>
            </div>
            <div>
              <dt>结论强度（主结论）</dt>
              <dd>{strengthCell}</dd>
            </div>
          </dl>
        </section>
      </div>
    </>
  )
}
