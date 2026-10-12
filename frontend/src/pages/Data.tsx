import Bindings from '../components/Bindings'
import { useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Dataset } from '../api/datasets'
import DatasetImport from '../components/DatasetImport'
import DatasetDetails from '../components/DatasetDetails'
import JobProgress from '../components/JobProgress'
import type { Job } from '../components/JobProgress'
import { ErrorNote, ProjectBack } from '../components/Shared'
export default function Data() {
  const { id } = useParams(),
    qc = useQueryClient(),
    [params, setParams] = useSearchParams(),
    [job, setJob] = useState('')
  const datasets = useQuery({ queryKey: ['datasets'], queryFn: () => api<Dataset[]>('/datasets') })
  const tasks = useQuery({
    queryKey: ['dataset-tasks', id],
    queryFn: () => api<Job[]>(`/projects/${id}/jobs?kind=dataset`),
  })
  const current = datasets.data?.find((d) => d.id === params.get('dataset')) || datasets.data?.[0]
  const activeJob = job || tasks.data?.[0]?.id
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['datasets'] })
    qc.invalidateQueries({ queryKey: ['dataset-tasks', id] })
  }
  return (
    <>
      <ProjectBack />
      <p className="eyebrow">第五阶段 / 数据与检验</p>
      <h1>数据资产</h1>
      <p className="muted">数据资产可在项目之间复用。导入保留原始观测，变量变换在绑定阶段定义。</p>
      <DatasetImport
        projectId={id!}
        onStart={(j) => {
          setJob(j)
          refresh()
        }}
      />
      {activeJob && (
        <JobProgress
          id={activeJob}
          onComplete={(j) => {
            refresh()
            if (j.status === 'succeeded' && j.result?.dataset_id)
              setParams({ dataset: String(j.result.dataset_id) })
          }}
        />
      )}
      <ErrorNote error={datasets.error || tasks.error} />
      {datasets.isPending ? (
        <p>正在读取数据资产…</p>
      ) : !current ? (
        <section className="panel">
          <h2>等待你的研究数据</h2>
          <p>
            上传 CSV、Excel 或 Stata 文件，或按 README
            运行碳市场数据准备命令。尚无数据时仍可保留方案。
          </p>
        </section>
      ) : (
        <>
          <label>
            选择数据资产
            <select value={current.id} onChange={(e) => setParams({ dataset: e.target.value })}>
              {datasets.data?.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} · {d.n_rows.toLocaleString()} 行
                </option>
              ))}
            </select>
          </label>
          <Bindings projectId={id!} dataset={current} />
          <DatasetDetails key={current.id} dataset={current} onSaved={refresh} />
        </>
      )}
    </>
  )
}
