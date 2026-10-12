import Bindings from '../components/Bindings'
import Analysis from './Analysis'
import { useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Dataset } from '../api/datasets'
import DatasetImport from '../components/DatasetImport'
import DatasetDetails from '../components/DatasetDetails'
import JobProgress from '../components/JobProgress'
import type { Job } from '../components/JobProgress'
import { ErrorNote } from '../components/Shared'
import { VersionPills } from '../components/ui/Bits'
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
  const tab = (params.get('tab') as 'assets' | 'binding' | 'results') || 'assets'
  const current = datasets.data?.find((d) => d.id === params.get('dataset')) || datasets.data?.[0]
  const activeJob = job || tasks.data?.[0]?.id
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['datasets'] })
    qc.invalidateQueries({ queryKey: ['dataset-tasks', id] })
  }
  return (
    <>
      <div className="stage-tabs" role="tablist" aria-label="数据与检验">
        {(
          [
            ['assets', '数据资产', '导入与字段档案'],
            ['binding', '变量绑定', '字段映射与就绪检查'],
            ['results', '运行结果', '主模型、诊断与结论'],
          ] as const
        ).map(([k, label, note]) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={tab === k}
            className={tab === k ? 'is-active' : ''}
            onClick={() => {
              const next = new URLSearchParams(params)
              next.set('tab', k)
              if (k !== 'results') next.delete('run')
              setParams(next)
            }}
          >
            <strong>{label}</strong>
            <small>{note}</small>
          </button>
        ))}
      </div>
      {tab === 'results' ? (
        <Analysis />
      ) : (
        <>
          <h2 className="stage-section-title">{tab === 'assets' ? '数据资产' : '变量绑定'}</h2>
          <p className="muted">
            {tab === 'assets'
              ? '数据资产可在项目之间复用。导入保留原始观测，变量变换在绑定阶段定义。'
              : '把方案中的变量绑定到数据字段或派生公式，保存后检查有效样本。'}
          </p>
          {tab === 'assets' && (
            <DatasetImport
              projectId={id!}
              onStart={(j) => {
                setJob(j)
                refresh()
              }}
            />
          )}
          {activeJob && (
            <JobProgress
              id={activeJob}
              onComplete={(j) => {
                refresh()
                if (j.status === 'succeeded' && j.result?.dataset_id)
                  setParams({ tab: 'assets', dataset: String(j.result.dataset_id) })
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
              <VersionPills
                label="数据资产"
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
              {tab === 'binding' ? (
                <Bindings projectId={id!} dataset={current} />
              ) : (
                <DatasetDetails key={current.id} dataset={current} onSaved={refresh} />
              )}
            </>
          )}
        </>
      )}
    </>
  )
}
