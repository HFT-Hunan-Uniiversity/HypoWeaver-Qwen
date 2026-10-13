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

/** 阶段是否已解锁；未解锁时返回原因（用于置灰 + tooltip） */
export function lockReason(stages: Stage[], key: string): string | null {
  const i = STAGE_ORDER.indexOf(key)
  const me = stages.find((s) => s.key === key)
  if (i <= 0 || !me || me.status !== 'not_started') return null
  const blocker = stages
    .slice(0, i)
    .find((s) => ['not_started', 'failed', 'awaiting_selection', 'draft'].includes(s.status))
  if (!blocker) return null
  return `需先完成「${STAGE_TITLES[blocker.key]}」（当前：${STATUS_LABELS[blocker.status] || blocker.status}）`
}

/** 每个阶段一句"这里要做什么"（页头下方） */
export const STAGE_TODO: Record<string, string> = {
  direction: '用一句话写下想法，回答几个问题，把右侧方向卡补完整。',
  literature: '系统检索文献，你勾选能支持研究的证据。',
  candidates: '系统生成几条候选假设，你比较后选一条。',
  plan: '系统起草研究计划，你检查后确认。',
  data: '上传数据，确认系统建议的变量绑定，然后运行检验。',
  proposal: '系统生成研究提案，你检查后确认并导出。',
}

/** 首次进入的引导卡 */
export const STAGE_INTRO: Record<string, string> = {
  direction:
    '先用一句话说说你想研究什么。系统一次问一个问题，帮你整理成方向卡：研究问题、变量、范围和检索关键词。',
  literature:
    '系统按方向卡的关键词检索论文。你只需要勾选认可的证据；右侧会告诉你哪些变量关系还缺证据。',
  candidates: '系统根据你勾选的证据提出几条可检验的候选假设，并推荐一条。你比较后选一条最想做的。',
  plan: '系统把选定的假设变成变量、模型、稳健性检验和决策规则。你检查一遍，没问题就确认。',
  data: '上传数据表后，系统会建议每个变量对应哪一列。你确认绑定，系统运行主回归和稳健性检验。',
  proposal: '系统把前面所有已确认的内容写成研究提案。内容自动保存；某一节失败可以单独重新生成。',
}
