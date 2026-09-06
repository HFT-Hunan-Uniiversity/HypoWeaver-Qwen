import { AlertTriangle, Check, ChevronRight, FileText, FolderArchive, ListChecks } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { MockTask } from '../data/mockPipeline'
import type { RunSnapshot } from '../runtime/types'

const reviewStages = [
  { gate: 'H1', label: '确认研究边界', note: '问题、假设、变量与样本' },
  { gate: 'H2', label: '冻结研究方案', note: '数据、识别策略与诊断' },
  { gate: 'H3', label: '审核证据结论', note: '复现结果与主张强度' },
  { gate: 'H4', label: '确认最终交付', note: '报告、限制与复现材料' },
] as const

const planStages = [
  { label: '接收研究问题与证据', detail: '核对输入材料和证据边界' },
  { label: '识别研究空白', detail: '定位尚未回答的关键问题' },
  { label: '形成候选假设', detail: '明确机制、变量和证伪路径' },
  { label: '确认研究边界', detail: '人工确认问题、样本与时间范围' },
  { label: '冻结研究方案', detail: '确定数据、识别策略与诊断' },
  { label: '分析、审核与交付', detail: '执行、复现、授权结论并封存' },
]

function activePlanIndex(status: string, gate?: string): number {
  if (status === 'completed') return planStages.length
  if (gate === 'H1') return 3
  if (gate === 'H2') return 4
  if (gate === 'H3' || gate === 'H4') return 5
  if (status === 'failed' || status === 'blocked') return 4
  return 1
}

function shortText(value: string | undefined, fallback: string, max = 96): string {
  const text = value?.trim() || fallback
  return text.length > max ? `${text.slice(0, max)}…` : text
}

function readableUnit(value: string | undefined): string {
  return value === 'firm-region-year' ? '企业—地区—年份' : value || '待确认'
}

function readablePeriod(value: string | undefined): string {
  return value?.replace(/^Literature coverage\s*/i, '文献覆盖 ') || '待确认'
}

export function TaskResearchRail({ run, mockTask, onOpenDrawer }: {
  run?: RunSnapshot
  mockTask?: MockTask
  onOpenDrawer: () => void
}) {
  const [tab, setTab] = useState<'plan' | 'overview'>('plan')
  const status = run?.status ?? mockTask?.status ?? 'running'
  const currentGate = run?.currentGate ?? mockTask?.currentGate
  const planIndex = activePlanIndex(status, currentGate)
  const caseInput = run?.caseSubmission
  const completedMockStages = mockTask?.stages.filter((stage) => stage.status === 'done').length ?? 0
  const artifactCount = mockTask?.stages.reduce((total, stage) => total + stage.artifacts.length, 0) ?? 0
  const evidenceCount = run?.upstreamPackage?.evidenceRefCount ?? run?.upstreamPackage?.verifiedArtifactCount ?? 0
  const variableCount = caseInput?.variables.length ?? 0
  const blockers = run?.intakeReadiness?.blockers ?? []
  const primaryHypothesis = caseInput?.hypotheses[0]?.statement
  const keyVariables = useMemo(() => {
    if (!caseInput) return '等待研究边界确认后生成变量表'
    const exposure = caseInput.variables.find((item) => item.role === 'treatment' || item.role === 'exposure')?.label
    const outcomes = caseInput.variables.filter((item) => item.role === 'outcome').map((item) => item.label)
    return [exposure, ...outcomes].filter(Boolean).join(' → ') || `${caseInput.variables.length} 个候选变量`
  }, [caseInput])

  return (
    <aside className="task-context" aria-label="研究计划与证据">
      <div className="task-context__tabs" role="tablist" aria-label="研究侧栏">
        <button type="button" role="tab" aria-selected={tab === 'plan'} className={tab === 'plan' ? 'is-active' : ''} onClick={() => setTab('plan')}>研究计划</button>
        <button type="button" role="tab" aria-selected={tab === 'overview'} className={tab === 'overview' ? 'is-active' : ''} onClick={() => setTab('overview')}>信息概览</button>
      </div>

      <div className="task-context__scroll">
        {tab === 'plan' ? (
          <>
            <section className="task-context__section">
              <header><div><strong>研究进度</strong><small>{currentGate ? `当前等待 ${currentGate} 人工确认` : status === 'completed' ? '研究已完成' : '工作流正在推进'}</small></div><ListChecks size={16} /></header>
              <ol className="research-plan-list">
                {planStages.map((stage, index) => {
                  const state = index < planIndex ? 'done' : index === planIndex ? 'active' : 'pending'
                  return <li key={stage.label} className={`is-${state}`}>
                    <span>{state === 'done' ? <Check size={12} /> : index + 1}</span>
                    <div><strong>{stage.label}</strong><small>{stage.detail}</small></div>
                  </li>
                })}
              </ol>
            </section>

            <section className="task-context__section">
              <header><div><strong>证据与文件</strong><small>随研究进度持续更新</small></div><button type="button" onClick={onOpenDrawer}>全部打开 <ChevronRight size={13} /></button></header>
              <div className="task-context__metrics">
                <span><strong>{run ? evidenceCount : completedMockStages}</strong><small>{run ? '条上游证据' : '个完成阶段'}</small></span>
                <span><strong>{run ? variableCount : artifactCount}</strong><small>{run ? '个候选变量' : '份研究产物'}</small></span>
                <span><strong>{run?.claims.length ?? 0}</strong><small>条待审结论</small></span>
              </div>
              <div className="task-context__files">
                {['证据与来源摘要', '研究边界说明', '变量与数据需求'].map((name) => (
                  <button type="button" key={name} onClick={onOpenDrawer}><FileText size={14} /><span><strong>{name}</strong><small>查看最新版本</small></span><ChevronRight size={13} /></button>
                ))}
              </div>
            </section>

            {blockers.length > 0 && (
              <section className="task-context__blocker">
                <AlertTriangle size={16} />
                <div><strong>执行前还需补充数据</strong><p>{shortText(blockers[0], '存在数据缺口')}</p><small>这不会阻止当前研究边界与方案审核。</small></div>
              </section>
            )}
          </>
        ) : (
          <>
            <section className="task-context__section task-context__overview">
              <header><div><strong>当前研究</strong><small>从真实任务数据生成</small></div><FolderArchive size={16} /></header>
              <dl>
                <div><dt>研究问题</dt><dd>{shortText(caseInput?.researchQuestion, mockTask?.title ?? '等待研究问题')}</dd></div>
                <div><dt>主要假设</dt><dd>{shortText(primaryHypothesis, '等待证据检索与假设生成')}</dd></div>
                <div><dt>核心变量</dt><dd>{keyVariables}</dd></div>
                <div><dt>样本边界</dt><dd>{caseInput ? `${readableUnit(caseInput.unitOfAnalysis)} · ${readablePeriod(caseInput.samplePeriod)}` : '等待确认'}</dd></div>
              </dl>
            </section>

            <section className="task-context__section">
              <header><div><strong>四次人工确认</strong><small>中文动作优先，编号仅用于审计</small></div></header>
              <ol className="review-sequence">
                {reviewStages.map((stage, index) => {
                  const gateIndex = reviewStages.findIndex((item) => item.gate === currentGate)
                  const state = status === 'completed' || (gateIndex >= 0 && index < gateIndex) ? 'done' : stage.gate === currentGate ? 'active' : 'pending'
                  return <li key={stage.gate} className={`is-${state}`}><span>{state === 'done' ? <Check size={11} /> : stage.gate}</span><div><strong>{stage.label}</strong><small>{stage.note}</small></div></li>
                })}
              </ol>
            </section>
          </>
        )}
      </div>
    </aside>
  )
}
