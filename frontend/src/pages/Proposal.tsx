import { fmtNumber } from '../components/ResultTable'
import { ScrollRegion } from '../components/shell/ShellContext'
import { useUrlParam } from '../lib/urlState'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, body } from '../api/client'
import type { AnalysisResult } from '../api/analysis'
import AnalysisCharts from '../components/AnalysisCharts'
import JobProgress from '../components/JobProgress'
import { ErrorNote } from '../components/Shared'
import { GeneratedBy, VersionPills } from '../components/ui/Bits'
import { useFlow, useFlowStage, useStageUi } from '../components/flow/FlowContext'
import { EmptyState, ProgressView } from '../components/flow/FlowBits'
import { useLlm } from '../lib/llm'
import { Copy, Download, FileText } from 'lucide-react'
import ProcessTimeline, { jobSeconds, useStageJob } from '../components/flow/ProcessTimeline'
import { displayProjectTitle } from '../lib/displayTitle'
// 赛题《科学假设与研究计划》十项，顺序固定
const titles: Record<string, string> = {
  problem: '一、待研究问题',
  rationale: '二、解决思路',
  techniques: '三、必要的技术手段',
  datasets: '四、数据集',
  title: '五、标题',
  abstract: '六、摘要',
  methods: '七、方法论',
  experiments: '八、实验设计',
  results: '九、实验结果',
  references: '十、参考论文',
  // 旧版提案节名，仅用于显示历史版本
  overview: '一页概览',
  question: '研究问题与贡献',
  literature: '文献依据',
  gap: '研究缺口',
  hypothesis: '假设与机制',
  design: '识别设计',
  data: '数据与变量',
  conclusions: '结论与边界',
  limitations: '局限和后续计划',
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
  llm_model?: string | null
  interpretation?: { llm_model?: string | null } | null
  /** R5：叙述生成状态；旧提案可能缺省 */
  narrative_status?: 'complete' | 'partial' | null
  /** R5：按节归并的失败原因 */
  narrative_failures?: { section: string; reason: string }[] | null
  snapshot: { project: { title: string }; run: null | { id: string; result: AnalysisResult } }
}
function narrativeIssues(p: ProposalRecord): string[] {
  return (p.narrative_failures || []).map((x) => `${titles[x.section] || x.section}：${x.reason}`)
}
/** 去掉与节名重复的首行标题（忽略序号、空格、英文括注）。 */
function normTitle(x: string) {
  return x
    .replace(/[（(][^）)]*[）)]/g, '')
    .replace(/^[一二三四五六七八九十]+、/, '')
    .replace(/[\s#:：]/g, '')
}
export function stripDuplicateHeading(md: string, title?: string) {
  if (!title) return md
  const m = md.match(/^\s*#{1,6}\s*([^\n]*)\n?/)
  if (!m || normTitle(m[1]) !== normTitle(title)) return md
  return md.slice(m[0].length).replace(/^\s*\n/, '')
}
function render(s: Section) {
  return stripDuplicateHeading(s.markdown, titles[s.key]).replace(/\{\{num:([\w.]+)\}\}/g, (_, key) =>
    s.injected_numbers_ref[key] === null
      ? '未估计'
      : fmtNumber(Number(s.injected_numbers_ref[key])),
  )
}
function SectionView({
  section,
  proposalId,
  failure,
  onRegenerate,
  readOnly,
}: {
  section: Section
  proposalId: string
  failure?: string
  onRegenerate?: () => void
  readOnly?: boolean
}) {
  const [editing, setEditing] = useState(false),
    [draft, setDraft] = useState(section.markdown),
    qc = useQueryClient()
  const save = useMutation({
    mutationFn: () =>
      api(`/proposals/${proposalId}/sections/${section.key}`, body('PATCH', { markdown: draft })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['proposals'] }),
  })
  // 叙述编辑自动保存（不再有"保存叙述"按钮）
  useEffect(() => {
    if (!editing || draft === section.markdown) return
    const t = setTimeout(() => save.mutate(), 900)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, editing])
  return (
    <section className={'proposal-section ' + (!section.editable ? 'injected' : '')}>
      <div className="section-heading">
        <h2>{titles[section.key] || section.key}</h2>
        {section.editable && !readOnly && (
          <button
            className="secondary no-print"
            onClick={() => {
              setDraft(section.markdown)
              setEditing(!editing)
            }}
          >
            {editing ? '完成编辑' : '编辑叙述'}
          </button>
        )}
        {!section.editable && <span className="badge no-print">系统生成 · 只读</span>}
      </div>
      {failure && (
        <div className="notice proposal-fail no-print" role="status">
          <span>本节生成失败：{failure}</span>
          {onRegenerate && (
            <button
              type="button"
              className="product-button is-quiet"
              onClick={onRegenerate}
              title="后端暂无单节重生成接口：会生成新的提案版本"
            >
              重新生成本节
            </button>
          )}
        </div>
      )}
      {editing ? (
        <div className="no-print">
          <p className="muted">数字占位符不可增加、删除或更换。新数字请回到方案与检验中更新。</p>
          <textarea rows={8} value={draft} onChange={(e) => setDraft(e.target.value)} />
          <ErrorNote error={save.error} />
          <small className="muted">{save.isPending ? '正在自动保存…' : '编辑会自动保存'}</small>
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
  const navigate = useNavigate()
  const { confirm } = useFlow()
  const stage = useFlowStage('proposal')
  const llmOk = useLlm().data?.configured !== false
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
  const busy =
    generate.isPending || !!jobs.data?.some((j) => ['queued', 'running'].includes(j.status))
  const failedJob = jobs.data?.[0]?.status === 'failed' ? '提案生成失败' : null
  const needNew = !active || (active.stale && stage.status !== 'confirmed')
  const propJob = useStageJob(id, 'proposal', currentJob || undefined)
  const [docOpen, setDocOpen] = useState(true)
  const [copied, setCopied] = useState(false)
  const fullText = active ? active.sections.map((x) => render(x)).join('\n\n') : ''
  /** 字数：汉字逐字计，其余按词计 */
  const wordCount =
    (fullText.match(/[\u4e00-\u9fff]/g)?.length || 0) +
    (fullText.replace(/[\u4e00-\u9fff]/g, ' ').match(/[A-Za-z0-9]+/g)?.length || 0)
  const copyMd = async () => {
    if (!active) return
    let text = fullText
    try {
      const r = await fetch(`/api/proposals/${active.id}.md`)
      if (r.ok) text = await r.text()
    } catch {
      /* 退回到页面上的正文 */
    }
    await navigator.clipboard?.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  const exportMd = () => {
    if (!active) return
    const a = document.createElement('a')
    a.href = `/api/proposals/${active.id}.md`
    a.download = ''
    a.click()
  }
  useStageUi({
    checklist: [
      { label: '生成提案', done: !!active && !active.stale },
      { label: '确认提案', done: stage.status === 'confirmed' },
      { label: '导出', done: false },
    ],
    primary: busy
      ? { label: '正在生成提案…', busy: true }
      : needNew
        ? {
            label: active ? '重新生成提案' : '生成提案',
            needsLlm: true,
            onClick: () => generate.mutate(),
            error: generate.error ? (generate.error as Error).message : failedJob,
          }
        : stage.status === 'confirmed'
          ? { label: '导出', onClick: exportMd, reason: 'Markdown · 也可打印为 PDF' }
          : {
              label: '确认提案',
              reason:
                active.narrative_status === 'partial'
                  ? `${active.narrative_failures?.length || 0} 节生成失败，可先重新生成`
                  : `第 ${active.version} 版`,
              onClick: () => {
                if (!confirm('proposal')) navigate(`/p/${id}/proposal`)
              },
            },
  })
  const [sec, setSec] = useUrlParam<string>('sec', '')
  useEffect(() => {
    if (sec) document.getElementById('sec-' + sec)?.scrollIntoView({ block: 'start' })
    // 仅在提案载入时定位一次
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.id])
  return (
    <>
      <div className="no-print">
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
      {busy ? (
        <ProgressView
          title="正在生成研究提案"
          detail="按已确认的方向、证据、候选、方案和检验结果逐节撰写。完成后自动显示。"
          steps={Object.values(titles)
            .slice(0, 10)
            .map((t) => ({ label: t, state: 'todo' as const }))}
        />
      ) : !active ? (
        <EmptyState
          title="这里会生成一份完整的研究提案"
          what="按赛题《科学假设与研究计划》十项：待研究问题、解决思路、必要的技术手段、数据集、标题、摘要、方法论、实验设计、实验结果、参考论文。数字和图表由系统注入，内容自动保存。"
          example={{
            title: '假设与机制',
            body: 'H1：同行业出现控排企业后，行业内上市公司的绿色发明专利申请增加……',
          }}
          action={
            stage.editable ? { label: '生成提案', onClick: () => generate.mutate() } : undefined
          }
        />
      ) : (
        <>
          <div className="toolbar proposal-toolbar no-print">
            <VersionPills
              label="提案版本"
              value={active.id}
              onChange={(v) => setParams({ proposal: v })}
              items={(query.data || []).map((p) => ({
                id: p.id,
                label: `第 ${p.version} 版`,
                note: (p.kind === 'plan_only' ? '计划型' : '含结果') + (p.stale ? ' · 已过期' : ''),
                tone: p.stale ? 'stale' : undefined,
              }))}
            />
            <GeneratedBy of={active} />
            <button className="product-button is-quiet" onClick={() => window.print()}>
              打印 / 保存 PDF
            </button>
          </div>
          {active.stale && (
            <p className="notice">
              上游内容已修改，本提案需要更新。历史正文保留，点右上角重新生成。
            </p>
          )}
          {active.narrative_status === 'partial' && (
            <div className="notice narrative-partial" role="status">
              <strong>叙述部分生成：</strong>
              {narrativeIssues(active).length} 节未能由模型生成，已在对应位置标出，可单独重新生成。
              {narrativeIssues(active).length === 0 && (
                <span className="muted"> 后端未返回具体失败原因。</span>
              )}
              {(active.narrative_failures || [])
                .filter((f) => !active.sections.some((s) => s.key === f.section))
                .map((f) => (
                  <span key={f.section} className="muted">
                    {' '}
                    {titles[f.section] || f.section}：{f.reason}
                  </span>
                ))}
            </div>
          )}
          <ProcessTimeline
            title="提案生成"
            seconds={jobSeconds(propJob)}
            steps={[
              {
                key: 'gen',
                label: `生成第 ${active.version} 版 · ${active.sections.length} 节`,
                state: 'done',
              },
              {
                key: 'narr',
                label:
                  active.narrative_status === 'partial'
                    ? `叙述部分生成 · ${(active.narrative_failures || []).length} 节失败`
                    : '叙述与数字注入完成',
                state: active.narrative_status === 'partial' ? 'failed' : 'done',
                detail: active.narrative_failures?.length ? (
                  <ul>
                    {narrativeIssues(active).map((t) => (
                      <li key={t}>{t}</li>
                    ))}
                  </ul>
                ) : undefined,
              },
            ]}
          />
          <div className="file-card">
            <span className="file-card__icon" aria-hidden="true">
              <FileText size={18} />
            </span>
            <span className="file-card__body">
              <strong>
                {displayProjectTitle(active.snapshot.project.title, id)} · 研究提案 v
                {active.version}
              </strong>
              <small>
                {active.kind === 'plan_only' ? '计划型提案' : '含探索性结果'} ·{' '}
                {active.sections.length} 节 · 约 {wordCount.toLocaleString()} 字
              </small>
            </span>
            <button type="button" className="product-button" onClick={() => setDocOpen(!docOpen)}>
              {docOpen ? '收起' : '打开'}
            </button>
          </div>
          {docOpen && (
            <div className="doc-preview">
              <div className="doc-preview__bar no-print">
                <strong>研究提案 v{active.version}</strong>
                <button type="button" className="product-button" onClick={copyMd}>
                  <Copy size={14} aria-hidden="true" /> {copied ? '已复制' : '复制'}
                </button>
                <button type="button" className="product-button" onClick={exportMd}>
                  <Download size={14} aria-hidden="true" /> 导出 .md
                </button>
              </div>
              <div className="proposal-layout fill">
                <nav className="proposal-toc no-print" data-scroll-region="" aria-label="提案目录">
                  {active.sections.map((s) => (
                    <button
                      key={s.key}
                      className={sec === s.key ? 'is-active' : ''}
                      aria-current={sec === s.key ? 'true' : undefined}
                      onClick={() => {
                        setSec(s.key)
                        document.getElementById('sec-' + s.key)?.scrollIntoView({ block: 'start' })
                      }}
                    >
                      {titles[s.key] || s.key}
                    </button>
                  ))}
                </nav>
                <ScrollRegion className="proposal-scroll" label="提案正文">
                  <article className="proposal-document">
                    {active.snapshot.run && (
                      <Link
                        className="no-print"
                        to={`/p/${id}/analysis?run=${active.snapshot.run.id}`}
                      >
                        查看本提案的原始检验与复算 →
                      </Link>
                    )}
                    <p className="eyebrow">
                      {active.kind === 'plan_only'
                        ? '计划型提案 · 尚无实证结果'
                        : '研究提案 · 含探索性结果'}
                    </p>
                    <h1>{displayProjectTitle(active.snapshot.project.title, id)}</h1>
                    <p className="muted">已移除无效引用 {active.removed_references} 处</p>
                    {active.sections.map((s) => (
                      <div key={active.id + s.key} id={'sec-' + s.key} className="proposal-anchor">
                        <SectionView
                          section={s}
                          proposalId={active.id}
                          readOnly={!stage.editable}
                          failure={
                            active.narrative_failures?.find((f) => f.section === s.key)?.reason
                          }
                          onRegenerate={
                            stage.editable && llmOk ? () => generate.mutate() : undefined
                          }
                        />
                        {s.key === 'results' && active.interpretation?.llm_model && (
                          <p className="no-print">
                            结果解读 <GeneratedBy of={active.interpretation} />
                          </p>
                        )}
                        {s.key === 'results' && active.snapshot.run?.result && (
                          <AnalysisCharts result={active.snapshot.run.result} />
                        )}
                      </div>
                    ))}
                  </article>
                </ScrollRegion>
              </div>
              <div className="doc-preview__foot">{wordCount.toLocaleString()} 字</div>
            </div>
          )}
        </>
      )}
    </>
  )
}
