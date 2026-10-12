import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, body } from '../api/client'
import type { Inspection, Source } from '../api/datasets'
import { ErrorNote } from './Shared'
export default function DatasetImport({
  projectId,
  onStart,
}: {
  projectId: string
  onStart: (job: string) => void
}) {
  const qc = useQueryClient(),
    uploads = useQuery({
      queryKey: ['dataset-uploads'],
      queryFn: () => api<Inspection[]>('/dataset-uploads'),
    })
  const reuse = (d: Inspection) => {
    setInfo(d)
    setName(d.name)
    setColumns(
      d.columns.length <= 30
        ? d.columns.map((c) => c.name)
        : d.columns.slice(0, 10).map((c) => c.name),
    )
    setUnit('')
    setTime('')
  }
  const file = useRef<HTMLInputElement>(null),
    [info, setInfo] = useState<Inspection | null>(null),
    [columns, setColumns] = useState<string[]>([]),
    [name, setName] = useState(''),
    [filter, setFilter] = useState(''),
    [unit, setUnit] = useState(''),
    [time, setTime] = useState(''),
    [source, setSource] = useState<Source>({ url: '', doi: '', license: '', citation: '' })
  const inspect = useMutation({
    mutationFn: async (f: File) => {
      const form = new FormData()
      form.append('file', f)
      return api<Inspection>('/datasets:inspect', { method: 'POST', body: form })
    },
    onSuccess: (d) => {
      reuse(d)
      qc.invalidateQueries({ queryKey: ['dataset-uploads'] })
    },
  })
  const sheet = useMutation({
    mutationFn: (s: string) =>
      api<Inspection>(`/dataset-uploads/${info!.upload_id}?sheet=${encodeURIComponent(s)}`),
    onSuccess: (d) => {
      setInfo(d)
      setColumns(d.columns.slice(0, 30).map((c) => c.name))
      setUnit('')
      setTime('')
    },
  })
  const importData = useMutation({
    mutationFn: () =>
      api<{ job_id: string }>(
        '/datasets',
        body('POST', {
          upload_id: info!.upload_id,
          project_id: projectId,
          name,
          columns,
          sheet: info!.sheet,
          source,
          unit: unit || null,
          time: time || null,
        }),
      ),
    onSuccess: (d) => {
      onStart(d.job_id)
      setInfo(null)
      if (file.current) file.current.value = ''
    },
  })
  return (
    <details className="panel" open={!info ? undefined : true}>
      <summary>导入 CSV、Excel 或 Stata 数据</summary>
      <div className="form">
        <p className="muted">
          先读取字段清单，再选择实际需要的列。单个文件上限 500 MB，最多导入 300 列、200
          万行；大文件优先使用 Stata 按列读取。
        </p>
        <label>
          选择本地数据文件
          <input
            ref={file}
            type="file"
            accept=".csv,.xlsx,.dta"
            disabled={inspect.isPending || importData.isPending}
            onChange={(e) => {
              if (e.target.files?.[0]) inspect.mutate(e.target.files[0])
            }}
          />
        </label>
        {!!uploads.data?.length && (
          <label>
            复用已上传文件
            <select
              value={info?.upload_id || ''}
              onChange={(e) => {
                const previous = uploads.data?.find((u) => u.upload_id === e.target.value)
                if (previous) reuse(previous)
              }}
            >
              <option value="">选择已有文件，避免重复上传</option>
              {uploads.data?.map((u) => (
                <option value={u.upload_id} key={u.upload_id}>
                  {u.name}
                </option>
              ))}
            </select>
          </label>
        )}
        {inspect.isPending && <p role="status">正在上传并读取列名与标签…</p>}
        <ErrorNote error={inspect.error || sheet.error || importData.error} />
        {info && (
          <>
            <label>
              资产名称
              <input required value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            {info.sheets.length > 0 && (
              <label>
                工作表
                <select
                  value={info.sheet || ''}
                  disabled={sheet.isPending}
                  onChange={(e) => sheet.mutate(e.target.value)}
                >
                  {info.sheets.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </label>
            )}
            <h3>
              选择列（已选 {columns.length} / 共 {info.columns.length}）
            </h3>
            <label>
              筛选列名或标签
              <input
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="例如：green、Size、企业代码"
              />
            </label>
            <div className="actions">
              <button
                className="secondary"
                disabled={info.columns.length > 300}
                onClick={() => setColumns(info.columns.map((c) => c.name))}
              >
                全选
              </button>
              <button className="secondary" onClick={() => setColumns([])}>
                清空选择
              </button>
            </div>
            <div className="column-picker">
              {info.columns
                .filter((c) =>
                  (c.name + ' ' + c.label).toLowerCase().includes(filter.toLowerCase()),
                )
                .map((c) => (
                  <label className="check" key={c.name}>
                    <input
                      type="checkbox"
                      checked={columns.includes(c.name)}
                      disabled={!columns.includes(c.name) && columns.length >= 300}
                      onChange={(e) =>
                        setColumns(
                          e.target.checked
                            ? [...columns, c.name]
                            : columns.filter((x) => x !== c.name),
                        )
                      }
                    />
                    <span>
                      <strong>{c.name}</strong>
                      {c.label && <small> · {c.label}</small>}
                    </span>
                  </label>
                ))}
            </div>
            <div className="two-columns">
              <label>
                个体字段
                <select value={unit} onChange={(e) => setUnit(e.target.value)}>
                  <option value="">自动识别</option>
                  {columns.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </label>
              <label>
                时间字段
                <select value={time} onChange={(e) => setTime(e.target.value)}>
                  <option value="">自动识别</option>
                  {columns.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </label>
            </div>
            {(['url', 'doi', 'license', 'citation'] as const).map((k, i) => (
              <label key={k}>
                {['来源网址', '数据 DOI', '许可', '引用说明'][i]}
                <input
                  value={source[k]}
                  onChange={(e) => setSource({ ...source, [k]: e.target.value })}
                />
              </label>
            ))}
            <button
              disabled={importData.isPending || sheet.isPending || !columns.length || !name.trim()}
              onClick={() => importData.mutate()}
            >
              确认导入所选列
            </button>
          </>
        )}
      </div>
    </details>
  )
}
