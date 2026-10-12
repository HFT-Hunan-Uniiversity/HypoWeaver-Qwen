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
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>统计检验</h1>
          <p className="muted">按确认后的方案执行。每次运行保留当时的方案和绑定设定。</p>
        </div>
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
      </div>
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
          <label>
            运行记录
            <select
              value={current.id}
              onChange={(e) => {
                setJob('')
                setParams({ tab: 'results', run: e.target.value })
              }}
            >
              {runs.data?.map((r) => (
                <option key={r.id} value={r.id}>
                  {new Date(r.created_at).toLocaleString('zh-CN')} · 方案第{r.plan_snapshot.version}
                  版 · {statusNames[r.status]}
                  {r.stale ? ' · 已过期' : ''}
                </option>
              ))}
            </select>
          </label>
          {current.stale && (
            <p className="notice">上游方案、数据或绑定已变更，本次运行已过期；旧数字保留供核对。</p>
          )}
          {current.error && <p className="error">{current.error}</p>}
          <section className="panel">
            <h2>计算步骤</h2>
            <div className="run-steps">
              {Object.entries(current.steps).map(([key, s]) => (
                <div key={key}>
                  <strong>{stepNames[key] || key}</strong>
                  <span className={s.status === 'failed' ? 'error' : 'muted'}>
                    {statusNames[s.status] || s.status}
                  </span>
                  {s.error && <small>{s.error}</small>}
                </div>
              ))}
            </div>
          </section>
          {!result && current.status === 'failed' && <Claims runId={current.id} />}{' '}
          {result && (
            <>
              <section className="panel">
                <h2>主模型结果</h2>
                <p className="muted">
                  结果：{current.spec.outcome} · 核心解释：{current.spec.treatment} · 聚类：
                  {current.spec.cluster === 'unit'
                    ? '个体'
                    : current.spec.cluster === 'time'
                      ? '时间'
                      : current.spec.cluster}
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
              </section>
              <AnalysisCharts result={result} />
              <section className="panel">
                <h2>稳健性检查</h2>
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
              </section>
              {current.reproduction && (
                <section className="panel">
                  <h2>独立复算：{current.reproduction.consistent ? '一致' : '未全部一致'}</h2>
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
                            <td>{r.status === 'consistent' ? '一致' : r.error || '未一致'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
              <Claims runId={current.id} />
              {result.warnings.length > 0 && (
                <section className="panel">
                  <h2>解释边界与提示</h2>
                  <ul>
                    {result.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </section>
              )}
            </>
          )}
        </>
      )}
    </>
  )
}
