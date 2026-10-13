export interface Variable {
  role: string
  name: string
  definition: string
  uncertain: boolean
}
export interface Robustness {
  id: string
  change: string
  kind: string
  args: { years?: number[]; outcome?: string; controls?: string[] }
}
/** R5：方案起草时给出的建议绑定，role_name → {field} 或 {formula}（可缺省） */
export type SuggestedBinding = Record<string, { field: string } | { formula: string }>
export interface StudyPlan {
  suggested_binding?: SuggestedBinding | null
  id: string
  project_id: string
  candidate_id: string
  version: number
  status: string
  stale: boolean
  method_family: string
  variables: Variable[]
  model: {
    fixed_effects: string[]
    cluster: string
    event_window: number[]
    bins: number[]
    identification_assumptions: string[]
  }
  robustness: Robustness[]
  permutation: { n: number; seed: number }
  decision_rules: {
    expected_sign: number
    alpha: number
    pretrend_alpha: number
    robustness_share: number
    permutation_alpha: number
  }
  claims_planned: { id: string; text: string; type: string }[]
  boundary_notes: string
  treatment_is_real_assignment: boolean
  /** R2-01：处理变量所绑定字段的语义；后端未提供时为 undefined */
  treatment_semantics?: 'real_assignment' | 'peer_exposure' | 'unknown' | null
  /** 生成该版本的模型名（plan.model 是统计模型设定，勿混用） */
  llm_model?: string | null
}
export const methods: Record<string, string> = {
  policy_causal: '政策 DID 框架',
  panel_association: '面板关联',
  mechanism_boundary: '机制与边界线索',
}
export const roles: Record<string, string> = {
  outcome: '结果变量',
  treatment: '处理 / 核心解释变量',
  control: '控制变量',
  mechanism: '机制变量',
  moderator: '调节变量',
  unit: '个体标识',
  time: '时间标识',
}
export const robustKinds: Record<string, string> = {
  drop_controls: '去掉控制变量',
  exclude_years: '剔除年份',
  monotone_only: '仅单调处理路径',
  alt_outcome: '替换结果变量',
  add_controls: '增加控制变量',
}
export const semanticsLabels: Record<string, string> = {
  real_assignment: '真实分配',
  peer_exposure: '同群 / 暴露',
  unknown: '未知',
}
export const levelLabels: Record<string, string> = {
  firm: '企业',
  industry: '行业',
  region: '地区',
  other: '其他',
}
