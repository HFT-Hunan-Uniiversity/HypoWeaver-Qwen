import { useUrlParam } from '../lib/urlState'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, body } from '../api/client'
import { type StudyPlan, methods, semanticsLabels } from '../api/plans'
import { ErrorNote } from '../components/Shared'
import PlanEditor, { sectionTitles } from '../components/PlanEditor'
import JobProgress from '../components/JobProgress'
import type { Job } from '../components/JobProgress'
import { GeneratedBy, VersionPills } from '../components/ui/Bits'
import { useFlow, useFlowStage, useStageUi } from '../components/flow/FlowContext'
import { EmptyState, ProgressView } from '../components/flow/FlowBits'
import { useOverview } from '../lib/stages'
import { useLlm } from '../lib/llm'
export default function Plan() {
  const { id } = useParams(),
    qc = useQueryClient(),
    [version, setVersion] = useState(''),
    [job, setJob] = useState(''),
    [dirty, setDirty] = useState(false)
  const [sec, setSec] = useUrlParam<string>('sec', 'summary')
  const plans = useQuery({
    queryKey: ['plans', id],
    queryFn: () => api<StudyPlan[]>(`/projects/${id}/plans`),
  })
  const tasks = useQuery({
    queryKey: ['plan-tasks', id],
    queryFn: () => api<Job[]>(`/projects/${id}/plan-tasks`),
  })
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['plans', id] })
    qc.invalidateQueries({ queryKey: ['plan-tasks', id] })
    qc.invalidateQueries({ queryKey: ['overview', id] })
  }
  const current = plans.data?.find((p) => p.id === version) || plans.data?.[0],
    activeJob = job || tasks.data?.[0]?.id
  const draft = useMutation({
    mutationFn: () => api<{ job_id: string }>(`/projects/${id}/plans`, body('POST')),
    onSuccess: (d) => {
      setJob(d.job_id)
      setVersion('')
      refresh()
    },
  })
  const action = useMutation({
    mutationFn: (op: string) => api<StudyPlan>(`/plans/${current!.id}:${op}`, body('POST')),
    onSuccess: (p) => {
      setVersion(p.id)
      refresh()
      if (p.status === 'confirmed' && !confirm('plan')) navigate(`/p/${id}/data`)
    },
  })
  const navigate = useNavigate()
  const { confirm } = useFlow()
  const stage = useFlowStage('plan')
  const llmOk = useLlm().data?.configured !== false
  const selected = useOverview(id).data?.project.selected_candidate_id
  const running =
    draft.isPending || tasks.data?.some((j) => ['running', 'queued'].includes(j.status))
  const failedTask =
    tasks.data?.[0]?.status === 'failed' ? tasks.data[0].error || '方案起草失败' : null
  const draftable = !current || current.stale
  useStageUi({
    onStartEdit: () => current?.status === 'confirmed' && action.mutate('new-version'),
    primary: running
      ? { label: '正在起草…', busy: true }
      : !selected
        ? { label: '起草研究计划', disabled: true, reason: '先在候选阶段选定一条假设' }
        : draftable
          ? {
              label: current ? '重新起草研究计划' : '起草研究计划',
              needsLlm: true,
              onClick: () => draft.mutate(),
              error: draft.error ? (draft.error as Error).message : failedTask,
            }
          : current.status === 'draft'
            ? {
                label: '确认并进入下一阶段',
                disabled: dirty || action.isPending,
                busy: action.isPending,
                reason: dirty
                  ? '正在自动保存编辑…'
                  : `第 ${current.version} 版草稿 · ${current.variables.filter((v) => v.uncertain).length} 个变量含义待确认`,
                error: action.error ? (action.error as Error).message : null,
                onClick: () => action.mutate('confirm'),
              }
            : {
                label: '确认并进入下一阶段',
                onClick: () => !confirm('plan') && navigate(`/p/${id}/data`),
              },
  })
  const peer = current?.treatment_semantics === 'peer_exposure'
  return (
    <>
      <ErrorNote error={plans.error || tasks.error || draft.error || action.error} />
      {activeJob && <JobProgress id={activeJob} onComplete={refresh} />}
      {plans.isPending ? (
        <p className="loading-line">正在读取方案…</p>
      ) : running ? (
        <ProgressView
          title="正在起草研究计划"
          detail="把选定的假设变成变量、模型、稳健性检验与决策规则。完成后自动显示。"
        />
      ) : !current ? (
        <EmptyState
          title="这里会出现一份研究计划草案"
          what="包括：变量怎么度量、用什么模型、做哪些稳健性检验、置换与决策规则。你检查一遍，没问题就确认。"
          example={{
            title: '双重差分（DID）· 企业与年份双向固定效应',
            body: '因变量 绿色专利数 · 处理 试点×试点后 · 稳健性：PSM-DID、安慰剂检验',
          }}
          blocked={!selected ? '先在候选阶段选定一条假设。' : undefined}
          action={
            stage.editable ? { label: '起草研究计划', onClick: () => draft.mutate() } : undefined
          }
        />
      ) : (
        <>
          <div className="candidate-toolbar">
            <VersionPills
              label="方案版本"
              value={current.id}
              onChange={setVersion}
              items={(plans.data || []).map((p) => ({
                id: p.id,
                label: `第 ${p.version} 版`,
                note:
                  (p.status === 'draft'
                    ? '草稿'
                    : p.status === 'confirmed'
                      ? '已确认'
                      : '已有更新版') + (p.stale ? ' · 已过期' : ''),
                tone: p.stale ? 'stale' : undefined,
              }))}
            />
            <GeneratedBy of={current} />
          </div>
          <div className="plan-layout fill">
            <nav className="plan-nav" aria-label="方案分节">
              {[['summary', '概要与重点审阅'], ...Object.entries(sectionTitles)].map(([k, t]) => (
                <button
                  type="button"
                  key={k}
                  className={sec === k ? 'is-active' : ''}
                  aria-current={sec === k ? 'true' : undefined}
                  onClick={() => setSec(k)}
                >
                  {t}
                </button>
              ))}
              {dirty && <small className="plan-nav__dirty">正在自动保存…</small>}
            </nav>
            <div className="plan-main">
              {current.stale && (
                <p className="notice">
                  方向或候选已变更，此方案已过期。原内容保留，请根据当前候选重新起草。
                </p>
              )}
              <div className="cols-2 plan-summary-grid fill" hidden={sec !== 'summary'}>
                <section
                  className="panel scroll-region"
                  data-scroll-region=""
                  tabIndex={0}
                  id="plan-summary"
                >
                  <h2>{methods[current.method_family]}</h2>
                  <p>
                    {current.variables.length} 个变量 · {current.robustness.length} 项稳健性检查 ·{' '}
                    {current.permutation.n} 次置换
                  </p>
                  <p>{current.boundary_notes}</p>
                  {stage.editable && !running && llmOk && (
                    <button className="product-button is-quiet" onClick={() => draft.mutate()}>
                      按当前候选重新起草
                    </button>
                  )}
                </section>
                <section
                  className="panel scroll-region"
                  data-scroll-region=""
                  tabIndex={0}
                  id="plan-review"
                >
                  <h2>重点审阅</h2>
                  {current.variables
                    .filter((v) => v.uncertain)
                    .map((v) => (
                      <p key={v.name}>
                        <strong>待确认：{v.name}</strong> — {v.definition}
                      </p>
                    ))}
                  {!current.variables.some((v) => v.uncertain) && (
                    <p>未标记含义不确定的变量，仍需检查下列识别假设。</p>
                  )}
                  <ul>
                    {current.model.identification_assumptions.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                  <p>
                    处理是否为真实分配：
                    <strong>
                      {current.treatment_is_real_assignment ? '已由用户标记为是' : '否 / 尚未核实'}
                    </strong>
                    {current.treatment_semantics && (
                      <span className="muted">
                        {' '}
                        · 绑定字段语义：
                        {semanticsLabels[current.treatment_semantics] ||
                          current.treatment_semantics}
                      </span>
                    )}
                  </p>
                  {peer && current.treatment_is_real_assignment && (
                    <p className="error">
                      冲突：处理变量绑定的字段是“同群 /
                      暴露”变量，并非真实分配，结论最高只能到“关联”。请新建版本并取消该勾选。
                    </p>
                  )}
                </section>
              </div>
              <div className="plan-editor-wrap fill" hidden={sec === 'summary'}>
                <PlanEditor
                  section={sec}
                  key={current.id + JSON.stringify(current)}
                  plan={current}
                  onDirty={setDirty}
                  onSaved={(p) => {
                    setVersion(p.id)
                    refresh()
                  }}
                />
              </div>
            </div>
          </div>
        </>
      )}
    </>
  )
}
