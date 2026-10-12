import { ScrollRegion } from './shell/ShellContext'
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { levelLabels, semanticsLabels } from '../api/plans'
import { api, body } from '../api/client'
import type { Dataset } from '../api/datasets'
import { ErrorNote } from './Shared'
export default function DatasetDetails({
  dataset,
  onSaved,
}: {
  dataset: Dataset
  onSaved: () => void
}) {
  const [source, setSource] = useState(dataset.source),
    [name, setName] = useState(dataset.name),
    [saved, setSaved] = useState(false)
  const save = useMutation({
    mutationFn: () => api(`/datasets/${dataset.id}`, body('PATCH', { name, source })),
    onSuccess: () => {
      setSaved(true)
      onSaved()
    },
  })
  const qc = useQueryClient()
  const hasSemantics = dataset.profile.some((p) => 'semantics' in p || 'level' in p)
  const field = useMutation({
    mutationFn: (v: { name: string; semantics?: string; level?: string }) =>
      api(
        `/datasets/${dataset.id}/fields/${encodeURIComponent(v.name)}`,
        body('PATCH', { semantics: v.semantics, level: v.level }),
      ),
    onSuccess: () => {
      // 字段语义影响结论上限：刷新数据、方案、运行、结论、提案与阶段过期状态
      for (const k of ['datasets', 'overview', 'plans', 'runs', 'claims', 'proposals', 'readiness'])
        qc.invalidateQueries({ queryKey: [k] })
      onSaved()
    },
  })
  const panel = dataset.panel
  return (
    <>
      <section className="info-strip" aria-label="数据资产概况">
        <div>
          <span>数据资产</span>
          <strong>{dataset.name}</strong>
        </div>
        <div>
          <span>规模</span>
          <strong>
            {dataset.n_rows.toLocaleString()} 行 · {dataset.n_cols} 列 ·{' '}
            {(dataset.size_bytes / 1024 ** 2).toFixed(2)} MB
          </strong>
        </div>
        {panel.detected ? (
          <>
            <div>
              <span>面板结构</span>
              <strong>
                {panel.unit} × {panel.time} · {panel.n_units?.toLocaleString()} 个体 ·{' '}
                {panel.n_periods} 期 · {panel.balanced ? '平衡' : '非平衡'}
              </strong>
            </div>
            <div>
              <span>时间范围</span>
              <strong>
                {panel.time_min} — {panel.time_max}
              </strong>
            </div>
            <div>
              <span>重复 / 缺失键</span>
              <strong>
                {panel.duplicates} / {panel.missing_keys} 行
              </strong>
            </div>
          </>
        ) : (
          <div>
            <span>面板结构</span>
            <strong>尚未识别完整的个体和时间字段，可在变量绑定中指定</strong>
          </div>
        )}
      </section>
      <details className="panel">
        <summary>来源、许可与引用说明</summary>
        <form
          className="form"
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate()
          }}
        >
          <label>
            名称
            <input
              required
              value={name}
              onChange={(e) => {
                setName(e.target.value)
                setSaved(false)
              }}
            />
          </label>
          {(['url', 'doi', 'license', 'citation'] as const).map((k, i) => (
            <label key={k}>
              {['来源网址', '数据 DOI', '许可', '引用说明'][i]}
              <input
                value={source[k] || ''}
                onChange={(e) => {
                  setSource({ ...source, [k]: e.target.value })
                  setSaved(false)
                }}
              />
            </label>
          ))}
          <p className="muted">
            文件校验值：<code className="hash">{dataset.sha256}</code>
          </p>
          <ErrorNote error={save.error} />
          <div className="actions">
            <span role="status">{saved ? '已保存' : ''}</span>
            <button disabled={save.isPending}>保存元数据</button>
          </div>
        </form>
      </details>
      <section className="panel fill">
        <h2>字段档案</h2>
        <p className="muted">
          {hasSemantics
            ? '“语义”决定结论上限：同群 / 暴露变量最高只能报告关联。修改后，依赖该数据的方案、运行与提案将标记为过期。'
            : '字段语义与层级标注需要后端更新后才能编辑（R2-01）。'}
        </p>
        <ErrorNote error={field.error} />
        <ScrollRegion label="字段档案">
          <table>
            <thead>
              <tr>
                <th>字段 / 标签</th>
                <th>类型</th>
                <th>缺失率</th>
                <th>唯一值</th>
                <th>范围</th>
                <th>语义</th>
                <th>层级</th>
              </tr>
            </thead>
            <tbody>
              {dataset.profile.map((p) => (
                <tr key={p.name}>
                  <td>
                    <strong>{p.name}</strong>
                    <small>{p.label}</small>
                  </td>
                  <td>{p.type}</td>
                  <td>{(p.missing_rate * 100).toFixed(1)}%</td>
                  <td>{p.unique_count.toLocaleString()}</td>
                  <td>
                    {p.min === null
                      ? '—'
                      : `${p.min.toLocaleString()} — ${p.max?.toLocaleString()}`}
                  </td>
                  <td>
                    {hasSemantics ? (
                      <select
                        className="field-select"
                        aria-label={`${p.name} 语义`}
                        value={p.semantics || 'unknown'}
                        disabled={field.isPending}
                        onChange={(e) => field.mutate({ name: p.name, semantics: e.target.value })}
                      >
                        {Object.entries(semanticsLabels).map(([k, v]) => (
                          <option key={k} value={k}>
                            {v}
                          </option>
                        ))}
                      </select>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>
                    {hasSemantics ? (
                      <select
                        className="field-select"
                        aria-label={`${p.name} 层级`}
                        value={p.level || 'other'}
                        disabled={field.isPending}
                        onChange={(e) => field.mutate({ name: p.name, level: e.target.value })}
                      >
                        {Object.entries(levelLabels).map(([k, v]) => (
                          <option key={k} value={k}>
                            {v}
                          </option>
                        ))}
                      </select>
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollRegion>
      </section>
    </>
  )
}
