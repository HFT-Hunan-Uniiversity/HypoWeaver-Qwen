/**
 * TaskStream：任务详情页（会话流形态）。
 * - MockTaskStream：11 阶段演示流，逐句吐出，H1–H4 处内嵌 mock 闸门卡。
 * - RunTaskStream：真实运行，前半程折叠占位，后半程由 RunSnapshot 映射，
 *   闸门用 GateDecisionCard（走真实 API）。
 * 左侧纵向进度轨道 + 彗星拖尾指示当前进行位置；等待人工的闸门节点呼吸环。
 */
import { ArrowUp, CircleAlert, LoaderCircle, RotateCcw, ShieldCheck } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { GateDecisionInput, RunSnapshot, WorkflowDefinition, WorkflowStage } from '../runtime/types'
import { MOCK_H2_CANDIDATES, MOCK_H3_CLAIMS, type MockGateAction, type MockStage, type MockTask } from '../data/mockPipeline'
import { GateDecisionCard, claimDecisionText, returnedRevisionGate } from './GateDecisionCard'
import { stageState } from './WorkspaceDrawer'

/* ============================== 公共 ============================== */

function useAutoScroll(dependency: unknown, enabled = true) {
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (enabled) endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [dependency, enabled])
  return endRef
}

function StageNode({ state, gate }: { state: 'pending' | 'active' | 'waiting' | 'done' | 'problem'; gate?: string }) {
  return (
    <span className={`stream-node is-${state} ${gate ? 'is-gate' : ''}`} aria-hidden="true">
      {gate ?? ''}
    </span>
  )
}

/* ============================== Mock 流 ============================== */

function MockGateCard({ stage, onDecide }: { stage: MockStage; onDecide: (action: MockGateAction, comment?: string) => void }) {
  const [comment, setComment] = useState('')
  const [candidateId, setCandidateId] = useState(MOCK_H2_CANDIDATES[0].id)
  const [claimDecisions, setClaimDecisions] = useState<Record<string, 'approve' | 'reject'>>(
    () => Object.fromEntries(MOCK_H3_CLAIMS.map((claim) => [claim.id, 'approve' as const])),
  )
  const gate = stage.gate!
  const gateTitle = {
    H1: '确认研究边界并继续设计',
    H2: '确认研究方案并冻结',
    H3: '审核证据与结论',
    H4: '确认最终交付并封存',
  }[gate]
  return (
    <section className="human-review-card stream-gate-card">
      <header><ShieldCheck size={22} /><div><div className="review-card__title-row"><strong>{gateTitle}</strong><span>{gate}</span></div><p>{stage.gateHint}（演示决策，仅更新本地状态）</p></div></header>
      {gate === 'H2' && (
        <section className="design-candidate-list" aria-label="可行研究设计候选（演示）">
          {MOCK_H2_CANDIDATES.map((candidate) => (
            <label key={candidate.id} className={`design-candidate ${candidateId === candidate.id ? 'is-selected' : ''} ${candidate.recommended ? '' : 'is-unavailable'}`}>
              <input type="radio" name="mock-design-candidate" value={candidate.id} checked={candidateId === candidate.id} disabled={!candidate.recommended} onChange={() => setCandidateId(candidate.id)} />
              <span><strong>{candidate.label}</strong><small>{candidate.detail}</small></span>
            </label>
          ))}
        </section>
      )}
      {gate === 'H3' && (
        <div className="claim-review-list">
          {MOCK_H3_CLAIMS.map((claim) => (
            <article key={claim.id}>
              <p>{claim.text}</p>
              <div className="claim-gate-summary"><small>Gate：{claim.admission}</small></div>
              <div>
                {(['approve', 'reject'] as const).map((decision) => (
                  <button type="button" key={decision} aria-pressed={claimDecisions[claim.id] === decision} className={claimDecisions[claim.id] === decision ? 'is-selected' : ''} onClick={() => setClaimDecisions((current) => ({ ...current, [claim.id]: decision }))}>
                    {decision === 'approve' ? '批准' : '拒绝'}
                  </button>
                ))}
              </div>
            </article>
          ))}
        </div>
      )}
      <label>你的备注（可选）<textarea rows={2} value={comment} onChange={(event) => setComment(event.target.value)} placeholder="补充边界、风险或需要修改的内容" /></label>
      <footer>
        <button type="button" className="danger-button" onClick={() => onDecide('reject', comment)}>终止研究</button>
        <button type="button" className="secondary-button" onClick={() => onDecide('revise', comment)}>退回修改</button>
        <button type="button" className="primary-button" onClick={() => onDecide('approve', comment)}>{gate === 'H1' ? '确认并继续' : gate === 'H2' ? '冻结方案并执行' : gate === 'H3' ? '确认授权结论' : '确认交付并封存'}</button>
      </footer>
    </section>
  )
}

const mockArtifactKindText = { figure: '图', table: '表', document: '文档', data: '数据' } as const

export function MockTaskStream({ task, onGateDecision, onOpenDrawer }: {
  task: MockTask
  onGateDecision: (gate: MockTask['currentGate'] & string, action: MockGateAction, comment?: string) => void
  onOpenDrawer: () => void
}) {
  const [notes, setNotes] = useState<string[]>([])
  const [noteDraft, setNoteDraft] = useState('')
  const progressKey = task.stages.map((stage) => `${stage.status}:${stage.revealed}`).join('|')
  const endRef = useAutoScroll(`${progressKey}|${notes.length}`)

  function stageVisual(stage: MockStage): 'pending' | 'active' | 'waiting' | 'done' | 'problem' {
    if (stage.status === 'waiting_gate') return 'waiting'
    if (stage.status === 'running') return 'active'
    if (stage.status === 'done') return stage.gateDecision === 'reject' ? 'problem' : 'done'
    if (stage.status === 'skipped') return 'problem'
    return 'pending'
  }

  return (
    <div className="stream">
      <div className="stream__scroll">
        <div className="stream__inner">
          <p className="stream__demo-badge">预置示范研究 · 完整流程已封存，可稳定复现</p>
          {task.stages.map((stage) => {
            const visual = stageVisual(stage)
            if (stage.status === 'pending' || stage.status === 'skipped') {
              return (
                <section className={`stream-stage is-${visual}`} key={stage.key}>
                  <StageNode state={visual === 'problem' ? 'problem' : 'pending'} gate={stage.gate} />
                  <div className="stream-stage__body">
                    <p className="stream-stage__eyebrow">{stage.eyebrow}</p>
                    <h2>{stage.label}</h2>
                    <p className="stream-stage__pending">{stage.status === 'skipped' ? '流程已终止，本阶段跳过。' : '等待上游阶段完成。'}</p>
                  </div>
                </section>
              )
            }
            return (
              <section className={`stream-stage is-${visual}`} key={stage.key}>
                <StageNode state={visual} gate={stage.gate} />
                <div className="stream-stage__body">
                  <p className="stream-stage__eyebrow">{stage.eyebrow}</p>
                  <h2>{stage.label}</h2>
                  <div className="stream-stage__lines">
                    {stage.lines.slice(0, stage.revealed).map((line, index) => (
                      <p className="stream-line" key={index}>{line}</p>
                    ))}
                    {stage.status === 'running' && stage.revealed < stage.lines.length && (
                      <p className="stream-line stream-line--typing"><LoaderCircle size={13} className="spin" />正在推进…</p>
                    )}
                  </div>
                  {stage.revealed >= stage.lines.length && stage.artifacts.length > 0 && (
                    <div className="stream-stage__artifacts">
                      {stage.artifacts.map((artifact) => (
                        <button type="button" className="stream-artifact" key={artifact.id} onClick={onOpenDrawer}>
                          <span>{mockArtifactKindText[artifact.kind]}</span>
                          <strong>{artifact.name}</strong>
                          <small>{artifact.note}</small>
                        </button>
                      ))}
                    </div>
                  )}
                  {stage.status === 'waiting_gate' && stage.gate && (
                    <MockGateCard stage={stage} onDecide={(action, comment) => onGateDecision(stage.gate!, action, comment)} />
                  )}
                  {stage.gateDecision === 'approve' && <p className="stream-stage__decision">已批准{stage.gateComment ? ` · ${stage.gateComment}` : ''}</p>}
                  {stage.gateDecision === 'reject' && <p className="stream-stage__decision is-reject">已拒绝并终止{stage.gateComment ? ` · ${stage.gateComment}` : ''}</p>}
                </div>
              </section>
            )
          })}
          {task.status === 'completed' && (
            <section className="stream-final">
              <h2>成果已封存</h2>
              <p>研究计划、执行结果、结论台账与研究报告初稿已完成封存。</p>
              <button type="button" className="secondary-button" onClick={onOpenDrawer}>查看工作区文件</button>
            </section>
          )}
          {notes.map((note, index) => (
            <div className="stream-note" key={index}><span>备注</span><p>{note}</p></div>
          ))}
          <div ref={endRef} />
        </div>
      </div>
      <div className="stream__dock">
        <form
          className="composer__box composer__box--mini"
          onSubmit={(event) => {
            event.preventDefault()
            const text = noteDraft.trim()
            if (!text) return
            setNotes((current) => [...current, text])
            setNoteDraft('')
          }}
        >
          <textarea
            rows={1}
            value={noteDraft}
            placeholder={task.status === 'waiting_human' ? `等待 ${task.currentGate} 决策 · 可先记录工作备注` : task.status === 'running' ? '任务推进中 · 记录工作备注' : '任务已结束 · 记录工作备注'}
            onChange={(event) => setNoteDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault()
                event.currentTarget.form?.requestSubmit()
              }
            }}
          />
        </form>
      </div>
    </div>
  )
}

/* ============================== 真实运行流 ============================== */

const runStatusText: Record<RunSnapshot['status'], string> = {
  created: '待启动',
  running: '运行中',
  waiting_human: '等待人工审核',
  blocked: '已阻塞',
  failed: '执行失败',
  completed: '已完成',
  stopped: '已终止',
  cancelled: '已取消',
}

const executionStatusText: Record<string, string> = {
  not_started: '待启动',
  succeeded: '成功',
  fixture_only: '仅流程演示',
  failed: '失败',
  blocked: '已阻塞',
}

const scientificStatusText: Record<string, string> = {
  not_evaluated: '待评估',
  not_assessed: '待评估',
  limited: '受限',
  supported: '获支持',
  failed: '未通过',
}

const providedStages = [
  { key: 'task_understanding', label: '任务理解' },
  { key: 'literature', label: '文献调研' },
  { key: 'hypothesis', label: '假设生成' },
]

function readableAnalysisUnit(value: string | undefined): string {
  return value === 'firm-region-year' ? '企业—地区—年份' : value || '等待确认'
}

const plainNodeTitles: Record<string, string> = {
  case_input: '研究材料已接收',
  intake_agent: '研究问题已规范化',
  input_validation: '边界与数据已检查',
  h1_gate: '等待确认研究边界',
  hypothesis_decomposer: '候选假设已拆解',
  data_profiler: '数据结构已检查',
  method_router: '识别策略已初选',
  h2_gate: '等待冻结研究方案',
  h3_gate: '等待审核证据结论',
  h4_gate: '等待确认最终交付',
}

export function RunTaskStream({ definition, run, busy, busyLabel, onGateDecision, onSubmitRevision, onRetryWriting, onOpenDrawer }: {
  definition: WorkflowDefinition
  run: RunSnapshot
  busy: boolean
  busyLabel: string
  onGateDecision: (gate: string, input: GateDecisionInput) => Promise<void>
  onSubmitRevision: (gate: 'H1' | 'H2', revision: unknown, comment: string) => Promise<void>
  onRetryWriting: () => Promise<void>
  onOpenDrawer: () => void
}) {
  const autoScrollEnabled = !['completed', 'blocked', 'failed', 'waiting_human'].includes(run.status)
  const endRef = useAutoScroll(`${run.id}:${run.version}:${run.status}`, autoScrollEnabled)
  const scrollRef = useRef<HTMLDivElement>(null)
  const [notes, setNotes] = useState<string[]>([])
  const [noteDraft, setNoteDraft] = useState('')
  useEffect(() => {
    if (autoScrollEnabled) return
    if (run.status === 'waiting_human') {
      window.requestAnimationFrame(() => {
        scrollRef.current?.querySelector('.human-review-card')?.scrollIntoView({ block: 'center', behavior: 'auto' })
      })
      return
    }
    scrollRef.current?.scrollTo({ top: 0, behavior: 'auto' })
  }, [autoScrollEnabled, run.id, run.status])
  const currentNode = definition.nodes.find((node) => node.id === run.currentNodeId)
  const returnedGate = run.status === 'blocked' ? returnedRevisionGate(run) : undefined
  const gateStageId = run.currentGate || returnedGate ? currentNode?.stageId : undefined
  const writingFailed = run.status === 'failed' && run.currentNodeId === 'scientific_writer'
  const approvedClaims = run.claims.filter((claim) => claim.decision === 'approve' || claim.decision === 'downgrade')
  const rejectedClaims = run.claims.filter((claim) => claim.decision === 'reject')
  const identificationFailure = run.manuscript?.mode === 'identification_failure_report'
  const isEngineeringComplete = run.status === 'completed' && run.executionStatus === 'succeeded'
  const isScienceLimited = run.scientificStatus === 'limited'
  const verdictTone = run.status === 'blocked' || run.status === 'failed'
    ? 'problem'
    : isEngineeringComplete && isScienceLimited
      ? 'limited'
      : isEngineeringComplete
        ? 'success'
        : 'active'
  const verdictTitle = isEngineeringComplete && isScienceLimited
    ? '工程链路已通过，科学结论受限'
    : isEngineeringComplete
      ? '研究执行与复现已完成'
      : run.status === 'waiting_human' && run.currentGate === 'H1'
        ? '研究边界已整理，等待你确认'
        : run.status === 'blocked'
          ? '研究已暂停，需要处理阻断项'
          : run.status === 'failed'
            ? '研究执行遇到问题'
            : '研究正在推进'
  const verdictDescription = isEngineeringComplete && isScienceLimited
    ? '统计执行、独立估计器复现和 H4 封存均已完成；冻结的 sign-switch 假设未获证据支持，因此不发布因果结论。'
    : run.status === 'waiting_human' && run.currentGate === 'H1'
      ? '我已核对研究问题、候选假设、变量与样本范围。确认后才会继续设计方法；此时还不会批准任何科学结论。'
      : run.lastError || '系统会把执行状态与科学结论分开记录，只允许发布得到证据支持的主张。'

  const gateByStage = new Map<string, string>()
  for (const node of definition.nodes) {
    if (node.kind !== 'gate') continue
    const match = /H[1-4]/.exec(node.title) ?? /h([1-4])_gate/i.exec(node.id)
    if (match) gateByStage.set(node.stageId, match[0].toUpperCase().startsWith('H') ? match[0].toUpperCase() : `H${match[1]}`)
  }

  function stageVisual(stage: WorkflowStage): 'pending' | 'active' | 'waiting' | 'done' | 'problem' {
    const state = stageState(stage, definition, run)
    if (state === 'complete') return 'done'
    if (state === 'problem') return 'problem'
    if (state === 'active') return run.status === 'waiting_human' ? 'waiting' : 'active'
    return 'pending'
  }

  return (
    <div className="stream">
      <div className="stream__scroll" ref={scrollRef}>
        <div className="stream__inner">
          {run.upstreamPackage && (
            <section className={`run-verdict is-${verdictTone}`} aria-label="本次真实运行结论">
              <div className="run-verdict__eyebrow">
                <span>HypoWeaver 研究助手</span>
                <strong>{run.status === 'completed' ? '已完成' : run.currentGate ? `${run.currentGate} · 等待人工确认` : runStatusText[run.status]}</strong>
              </div>
              <h2>{verdictTitle}</h2>
              <p>{verdictDescription}</p>
              <div className="run-verdict__metrics">
                <div><span>证据来源</span><strong>{run.upstreamPackage.evidenceRefCount ?? run.upstreamPackage.verifiedArtifactCount} 条已接入</strong></div>
                <div><span>分析单位</span><strong>{readableAnalysisUnit(run.caseSubmission?.unitOfAnalysis)}</strong></div>
                <div><span>数据状态</span><strong>{run.intakeReadiness?.canExecute ? '已具备执行条件' : '执行前需补充'}</strong></div>
                {run.claims.length > 0 && <div><span>结论审核</span><strong>{approvedClaims.length} 通过 / {rejectedClaims.length} 拒绝</strong></div>}
              </div>
            </section>
          )}
          {run.mode === 'fixture' && <p className="stream__demo-badge"><CircleAlert size={13} />当前未接入可执行数据，本次只能形成研究设计，不会生成实证结论。</p>}
          {run.upstreamPackage && (
            <section className={`stream-provided stream-upstream is-${run.intakeReadiness?.status ?? 'conditional'}`}>
              <p className="stream-stage__eyebrow">已检索证据</p>
              <div className="stream-provided__row">
                <span>{run.upstreamPackage.evidenceRefCount ?? run.upstreamPackage.verifiedArtifactCount} 条证据来源</span>
                <span>{run.caseSubmission?.hypotheses.length ?? 0} 条候选假设</span>
                <span>{run.caseSubmission?.variables.length ?? 0} 个候选变量</span>
                <span>{run.intakeReadiness?.canApproveH1 ? '可以确认研究边界' : '边界信息仍不完整'}</span>
              </div>
              {run.intakeReadiness?.blockers.length ? (
                <div className="stream-upstream__pending">
                  <strong>执行前还需补充 · 不阻止当前研究设计</strong>
                  <ul className="stream-upstream__blockers">
                    {run.intakeReadiness.blockers.slice(0, 4).map((blocker) => <li key={blocker}>{blocker}</li>)}
                  </ul>
                </div>
              ) : <small>证据材料与执行数据均已满足当前阶段要求。</small>}
            </section>
          )}
          {run.group2Feasibility && (
            <section className="stream-provided stream-feasibility">
              <p className="stream-stage__eyebrow">Group 2 可行性接管包</p>
              <div className="stream-provided__row">
                <span>交接已接收</span>
                <span>{run.group2Feasibility.goNoGoDecision}</span>
                <span>{run.group2Feasibility.dataMatrix.length} 项变量/数据审计</span>
                <span>{run.group2Feasibility.methodMatrix.length} 项方法审计</span>
                <span>科学十项 {run.group2Feasibility.scientificTen.length}/10</span>
              </div>
              <p className="stream-feasibility__decision">
                {run.intakeReadiness?.canExecute
                  ? '冻结核心 sign-switch 合同的真实面板与代码执行器已就绪；科学发布及机制扩展仍受权利、边界、分母口径和缺失变量约束。'
                  : run.group2Feasibility.decisionRationale}
              </p>
              <details className="stream-feasibility__details">
                <summary>查看科学十项 Proposal 草案</summary>
                <ol>
                  {run.group2Feasibility.scientificTen.map((item) => (
                    <li key={item.itemNo}>
                      <div><strong>{item.itemNo}. {item.title}</strong><span>{item.status}</span></div>
                      <p>{item.content}</p>
                      {item.unresolvedActions.length > 0 && <small>待办：{item.unresolvedActions.join('；')}</small>}
                    </li>
                  ))}
                </ol>
              </details>
            </section>
          )}
          <section className="stream-provided">
            <p className="stream-stage__eyebrow">研究基础</p>
            <div className="stream-provided__row">
              {providedStages.map((stage) => (
                <span key={stage.key}>{stage.label}</span>
              ))}
            </div>
            <small>研究问题、候选假设与变量定义已经接入；系统从研究边界确认开始继续推进。</small>
          </section>
          {definition.stages.map((stage) => {
            const visual = stageVisual(stage)
            const gate = gateByStage.get(stage.id)
            const attempts = run.steps.filter((step) => stage.nodeIds.includes(step.nodeId))
            const isGateHere = gateStageId === stage.id
            if (visual === 'pending') {
              return (
                <section className="stream-stage is-pending" key={stage.id}>
                  <StageNode state="pending" gate={gate} />
                  <div className="stream-stage__body">
                    <p className="stream-stage__eyebrow">研究进度 {stage.order}{gate ? ` · ${gate} 人工确认` : ''}</p>
                    <h2>{stage.title}</h2>
                    <p className="stream-stage__pending">等待上游阶段完成。</p>
                  </div>
                </section>
              )
            }
            return (
              <section className={`stream-stage is-${visual}`} key={stage.id}>
                <StageNode state={visual} gate={gate} />
                <div className="stream-stage__body">
                  <p className="stream-stage__eyebrow">研究进度 {stage.order}{gate ? ` · ${gate} 人工确认` : ''}</p>
                  <h2>{stage.title}</h2>
                  <p className="stream-stage__desc">{stage.description}</p>
                  {attempts.length > 0 && (
                    <div className="stream-stage__steps">
                      {attempts.map((attempt) => (
                        <button type="button" className={`stream-step is-${attempt.status}`} key={attempt.id} onClick={onOpenDrawer} title="在工作区文件中查看明细">
                          <span className={`step-status step-status--${attempt.status}`} />
                          {plainNodeTitles[attempt.nodeId] ?? definition.nodes.find((node) => node.id === attempt.nodeId)?.title ?? attempt.nodeId}
                        </button>
                      ))}
                    </div>
                  )}
                  {visual === 'active' && run.status === 'running' && (
                    <p className="stream-line stream-line--typing"><LoaderCircle size={13} className="spin" />{busy ? (busyLabel || '正在执行…') : `正在执行 · ${currentNode?.title ?? '处理中'}`}</p>
                  )}
                  {visual === 'problem' && run.lastError && stage.id === currentNode?.stageId && (
                    <div className="stream-error"><CircleAlert size={15} /><div><strong>失败原因</strong>{run.lastError}</div>{writingFailed && <button type="button" className="secondary-button" disabled={busy} onClick={() => void onRetryWriting()}><RotateCcw size={13} />重试写作</button>}</div>
                  )}
                  {isGateHere && (
                    <GateDecisionCard key={`${run.id}:${run.version}:${run.currentGate}`} run={run} busy={busy} onDecision={onGateDecision} onSubmitRevision={onSubmitRevision} />
                  )}
                </div>
              </section>
            )
          })}
          {run.status === 'completed' && (
            <section className="stream-final">
              <h2>{run.planOnly ? '研究计划已生成' : identificationFailure ? '识别失败报告已生成' : '成果已封存'}</h2>
              <p>执行 · {executionStatusText[run.executionStatus] ?? run.executionStatus} · 科学 · {scientificStatusText[run.scientificStatus] ?? run.scientificStatus}{run.manuscript ? ` · ${run.manuscript.sections.filter((section) => section.status === 'generated').length} 节` : ''}</p>
              {approvedClaims.slice(0, 3).map((claim) => (
                <p className="stream-claim" key={claim.id}><b>{claimDecisionText[claim.decision!]}</b>{claim.finalText ?? claim.text}</p>
              ))}
              <div className="stream-final__actions">
                <button type="button" className="secondary-button" onClick={onOpenDrawer}>论文与图表</button>
                {!run.planOnly && !identificationFailure && (
                  <button type="button" className="quiet-button" disabled={busy} onClick={() => void onRetryWriting()}><RotateCcw size={14} />重新生成论文</button>
                )}
              </div>
            </section>
          )}
          {notes.map((note, index) => (
            <div className="stream-note" key={`${run.id}-note-${index}`}><span>你的备注</span><p>{note}</p></div>
          ))}
          <div ref={endRef} />
        </div>
      </div>
      <div className="stream__dock">
        <form
          className="composer__box composer__box--mini task-note-composer"
          onSubmit={(event) => {
            event.preventDefault()
            const text = noteDraft.trim()
            if (!text) return
            setNotes((current) => [...current, text])
            setNoteDraft('')
          }}
        >
          <textarea
            rows={1}
            value={noteDraft}
            placeholder={run.status === 'waiting_human' ? `请先处理上方 ${run.currentGate} 人工确认，也可以在这里记录备注` : '补充研究要求或记录你的判断…'}
            onChange={(event) => setNoteDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault()
                event.currentTarget.form?.requestSubmit()
              }
            }}
          />
          <div className="task-note-composer__row">
            <small>{busy ? (busyLabel || '正在执行…') : run.status === 'waiting_human' ? `${run.currentGate} 等待你的确认` : runStatusText[run.status]}</small>
            <button type="submit" className="composer__send" disabled={!noteDraft.trim()} aria-label="记录备注"><ArrowUp size={15} /></button>
          </div>
        </form>
      </div>
    </div>
  )
}
