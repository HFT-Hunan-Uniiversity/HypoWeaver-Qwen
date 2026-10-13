import { ScrollRegion } from './shell/ShellContext'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, body } from '../api/client'
import type { Dataset } from '../api/datasets'
import { type StudyPlan, roles } from '../api/plans'
import { ErrorNote } from './Shared'
import { useLlm } from '../lib/llm'
interface Value {
  field?: string | null
  formula?: string | null
}
interface SavedBinding {
  dataset_id: string
  bindings: Record<string, Value>
  confirmed: boolean
  /** R5：从上一版方案继承时的源方案 id；继承绑定总是 confirmed=false */
  inherited_from?: string | null
  /** 后端给出的说明，例如“继承自 v1，请重新确认” */
  note?: string
  /** 真实保存的绑定才有；GET 在无绑定时会返回由 suggested_binding 拼出的预填对象（无此字段） */
  updated_at?: string
}
/** 方案的 suggested_binding 归一为 {field|formula}，丢弃空值 */
function normalizeSuggested(plan: StudyPlan): Record<string, Value> {
  const out: Record<string, Value> = {}
  const names = new Set(plan.variables.map((v) => v.name))
  for (const [k, v] of Object.entries(plan.suggested_binding || {})) {
    if (!names.has(k) || !v) continue
    if ('field' in v && v.field) out[k] = { field: v.field }
    else if ('formula' in v && v.formula) out[k] = { formula: v.formula }
  }
  return out
}
interface Suggestion extends Value {
  role_name: string
  confidence: number
  note: string
}
interface Readiness {
  status: string
  missing: string[]
  bound: string[]
  data_plan: string[]
  dataset_id?: string
  sample: null | {
    n_total: number
    n_valid: number
    dropped: number
    n_units: number
    n_periods: number
    treated_units: number | null
    control_units: number | null
    monotone_units: number | null
    reversal_transitions: number | null
    duplicates: number
    invalid_by_variable: Record<string, number>
    first_exposure: { year: number; count: number }[]
  }
}
/** 页面主按钮"确认数据绑定"调用的动作 */
export type ConfirmBinding = (() => void) | null
function Editor({
  plan,
  dataset,
  saved,
  registerConfirm,
}: {
  plan: StudyPlan
  dataset: Dataset
  saved: SavedBinding | null
  registerConfirm?: (fn: ConfirmBinding) => void
}) {
  // 无真实绑定时，后端 GET 会把 suggested_binding 包装成未确认绑定返回；视作建议而非已保存
  const isSuggestionOnly = !!saved && !saved.updated_at && !saved.inherited_from
  if (isSuggestionOnly) saved = null
  const base = saved?.dataset_id === dataset.id ? saved.bindings : {}
  // 方案自带建议：只预填尚未绑定的角色，不保存、不确认
  const planSuggested = Object.fromEntries(
    Object.entries(normalizeSuggested(plan)).filter(([k]) => !(base[k]?.field || base[k]?.formula)),
  )
  const qc = useQueryClient(),
    [mapping, setMapping] = useState<Record<string, Value>>({ ...base, ...planSuggested }),
    [suggestedKeys, setSuggestedKeys] = useState<Set<string>>(
      () => new Set(Object.keys(planSuggested)),
    ),
    [confirmed, setConfirmed] = useState(saved?.dataset_id === dataset.id && saved.confirmed),
    [suggestions, setSuggestions] = useState<Suggestion[]>([]),
    [dirty, setDirty] = useState(Object.keys(planSuggested).length > 0)
  const llmOk = useLlm().data?.configured !== false
  const pendingReconfirm = !!saved && saved.dataset_id === dataset.id && !saved.confirmed
  const readiness = useQuery({
    queryKey: ['readiness', plan.id],
    queryFn: () => api<Readiness>(`/plans/${plan.id}/readiness`),
  })
  const save = useMutation({
    mutationFn: (asConfirmed: boolean) =>
      api(
        `/plans/${plan.id}/bindings`,
        body('PUT', {
          dataset_id: dataset.id,
          bindings: Object.fromEntries(
            Object.entries(mapping).filter(([, v]) => v.field || v.formula),
          ),
          confirmed: asConfirmed,
        }),
      ),
    onSuccess: (_, asConfirmed) => {
      setDirty(false)
      setConfirmed(asConfirmed)
      qc.invalidateQueries({ queryKey: ['overview'] })
      qc.invalidateQueries({ queryKey: ['bindings', plan.id] })
      qc.invalidateQueries({ queryKey: ['readiness', plan.id] })
    },
  })
  // 一键确认：沿用现有 PUT /plans/{id}/bindings，原样提交已保存绑定并置 confirmed=true
  const reconfirm = useMutation({
    mutationFn: () =>
      api(
        `/plans/${plan.id}/bindings`,
        body('PUT', { dataset_id: saved!.dataset_id, bindings: saved!.bindings, confirmed: true }),
      ),
    onSuccess: () => {
      setConfirmed(true)
      setDirty(false)
      qc.invalidateQueries({ queryKey: ['bindings', plan.id] })
      qc.invalidateQueries({ queryKey: ['readiness', plan.id] })
      qc.invalidateQueries({ queryKey: ['overview'] })
    },
  })
  // 草稿自动保存（未确认）；确认由页头主按钮触发
  useEffect(() => {
    if (!dirty || plan.stale || plan.status !== 'confirmed') return
    const t = setTimeout(() => save.mutate(false), 900)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapping, dirty])
  useEffect(() => {
    registerConfirm?.(plan.stale || plan.status !== 'confirmed' ? null : () => save.mutate(true))
    return () => registerConfirm?.(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapping, plan.id, plan.stale])
  const suggest = useMutation({
    mutationFn: () =>
      api<{ bindings: Suggestion[] }>(
        `/plans/${plan.id}/bindings:suggest`,
        body('POST', { dataset_id: dataset.id }),
      ),
    onSuccess: (d) => {
      setSuggestions(d.bindings)
      setMapping(
        Object.fromEntries(
          d.bindings.map((x) => [x.role_name, { field: x.field, formula: x.formula }]),
        ),
      )
      setConfirmed(false)
      setDirty(true)
    },
  })
  const change = (name: string, value: Value) => {
    setMapping({ ...mapping, [name]: value })
    if (suggestedKeys.has(name)) {
      const n = new Set(suggestedKeys)
      n.delete(name)
      setSuggestedKeys(n)
    }
    setConfirmed(false)
    setDirty(true)
  }
  const ready = readiness.data,
    showSample = ready?.dataset_id === dataset.id && !dirty
  return (
    <div className="binding-grid fill">
      <section className="panel form fill binding-panel">
        <div className="binding-head">
          <div>
            <h2>变量绑定</h2>
            <span className="inline-meta">
              方案第 {plan.version} 版 · {dataset.name}
            </span>
            {pendingReconfirm && (
              <span
                className="status-badge is-yellow"
                title={
                  saved?.note ||
                  (saved?.inherited_from ? '绑定继承自上一版方案' : '已保存的绑定尚未确认')
                }
              >
                {saved?.inherited_from ? '待重新确认' : '待确认'}
              </span>
            )}
          </div>
          {llmOk && (
            <span className="action-cluster">
              <button
                className="secondary"
                disabled={suggest.isPending}
                onClick={() => suggest.mutate()}
              >
                {suggest.isPending ? '正在建议…' : '让模型建议绑定'}
              </button>
            </span>
          )}
        </div>
        <p className="muted binding-hint">
          支持
          log、log1p、加减乘除。字段含义需人工核对；无定义的对数或除法记为缺失并从有效样本排除。
        </p>
        {plan.stale && <p className="notice">方案已过期，请先返回方案页重新起草。</p>}
        {saved && saved.dataset_id !== dataset.id && (
          <p className="notice">
            当前选择与已保存绑定的数据资产不同，保存后会替换绑定并让既有运行过期。
          </p>
        )}
        {pendingReconfirm && (
          <div className="notice binding-reconfirm" role="status">
            <span>
              {saved?.inherited_from
                ? `${saved.note || '此绑定继承自上一版方案'}。字段映射已带入，核对无误后点右上角「确认数据绑定」。`
                : '已保存的绑定尚未确认，核对后点右上角「确认数据绑定」。'}
            </span>
          </div>
        )}
        {suggestedKeys.size > 0 && (
          <p className="notice" role="status">
            已按方案建议预填 {suggestedKeys.size} 个变量（标注“建议”），尚未保存或确认。
          </p>
        )}
        <ErrorNote error={reconfirm.error} />
        <ScrollRegion className="binding-rows" label="变量绑定表">
          <div className="binding-row binding-row--head" aria-hidden="true">
            <span>变量</span>
            <span>绑定方式</span>
            <span>字段 / 公式</span>
          </div>
          {plan.variables.map((v) => {
            const value = mapping[v.name] || {},
              mode = value.formula !== undefined && value.formula !== null ? 'formula' : 'field',
              s = suggestions.find((x) => x.role_name === v.name)
            return (
              <div className="binding-row" key={v.name}>
                <div className="binding-row__var">
                  <strong>
                    {roles[v.role]} · {v.name}
                    {suggestedKeys.has(v.name) && (
                      <span className="tag-suggested" title="来自方案的建议绑定，尚未保存">
                        建议
                      </span>
                    )}
                  </strong>
                  <small className="muted" title={v.definition}>
                    {v.definition}
                    {v.uncertain ? '（含义待确认）' : ''}
                  </small>
                </div>
                <label>
                  绑定方式
                  <select
                    aria-label={`${v.name} 绑定方式`}
                    value={mode}
                    onChange={(e) =>
                      change(v.name, e.target.value === 'formula' ? { formula: '' } : { field: '' })
                    }
                  >
                    <option value="field">数据字段</option>
                    {!['unit', 'time'].includes(v.role) && (
                      <option value="formula">派生公式</option>
                    )}
                  </select>
                </label>
                {mode === 'field' ? (
                  <label>
                    字段
                    <select
                      aria-label={`${v.name} 字段`}
                      value={value.field || ''}
                      onChange={(e) => change(v.name, { field: e.target.value })}
                    >
                      <option value="">请选择字段</option>
                      {dataset.profile.map((p) => (
                        <option key={p.name} value={p.name}>
                          {p.name}
                          {p.label ? ` · ${p.label}` : ''}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : (
                  <label>
                    公式
                    <input
                      aria-label={`${v.name} 公式`}
                      value={value.formula || ''}
                      onChange={(e) => change(v.name, { formula: e.target.value })}
                      placeholder="例如：log1p(a + b)"
                    />
                  </label>
                )}
                {s && (
                  <p className="muted binding-row__note">
                    建议置信度 {(s.confidence * 100).toFixed(0)}% · {s.note}
                  </p>
                )}
              </div>
            )
          })}
        </ScrollRegion>
        <div className="binding-foot">
          <span className={`status-badge is-${confirmed && !dirty ? 'green' : 'yellow'}`}>
            {confirmed && !dirty ? '绑定已确认' : '待确认'}
          </span>
          <span className="muted">
            {save.isPending
              ? '正在自动保存…'
              : dirty
                ? '编辑会自动保存为未确认草稿'
                : '核对字段含义与公式后，点右上角「确认数据绑定」'}
          </span>
          <ErrorNote error={save.error || suggest.error} />
        </div>
      </section>
      <section className="panel fill">
        <h2>数据就绪检查</h2>
        <ScrollRegion label="数据就绪检查">
          <ErrorNote error={readiness.error} />
          {ready && (
            <>
              {showSample && ready.status === 'ready' ? (
                <p className="success">数据已就绪，可以开始检验。</p>
              ) : (
                <p className="notice">
                  {dirty
                    ? '请先保存当前编辑。'
                    : ready.dataset_id && ready.dataset_id !== dataset.id
                      ? '当前显示的数据尚未保存为本方案绑定。'
                      : '尚未就绪，按下列事项补充。'}
                </p>
              )}
              {ready.data_plan.length > 0 && (
                <>
                  <h3>待补数据计划</h3>
                  <ul>
                    {ready.data_plan.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                </>
              )}
              {showSample && ready.sample && (
                <>
                  <p>
                    有效样本 {ready.sample.n_valid.toLocaleString()} /{' '}
                    {ready.sample.n_total.toLocaleString()} 行；排除{' '}
                    {ready.sample.dropped.toLocaleString()} 行。
                  </p>
                  <p>
                    {ready.sample.n_units.toLocaleString()} 个个体 · {ready.sample.n_periods} 期 ·
                    重复键 {ready.sample.duplicates}
                  </p>
                  {ready.sample.treated_units !== null ? (
                    <>
                      <p>
                        曾暴露 {ready.sample.treated_units} 个体 · 从未暴露对照{' '}
                        {ready.sample.control_units} 个体
                      </p>
                      <p>
                        单调路径 {ready.sample.monotone_units} 个体 · 1→0 回退{' '}
                        {ready.sample.reversal_transitions} 次
                      </p>
                      <h3>首次暴露年份</h3>
                      <div className="cohort-list">
                        {ready.sample.first_exposure.map((c) => (
                          <span key={c.year}>
                            {c.year} 年 <strong>{c.count}</strong>
                          </span>
                        ))}
                      </div>
                    </>
                  ) : (
                    <p>解释变量非二元变量，不划分处理与对照组。</p>
                  )}
                  <details>
                    <summary>各变量缺失或无效值</summary>
                    <ul>
                      {Object.entries(ready.sample.invalid_by_variable).map(([k, n]) => (
                        <li key={k}>
                          {k}：{n} 行
                        </li>
                      ))}
                    </ul>
                  </details>
                </>
              )}
            </>
          )}
        </ScrollRegion>
      </section>
    </div>
  )
}
function BoundEditor({
  plan,
  dataset,
  registerConfirm,
}: {
  plan: StudyPlan
  dataset: Dataset
  registerConfirm?: (fn: ConfirmBinding) => void
}) {
  const saved = useQuery({
    queryKey: ['bindings', plan.id],
    queryFn: () => api<SavedBinding | null>(`/plans/${plan.id}/bindings`),
  })
  return (
    <>
      <ErrorNote error={saved.error} />
      {saved.isPending ? (
        <p>正在读取绑定…</p>
      ) : (
        !saved.error && (
          <Editor
            key={plan.id + dataset.id}
            plan={plan}
            dataset={dataset}
            saved={saved.data || null}
            registerConfirm={registerConfirm}
          />
        )
      )}
    </>
  )
}
export default function Bindings({
  projectId,
  dataset,
  registerConfirm,
}: {
  projectId: string
  dataset: Dataset
  registerConfirm?: (fn: ConfirmBinding) => void
}) {
  const [selected, setSelected] = useState('')
  const plans = useQuery({
    queryKey: ['plans', projectId],
    queryFn: () => api<StudyPlan[]>(`/projects/${projectId}/plans`),
  })
  const confirmed = plans.data?.filter((p) => p.status === 'confirmed') || [],
    plan = confirmed.find((p) => p.id === selected) || confirmed[0]
  return (
    <>
      <ErrorNote error={plans.error} />
      {plan ? (
        <>
          <label className="inline-select">
            绑定到研究方案
            <select value={plan.id} onChange={(e) => setSelected(e.target.value)}>
              {confirmed.map((p) => (
                <option key={p.id} value={p.id}>
                  第 {p.version} 版{p.stale ? ' · 已过期' : ''}
                </option>
              ))}
            </select>
          </label>
          <BoundEditor plan={plan} dataset={dataset} registerConfirm={registerConfirm} />
        </>
      ) : (
        <section className="panel">
          <h2>准备变量绑定</h2>
          <p>请先审阅并确认研究方案，随后可以在这里将变量绑定到当前数据。</p>
          <Link to={`/p/${projectId}/plan`}>前往研究方案 →</Link>
        </section>
      )}
    </>
  )
}
