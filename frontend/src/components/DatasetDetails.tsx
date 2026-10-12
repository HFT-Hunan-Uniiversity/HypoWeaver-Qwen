import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
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
  const panel = dataset.panel
  return (
    <>
      <section className="panel">
        <p className="eyebrow">数据资产</p>
        <h2>{dataset.name}</h2>
        <p>
          <strong>{dataset.n_rows.toLocaleString()}</strong> 行 · <strong>{dataset.n_cols}</strong>{' '}
          列 · {(dataset.size_bytes / 1024 ** 2).toFixed(2)} MB
        </p>
        {panel.detected ? (
          <>
            <h3>
              {panel.unit} × {panel.time} 面板
            </h3>
            <p>
              {panel.n_units?.toLocaleString()} 个个体 · {panel.n_periods} 期 ·{' '}
              {panel.balanced ? '平衡' : '非平衡'}面板 · 重复个体—时间记录 {panel.duplicates} 行
            </p>
            <p>
              时间范围：{panel.time_min} — {panel.time_max}；缺失面板键 {panel.missing_keys} 行
            </p>
          </>
        ) : (
          <p className="notice">尚未识别完整的个体和时间字段，后续变量绑定中仍可指定。</p>
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
      <section className="panel">
        <h2>字段档案</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>字段 / 标签</th>
                <th>类型</th>
                <th>缺失率</th>
                <th>唯一值</th>
                <th>范围</th>
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}
