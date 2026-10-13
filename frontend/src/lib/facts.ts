import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { AnalysisRun } from '../api/analysis'
import type { StudyPlan } from '../api/plans'
import type { Dataset } from '../api/datasets'

interface ClaimLite {
  claim_id: string
  max_strength: string
  chosen_strength: string
  user_decision: string
  verdict: string
}

/** 总览与右侧栏共用：组合现有接口，不依赖 overview metrics */
export function useProjectFacts(id: string | undefined) {
  const on = !!id
  const evidence = useQuery({
    queryKey: ['evidence', id],
    queryFn: () => api<{ id: string; included: boolean }[]>(`/projects/${id}/evidence`),
    enabled: on,
  })
  const sets = useQuery({
    queryKey: ['candidate-sets', id],
    queryFn: () => api<{ id: string; candidates: unknown[] }[]>(`/projects/${id}/candidate-sets`),
    enabled: on,
  })
  const plans = useQuery({
    queryKey: ['plans', id],
    queryFn: () => api<StudyPlan[]>(`/projects/${id}/plans`),
    enabled: on,
  })
  const runs = useQuery({
    queryKey: ['runs', id],
    queryFn: () => api<AnalysisRun[]>(`/projects/${id}/runs`),
    enabled: on,
  })
  const datasets = useQuery({ queryKey: ['datasets'], queryFn: () => api<Dataset[]>('/datasets') })
  const run = runs.data?.find((r) => r.result && !r.stale) || runs.data?.find((r) => r.result)
  const claims = useQuery({
    queryKey: ['claims', run?.id],
    queryFn: () => api<ClaimLite[]>(`/runs/${run!.id}/claims`),
    enabled: !!run,
  })
  const plan = plans.data?.[0]
  const dataset = datasets.data?.find((d) => d.id === run?.dataset_id)
  const claim = mainClaim(claims.data, run)
  return {
    evidenceCount: evidence.data?.filter((c) => c.included).length,
    candidateCount: sets.data?.[0]?.candidates.length,
    plan,
    runCount: runs.data?.length,
    run,
    dataset,
    strength: claim ? claim.chosen_strength || claim.max_strength : undefined,
    /** 主结论被研究者暂缓或拒绝时提示，强度仍按主结论显示 */
    strengthDecision: claim?.user_decision,
  }
}

/**
 * 汇总处的“结论强度”取主结论：运行快照里方案 claims_planned 中 type === 'main' 的那条
 * （后端 claims/service.py 也按 claim["type"] == "main" 给出强度上限）。
 * 不对所有结论（含暂缓/拒绝、机制或边界结论）取最弱值。
 * 回退顺序：claim_id === 'main' → 第一条未暂缓/拒绝的结论 → 第一条。
 */
export function mainClaim<C extends ClaimLite>(
  claims: C[] | undefined,
  run: Pick<AnalysisRun, 'plan_snapshot'> | undefined,
): C | undefined {
  if (!claims?.length) return undefined
  const planned = (
    run?.plan_snapshot as { claims_planned?: { id: string; type: string }[] } | undefined
  )?.claims_planned
  const mainIds = new Set((planned || []).filter((c) => c.type === 'main').map((c) => c.id))
  return (
    claims.find((c) => mainIds.has(c.claim_id)) ||
    claims.find((c) => c.claim_id === 'main') ||
    claims.find((c) => !['deferred', 'rejected'].includes(c.user_decision)) ||
    claims[0]
  )
}
