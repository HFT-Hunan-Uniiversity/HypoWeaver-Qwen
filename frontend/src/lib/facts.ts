import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { AnalysisRun } from '../api/analysis'
import type { StudyPlan } from '../api/plans'
import type { Dataset } from '../api/datasets'

interface ClaimLite {
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
  const claim = claims.data?.[0]
  return {
    evidenceCount: evidence.data?.filter((c) => c.included).length,
    candidateCount: sets.data?.[0]?.candidates.length,
    plan,
    runCount: runs.data?.length,
    run,
    dataset,
    strength: claim ? claim.chosen_strength || claim.max_strength : undefined,
  }
}
