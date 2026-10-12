import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, body } from '../api/client'
import { type StudyPlan, methods } from '../api/plans'
import { ErrorNote, ProjectBack } from '../components/Shared'
import PlanEditor from '../components/PlanEditor'
import JobProgress from '../components/JobProgress'
import type { Job } from '../components/JobProgress'
export default function Plan() {
  const { id } = useParams(),
    qc = useQueryClient(),
    [version, setVersion] = useState(''),
    [job, setJob] = useState(''),
    [confirming, setConfirming] = useState(false),
    [dirty, setDirty] = useState(false)
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
      setConfirming(false)
      refresh()
    },
  })
  return (
    <>
      <ProjectBack />
      <div className="page-heading">
        <div>
          <p className="eyebrow">第四阶段 / 把问题写成可检验的方案</p>
          <h1>研究方案</h1>
        </div>
        <button
          disabled={
            draft.isPending || tasks.data?.some((j) => ['running', 'queued'].includes(j.status))
          }
          onClick={() => draft.mutate()}
        >
          {plans.data?.length ? '重新起草方案' : '起草研究方案'}
        </button>
      </div>
      <ErrorNote error={plans.error || tasks.error || draft.error || action.error} />
      {activeJob && <JobProgress id={activeJob} onComplete={refresh} />}
      {plans.isPending ? (
        <p>正在读取方案…</p>
      ) : !current ? (
        <section className="panel">
          <h2>先选定一个研究问题</h2>
          <p>选择候选后，可生成变量、模型、稳健性与决策规则，再逐项审阅确认。</p>
          <Link to={`/p/${id}/candidates`}>前往选择候选 →</Link>
        </section>
      ) : (
        <>
          <label>
            方案版本
            <select value={current.id} onChange={(e) => setVersion(e.target.value)}>
              {plans.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  第 {p.version} 版 ·{' '}
                  {p.status === 'draft'
                    ? '草稿'
                    : p.status === 'confirmed'
                      ? '已确认'
                      : '已有更新版'}
                  {p.stale ? ' · 已过期' : ''}
                </option>
              ))}
            </select>
          </label>
          {current.stale && (
            <p className="notice">
              方向或候选已变更，此方案已过期。原内容保留，请根据当前候选重新起草。
            </p>
          )}
          <section className="panel">
            <h2>{methods[current.method_family]}</h2>
            <p>
              {current.variables.length} 个变量 · {current.robustness.length} 项稳健性检查 ·{' '}
              {current.permutation.n} 次置换
            </p>
            <p>{current.boundary_notes}</p>
            <div className="actions">
              {current.status === 'draft' ? (
                <button
                  disabled={current.stale || action.isPending || dirty}
                  onClick={() => setConfirming(true)}
                >
                  确认并锁定方案
                </button>
              ) : (
                <button
                  disabled={action.isPending || current.stale}
                  onClick={() => action.mutate('new-version')}
                >
                  新建版本
                </button>
              )}
              {current.status === 'confirmed' && <Link to={`/p/${id}/data`}>导入与绑定数据 →</Link>}
            </div>
          </section>
          {dirty && <p className="notice">有尚未保存的编辑，请先保存草稿再确认。</p>}
          <section className="panel">
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
            </p>
          </section>
          <PlanEditor
            key={current.id + JSON.stringify(current)}
            plan={current}
            onDirty={setDirty}
            onSaved={(p) => {
              setVersion(p.id)
              refresh()
            }}
          />
          {confirming && (
            <div className="modal-backdrop">
              <section className="modal" role="dialog" aria-label="确认研究方案">
                <h2>锁定当前已保存的方案</h2>
                <p>
                  请先保存所有编辑。确认后将按本版本的变量与决策阈值执行；后续修改需要新建版本。
                </p>
                <p>
                  尚有 {current.variables.filter((v) => v.uncertain).length}{' '}
                  个含义待确认的变量。该标记会保留。
                </p>
                <ErrorNote error={action.error} />
                <div className="actions">
                  <button className="secondary" onClick={() => setConfirming(false)}>
                    返回审阅
                  </button>
                  <button disabled={action.isPending} onClick={() => action.mutate('confirm')}>
                    确认锁定
                  </button>
                </div>
              </section>
            </div>
          )}
        </>
      )}
    </>
  )
}
