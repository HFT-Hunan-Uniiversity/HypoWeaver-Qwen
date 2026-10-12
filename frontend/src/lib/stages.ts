import { useQuery } from '@tanstack/react-query'
import { api, type Project, type Stage } from '../api/client'

export const STAGE_ORDER = ['direction', 'literature', 'candidates', 'plan', 'data', 'proposal']

export const STAGE_TITLES: Record<string, string> = {
  direction: '研究方向',
  literature: '文献调研',
  candidates: '缺口与候选',
  plan: '研究方案',
  data: '数据与检验',
  proposal: '研究提案',
}

export const STAGE_HINTS: Record<string, string> = {
  direction: '明确问题、对象与约束',
  literature: '检索、纳入证据卡',
  candidates: '比较候选并选定切入点',
  plan: '变量、模型、稳健性与决策规则',
  data: '导入、绑定数据并运行检验',
  proposal: '汇总成果，生成提案',
}

export const STATUS_LABELS: Record<string, string> = {
  not_started: '未开始',
  running: '进行中',
  completed: '已完成',
  stale: '已过期',
  draft: '待审阅',
  ready: '已绑定',
  failed: '需处理',
  awaiting_selection: '待选择',
}

/** 状态色：gray 未开始 / orange 进行中 / green 完成 / yellow 过期 / red 失败 */
export function statusTone(status: string): 'gray' | 'orange' | 'green' | 'yellow' | 'red' {
  if (status === 'completed') return 'green'
  if (status === 'stale') return 'yellow'
  if (status === 'failed') return 'red'
  if (['running', 'draft', 'ready', 'awaiting_selection'].includes(status)) return 'orange'
  return 'gray'
}

const TODO = ['not_started', 'awaiting_selection', 'draft', 'stale', 'failed', 'ready']

/** 第一个未完成或过期的阶段 */
export function nextStage(stages: Stage[]): Stage | undefined {
  return stages.find((s) => TODO.includes(s.status))
}

export function completedCount(stages: Stage[]) {
  return stages.filter((s) => s.status === 'completed').length
}

export function stageKeyFromPath(pathname: string): string | undefined {
  const seg = pathname.split('/')[3]
  if (seg === 'analysis') return 'data'
  return STAGE_ORDER.includes(seg) ? seg : undefined
}

export function useOverview(id: string | undefined) {
  return useQuery({
    queryKey: ['overview', id],
    queryFn: () => api<{ project: Project; stages: Stage[] }>(`/projects/${id}/overview`),
    enabled: !!id,
  })
}
