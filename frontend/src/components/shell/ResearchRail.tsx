import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Check } from 'lucide-react'
import { STAGE_TITLES, STATUS_LABELS, statusTone, useOverview } from '../../lib/stages'
import { useProjectFacts } from '../../lib/facts'
import { strengths } from '../Claims'
import { num } from '../ResultTable'

export default function ResearchRail({ projectId }: { projectId: string }) {
  const [tab, setTab] = useState<'plan' | 'overview'>('plan')
  const overview = useOverview(projectId)
  const f = useProjectFacts(projectId)
  const stages = overview.data?.stages || []
  return (
    <aside className="task-context no-print" aria-label="研究进度与证据">
      <div className="task-context__tabs" role="tablist" aria-label="研究侧栏">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'plan'}
          className={tab === 'plan' ? 'is-active' : ''}
          onClick={() => setTab('plan')}
        >
          研究进度
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'overview'}
          className={tab === 'overview' ? 'is-active' : ''}
          onClick={() => setTab('overview')}
        >
          信息概览
        </button>
      </div>
      <div className="task-context__scroll">
        {tab === 'plan' ? (
          <>
            <section className="task-context__section">
              <header>
                <div>
                  <strong>六阶段进度</strong>
                  <small>状态与总览一致</small>
                </div>
              </header>
              <ol className="research-plan-list">
                {stages.map((s, i) => {
                  const tone = statusTone(s.status)
                  const cls = tone === 'green' ? 'is-done' : tone === 'gray' ? '' : 'is-active'
                  return (
                    <li key={s.key} className={`${cls} tone-${tone}`}>
                      <span>{tone === 'green' ? <Check size={11} /> : i + 1}</span>
                      <div>
                        <Link to={`/p/${projectId}/${s.key}`}>
                          <strong>{STAGE_TITLES[s.key] || s.label}</strong>
                        </Link>
                        <small>
                          {STATUS_LABELS[s.status] || s.status} · {s.summary}
                        </small>
                      </div>
                    </li>
                  )
                })}
              </ol>
            </section>
            <section className="task-context__section">
              <header>
                <div>
                  <strong>证据与产出</strong>
                  <small>来自当前项目的真实记录</small>
                </div>
              </header>
              <div className="task-context__metrics">
                <span>
                  <strong>{f.evidenceCount ?? '—'}</strong>
                  <small>纳入证据</small>
                </span>
                <span>
                  <strong>{f.candidateCount ?? '—'}</strong>
                  <small>候选</small>
                </span>
                <span>
                  <strong>{f.plan ? `v${f.plan.version}` : '—'}</strong>
                  <small>方案版本</small>
                </span>
                <span>
                  <strong>{f.runCount ?? '—'}</strong>
                  <small>运行次数</small>
                </span>
                <span>
                  <strong>{f.run?.result ? num(f.run.result.main.coef) : '—'}</strong>
                  <small>主系数</small>
                </span>
                <span>
                  <strong>
                    {f.strength ? strengths[f.strength] : '—'}
                    {f.strengthDecision === 'deferred' && '（已暂缓）'}
                    {f.strengthDecision === 'rejected' && '（已拒绝）'}
                  </strong>
                  <small>结论强度</small>
                </span>
              </div>
            </section>
          </>
        ) : (
          <section className="task-context__section task-context__overview">
            <dl>
              <div>
                <dt>研究方向</dt>
                <dd>{overview.data?.project.direction.text || '待补充'}</dd>
              </div>
              <div>
                <dt>数据资产</dt>
                <dd>{f.dataset ? f.dataset.name : '尚未运行检验'}</dd>
              </div>
              <div>
                <dt>样本期</dt>
                <dd>
                  {f.dataset?.panel.time_min
                    ? `${f.dataset.panel.time_min}–${f.dataset.panel.time_max}`
                    : '—'}
                </dd>
              </div>
              <div>
                <dt>最近运行</dt>
                <dd>
                  {f.run?.result
                    ? [
                        `coef ${num(f.run.result.main.coef)}`,
                        `p ${num(f.run.result.main.p)}`,
                        `N ${f.run.result.main.n_obs.toLocaleString()}`,
                      ].join(' · ')
                    : '—'}
                </dd>
              </div>
            </dl>
          </section>
        )}
      </div>
    </aside>
  )
}
