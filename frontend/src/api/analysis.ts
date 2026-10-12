export interface Estimate {
  coef: number
  se: number
  t?: number
  p: number
  ci: number[]
  n_obs: number
  n_units?: number
  r2_within?: number
  target?: string
}
export interface AnalysisResult {
  main: Estimate
  event: null | {
    terms: { k: number; coef: number; se: number; p: number; ci: number[] }[]
    reference: number
    pretrend_wald: { stat: number | null; p: number | null; df: number }
    omitted_bins: number[]
    n_obs: number
    n_units: number
    excluded_nonmonotone_units: number
  }
  robustness: (Partial<Estimate> & { id: string; change: string; status: string; error?: string })[]
  permutation: null | {
    p: number
    n: number
    requested_n: number
    observed: number
    distribution: number[]
    n_obs: number
    n_units: number
    elapsed_seconds: number
    note: string
    excluded_incomplete_units: number
  }
  sample_report: {
    input_rows: number
    n_valid: number
    dropped_by_reason: Record<string, number>
    n_clusters: number
  }
  warnings: string[]
}
export interface AnalysisRun {
  id: string
  plan_id: string
  dataset_id: string
  status: string
  stale: boolean
  created_at: string
  job_id: string
  error: string | null
  steps: Record<string, { status: string; error: string | null }>
  result: AnalysisResult | null
  plan_snapshot: { version: number; method_family: string; boundary_notes: string }
  spec: { cluster: string; controls: string[]; outcome: string; treatment: string }
  reproduction: null | {
    consistent: boolean
    max_relative_diff: number
    method: string
    rows: {
      id: string
      label: string
      status: string
      error?: string
      estimate?: Estimate
      original?: Estimate
      max_relative_diff?: number
    }[]
  }
}
