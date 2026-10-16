import { ScrollRegion } from '../components/shell/ShellContext'
import Bindings, { type ConfirmBinding } from '../components/Bindings'
import Analysis from './Analysis'
import { useCallback, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, body } from '../api/client'
import type { Dataset } from '../api/datasets'
import type { StudyPlan } from '../api/plans'
import type { AnalysisRun } from '../api/analysis'
import DatasetImport from '../components/DatasetImport'
import DatasetDetails from '../components/DatasetDetails'
import JobProgress from '../components/JobProgress'
import type { Job } from '../components/JobProgress'
import { ErrorNote } from '../components/Shared'
import { VersionPills } from '../components/ui/Bits'
import { useFlow, useFlowStage, useStageUi } from '../components/flow/FlowContext'
import { EmptyState, ProgressView } from '../components/flow/FlowBits'

const STEP_NAMES: Record<string, string> = {
  main: '主模型',
  event_study: '事件研究',
  robustness: '稳健性',
  permutation: '置换检验',
  reproduction: '独立复算',
  assessment: '结论评估',
}
interface SavedBinding {
  dataset_id: string
  confirmed: boolean
  updated_at?: string
  inherited_from?: string | null
}

/** 数据与检验：上传数据 → 确认系统建议的变量绑定 → 运行检验 → 确认并进入下一阶段 */
export default function Data() {
  const { id } = useParams()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [job, setJob] = useState('')
  const [importOpen, setImportOpen] = useState(false)
  const { confirm } = useFlow()
  const stage = useFlowStage('data')
  const datasets = useQuery({ queryKey: ['datasets'], queryFn: () => api<Dataset[]>('/datasets') })
  const tasks = useQuery({
    queryKey: ['dataset-tasks', id],
    queryFn: () => api<Job[]>(`/projects/${id}/jobs?kind=dataset`),
  })
  const plans = useQuery({
    queryKey: ['plans', id],
    queryFn: () => api<StudyPlan[]>(`/projects/${id}/plans`),
  })
  const plan = plans.data?.find((p) => p.status === 'confirmed' && !p.stale)
  const binding = useQuery({
    queryKey: ['bindings', plan?.id],
    queryFn: () => api<SavedBinding | null>(`/plans/${plan!.id}/bindings`),
    enabled: !!plan,
  })
  const runs = useQuery({
    queryKey: ['runs', id],
    queryFn: () => api<AnalysisRun[]>(`/projects/${id}/runs`),
    refetchInterval: (q) =>
      q.state.data?.some((r) => ['queued', 'running'].includes(r.status)) ? 1000 : false,
  })
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['datasets'] })
    qc.invalidateQueries({ queryKey: ['dataset-tasks', id] })
    qc.invalidateQueries({ queryKey: ['runs', id] })
    qc.invalidateQueries({ queryKey: ['overview', id] })
  }
  const confirmRef = useRef<ConfirmBinding>(null)
  const [hasConfirm, setHasConfirm] = useState(false)
  const registerConfirm = useCallback((fn: ConfirmBinding) => {
    confirmRef.current = fn
    setHasConfirm(!!fn)
  }, [])
  const tab = (params.get('tab') as 'assets' | 'binding' | 'results') || 'assets'
  const setTab = (k: string) => {
    const next = new URLSearchParams(params)
    next.set('tab', k)
    if (k !== 'results') next.delete('run')
    setParams(next)
  }
  const current =
    datasets.data?.find((d) => d.id === params.get('dataset')) ||
    datasets.data?.find((d) => d.id === binding.data?.dataset_id) ||
    datasets.data?.[0]
  const importJob =
    job ||
    (tasks.data?.[0] && ['queued', 'running'].includes(tasks.data[0].status)
      ? tasks.data[0].id
      : '')
  const real =
    binding.data && (binding.data.updated_at || binding.data.inherited_from) ? binding.data : null
  const bound = !!real?.confirmed
  const planRuns = runs.data?.filter((r) => r.plan_id === plan?.id) || []
  const lastRun = planRuns[0]
  const running = lastRun && ['queued', 'running'].includes(lastRun.status)
  const mainOk = lastRun?.steps?.main?.status === 'succeeded' || !!lastRun?.result?.main
  /** 主模型成功即可进入提案；稳健性单步失败只作警告，不锁死 */
  const runOk = !!lastRun && !lastRun.stale && (lastRun.status === 'succeeded' || !!mainOk)
  const partialFail =
    !!lastRun &&
    !lastRun.stale &&
    !!mainOk &&
    (lastRun.status === 'failed' ||
      Object.values(lastRun.steps || {}).some((st) => st.status === 'failed'))
  const start = useMutation({
    mutationFn: () => api<{ job_id: string }>(`/plans/${plan!.id}/runs`, body('POST')),
    onSuccess: () => {
      setParams({ tab: 'results' })
      refresh()
    },
  })

  useStageUi({
    checklist: [
      { label: '上传数据', done: !!current },
      { label: '确认绑定', done: bound },
      { label: '运行检验', done: !!runOk },
    ],
    primary: !plan
      ? { label: '上传数据', disabled: true, reason: '先在研究计划阶段确认一个方案' }
      : importJob
        ? { label: '正在导入…', busy: true }
        : !current
          ? { label: '上传数据', onClick: () => setImportOpen(true) }
          : !bound
            ? tab !== 'binding'
              ? {
                  label: '确认数据绑定',
                  onClick: () => setTab('binding'),
                  reason: real?.inherited_from
                    ? '绑定继承自上一版方案，需要重新确认'
                    : '系统已建议变量绑定，核对后确认',
                }
              : {
                  label: '确认数据绑定',
                  disabled: !hasConfirm,
                  onClick: () => confirmRef.current?.(),
                  reason: '核对每个变量对应的列',
                }
            : running || start.isPending
              ? { label: '正在运行检验…', busy: true }
              : !runOk
                ? {
                    label: '运行检验',
                    onClick: () => start.mutate(),
                    error: start.error
                      ? (start.error as Error).message
                      : lastRun?.status === 'failed' && !lastRun.stale
                        ? lastRun.error || '检验失败'
                        : null,
                  }
                : {
                    label: '确认并进入下一阶段',
                    reason: partialFail
                      ? '主模型已成功；有稳健性步骤失败，可作为警告进入提案'
                      : '检验已完成',
                    onClick: () => {
                      if (!confirm('data')) navigate(`/p/${id}/proposal`)
                    },
                  },
  })

  if (running) {
    const steps = Object.entries(lastRun!.steps || {}).map(([k, v]) => ({
      label:
        (STEP_NAMES[k] || k) +
        (v.status === 'not_applicable' ? ' · 不适用' : v.status === 'failed' ? ' · 失败' : ''),
      state: (v.status === 'succeeded'
        ? 'done'
        : v.status === 'not_applicable'
          ? 'na'
          : v.status === 'running' || v.status === 'queued'
            ? 'now'
            : v.status === 'failed'
              ? 'failed'
              : 'todo') as 'done' | 'now' | 'todo' | 'failed' | 'na',
    }))
    return (
      <ProgressView
        title="正在运行检验"
        detail="主回归、事件研究、稳健性、置换检验与独立复算。完成后自动显示结果。"
        steps={steps}
      />
    )
  }
  return (
    <>
      <div className="stage-tabs is-compact" role="tablist" aria-label="数据与检验">
        {(
          [
            ['assets', '1 数据', current ? `${current.name}` : '尚未上传'],
            ['binding', '2 变量绑定', bound ? '已确认' : '待确认'],
            [
              'results',
              '3 检验结果',
              runOk
                ? partialFail
                  ? '主模型成功 · 有部分失败'
                  : '已完成'
                : lastRun
                  ? '需要重新运行'
                  : '尚未运行',
            ],
          ] as const
        ).map(([k, label, note]) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={tab === k}
            className={tab === k ? 'is-active' : ''}
            onClick={() => setTab(k)}
          >
            <strong>{label}</strong>
            <small>{note}</small>
          </button>
        ))}
        {tab === 'assets' && current && stage.editable && (
          <button className="product-button is-quiet" onClick={() => setImportOpen((v) => !v)}>
            导入其他数据
          </button>
        )}
      </div>
      {importOpen && (
        <div className="side-drawer" role="dialog" aria-label="导入数据">
          <div className="side-drawer__head">
            <strong>上传数据</strong>
            <button className="icon-button" aria-label="关闭" onClick={() => setImportOpen(false)}>
              ×
            </button>
          </div>
          <ScrollRegion label="导入数据">
            <DatasetImport
              defaultOpen
              projectId={id!}
              onStart={(j) => {
                setJob(j)
                setImportOpen(false)
                refresh()
              }}
            />
          </ScrollRegion>
        </div>
      )}
      {importJob && (
        <JobProgress
          id={importJob}
          onComplete={(j) => {
            setJob('')
            refresh()
            if (j.status === 'succeeded' && j.result?.dataset_id)
              setParams({ tab: 'binding', dataset: String(j.result.dataset_id) })
          }}
        />
      )}
      <ErrorNote error={datasets.error || tasks.error || start.error} />
      {tab === 'results' ? (
        lastRun ? (
          <Analysis />
        ) : (
          <EmptyState
            title="这里会显示检验结果"
            what="主回归系数、事件研究图、稳健性检验、置换检验与独立复算，以及系统给出的结论强度（关联 / 谨慎因果）。"
            example={{
              title: '主系数 0.084（p = 0.012）',
              body: '平行趋势通过 · 4/5 项稳健性同号显著 · 结论强度：关联',
            }}
            blocked={!bound ? '先确认变量绑定。' : undefined}
            action={
              stage.editable ? { label: '运行检验', onClick: () => start.mutate() } : undefined
            }
          />
        )
      ) : datasets.isPending ? (
        <p className="loading-line">正在读取数据…</p>
      ) : !current ? (
        <EmptyState
          title="上传数据表，系统会建议每个变量对应哪一列"
          what={
            plan
              ? `支持 CSV、Excel、Stata。研究计划需要这些变量：${plan.variables.map((v) => v.name).join('、')}。`
              : '支持 CSV、Excel、Stata。先确认研究计划，系统才知道需要哪些变量。'
          }
          example={{
            title: 'firm_year_panel.csv · 3,412 家企业 × 13 年',
            body: '系统建议：绿色专利数 ← green_patents；是否试点 ← pilot',
          }}
          action={
            plan && stage.editable
              ? { label: '上传数据', onClick: () => setImportOpen(true) }
              : undefined
          }
        />
      ) : (
        <>
          {(datasets.data?.length || 0) > 1 && (
            <VersionPills
              label="数据"
              value={current.id}
              onChange={(v) => {
                const next = new URLSearchParams(params)
                next.set('dataset', v)
                setParams(next)
              }}
              items={(datasets.data || []).map((d) => ({
                id: d.id,
                label: d.name,
                note: `${d.n_rows.toLocaleString()} 行`,
              }))}
            />
          )}
          {/* 已确认的阶段只读：先"修改此阶段" */}
          <fieldset className="flow-ro fill" disabled={!stage.editable}>
            {tab === 'binding' ? (
              <Bindings projectId={id!} dataset={current} registerConfirm={registerConfirm} />
            ) : (
              <DatasetDetails key={current.id} dataset={current} onSaved={refresh} />
            )}
          </fieldset>
        </>
      )}
    </>
  )
}
