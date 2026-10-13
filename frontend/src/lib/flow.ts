/**
 * 研究流程（向导）状态模型 —— 见 docs/flow.md、GLOSSARY.md、docs/adr/0001。
 * 纯函数：输入后端阶段状态 + 本地流程记录，输出每个阶段的 锁定/进行中/已确认/需要更新。
 * 由 prototype/flow/flowMachine.ts 提炼而来。
 */
import type { Stage } from '../api/client'

export const FLOW_ORDER = [
  'direction',
  'literature',
  'candidates',
  'plan',
  'data',
  'proposal',
] as const
export type StageKey = (typeof FLOW_ORDER)[number]
export type FlowStatus = 'locked' | 'active' | 'confirmed' | 'stale'

/** 本地流程记录（后端缺少阶段级"确认/版本"接口时的前端补位，按项目存 localStorage） */
export interface LocalFlow {
  /** 已确认的阶段 → 版本号 */
  confirmed: Partial<Record<StageKey, number>>
  /** 正在编辑（已解锁重改）的已确认阶段 */
  editing: Partial<Record<StageKey, boolean>>
  /** 因上游新版本而需要更新的阶段（后端未传播时的补充） */
  stale: Partial<Record<StageKey, boolean>>
}
export const emptyLocal = (): LocalFlow => ({ confirmed: {}, editing: {}, stale: {} })

export interface FlowStage {
  key: StageKey
  status: FlowStatus
  version: number
  /** 后端原始状态 */
  backend: string
  summary?: string
}

/** 后端状态表示"该阶段有实质进展" */
const touched = (s?: Stage) => !!s && s.status !== 'not_started'

export function deriveFlow(stages: Stage[], local: LocalFlow): FlowStage[] {
  const by = (k: string) => stages.find((s) => s.key === k)
  const out: FlowStage[] = []
  let open = true // 前面阶段都已确认 / 需更新 → 本阶段可进入
  FLOW_ORDER.forEach((key, i) => {
    const s = by(key)
    const later = FLOW_ORDER.slice(i + 1).some((k) => touched(by(k)))
    const v = local.confirmed[key] ?? 0
    let status: FlowStatus
    if (local.editing[key]) status = 'active'
    else if (s?.status === 'stale' || local.stale[key]) status = open ? 'stale' : 'locked'
    // 后端已完成 + 用户确认过（或下游已有进展，说明此前流程中已确认）
    else if (s?.status === 'completed' && (v > 0 || later)) status = 'confirmed'
    else status = open ? 'active' : 'locked'
    out.push({
      key,
      status,
      version: Math.max(v, status === 'confirmed' ? 1 : 0),
      backend: s?.status || 'not_started',
      summary: s?.summary,
    })
    if (status === 'active' || status === 'locked') open = false
  })
  return out
}

/** 下一个需要用户处理的阶段（进行中或需要更新） */
export function nextFlowStage(flow: FlowStage[]): FlowStage | undefined {
  return flow.find((s) => s.status === 'active' || s.status === 'stale')
}

/** 修改某阶段会影响的下游阶段数（已确认或需要更新的） */
export function downstreamCount(flow: FlowStage[], key: StageKey): number {
  const i = FLOW_ORDER.indexOf(key)
  return flow.slice(i + 1).filter((s) => s.status === 'confirmed' || s.status === 'stale').length
}

/** 确认并进入下一阶段：锁定版本；若是编辑后的确认，下游全部标为需要更新 */
export function confirmStage(local: LocalFlow, flow: FlowStage[], key: StageKey): LocalFlow {
  const wasEdit = !!local.editing[key]
  const i = FLOW_ORDER.indexOf(key)
  const stale = { ...local.stale, [key]: false }
  if (wasEdit)
    for (const s of flow.slice(i + 1))
      if (s.status === 'confirmed' || s.status === 'stale') stale[s.key] = true
  return {
    confirmed: { ...local.confirmed, [key]: (local.confirmed[key] ?? (flow[i]?.version || 0)) + 1 },
    editing: { ...local.editing, [key]: false },
    stale,
  }
}

export function startEdit(local: LocalFlow, key: StageKey): LocalFlow {
  return { ...local, editing: { ...local.editing, [key]: true } }
}

export function cancelEdit(local: LocalFlow, key: StageKey): LocalFlow {
  return { ...local, editing: { ...local.editing, [key]: false } }
}

const storeKey = (projectId: string) => `hw.flow.${projectId}`
export function loadLocal(projectId: string): LocalFlow {
  try {
    return { ...emptyLocal(), ...JSON.parse(localStorage.getItem(storeKey(projectId)) || '{}') }
  } catch {
    return emptyLocal()
  }
}
export function saveLocal(projectId: string, l: LocalFlow) {
  localStorage.setItem(storeKey(projectId), JSON.stringify(l))
}
