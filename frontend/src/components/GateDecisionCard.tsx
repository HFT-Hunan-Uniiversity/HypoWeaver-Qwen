/**
 * GateDecisionCard：H1–H4 人工闸门决策卡（自 ExecutionWorkspace 抽取）。
 * 逻辑保持不变：候选选择（H2）、逐条 Claim 授权（H3）、终稿审核（H4）、结构化修订（H1/H2）。
 * 在 TaskStream 会话流中内嵌渲染。
 */
import { ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import type { ClaimDecision, ClaimRecord, GateDecisionInput, ManuscriptStatementSourceView, RunSnapshot } from '../runtime/types'

export const claimDecisionText: Record<ClaimDecision, string> = {
  approve: 'H3 已批准',
  downgrade: 'H3 已降级授权',
  reject: 'H3 已拒绝',
  hold: 'H3 已暂缓',
}

const allClaimDecisions: ClaimDecision[] = ['approve', 'downgrade', 'reject', 'hold']
const claimAdmissionText: Record<string, string> = {
  unassessed: '旧版未评估',
  admitted: '已准入',
  downgrade_required: '必须降级',
  prohibited: '禁止使用',
  rejected: '已拒绝准入',
}

const designStrategyLabels = {
  direct_baseline: '直接基准',
  identification_first: '识别优先',
  measurement_robustness: '测量稳健性优先',
} as const

const gateTitles = {
  H1: '确认研究边界并继续设计',
  H2: '确认研究方案并冻结',
  H3: '审核证据与结论',
  H4: '确认最终交付并封存',
} as const

const gateNotes = {
  H1: '确认研究问题、假设、变量和样本边界；这一步不代表科学结论获批。',
  H2: '执行前冻结数据、识别策略、模型与诊断，避免事后改变研究口径。',
  H3: '逐条核对复现结果与证据强度，只有获得支持的主张可以进入论文。',
  H4: '核对报告、限制说明和复现材料，确认后生成不可变的最终成果包。',
} as const

const statementKindText: Record<ManuscriptStatementSourceView['kind'], string> = {
  authorized_claim: '获批结论',
  estimate_fact: '估计事实',
  sample_fact: '样本事实',
  diagnostic_fact: '诊断事实',
  citation: '核验引文',
}

export function StatementProvenance({ statements }: { statements: ManuscriptStatementSourceView[] }) {
  if (!statements.length) return null
  return <details className="statement-provenance">
    <summary>语句来源 · {statements.length} 条</summary>
    <ul>{statements.map((statement) => <li key={statement.id}>
      <strong>{statementKindText[statement.kind] ?? statement.kind}</strong>
      <span>{statement.id}</span>
      {statement.sources.length > 0 && <small>{statement.sources.map((source) => `${source.kind} · ${source.id} · ${source.path}`).join('；')}</small>}
    </li>)}</ul>
  </details>
}

export function permittedClaimDecisions(claim: ClaimRecord, fixture: boolean): ClaimDecision[] {
  if (fixture) return ['reject', 'hold']
  if (claim.admissionStatus === 'admitted' && !['insufficient', 'prohibited'].includes(claim.allowedStrength ?? '')) {
    return ['approve', 'downgrade', 'reject', 'hold']
  }
  if (claim.admissionStatus === 'downgrade_required' && !['insufficient', 'prohibited'].includes(claim.allowedStrength ?? '')) {
    return ['downgrade', 'reject', 'hold']
  }
  if (claim.admissionStatus === 'prohibited' || claim.admissionStatus === 'rejected' || claim.allowedStrength === 'prohibited') {
    return ['reject', 'hold']
  }
  return ['approve', 'downgrade', 'reject', 'hold']
}

export function revisionSeed(run: RunSnapshot, gate: 'H1' | 'H2'): string {
  const nodeId = gate === 'H1' ? 'h1_gate' : 'h2_gate'
  const waitingSource = [...run.steps].reverse().find((step) => step.nodeId === nodeId && step.status === 'waiting_human')?.input
  const blockedPlan = gate === 'H2'
    ? [...run.steps].reverse().find((step) => ['plan_revision', 'analysis_plan_merge'].includes(step.nodeId) && ['succeeded', 'blocked'].includes(step.status))?.output
    : undefined
  const source = waitingSource ?? blockedPlan
  const sourceRecord = source && typeof source === 'object' && !Array.isArray(source)
    ? source as Record<string, unknown>
    : {}
  const editable = gate === 'H2' && sourceRecord.analysis_plan && typeof sourceRecord.analysis_plan === 'object' && !Array.isArray(sourceRecord.analysis_plan)
    ? sourceRecord.analysis_plan
    : sourceRecord
  const value = editable && typeof editable === 'object' && !Array.isArray(editable)
    ? JSON.parse(JSON.stringify(editable)) as Record<string, unknown>
    : {}
  if (gate === 'H1') {
    delete value.input_conflicts
    delete value.missing_required_information
  } else {
    value.plan_version = Number(value.plan_version ?? 0) + 1
  }
  return JSON.stringify(value, null, 2)
}

export function returnedRevisionGate(run: RunSnapshot): 'H1' | 'H2' | undefined {
  const blockedByCritic = [...run.steps].reverse().find((step) => step.nodeId === run.currentNodeId)
  if (['critic_merge', 'design_arena_merge'].includes(run.currentNodeId ?? '') && blockedByCritic?.status === 'blocked') return 'H2'
  const latestDecision = [...run.steps].reverse().find((step) => (
    step.status === 'succeeded' && ['h1_gate', 'h2_gate'].includes(step.nodeId)
  ))
  const action = latestDecision?.output && typeof latestDecision.output === 'object' && !Array.isArray(latestDecision.output)
    ? (latestDecision.output as Record<string, unknown>).action
    : undefined
  if (action !== 'revise') return undefined
  if (latestDecision?.nodeId === 'h1_gate' && run.currentNodeId === 'input_validation') return 'H1'
  if (latestDecision?.nodeId === 'h2_gate' && run.currentNodeId === 'analysis_plan_merge') return 'H2'
  return undefined
}

export function GateDecisionCard({ run, busy, onDecision, onSubmitRevision }: {
  run: RunSnapshot
  busy: boolean
  onDecision: (gate: string, input: GateDecisionInput) => Promise<void>
  onSubmitRevision: (gate: 'H1' | 'H2', revision: unknown, comment: string) => Promise<void>
}) {
  const returnedGate = run.status === 'blocked' ? returnedRevisionGate(run) : undefined
  const gate = run.currentGate ?? returnedGate
  const returnedForRevision = Boolean(returnedGate)
  const blockedByCritic = returnedGate === 'H2' && ['critic_merge', 'design_arena_merge'].includes(run.currentNodeId ?? '')
  const criticOutput = blockedByCritic
    ? [...run.steps].reverse().find((step) => step.nodeId === run.currentNodeId)?.output
    : undefined
  const criticIssues = criticOutput && typeof criticOutput === 'object' && !Array.isArray(criticOutput)
    ? (criticOutput as Record<string, unknown>).issues
    : undefined
  const [comment, setComment] = useState('')
  const [decisions, setDecisions] = useState<Record<string, ClaimDecision>>({})
  const [finalTexts, setFinalTexts] = useState<Record<string, string>>({})
  const [showRevision, setShowRevision] = useState(returnedForRevision)
  const [revisionText, setRevisionText] = useState(() => gate === 'H1' || gate === 'H2' ? revisionSeed(run, gate) : '')
  const [revisionError, setRevisionError] = useState<string | null>(null)
  const [selectedCandidateId, setSelectedCandidateId] = useState(run.designArena?.provisionalCandidateId ?? '')
  if (!gate || (run.status !== 'waiting_human' && !returnedForRevision)) return null
  const fixtureH3 = gate === 'H3' && (run.mode === 'fixture' || run.planOnly)
  const allClaimsReady = gate !== 'H3' || (Boolean(run.claims.length) && run.claims.every((claim) => {
    const decision = decisions[claim.id] ?? claim.decision
    return Boolean(decision)
      && permittedClaimDecisions(claim, fixtureH3).includes(decision!)
      && (decision !== 'downgrade' || Boolean(finalTexts[claim.id]?.trim()))
      && (!(decision === 'approve' && /\d/.test(claim.text)) || Boolean(finalTexts[claim.id]?.trim()))
  }))
  const selectedCandidateReady = gate !== 'H2'
    || !run.designArena
    || run.designArena.recommendedCandidateIds.includes(selectedCandidateId)
  const willGenerateFailureReport = gate === 'H3' && !fixtureH3 && !run.claims.some((claim) => {
    const decision = decisions[claim.id] ?? claim.decision ?? 'reject'
    return decision === 'approve' || decision === 'downgrade'
  })
  const caseInput = run.caseSubmission
  const exposure = caseInput?.variables.find((item) => item.role === 'treatment' || item.role === 'exposure')
  const outcomes = caseInput?.variables.filter((item) => item.role === 'outcome') ?? []
  const analysisUnit = caseInput?.unitOfAnalysis === 'firm-region-year' ? '企业—地区—年份' : caseInput?.unitOfAnalysis
  const samplePeriod = caseInput?.samplePeriod.replace(/^Literature coverage\s*/i, '文献覆盖 ')
  const reviewTitle = blockedByCritic
    ? '处理关键审查问题后重新提交'
    : returnedForRevision
      ? `继续修改${gate === 'H1' ? '研究边界' : '研究方案'}`
      : gateTitles[gate]
  const reviewNote = blockedByCritic
    ? '当前方案未通过审查。请按意见修改并重新提交；通过后才会开放下一步。'
    : returnedForRevision
      ? '上一次退回已经记录；修改结构化内容后可重新提交，刷新页面也不会丢失任务状态。'
      : gateNotes[gate]

  async function submitH3() {
    const claimDecisions = run.claims.map((claim) => ({
      claimId: claim.id,
      decision: decisions[claim.id] ?? claim.decision ?? (fixtureH3 ? 'hold' : 'reject'),
      finalText: finalTexts[claim.id]?.trim() || undefined,
      reason: comment,
    }))
    const hasAdmittedClaim = claimDecisions.some(({ decision }) => decision === 'approve' || decision === 'downgrade')
    await onDecision('H3', {
      action: fixtureH3
        ? 'generate_plan_only'
        : hasAdmittedClaim
          ? 'approve'
          : 'generate_identification_failure_report',
      comment,
      claims: claimDecisions,
    })
  }

  function openRevision() {
    if (gate !== 'H1' && gate !== 'H2') return
    setRevisionText(revisionSeed(run, gate))
    setRevisionError(null)
    setShowRevision(true)
  }

  async function submitRevision() {
    if (gate !== 'H1' && gate !== 'H2') return
    try {
      const revision = JSON.parse(revisionText) as unknown
      if (!revision || typeof revision !== 'object' || Array.isArray(revision)) throw new Error('修订内容必须是一个 JSON 对象。')
      setRevisionError(null)
      await onSubmitRevision(gate, revision, comment)
    } catch (reason) {
      setRevisionError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  return (
    <section className="human-review-card">
      <header><ShieldCheck size={22} /><div><div className="review-card__title-row"><strong>{reviewTitle}</strong><span>{gate}</span></div><p>{reviewNote}</p></div></header>
      {gate === 'H1' && caseInput && (
        <section className="gate-scope" aria-label="本次研究边界摘要">
          <div className="gate-scope__wide"><span>研究问题</span><strong>{caseInput.researchQuestion}</strong></div>
          <div><span>主要假设</span><strong>{caseInput.hypotheses[0]?.statement ?? '尚未提供候选假设'}</strong></div>
          <div><span>核心变量</span><strong>{[exposure?.label, ...outcomes.map((item) => item.label)].filter(Boolean).join(' → ') || `${caseInput.variables.length} 个候选变量`}</strong></div>
          <div><span>分析单位</span><strong>{analysisUnit || '待确认'}</strong></div>
          <div><span>时间边界</span><strong>{samplePeriod || '待确认'}</strong></div>
        </section>
      )}
      {blockedByCritic && Array.isArray(criticIssues) && <ul className="review-issue-list">{criticIssues.map((issue, index) => {
        const item = issue && typeof issue === 'object' && !Array.isArray(issue) ? issue as Record<string, unknown> : {}
        return <li key={`${String(item.issue_id ?? 'issue')}-${index}`}><strong>{String(item.severity ?? 'issue')}</strong><span>{String(item.evidence ?? item.why_it_matters ?? '请查看 CriticReport 输出。')}</span><small>需要修改：{String(item.required_fix ?? '请根据审查意见补充研究设计。')}</small></li>
      })}</ul>}
      {gate === 'H2' && run.designArena && <section className="design-candidate-list" aria-label="可行研究设计候选">
        {run.designArena.candidates.map((candidate) => {
          const recommended = run.designArena?.recommendedCandidateIds.includes(candidate.id)
          return <label key={candidate.id} className={`design-candidate ${selectedCandidateId === candidate.id ? 'is-selected' : ''} ${recommended ? '' : 'is-unavailable'}`}>
            <input type="radio" name="design-candidate" value={candidate.id} checked={selectedCandidateId === candidate.id} disabled={!recommended} onChange={() => setSelectedCandidateId(candidate.id)} />
            <span><strong>{designStrategyLabels[candidate.strategy]}</strong><small>{candidate.methodFamily} · {candidate.estimator || '估计器待确认'}</small></span>
            <em>Probe {candidate.probeVerdict} · Reviewer 问题 {candidate.reviewIssueCount}</em>
            <p>{candidate.rationale}</p>
            {candidate.formula && <code>{candidate.formula}</code>}
            <details><summary>查看 Probe 检查</summary><ul>{candidate.probeChecks.map((check) => <li key={check.id}><strong>{check.status}</strong> {check.evidence}</li>)}</ul></details>
          </label>
        })}
        <p className="design-arena-note">不按总分或多数票自动选“赢家”；不可执行、目标错配或存在 critical 问题的候选不能冻结。</p>
      </section>}
      {gate === 'H3' && <div className="claim-review-list">{run.claims.map((claim) => {
        const permitted = permittedClaimDecisions(claim, fixtureH3)
        const selected = decisions[claim.id] ?? claim.decision
        return <article key={claim.id}>
          <p>{claim.text}</p>
          <div className="claim-gate-summary">
            <small>Gate：{claimAdmissionText[claim.admissionStatus ?? 'unassessed'] ?? claim.admissionStatus}</small>
            <small>代码上限：{claim.maxAllowedStrength ?? claim.allowedStrength ?? '未指定'}</small>
            <small>候选强度：{claim.allowedStrength ?? '未指定'}</small>
          </div>
          {claim.requiredCheckIds.length > 0 && <details><summary>必做检查 · {claim.requiredCheckIds.length}</summary><ul>{claim.requiredCheckIds.map((checkId) => <li key={checkId}>{checkId}</li>)}</ul></details>}
          {claim.gateReasons.length > 0 && <details open><summary>Gate 理由 · {claim.gateReasons.length}</summary><ul>{claim.gateReasons.map((reason, index) => <li key={`${claim.id}-reason-${index}`}>{reason}</li>)}</ul></details>}
          <div>{allClaimDecisions.map((decision) => <button type="button" key={decision} disabled={!permitted.includes(decision)} aria-pressed={selected === decision} className={selected === decision ? 'is-selected' : ''} onClick={() => setDecisions((current) => ({ ...current, [claim.id]: decision }))}>{{ approve: '批准', downgrade: '降级', reject: '拒绝', hold: '暂缓' }[decision]}</button>)}</div>
          {(selected === 'approve' || selected === 'downgrade') && <textarea value={finalTexts[claim.id] ?? ''} onChange={(event) => setFinalTexts((current) => ({ ...current, [claim.id]: event.target.value }))} placeholder={selected === 'downgrade' ? '填写降级后的审慎表述' : /\d/.test(claim.text) ? '候选含裸数字，必须填写不含数字的安全表述' : '可选：填写最终授权表述'} />}
        </article>
      })}</div>}
      {gate === 'H4' && run.manuscript && <section className="h4-manuscript-review"><p><strong>{run.manuscript.mode === 'identification_failure_report' ? '识别失败报告' : '论文初稿'} v{run.manuscript.version}</strong> · IR {run.manuscript.irVersion} · {run.manuscript.sections.length} 节 · {run.manuscript.auditResult === 'pass_with_no_critical_issues' ? '一致性审计通过' : '需要修订'}</p>{run.manuscript.sections.map((section) => <details key={section.id}><summary>{section.title}</summary><div className="manuscript-copy">{section.content}</div><StatementProvenance statements={section.statements} /></details>)}</section>}
      {fixtureH3 && <p className="fixture-warning">本次没有真实实证结果，每条 Claim 只能拒绝或暂缓；提交后仅生成研究计划。</p>}
      {!returnedForRevision && <label>你的备注（可选）<textarea rows={3} value={comment} onChange={(event) => setComment(event.target.value)} placeholder={gate === 'H4' ? '如需退回，请写明需要修改的章节和具体问题' : '补充边界、风险或需要修改的内容'} /></label>}
      {showRevision && (gate === 'H1' || gate === 'H2') && <section className="revision-editor"><header><div><strong>{gate} 结构化修订</strong><p>{gate === 'H1' ? '修改 CaseSubmission 后，系统会重新执行 Intake 与输入校验，再回到 H1。' : '修改 AnalysisPlan 后，系统会重新执行四类 Critic；plan_version 已自动加一。'}</p></div></header><textarea aria-label={`${gate} 结构化修订 JSON`} rows={18} spellCheck={false} value={revisionText} onChange={(event) => setRevisionText(event.target.value)} />{revisionError && <p className="revision-error" role="alert">{revisionError}</p>}<footer>{!returnedForRevision && <button type="button" className="secondary-button" disabled={busy} onClick={() => setShowRevision(false)}>取消修订</button>}<button type="button" className="primary-button" disabled={busy} onClick={submitRevision}>提交修订并重新校验</button></footer></section>}
      {!returnedForRevision && <footer><button type="button" className="danger-button" disabled={busy} onClick={() => onDecision(gate, { action: 'reject', comment })}>终止研究</button>{gate !== 'H3' && <button type="button" className="secondary-button" disabled={busy || (gate === 'H4' && !comment.trim())} onClick={() => gate === 'H4' ? onDecision('H4', { action: 'revise', comment }) : openRevision()}>{gate === 'H4' ? '退回重写' : '退回修改'}</button>}{gate === 'H3' ? <button type="button" className="primary-button" disabled={busy || !allClaimsReady} onClick={submitH3}>{fixtureH3 ? '生成研究计划成果' : willGenerateFailureReport ? '生成识别失败报告' : '确认授权结论'}</button> : <button type="button" className="primary-button" disabled={busy || !selectedCandidateReady} onClick={() => onDecision(gate, { action: 'approve', comment, ...(gate === 'H2' && selectedCandidateId ? { selectedCandidateId } : {}) })}>{gate === 'H1' ? '确认并继续' : gate === 'H2' ? '冻结方案并执行' : '确认交付并封存'}</button>}</footer>}
    </section>
  )
}
