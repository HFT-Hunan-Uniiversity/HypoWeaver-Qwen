import { Link, useParams } from 'react-router-dom'
import { ArrowRight, Check } from 'lucide-react'
import { ErrorNote } from '../components/Shared'
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
      <div className="product-page">
        <ErrorNote error={q.error} />
      </div>
    )
  const { project, stages } = q.data
  const next = nextStage(stages)
  const done = completedCount(stages)
  const stale = stages.filter((s) => s.status === 'stale')
  const main = f.run?.result?.main
  const status =
    done === 6
      ? ['green', '可交接']
      : stale.length
        ? ['yellow', '有过期阶段']
        : ['orange', '进行中']
  return (
    <div className="product-page project-overview">
      <Link className="product-back" to="/">
        ← 全部项目
      </Link>
      <header className="product-page__header project-overview__header">
        <div>
          <span className="product-eyebrow">项目总览 · 已完成 {done} / 6</span>
          <div className="project-overview__titleline">
            <h1>{project.title}</h1>
            <span className={`status-badge is-${status[0]}`}>{status[1]}</span>
          </div>
          <p>{project.direction.question || project.direction.text || '尚未填写研究方向。'}</p>
        </div>
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
      </header>
      <section className="project-overview__facts is-wide" aria-label="关键信息">
        <div>
          <span>数据资产与样本期</span>
          <strong title={f.dataset?.name}>
            {f.dataset
              ? `${f.dataset.name}${f.dataset.panel.time_min ? ` · ${f.dataset.panel.time_min}–${f.dataset.panel.time_max}` : ''}`
              : '尚未运行检验'}
          </strong>
        </div>
        <div>
          <span>纳入证据</span>
          <strong>{f.evidenceCount ?? '—'} 张</strong>
        </div>
        <div>
          <span>当前方案</span>
          <strong>
            {f.plan
              ? `第 ${f.plan.version} 版 · ${f.plan.status === 'confirmed' ? '已确认' : '草稿'}`
              : '—'}
          </strong>
        </div>
        <div>
          <span>最近运行</span>
          <strong>{main ? `coef ${num(main.coef)} · p ${num(main.p)}` : '—'}</strong>
        </div>
        <div>
          <span>结论强度</span>
          <strong>
            {f.strength ? (
              <span
                className={`status-badge is-${f.strength === 'causal_cautious' ? 'orange' : 'green'}`}
              >
                {strengths[f.strength]}
              </span>
            ) : (
              '—'
            )}
          </strong>
        </div>
      </section>
      {stale.length > 0 && (
        <p className="notice" role="status">
          {stale.map((s) => STAGE_TITLES[s.key]).join('、')}
          已过期：上游信息已变化，旧内容仍保留，可在对应阶段重新生成或运行。
        </p>
      )}
      <section className="stage-timeline" aria-label="六阶段进度">
        {stages.map((s, i) => {
          const tone = statusTone(s.status)
          return (
            <Link
              key={s.key}
              to={`/p/${id}/${s.key}`}
              className={`tone-${tone} ${next?.key === s.key ? 'is-next' : ''}`}
            >
              <span className="stage-timeline__node">
                {tone === 'green' ? <Check size={12} /> : i + 1}
              </span>
              <strong>{STAGE_TITLES[s.key] || s.label}</strong>
              <small>{STATUS_LABELS[s.status] || s.status}</small>
              <em>{s.summary}</em>
            </Link>
          )
        })}
      </section>
      {main && (
        <section className="overview-result">
          <div className="product-section-heading">
            <span className="product-eyebrow">研究成果直达</span>
            <h2>最近一次检验</h2>
          </div>
          <dl>
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
              查看完整结果与图表
            </Link>
            <Link className="product-button" to={`/p/${id}/proposal`}>
              研究提案
            </Link>
          </div>
        </section>
      )}
    </div>
  )
}
