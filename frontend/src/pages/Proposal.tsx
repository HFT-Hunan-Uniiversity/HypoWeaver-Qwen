import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, body } from '../api/client'
import type { AnalysisResult } from '../api/analysis'
import AnalysisCharts from '../components/AnalysisCharts'
import JobProgress from '../components/JobProgress'
import { ErrorNote } from '../components/Shared'
const titles: Record<string, string> = {
  overview: '一页概览',
  question: '研究问题与贡献',
  literature: '文献依据',
  gap: '研究缺口',
  hypothesis: '假设与机制',
  design: '识别设计',
  data: '数据与变量',
  results: '探索性结果',
  conclusions: '结论与边界',
  limitations: '局限和后续计划',
  references: '参考文献',
}
type Section = {
  key: string
  markdown: string
  injected_numbers_ref: Record<string, number | null>
  editable: boolean
}
type ProposalRecord = {
  id: string
  version: number
  kind: string
  stale: boolean
  sections: Section[]
  removed_references: number
  snapshot: { project: { title: string }; run: null | { id: string; result: AnalysisResult } }
}
function render(s: Section) {
  return s.markdown.replace(/\{\{num:([\w.]+)\}\}/g, (_, key) =>
    s.injected_numbers_ref[key] === null
      ? '未估计'
      : String(Number(Number(s.injected_numbers_ref[key]).toPrecision(6))),
  )
}
function SectionView({ section, proposalId }: { section: Section; proposalId: string }) {
  const [editing, setEditing] = useState(false),
    [draft, setDraft] = useState(section.markdown),
    qc = useQueryClient()
  const save = useMutation({
    mutationFn: () =>
      api(`/proposals/${proposalId}/sections/${section.key}`, body('PATCH', { markdown: draft })),
    onSuccess: () => {
      setEditing(false)
      qc.invalidateQueries({ queryKey: ['proposals'] })
    },
  })
  return (
    <section className={'proposal-section ' + (!section.editable ? 'injected' : '')}>
      <div className="section-heading">
        <h2>{titles[section.key]}</h2>
        {section.editable && (
          <button
            className="secondary no-print"
            onClick={() => {
              setDraft(section.markdown)
              setEditing(!editing)
            }}
          >
            {editing ? '取消编辑' : '编辑叙述'}
          </button>
        )}
        {!section.editable && <span className="badge no-print">系统生成 · 只读</span>}
      </div>
      {editing ? (
        <div className="no-print">
          <p className="muted">数字占位符不可增加、删除或更换。新数字请回到方案与检验中更新。</p>
          <textarea rows={8} value={draft} onChange={(e) => setDraft(e.target.value)} />
          <ErrorNote error={save.error} />
          <button onClick={() => save.mutate()} disabled={save.isPending}>
            保存叙述
          </button>
        </div>
      ) : (
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{render(section)}</ReactMarkdown>
      )}
    </section>
  )
}
export default function Proposal() {
  const { id } = useParams(),
    [params, setParams] = useSearchParams(),
    [job, setJob] = useState(''),
    qc = useQueryClient()
  const query = useQuery({
    queryKey: ['proposals', id],
    queryFn: () => api<ProposalRecord[]>(`/projects/${id}/proposals`),
  })
  const jobs = useQuery({
    queryKey: ['proposal-jobs', id],
    queryFn: () => api<{ id: string; status: string }[]>(`/projects/${id}/jobs?kind=proposal`),
    refetchInterval: (q) =>
      q.state.data?.some((j) => ['queued', 'running'].includes(j.status)) ? 1000 : false,
  })
  const active = query.data?.find((p) => p.id === params.get('proposal')) || query.data?.[0]
  const currentJob = job || jobs.data?.[0]?.id || ''
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['proposals', id] })
    qc.invalidateQueries({ queryKey: ['proposal-jobs', id] })
    qc.invalidateQueries({ queryKey: ['overview', id] })
  }
  const generate = useMutation({
    mutationFn: () => api<{ job_id: string }>(`/projects/${id}/proposals`, body('POST')),
    onSuccess: (d) => {
      setJob(d.job_id)
      refresh()
    },
  })
  return (
    <>
      <div className="no-print">
        <div className="page-heading">
          <div>
            <h1>研究提案</h1>
            <p className="muted">数字来自已保存的检验，叙述须遵守结论强度。</p>
          </div>
          <button
            disabled={
              generate.isPending || jobs.data?.some((j) => ['queued', 'running'].includes(j.status))
            }
            onClick={() => generate.mutate()}
          >
            生成新版本
          </button>
        </div>
        <ErrorNote error={query.error || generate.error || jobs.error} />
        {currentJob && (
          <JobProgress
            id={currentJob}
            onComplete={(j) => {
              refresh()
              if (j.result?.proposal_id) setParams({ proposal: String(j.result.proposal_id) })
            }}
          />
        )}
      </div>
      {!active ? (
        <section className="panel">
          <h2>尚无提案</h2>
          <p>选定候选并起草方案后即可生成。没有数据时生成计划型提案，列出待补数据。</p>
        </section>
      ) : (
        <>
          <div className="toolbar no-print">
            <label>
              提案版本
              <select value={active.id} onChange={(e) => setParams({ proposal: e.target.value })}>
                {query.data?.map((p) => (
                  <option key={p.id} value={p.id}>
                    第{p.version}版 · {p.kind === 'plan_only' ? '计划型' : '含探索性结果'}
                    {p.stale ? ' · 已过期' : ''}
                  </option>
                ))}
              </select>
            </label>
            <a className="button secondary" href={`/api/proposals/${active.id}.md`} download>
              下载 Markdown
            </a>
            <button className="secondary" onClick={() => window.print()}>
              打印 / 保存 PDF
            </button>
          </div>
          {active.stale && (
            <p className="notice">上游信息已变更，本提案已过期。历史正文保留，请生成新版本。</p>
          )}
          <article className="proposal-document">
            {active.snapshot.run && (
              <Link className="no-print" to={`/p/${id}/analysis?run=${active.snapshot.run.id}`}>
                查看本提案的原始检验与复算 →
              </Link>
            )}
            <p className="eyebrow">
              {active.kind === 'plan_only'
                ? '计划型提案 · 尚无实证结果'
                : '研究提案 · 含探索性结果'}
            </p>
            <h1>{active.snapshot.project.title}</h1>
            <p className="muted">已移除无效引用 {active.removed_references} 处</p>
            {active.sections.map((s) => (
              <div key={active.id + s.key}>
                <SectionView section={s} proposalId={active.id} />
                {s.key === 'results' && active.snapshot.run?.result && (
                  <AnalysisCharts result={active.snapshot.run.result} />
                )}
              </div>
            ))}
          </article>
        </>
      )}
    </>
  )
}
