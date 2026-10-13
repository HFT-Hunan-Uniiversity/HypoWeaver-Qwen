import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api, body } from '../api/client'
import { type StudyPlan, methods, roles, robustKinds } from '../api/plans'
import { ErrorNote } from './Shared'
export const sectionTitles: Record<string, string> = {
  variables: '方法与变量',
  model: '模型与识别',
  robustness: '稳健性检查',
  rules: '置换与决策规则',
  claims: '计划结论与边界',
}
/** section 为空时显示全部分节；否则只显示当前节（其余节保持挂载，编辑不丢失） */
export default function PlanEditor({
  plan,
  onSaved,
  onDirty,
  section,
}: {
  plan: StudyPlan
  onSaved: (p: StudyPlan) => void
  onDirty: (dirty: boolean) => void
  section?: string
}) {
  const [draft, setDraft] = useState(plan),
    locked = plan.status !== 'draft'
  useEffect(() => onDirty(JSON.stringify(draft) !== JSON.stringify(plan)), [draft, plan, onDirty])
  const save = useMutation({
    mutationFn: () => api<StudyPlan>(`/plans/${plan.id}`, body('PATCH', draft)),
    onSuccess: onSaved,
  })
  // 自动保存草稿：停止编辑 0.8 秒后写入（不再有"保存方案草稿"按钮）
  const dirty = JSON.stringify(draft) !== JSON.stringify(plan)
  useEffect(() => {
    if (!dirty || locked || plan.stale) return
    const t = setTimeout(() => save.mutate(), 800)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, dirty, locked, plan.stale])
  const numbers = (text: string) =>
    text
      .split(/[,，\s]+/)
      .filter(Boolean)
      .map(Number)
  return (
    <form
      className="panel form plan-form"
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate()
      }}
    >
      <h2>{section ? sectionTitles[section] || '完整方案' : '完整方案'}</h2>
      <fieldset
        className="scroll-region plan-fieldset"
        data-scroll-region=""
        tabIndex={0}
        aria-label="方案编辑"
        disabled={locked || plan.stale}
      >
        <div className="plan-sec plan-sec--variables" hidden={!!section && section !== 'variables'}>
          <label>
            方法类别
            <select
              value={draft.method_family}
              onChange={(e) => setDraft({ ...draft, method_family: e.target.value })}
            >
              {Object.entries(methods).map(([k, v]) => (
                <option value={k} key={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          <h3>变量与定义</h3>
          {draft.variables.map((v, i) => (
            <div className="editor-row" key={i}>
              <label>
                角色
                <select
                  value={v.role}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      variables: draft.variables.map((x, j) =>
                        i === j ? { ...x, role: e.target.value } : x,
                      ),
                    })
                  }
                >
                  {Object.entries(roles).map(([k, v]) => (
                    <option value={k} key={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                变量名（英文）
                <input
                  required
                  value={v.name}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      variables: draft.variables.map((x, j) =>
                        i === j ? { ...x, name: e.target.value } : x,
                      ),
                    })
                  }
                />
              </label>
              <label>
                含义
                <textarea
                  required
                  value={v.definition}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      variables: draft.variables.map((x, j) =>
                        i === j ? { ...x, definition: e.target.value } : x,
                      ),
                    })
                  }
                />
              </label>
              <label className="check">
                <input
                  type="checkbox"
                  checked={v.uncertain}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      variables: draft.variables.map((x, j) =>
                        i === j ? { ...x, uncertain: e.target.checked } : x,
                      ),
                    })
                  }
                />
                含义待确认
              </label>
              <button
                type="button"
                className="secondary"
                onClick={() =>
                  setDraft({ ...draft, variables: draft.variables.filter((_, j) => i !== j) })
                }
              >
                移除此变量
              </button>
            </div>
          ))}
          <button
            type="button"
            className="secondary"
            onClick={() =>
              setDraft({
                ...draft,
                variables: [
                  ...draft.variables,
                  { role: 'control', name: '', definition: '', uncertain: true },
                ],
              })
            }
          >
            添加变量
          </button>
        </div>
        <div className="plan-sec plan-sec--model" hidden={!!section && section !== 'model'}>
          <h3>模型与识别</h3>
          {['unit', 'time'].map((x) => (
            <label className="check" key={x}>
              <input
                type="checkbox"
                checked={draft.model.fixed_effects.includes(x)}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    model: {
                      ...draft.model,
                      fixed_effects: e.target.checked
                        ? [...draft.model.fixed_effects, x]
                        : draft.model.fixed_effects.filter((v) => v !== x),
                    },
                  })
                }
              />
              {x === 'unit' ? '个体' : '时间'}固定效应
            </label>
          ))}
          <label>
            聚类层级（unit、time 或数据字段名）
            <input
              required
              value={draft.model.cluster}
              onChange={(e) =>
                setDraft({ ...draft, model: { ...draft.model, cluster: e.target.value } })
              }
            />
          </label>
          <label>
            识别假设（每行一项）
            <textarea
              value={draft.model.identification_assumptions.join('\n')}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  model: { ...draft.model, identification_assumptions: e.target.value.split('\n') },
                })
              }
            />
          </label>
          <div className="two-columns">
            <label>
              事件窗口左端
              <input
                type="number"
                max={-2}
                value={draft.model.event_window[0]}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    model: {
                      ...draft.model,
                      event_window: [+e.target.value, draft.model.event_window[1]],
                    },
                  })
                }
              />
            </label>
            <label>
              事件窗口右端
              <input
                type="number"
                min={0}
                value={draft.model.event_window[1]}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    model: {
                      ...draft.model,
                      event_window: [draft.model.event_window[0], +e.target.value],
                    },
                  })
                }
              />
            </label>
          </div>
          <label>
            事件分箱（逗号分隔，省略基期 -1）
            <input
              key={plan.id + 'bins'}
              defaultValue={draft.model.bins.join(', ')}
              onBlur={(e) =>
                setDraft({ ...draft, model: { ...draft.model, bins: numbers(e.target.value) } })
              }
            />
          </label>
        </div>
        <div
          className="plan-sec plan-sec--robustness"
          hidden={!!section && section !== 'robustness'}
        >
          <h3>稳健性检查</h3>
          {draft.robustness.map((r, i) => (
            <div className="editor-row" key={i}>
              <label>
                说明
                <input
                  required
                  value={r.change}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      robustness: draft.robustness.map((x, j) =>
                        i === j ? { ...x, change: e.target.value } : x,
                      ),
                    })
                  }
                />
              </label>
              <label>
                检查类型
                <select
                  value={r.kind}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      robustness: draft.robustness.map((x, j) =>
                        i === j ? { ...x, kind: e.target.value, args: {} } : x,
                      ),
                    })
                  }
                >
                  {Object.entries(robustKinds).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>
              {['exclude_years', 'alt_outcome', 'add_controls'].includes(r.kind) && (
                <label>
                  {r.kind === 'exclude_years'
                    ? '剔除年份（逗号分隔）'
                    : r.kind === 'alt_outcome'
                      ? '替代结果字段或公式'
                      : '增加控制字段或公式（每行一项）'}
                  <textarea
                    value={
                      r.kind === 'exclude_years'
                        ? (r.args.years || []).join(', ')
                        : r.kind === 'alt_outcome'
                          ? r.args.outcome || ''
                          : (r.args.controls || []).join('\n')
                    }
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        robustness: draft.robustness.map((x, j) =>
                          i === j
                            ? {
                                ...x,
                                args:
                                  r.kind === 'exclude_years'
                                    ? { years: numbers(e.target.value) }
                                    : r.kind === 'alt_outcome'
                                      ? { outcome: e.target.value }
                                      : { controls: e.target.value.split('\n') },
                              }
                            : x,
                        ),
                      })
                    }
                  />
                </label>
              )}
              <button
                type="button"
                className="secondary"
                onClick={() =>
                  setDraft({ ...draft, robustness: draft.robustness.filter((_, j) => i !== j) })
                }
              >
                移除此检查
              </button>
            </div>
          ))}
          <button
            type="button"
            className="secondary"
            onClick={() =>
              setDraft({
                ...draft,
                robustness: [
                  ...draft.robustness,
                  { id: crypto.randomUUID(), change: '', kind: 'drop_controls', args: {} },
                ],
              })
            }
          >
            添加稳健性检查
          </button>
        </div>
        <div className="plan-sec plan-sec--rules" hidden={!!section && section !== 'rules'}>
          <h3>置换与决策规则</h3>
          <div className="two-columns">
            <label>
              置换次数
              <input
                type="number"
                min={19}
                max={1999}
                value={draft.permutation.n}
                onChange={(e) =>
                  setDraft({ ...draft, permutation: { ...draft.permutation, n: +e.target.value } })
                }
              />
            </label>
            <label>
              随机种子
              <input
                type="number"
                min={0}
                value={draft.permutation.seed}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    permutation: { ...draft.permutation, seed: +e.target.value },
                  })
                }
              />
            </label>
          </div>
          <label>
            预期方向
            <select
              value={draft.decision_rules.expected_sign}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  decision_rules: { ...draft.decision_rules, expected_sign: +e.target.value },
                })
              }
            >
              <option value={1}>正向</option>
              <option value={-1}>负向</option>
            </select>
          </label>
          {(['alpha', 'pretrend_alpha', 'robustness_share', 'permutation_alpha'] as const).map(
            (key, i) => (
              <label key={key}>
                {['主系数显著性阈值', '前趋势检验阈值', '稳健性同向比例下限', '置换显著性阈值'][i]}
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  max={key === 'robustness_share' ? 1 : 0.99}
                  value={draft.decision_rules[key]}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      decision_rules: { ...draft.decision_rules, [key]: +e.target.value },
                    })
                  }
                />
              </label>
            ),
          )}
        </div>
        <div className="plan-sec plan-sec--claims" hidden={!!section && section !== 'claims'}>
          <h3>计划结论与边界</h3>
          {draft.claims_planned.map((c, i) => (
            <div className="editor-row" key={i}>
              <label>
                待检验陈述
                <textarea
                  required
                  value={c.text}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      claims_planned: draft.claims_planned.map((x, j) =>
                        i === j ? { ...x, text: e.target.value } : x,
                      ),
                    })
                  }
                />
              </label>
              <label>
                类别
                <select
                  value={c.type}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      claims_planned: draft.claims_planned.map((x, j) =>
                        i === j ? { ...x, type: e.target.value } : x,
                      ),
                    })
                  }
                >
                  <option value="main">主结论</option>
                  <option value="mechanism">机制线索</option>
                  <option value="boundary">边界线索</option>
                </select>
              </label>
              <button
                type="button"
                className="secondary"
                onClick={() =>
                  setDraft({
                    ...draft,
                    claims_planned: draft.claims_planned.filter((_, j) => i !== j),
                  })
                }
              >
                移除此陈述
              </button>
            </div>
          ))}
          <button
            type="button"
            className="secondary"
            onClick={() =>
              setDraft({
                ...draft,
                claims_planned: [
                  ...draft.claims_planned,
                  { id: crypto.randomUUID(), text: '', type: 'main' },
                ],
              })
            }
          >
            添加计划结论
          </button>
          <label>
            边界说明
            <textarea
              required
              rows={4}
              value={draft.boundary_notes}
              onChange={(e) => setDraft({ ...draft, boundary_notes: e.target.value })}
            />
          </label>
          <label className="check">
            <input
              type="checkbox"
              disabled={
                plan.treatment_semantics === 'peer_exposure' && !draft.treatment_is_real_assignment
              }
              checked={draft.treatment_is_real_assignment}
              onChange={(e) =>
                setDraft({ ...draft, treatment_is_real_assignment: e.target.checked })
              }
            />
            我已核实：处理变量代表真实的处理分配
          </label>
          <p className="muted">
            行业同群暴露不代表企业实际被纳入政策。此项为否时，最高只能报告关联。
          </p>
          {plan.treatment_semantics === 'peer_exposure' && (
            <p className={draft.treatment_is_real_assignment ? 'error' : 'notice'}>
              处理变量绑定的字段在数据档案中标记为“同群 / 暴露”，不能勾选为真实分配
              {draft.treatment_is_real_assignment ? '：当前勾选与字段语义冲突，请取消。' : '。'}
            </p>
          )}
        </div>
      </fieldset>
      <ErrorNote error={save.error} />
      {!locked && !plan.stale && (
        <p className="muted">{save.isPending ? '正在自动保存…' : '编辑会自动保存为草稿。'}</p>
      )}
      {locked && (
        <p className="muted">
          已确认锁定。要修改请点页头的"修改此阶段"，会生成新版本；既有版本保留。
        </p>
      )}
    </form>
  )
}
