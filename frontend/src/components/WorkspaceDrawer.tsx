/**
 * WorkspaceDrawer：右侧「工作区文件」抽屉（ClawsGO 式）。
 * 真实运行：产物（论文与图表）/ 阶段明细与日志 / 基线对比 三个页签（自 ExecutionWorkspace 抽取）。
 * mock 任务：展示各阶段演示产物清单。
 */
import { Check, ChevronDown, Circle, Clock3, Download, FileText, Image as ImageIcon, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { BaselineRun, ModelCallGroup, ModelUsageView, RunSnapshot, StepAttempt, WorkflowDefinition, WorkflowStage } from '../runtime/types'
import type { MockArtifact, MockTask } from '../data/mockPipeline'
import { StatementProvenance } from './GateDecisionCard'

export const MODEL_CALL_PROTOCOL = {
  humanGateCount: 4,
  logicalCallCount: 9,
  maxProviderAttempts: 20,
} as const

const modelCallGroups: ModelCallGroup[] = ['h1_h2', 'h3', 'h4']
const modelCallStageLabels: Record<ModelCallGroup, string> = {
  h1_h2: '设计与审查阶段',
  h3: '证据与结论审计阶段',
  h4: '论文写作与复核阶段',
}

export function modelCallStageUsage(modelUsage: ModelUsageView) {
  return modelCallGroups.map((group) => ({
    label: modelCallStageLabels[group],
    attempts: modelUsage.groupUsage[group],
  }))
}

function usesSharedRetryPool(modelUsage: ModelUsageView): boolean {
  return modelUsage.retryPolicy === 'shared_bounded'
    || modelUsage.retryPolicy === 'shared-retry-v1'
    || modelUsage.retryMode === 'global_shared_retry_pool'
}

export function ModelCallContract({ modelUsage }: { modelUsage?: ModelUsageView }) {
  return (
    <section className="model-call-contract" aria-label="人工确认与模型调用结构">
      <header>
        <div><strong>确认与模型调用结构</strong><small>人工 Gate、逻辑任务和真实请求分别计数</small></div>
        {modelUsage && <span>当前 {modelUsage.logicalCalls}/{modelUsage.requiredLogicalCalls} 个逻辑调用 · {modelUsage.providerAttempts}/{modelUsage.maxCalls} 次 Provider Attempt</span>}
      </header>
      <div className="model-call-contract__totals">
        <article><strong>{MODEL_CALL_PROTOCOL.humanGateCount}</strong><span>个人工 Gate</span><small>H1–H4 决策点</small></article>
        <article><strong>{MODEL_CALL_PROTOCOL.logicalCallCount}</strong><span>个逻辑模型调用</span><small>完整首轮调用图</small></article>
        <article><strong>{MODEL_CALL_PROTOCOL.maxProviderAttempts}</strong><span>次 Provider Attempt 上限</span><small>包含首轮、网络重试与格式修复</small></article>
      </div>
      {modelUsage && (
        <div className="model-call-contract__usage">
          <p>{usesSharedRetryPool(modelUsage)
            ? <>共享重试池剩余 <strong>{modelUsage.sharedRetryRemaining}</strong> / {modelUsage.sharedRetrySlots} 次</>
            : '阶段调用用量'}</p>
          <ul aria-label="模型调用阶段用量">
            {modelCallStageUsage(modelUsage).map((stage) => (
              <li key={stage.label}><span>{stage.label}</span><strong>{stage.attempts} 次 attempt</strong></li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

const requiredManuscriptSections = [
  'abstract',
  'introduction',
  'theory_hypotheses',
  'data_variables',
  'research_design',
  'empirical_results',
  'discussion_limitations',
  'conclusion',
]

export function manuscriptQuality(run: RunSnapshot): { complete: boolean; characterCount: number } {
  const generated = run.manuscript?.sections.filter((section) => section.status === 'generated') ?? []
  const sectionIds = new Set(generated.map((section) => section.id))
  const characterCount = generated.reduce((total, section) => total + section.content.trim().length, 0)
  return {
    complete: run.manuscript?.auditResult === 'pass_with_no_critical_issues'
      && (run.manuscript.mode === 'identification_failure_report'
        || (run.manuscript.mode === 'full_manuscript'
          && requiredManuscriptSections.every((sectionId) => sectionIds.has(sectionId))
          && characterCount >= 3200)),
    characterCount,
  }
}

function FigureGallery({ run }: { run: RunSnapshot }) {
  const visibleBundles = run.figureBundles.filter((bundle) => bundle.status !== 'not_generated')
  if (!visibleBundles.length) return null
  const fileUrl = (figureId: string, format: string) => (
    `/api/v1/runs/${encodeURIComponent(run.id)}/figures/${encodeURIComponent(figureId)}/${encodeURIComponent(format)}`
  )
  return <section className="figure-gallery">
    <header><ImageIcon size={18} /><div><strong>HypoWeaver 科研绘图</strong><small>确定性绘图模块生成图片；HypoWeaver Writer 负责正文</small></div></header>
    {visibleBundles.map((bundle) => <section key={bundle.stage} className="figure-bundle">
      <div className="figure-bundle__heading"><strong>{bundle.stage === 'evidence' ? 'H3 前证据图' : 'H3 后论文图'}</strong><span>{bundle.status === 'succeeded' ? `${bundle.figures.length} 张` : '生成失败'}</span></div>
      {bundle.figures.length > 0 && <div className="figure-grid">{bundle.figures.map((figure) => {
        const png = figure.files.find((file) => file.format === 'png')
        return <article key={figure.id}>
          {png && <img src={fileUrl(figure.id, 'png')} alt={figure.altText} loading="lazy" />}
          <div className="figure-copy"><p className="figure-recipe">{figure.recipeId} · v{figure.recipeVersion}</p><h3>{figure.title}</h3><p>{figure.caption}</p>
            <div className="figure-downloads">{figure.files.map((file) => <a key={file.format} href={fileUrl(figure.id, file.format)} target="_blank" rel="noreferrer"><Download size={12} />{file.format.toUpperCase()}</a>)}</div>
            <small>Execution {figure.executionIds.join('、') || '冻结源数据聚合（未绑定估计样本）'} · Claim {figure.claimIds.join('、') || 'H3 前未授权'}</small>
          </div>
        </article>
      })}</div>}
      {bundle.warnings.length > 0 && <ul className="figure-warnings">{bundle.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>}
    </section>)}
  </section>
}

function JsonBlock({ value, empty = '本步骤尚未产生内容。' }: { value: unknown; empty?: string }) {
  if (value === null || value === undefined || value === '') return <p className="technical-empty">{empty}</p>
  return <pre>{typeof value === 'string' ? value : JSON.stringify(value, null, 2)}</pre>
}

export function stageState(stage: WorkflowStage, definition: WorkflowDefinition, run: RunSnapshot) {
  const currentNode = definition.nodes.find((node) => node.id === run.currentNodeId)
  const currentOrder = definition.stages.find((item) => item.id === currentNode?.stageId)?.order ?? 0
  if (run.status === 'completed') return 'complete'
  if (stage.id === currentNode?.stageId) return ['failed', 'blocked', 'stopped', 'cancelled'].includes(run.status) ? 'problem' : 'active'
  if (stage.order < currentOrder) return 'complete'
  return 'pending'
}

function StepDetails({ step, title }: { step: StepAttempt; title: string }) {
  const [tab, setTab] = useState<'prompt' | 'input' | 'output' | 'log'>('output')
  const tabPrefix = `step-${step.id.replaceAll(/[^a-zA-Z0-9_-]/g, '-')}`
  return (
    <article className="step-attempt">
      <header><span className={`step-status step-status--${step.status}`} /> <strong>{title}</strong><small>Attempt {step.attempt} · {step.status}</small></header>
      <details>
        <summary>查看本阶段提示词与输入输出 <ChevronDown size={15} /></summary>
        <div className="technical-tabs" role="tablist">
          {([['prompt', '提示词'], ['input', '实际输入'], ['output', '实际输出'], ['log', '运行日志']] as const).map(([id, label]) => <button type="button" role="tab" id={`${tabPrefix}-${id}-tab`} aria-controls={`${tabPrefix}-${id}-panel`} aria-selected={tab === id} tabIndex={tab === id ? 0 : -1} className={tab === id ? 'is-active' : ''} key={id} onClick={() => setTab(id)}>{label}</button>)}
        </div>
        <div className="technical-content" role="tabpanel" id={`${tabPrefix}-${tab}-panel`} aria-labelledby={`${tabPrefix}-${tab}-tab`}>
          {tab === 'prompt' && (step.prompts.length ? step.prompts.map((prompt) => <section className="prompt-entry" key={prompt.id}><strong>{prompt.role} · {prompt.rendered ? '本次渲染' : '模板'}</strong><pre>{prompt.rendered ?? prompt.template}</pre></section>) : <p className="technical-empty">这是确定性代码步骤，没有 LLM 提示词。</p>)}
          {tab === 'input' && <JsonBlock value={step.input} />}
          {tab === 'output' && <JsonBlock value={step.output} />}
          {tab === 'log' && <JsonBlock value={step.error ? [...step.logs, `ERROR: ${step.error}`].join('\n') : step.logs.join('\n')} empty="没有运行日志。" />}
        </div>
      </details>
    </article>
  )
}

const baselineStatusText: Record<BaselineRun['status'], string> = {
  queued: '排队中',
  running: '运行中',
  completed: '已完成',
  failed: '执行失败',
}

const baselineFallbackPhases: BaselineRun['phases'] = [
  { id: 'plan', title: '形成研究计划', status: 'pending' },
  { id: 'data', title: '准备分析数据', status: 'pending' },
  { id: 'execute', title: '运行实验', status: 'pending' },
  { id: 'interpret', title: '解释结果', status: 'pending' },
  { id: 'write', title: '生成研究报告', status: 'pending' },
]

function elapsedSeconds(start?: string, end?: string): string {
  if (!start || !end) return '—'
  const value = (new Date(end).getTime() - new Date(start).getTime()) / 1000
  if (!Number.isFinite(value) || value < 0) return '—'
  return value < 60 ? `${value.toFixed(1)} 秒` : `${(value / 60).toFixed(1)} 分钟`
}

function findMethodFamily(run: RunSnapshot | null): string {
  if (!run) return '—'
  for (const step of [...run.steps].reverse()) {
    const output = step.output
    if (!output || typeof output !== 'object' || Array.isArray(output)) continue
    const record = output as Record<string, unknown>
    const direct = record.method_family ?? record.primary_route ?? record.method
    if (typeof direct === 'string' && direct) return direct
    const route = record.method_route
    if (route && typeof route === 'object' && !Array.isArray(route)) {
      const nested = (route as Record<string, unknown>).method_family
      if (typeof nested === 'string' && nested) return nested
    }
  }
  return '待路由'
}

function BaselineLane({ run, busy, caseReady, onStart }: {
  run: BaselineRun | null
  busy: boolean
  caseReady: boolean
  onStart: () => Promise<void>
}) {
  const phases = run?.phases.length ? run.phases : baselineFallbackPhases
  return (
    <section className="bench-lane">
      <header className="bench-lane__header">
        <div><span className="bench-badge">AL</span><h2>Agent Laboratory</h2></div>
        <span className={`plain-status plain-status--${run?.status ?? 'idle'}`}>{run ? baselineStatusText[run.status] : '尚未启动'}</span>
      </header>
      {!run && <button type="button" className="secondary-button lane-start" disabled={busy || !caseReady} onClick={() => void onStart()}>{caseReady ? '启动基线' : '请重新选择案例'}</button>}
      <ol className="compact-flow compact-flow--runtime">
        {phases.map((phase, index) => (
          <li className={`is-${phase.status}`} key={phase.id}>
            <span>{phase.status === 'succeeded' ? <Check size={13} /> : index + 1}</span>
            <div><strong>{phase.title}</strong><small>{phase.status === 'succeeded' ? '已完成' : phase.status === 'running' ? '正在执行' : phase.status === 'failed' ? '执行失败' : '尚未开始'}</small></div>
          </li>
        ))}
      </ol>
      {run?.error && <p className="lane-error">{run.error}</p>}
      <p className="lane-note">基线保留原生调度；科学状态默认不判定。</p>
    </section>
  )
}

const mockArtifactKindText: Record<MockArtifact['kind'], string> = {
  figure: '图',
  table: '表',
  document: '文档',
  data: '数据',
}

interface WorkspaceDrawerProps {
  open: boolean
  onClose: () => void
  caseName: string
  definition?: WorkflowDefinition | null
  run?: RunSnapshot | null
  baselineRun?: BaselineRun | null
  busy?: boolean
  caseReady?: boolean
  onStartBaseline?: () => Promise<void>
  mockTask?: MockTask | null
}

type DrawerTab = 'artifacts' | 'steps' | 'compare'

export function WorkspaceDrawer({ open, onClose, caseName, definition, run, baselineRun, busy = false, caseReady = false, onStartBaseline, mockTask }: WorkspaceDrawerProps) {
  const [tab, setTab] = useState<DrawerTab>('artifacts')
  const attemptsByStage = useMemo(
    () => new Map((definition?.stages ?? []).map((stage) => [stage.id, run?.steps.filter((step) => stage.nodeIds.includes(step.nodeId)) ?? []])),
    [definition?.stages, run?.steps],
  )
  if (!open) return null
  const identificationFailure = run?.manuscript?.mode === 'identification_failure_report'
  const hasArtifacts = Boolean(run && (run.manuscript || run.figureBundles.some((bundle) => bundle.status !== 'not_generated')))
  const completedStages = run && definition ? definition.stages.filter((stage) => stageState(stage, definition, run) === 'complete').length : 0
  const tabs: Array<{ id: DrawerTab; label: string }> = mockTask
    ? [{ id: 'artifacts', label: '工作区文件' }]
    : [
      { id: 'artifacts', label: '论文与图表' },
      { id: 'steps', label: '阶段明细与日志' },
      ...(onStartBaseline ? [{ id: 'compare' as const, label: '基线对比' }] : []),
    ]

  return (
    <div className="exec-drawer" role="dialog" aria-modal="true">
      <div className="exec-drawer__scrim" onClick={onClose} />
      <div className="exec-drawer__panel">
        <div className="exec-drawer__head">
          <div><h2>工作区文件</h2><small>{caseName}</small></div>
          <button type="button" className="exec-drawer__close" aria-label="关闭" onClick={onClose}><X size={16} /></button>
        </div>
        {tabs.length > 1 && (
          <div className="exec-drawer__tabs" role="tablist">
            {tabs.map((item) => (
              <button type="button" role="tab" key={item.id} aria-selected={tab === item.id} className={tab === item.id ? 'is-active' : ''} onClick={() => setTab(item.id)}>{item.label}</button>
            ))}
          </div>
        )}
        <div className="exec-drawer__body">
          {mockTask && (
            <div className="mock-artifacts">
              {mockTask.stages.filter((stage) => stage.artifacts.length && (stage.status === 'done' || stage.status === 'waiting_gate' || (stage.status === 'running' && stage.revealed > 0))).map((stage) => (
                <section className="mock-artifacts__group" key={stage.key}>
                  <p className="mock-artifacts__stage">{stage.label}</p>
                  {stage.artifacts.map((artifact) => (
                    <div className="mock-artifact" key={artifact.id}>
                      <span className="mock-artifact__kind">{mockArtifactKindText[artifact.kind]}</span>
                      <div><strong>{artifact.name}</strong><small>{artifact.note}</small></div>
                    </div>
                  ))}
                </section>
              ))}
              {!mockTask.stages.some((stage) => stage.artifacts.length && stage.status !== 'pending') && <p className="exec-sub">任务推进后，各阶段产物会陆续出现在这里。</p>}
            </div>
          )}
          {!mockTask && tab === 'steps' && run && definition && (
            <>
              <ModelCallContract modelUsage={run.modelUsage} />
              <div className="stage-flow">
                {definition.stages.map((stage) => {
                  const state = stageState(stage, definition, run)
                  const attempts = attemptsByStage.get(stage.id) ?? []
                  return (
                    <section className={`stage-card stage-card--${state}`} key={stage.id}>
                      <div className="stage-rail"><Circle size={16} /><span /></div>
                      <div className="stage-card__content">
                        <header><div><small>阶段 {stage.order}</small><h2>{stage.title}</h2></div></header>
                        {attempts.length > 0 ? <div className="attempt-list">{attempts.map((attempt) => <StepDetails key={attempt.id} step={attempt} title={definition.nodes.find((node) => node.id === attempt.nodeId)?.title ?? attempt.nodeId} />)}</div> : <p className="stage-pending-copy"><Clock3 size={14} />尚无记录</p>}
                      </div>
                    </section>
                  )
                })}
              </div>
            </>
          )}
          {!mockTask && tab === 'artifacts' && run && (
            <>
              <FigureGallery run={run} />
              {run.manuscript && <article className="manuscript-draft">
                <header><FileText size={18} /><div><strong>{identificationFailure ? '识别失败报告' : '论文初稿'} · v{run.manuscript.version}</strong><small>{run.manuscript.auditResult === 'pass_with_no_critical_issues' ? '一致性审计通过' : '尚未通过一致性审计'}</small></div></header>
                <div className="manuscript-sections">
                  {run.manuscript.sections.filter((section) => section.status === 'generated').map((section, index) => (
                    <section key={section.id} id={`manuscript-${section.id}`}>
                      <p className="manuscript-section-index">{String(index + 1).padStart(2, '0')} · {section.id}</p>
                      <h3>{section.title}</h3>
                      <div className="manuscript-copy">{section.content}</div>
                      <StatementProvenance statements={section.statements} />
                    </section>
                  ))}
                </div>
                {run.manuscript.disclosures.length > 0 && <aside><strong>写作披露</strong><ul>{run.manuscript.disclosures.map((item) => <li key={item}>{item}</li>)}</ul></aside>}
              </article>}
              {!hasArtifacts && <p className="exec-sub">尚未生成论文或图表。</p>}
            </>
          )}
          {!mockTask && tab === 'compare' && onStartBaseline && (
            <>
              <div className="bench-grid is-comparing" style={{ marginBottom: 16 }}>
                <BaselineLane run={baselineRun ?? null} busy={busy} caseReady={caseReady} onStart={onStartBaseline} />
              </div>
              <div className="comparison-table-wrap">
                <table className="comparison-table">
                  <thead><tr><th>指标</th><th>HypoWeaver-Qwen</th><th>Agent Laboratory</th></tr></thead>
                  <tbody>
                    <tr><th>进度</th><td>{run && definition ? `${completedStages}/${definition.stages.length} 阶段` : '未启动'}</td><td>{baselineRun ? baselineStatusText[baselineRun.status] : '未启动'}</td></tr>
                    <tr><th>方法</th><td>{findMethodFamily(run ?? null)}</td><td>{baselineRun?.methodFamily ?? '待规划'}</td></tr>
                    <tr><th>执行状态</th><td>{run?.executionStatus ?? 'not_started'}</td><td>{baselineRun?.executionStatus ?? 'not_started'}</td></tr>
                    <tr><th>科学状态</th><td>{run?.scientificStatus ?? 'not_assessed'}</td><td>{baselineRun?.scientificStatus ?? 'not_assessed'}</td></tr>
                    <tr><th>结论约束</th><td>{run ? `${run.claims.length} 条 Claim` : '尚未生成'}</td><td>无 ClaimLedger</td></tr>
                    <tr><th>运行时间</th><td>{run ? elapsedSeconds(run.createdAt, run.updatedAt) : '—'}</td><td>{baselineRun ? `${baselineRun.wallTimeSeconds.toFixed(1)} 秒` : '—'}</td></tr>
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
