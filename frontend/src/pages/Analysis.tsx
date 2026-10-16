import ProcessTimeline, {
  jobSeconds,
  useStageJob,
  type StepState,
} from '../components/flow/ProcessTimeline'
import { ScrollRegion } from '../components/shell/ShellContext'
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
  const runJob = useStageJob(id, 'analysis', current?.job_id)
  /** 时间线每步展开的明细：只取本次运行结果里已有的数字 */
  const stepDetail = (key: string) => {
    if (!result) return undefined
    if (key === 'main')
      return (
        <p>
          系数 {num(result.main.coef)}，SE {num(result.main.se)}，p {num(result.main.p)}，N{' '}
          {result.main.n_obs.toLocaleString()}
        </p>
      )
    if (key === 'robustness' && result.robustness.length)
      return (
        <ul>
          {result.robustness.map((r) => (
            <li key={r.id}>
              {r.change}：
              {r.status === 'succeeded' ? `系数 ${num(r.coef)}，p ${num(r.p)}` : r.error}
            </li>
          ))}
        </ul>
      )
    if (key === 'event_study' && result.event?.pretrend_wald)
      return <p>前趋势联合检验 p {num(result.event.pretrend_wald.p)}</p>
    if (key === 'permutation' && result.permutation)
      return (
        <p>
          {result.permutation.n} 次置换，双侧 p {num(result.permutation.p)}
        </p>
      )
    if (key === 'reproduction' && current?.reproduction)
      return (
        <p>
          {current.reproduction.consistent ? '全部一致' : '未全部一致'}，最大相对差{' '}
          {current.reproduction.max_relative_diff.toExponential(3)}
        </p>
      )
    return undefined
  }
  const usedPlan = plans.data?.find((p) => p.id === current?.plan_id)
  /** 变量中文标签：用方案里变量的中文定义，原始公式作为次要文字 */
  const label = (expr: string) => {
    const v = usedPlan?.variables.find((x) => x.name === expr || expr.includes(x.name))
    return v ? `${v.definition.split(/[，,（(]/)[0]}` : expr
  }
  return (
    <>
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
                  (r.steps?.main?.status === 'succeeded' &&
                  Object.values(r.steps || {}).some((st) => st.status === 'failed')
                    ? ' · 主模型成功（有部分失败）'
                    : r.status === 'succeeded'
                      ? ''
                      : ' · ' + statusNames[r.status]) +
                  (r.stale ? ' · 已过期' : ''),
                tone: r.stale ? 'stale' : r.status === 'failed' ? 'failed' : undefined,
              }))}
            />
          </div>
          <ProcessTimeline
            title="检验运行"
            seconds={jobSeconds(runJob)}
            steps={Object.entries(current.steps).map(([key, st]) => {
              const finished = ['succeeded', 'failed'].includes(current.status)
              const na =
                st.status === 'not_applicable' || (!!st.error && /此方法类别不执行/.test(st.error))
              return {
                key,
                label: `${stepNames[key] || key}${
                  st.status === 'succeeded'
                    ? ''
                    : na
                      ? ' · 不适用'
                      : ' · ' + (statusNames[st.status] || st.status)
                }${st.error && !na ? '：' + st.error : na && st.error ? '：' + st.error : ''}`,
                state: (st.status === 'succeeded'
                  ? 'done'
                  : na || st.status === 'not_applicable'
                    ? 'na'
                    : st.status === 'running' || st.status === 'queued'
                      ? 'now'
                      : st.status === 'failed'
                        ? 'failed'
                        : finished
                          ? 'na'
                          : 'todo') as StepState,
                detail: stepDetail(key),
              }
            })}
          />
          {current.stale && (
            <p className="notice">上游方案、数据或绑定已变更，本次运行已过期；旧数字保留供核对。</p>
          )}
          {current.error && <p className="error">{current.error}</p>}
          {Object.entries(current.steps)
            .filter(
              ([, st]) =>
                st.error &&
                st.status !== 'not_applicable' &&
                !/此方法类别不执行/.test(st.error || ''),
            )
            .map(([key, st]) => (
              <p className="error" key={key}>
                {stepNames[key] || key}：{st.error}
              </p>
            ))}
          {Object.entries(current.steps)
            .filter(
              ([, st]) =>
                st.status === 'not_applicable' ||
                (!!st.error && /此方法类别不执行/.test(st.error || '')),
            )
            .map(([key, st]) => (
              <p className="muted" key={'na-' + key}>
                {stepNames[key] || key}
                {st.error ? `：${st.error}` : '：此方法类别不执行'}
              </p>
            ))}
          {current.steps?.main?.status === 'succeeded' &&
            Object.values(current.steps).some((st) => st.status === 'failed') && (
              <p className="notice">
                主模型已成功；部分稳健性步骤失败。仍可生成研究提案，失败步骤仅作警告。
              </p>
            )}
          {!result && current.status === 'failed' && <Claims runId={current.id} />}{' '}
          {result && (
            <div className="results-stack">
              <section className="panel">
                <h2>主模型结果</h2>

                <p>
                  结果：{label(current.spec.outcome)} · 核心解释：{label(current.spec.treatment)} ·
                  聚类：
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
              </section>
              <AnalysisCharts result={result} only="event" />
              <section className="panel">
                <h2>稳健性检查（{result.robustness.length}）</h2>
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
              </section>
              <section className="panel">
                <h2>
                  独立复算
                  {current.reproduction
                    ? current.reproduction.consistent
                      ? ' · 一致'
                      : ' · 未全部一致'
                    : ''}
                </h2>
                {current.reproduction ? (
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
                              <td>{r.status === 'consistent' ? '一致' : r.error || '未一致'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                ) : (
                  <p className="muted">本次运行没有独立复算记录。</p>
                )}
              </section>
              <AnalysisCharts result={result} only="permutation" />
              <section className="panel">
                <h2>解释边界（{result.warnings.length}）</h2>
                {result.warnings.length ? (
                  <ul>
                    {result.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">没有额外提示。</p>
                )}
              </section>
              <Claims runId={current.id} />
            </div>
          )}
        </>
      )}
    </>
  )
}
