import { ScrollRegion, StageActions } from '../components/shell/ShellContext'
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
  const [importOpen, setImportOpen] = useState(false)
  const tab = (params.get('tab') as 'assets' | 'binding' | 'results') || 'assets'
  const current = datasets.data?.find((d) => d.id === params.get('dataset')) || datasets.data?.[0]
  const activeJob = job || tasks.data?.[0]?.id
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['datasets'] })
    qc.invalidateQueries({ queryKey: ['dataset-tasks', id] })
  }
  return (
    <>
      <StageActions>
        {tab === 'assets' && (
          <button className="secondary" onClick={() => setImportOpen((v) => !v)}>
            导入数据
          </button>
        )}
      </StageActions>
      <div className="stage-tabs is-compact" role="tablist" aria-label="数据与检验">
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
          {tab === 'assets' && importOpen && (
            <div className="side-drawer" role="dialog" aria-label="导入数据">
              <div className="side-drawer__head">
                <strong>导入数据</strong>
                <button
                  className="icon-button"
                  aria-label="关闭"
                  onClick={() => setImportOpen(false)}
                >
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
              <button onClick={() => setImportOpen(true)}>导入数据</button>
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
