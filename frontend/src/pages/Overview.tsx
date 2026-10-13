import { Link, useParams } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { ErrorNote } from '../components/Shared'
import PageBar from '../components/shell/PageBar'
import StageBar from '../components/shell/StageBar'
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

/** 总览驾驶舱：hero + 关键信息条 + 主 CTA + 横向六阶段时间线（参考旧版 ProjectOverviewPage） */
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
  const status =
    done === 6
      ? ['green', '可交接']
      : stale.length
        ? ['yellow', '有过期阶段']
        : ['orange', '进行中']
  const factCells: [string, React.ReactNode][] = [
    [
      '数据资产与样本期',
      f.dataset ? [f.dataset.name, period].filter(Boolean).join(' · ') : '尚未运行检验',
    ],
    ['纳入证据', `${f.evidenceCount ?? '—'} 张`],
    [
      '当前方案',
      f.plan
        ? `第 ${f.plan.version} 版 · ${f.plan.status === 'confirmed' ? '已确认' : '草稿'}`
        : '—',
    ],
    ['最近运行', main ? `coef ${num(main.coef)} · p ${num(main.p)}` : '—'],
    [
      '结论强度',
      f.strength ? (
        <span
          className={`status-badge is-${f.strength === 'causal_cautious' ? 'orange' : 'green'}`}
        >
          {strengths[f.strength]}
          {['deferred', 'rejected'].includes(f.strengthDecision || '') &&
            (f.strengthDecision === 'deferred' ? '（已暂缓）' : '（已拒绝）')}
        </span>
      ) : (
        '—'
      ),
    ],
  ]
  return (
    <div className="page-fill">
      <PageBar
        title={project.title}
        badge={
          <>
            <span className={`status-badge is-${status[0]}`}>{status[1]}</span>
            <CaseTag project={project} />
          </>
        }
      >
        <span className="inline-meta">已完成 {done} / 6</span>
        {next ? (
          <Link className="product-button is-primary" to={`/p/${id}/${next.key}`}>
            继续：{STAGE_TITLES[next.key]}
            <ArrowRight size={15} aria-hidden="true" />
          </Link>
        ) : (
          <Link className="product-button is-primary" to={`/p/${id}/proposal`}>
            查看研究提案
            <ArrowRight size={15} aria-hidden="true" />
          </Link>
        )}
      </PageBar>
      <div className="page-body overview-body">
        <p className="overview-question">
          {project.direction.question || project.direction.text || '尚未填写研究方向。'}
        </p>
        <section className="project-overview__facts is-wide" aria-label="关键信息">
          {factCells.map(([k, v]) => (
            <div key={k}>
              <span>{k}</span>
              <strong>{v}</strong>
            </div>
          ))}
        </section>
        <StageBar projectId={id!} stages={stages} size="lg" current={next?.key} />
        {stale.length > 0 && (
          <p className="notice" role="status">
            {stale.map((s) => STAGE_TITLES[s.key]).join('、')}
            已过期：上游信息已变化，旧内容保留，可在对应阶段重新生成或运行。
          </p>
        )}
        <div className="cols-2 overview-lower">
          <section className="panel">
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
          <section className="panel">
            <h2>项目设置</h2>
            <CaseToggle project={project} />
          </section>
        </div>
      </div>
    </div>
  )
}
