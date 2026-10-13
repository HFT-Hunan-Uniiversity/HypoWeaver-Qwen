import { ScrollRegion, StageActions } from '../components/shell/ShellContext'
import { useUrlParam } from '../lib/urlState'
import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, body } from '../api/client'
import type { StudyPlan } from '../api/plans'
import type { AnalysisRun } from '../api/analysis'
import Claims from '../components/Claims'
import ResultTable, { num } from '../components/ResultTable'
import AnalysisCharts from '../components/AnalysisCharts'
import JobProgress from '../components/JobProgress'
import { ErrorNote } from '../components/Shared'
import { GeneratedBy, VersionPills } from '../components/ui/Bits'
const stepNames: Record<string, string> = {
  main: '主模型',
  event_study: '事件研究',
  robustness: '稳健性',
  permutation: '置换检验',
  reproduction: '独立复算',
  assessment: '结论评估',
}
const statusNames: Record<string, string> = {
  queued: '等待执行',
  running: '正在计算',
  succeeded: '已完成',
  failed: '失败',
  not_applicable: '不适用',
  not_started: '尚未开始',
}
export default function Analysis() {
  const { id } = useParams(),
    [params, setParams] = useSearchParams(),
    qc = useQueryClient(),
    [job, setJob] = useState('')
  const [sub, setSub] = useUrlParam('sub', 'robustness', [
    'robustness',
    'reproduction',
    'warnings',
  ] as const)
  const plans = useQuery({
    queryKey: ['plans', id],
    queryFn: () => api<StudyPlan[]>(`/projects/${id}/plans`),
  })
  const runs = useQuery({
    queryKey: ['runs', id],
    queryFn: () => api<AnalysisRun[]>(`/projects/${id}/runs`),
    refetchInterval: (q) =>
      q.state.data?.some((r) => ['queued', 'running'].includes(r.status)) ? 1000 : false,
  })
  const current = runs.data?.find((r) => r.id === params.get('run')) || runs.data?.[0],
    plan = plans.data?.find((p) => p.status === 'confirmed' && !p.stale),
    activeJob =
      job || (current && ['queued', 'running'].includes(current.status) ? current.job_id : '')
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['runs', id] })
    qc.invalidateQueries({ queryKey: ['overview', id] })
  }
  const start = useMutation({
    mutationFn: () => api<{ job_id: string }>(`/plans/${plan!.id}/runs`, body('POST')),
    onSuccess: (d) => {
      setJob(d.job_id)
      setParams({ tab: 'results' })
      refresh()
    },
  })
  const result = current?.result
  const usedPlan = plans.data?.find((p) => p.id === current?.plan_id)
  /** 变量中文标签：用方案里变量的中文定义，原始公式作为次要文字 */
  const label = (expr: string) => {
    const v = usedPlan?.variables.find((x) => x.name === expr || expr.includes(x.name))
    return v ? `${v.definition.split(/[，,（(]/)[0]}` : expr
  }
  return (
    <>
      <StageActions>
        <button
          disabled={
            !plan ||
            start.isPending ||
            runs.data?.some((r) => ['queued', 'running'].includes(r.status))
          }
          onClick={() => start.mutate()}
        >
          运行已确认方案
        </button>
      </StageActions>
      <ErrorNote error={runs.error || plans.error || start.error} />
      {!plan && (
        <p className="notice">
          请先确认一个未过期的方案，并完成 <Link to={`/p/${id}/data?tab=binding`}>变量绑定</Link>。
        </p>
      )}
      {activeJob && (
        <JobProgress
          id={activeJob}
          onComplete={(j) => {
            refresh()
            if (j.result?.run_id) setParams({ tab: 'results', run: String(j.result.run_id) })
          }}
        />
      )}
      {runs.isPending ? (
        <p>正在读取运行记录…</p>
      ) : !current ? (
        <section className="panel">
          <h2>尚未运行检验</h2>
          <p>数据就绪后，主回归和诊断会在后台计算并保存；错误会显示具体原因。</p>
          <Link to={`/p/${id}/data?tab=binding`}>检查数据与绑定 →</Link>
        </section>
      ) : (
        <>
          <div className="results-toolbar">
            <VersionPills
              label="运行记录"
              value={current.id}
              onChange={(v) => {
                setJob('')
                setParams({ tab: 'results', run: v })
              }}
              items={(runs.data || []).map((r) => ({
                id: r.id,
                label: new Date(r.created_at).toLocaleString('zh-CN', {
                  month: 'numeric',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                }),
                note:
                  `方案 v${r.plan_snapshot.version}` +
                  (r.status === 'succeeded' ? '' : ' · ' + statusNames[r.status]) +
                  (r.stale ? ' · 已过期' : ''),
                tone: r.stale ? 'stale' : r.status === 'failed' ? 'failed' : undefined,
              }))}
            />
            <div className="step-badges" aria-label="计算步骤">
              {Object.entries(current.steps).map(([key, st]) => (
                <span key={key} className={`is-${st.status}`} title={st.error || undefined}>
                  {stepNames[key] || key} · {statusNames[st.status] || st.status}
                </span>
              ))}
            </div>
          </div>
          {current.stale && (
            <p className="notice">上游方案、数据或绑定已变更，本次运行已过期；旧数字保留供核对。</p>
          )}
          {current.error && <p className="error">{current.error}</p>}
          {Object.entries(current.steps)
            .filter(([, st]) => st.error)
            .map(([key, st]) => (
              <p className="error" key={key}>
                {stepNames[key] || key}：{st.error}
              </p>
            ))}
          {!result && current.status === 'failed' && <Claims runId={current.id} />}{' '}
          {result && (
            <div className="results-grid fill">
              <section className="panel fill">
                <h2>主模型结果</h2>
                <ScrollRegion label="主模型结果">
                  <p>
                    结果：{label(current.spec.outcome)} · 核心解释：{label(current.spec.treatment)}{' '}
                    · 聚类：
                    {current.spec.cluster === 'unit'
                      ? '个体'
                      : current.spec.cluster === 'time'
                        ? '时间'
                        : current.spec.cluster}
                  </p>
                  <p className="muted">
                    原始设定：<code>{current.spec.outcome}</code> ~{' '}
                    <code>{current.spec.treatment}</code>
                  </p>
                  <ResultTable
                    rows={[
                      {
                        label: result.main.target === 'interaction' ? '交互项' : '主模型',
                        ...result.main,
                      },
                    ]}
                  />
                  <p>
                    个体数 {result.main.n_units?.toLocaleString()} · 组内 R²{' '}
                    {num(result.main.r2_within)} · 聚类组数 {result.sample_report.n_clusters}
                  </p>
                  <p className="muted">
                    输入 {result.sample_report.input_rows.toLocaleString()} 行，有效{' '}
                    {result.sample_report.n_valid.toLocaleString()} 行；样本筛选排除{' '}
                    {result.sample_report.dropped_by_reason.sample_filters} 行，缺失或非有限值排除{' '}
                    {result.sample_report.dropped_by_reason.missing_or_nonfinite} 行。
                  </p>
                </ScrollRegion>
              </section>
              <ScrollRegion className="results-cell" label="事件研究与置换检验">
                <AnalysisCharts result={result} />
              </ScrollRegion>
              <ScrollRegion className="results-cell" label="结论评估">
                <Claims runId={current.id} />
              </ScrollRegion>
              <section className="panel fill">
                <div className="sub-tabs" role="tablist" aria-label="稳健性与复算">
                  {(
                    [
                      ['robustness', `稳健性检查（${result.robustness.length}）`],
                      [
                        'reproduction',
                        `独立复算${current.reproduction ? (current.reproduction.consistent ? ' · 一致' : ' · 未全部一致') : ''}`,
                      ],
                      ['warnings', `解释边界（${result.warnings.length}）`],
                    ] as const
                  ).map(([k, t]) => (
                    <button
                      key={k}
                      role="tab"
                      aria-selected={sub === k}
                      className={sub === k ? 'is-active' : ''}
                      onClick={() => setSub(k)}
                    >
                      {t}
                    </button>
                  ))}
                </div>
                <ScrollRegion label="稳健性与复算明细">
                  {sub === 'robustness' ? (
                    <>
                      {result.robustness.length ? (
                        <>
                          <ResultTable
                            rows={result.robustness
                              .filter((r) => r.status === 'succeeded')
                              .map((r) => ({ ...r, label: r.change }))}
                          />
                          {result.robustness
                            .filter((r) => r.status === 'failed')
                            .map((r) => (
                              <p className="error" key={r.id}>
                                {r.change}：{r.error}
                              </p>
                            ))}
                        </>
                      ) : (
                        <p>当前方案未指定稳健性检查。</p>
                      )}
                    </>
                  ) : sub === 'reproduction' ? (
                    current.reproduction ? (
                      <>
                        <p className="muted">{current.reproduction.method} · 容差 0.000001</p>
                        <p>最大相对差：{current.reproduction.max_relative_diff.toExponential(3)}</p>
                        <div className="table-scroll">
                          <table>
                            <thead>
                              <tr>
                                <th>检验</th>
                                <th>原系数</th>
                                <th>复算系数</th>
                                <th>最大相对差</th>
                                <th>状态</th>
                              </tr>
                            </thead>
                            <tbody>
                              {current.reproduction.rows.map((r) => (
                                <tr key={r.id}>
                                  <td>{r.label}</td>
                                  <td>{num(r.original?.coef)}</td>
                                  <td>{num(r.estimate?.coef)}</td>
                                  <td>{r.max_relative_diff?.toExponential(3) || '—'}</td>
                                  <td>
                                    {r.status === 'consistent' ? '一致' : r.error || '未一致'}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </>
                    ) : (
                      <p className="muted">本次运行没有独立复算记录。</p>
                    )
                  ) : result.warnings.length ? (
                    <ul>
                      {result.warnings.map((w, i) => (
                        <li key={i}>{w}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="muted">没有额外提示。</p>
                  )}
                </ScrollRegion>
              </section>
            </div>
          )}
        </>
      )}
    </>
  )
}
