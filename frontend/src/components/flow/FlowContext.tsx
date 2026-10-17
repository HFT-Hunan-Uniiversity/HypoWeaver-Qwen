import { isShowcaseProject } from '../../lib/showcase'
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import type { ReactNode } from 'react'
import type { Stage } from '../../api/client'
import {
  cancelEdit,
  confirmStage,
  deriveFlow,
  loadLocal,
  runUnlocksProposal,
  saveLocal,
  startEdit,
  type FlowStage,
  type LocalFlow,
  type StageKey,
} from '../../lib/flow'

/** 主按钮描述：页面只声明"现在该做什么"，位置与样式由外壳统一决定 */
export interface PrimarySpec {
  label: string
  onClick?: () => void
  disabled?: boolean
  /** 显示在主按钮左侧的一句原因 / 提示 */
  reason?: string
  /** 此动作需要模型：未配置时主按钮变为"去设置模型" */
  needsLlm?: boolean
  /** 上次执行失败的原因：主按钮变为"重试" */
  error?: string | null
  /** 系统处理中 */
  busy?: boolean
}
export interface CheckItem {
  label: string
  done: boolean
}
export interface StageUi {
  primary?: PrimarySpec
  checklist?: CheckItem[]
  /** 进入编辑（已确认阶段解锁重改）时页面需要执行的动作，例如方案新建版本 */
  onStartEdit?: () => void
}

interface FlowCtx {
  projectId: string
  flow: FlowStage[]
  local: LocalFlow
  /** runs 查询已返回（成功或失败）；未 settle 前勿因提案锁定做深链回退 */
  runsSettled: boolean
  /** 存在足以解锁提案的检验运行 */
  dataRunOk: boolean
  uiRef: React.MutableRefObject<StageUi | null>
  uiSig: string
  setUiSig: (s: string) => void
  /** 确认并进入下一阶段：返回是否为"编辑后的确认" */
  confirm: (key: StageKey) => boolean
  edit: (key: StageKey) => void
  cancel: (key: StageKey) => void
}
const Ctx = createContext<FlowCtx | null>(null)

export function FlowProvider({
  projectId,
  stages,
  title,
  children,
}: {
  projectId: string
  stages: Stage[]
  /** 后端原始题名：碳市场项目的提案步骤始终可进入（展示稿） */
  title?: string
  children: ReactNode
}) {
  const [local, setLocal] = useState<LocalFlow>(() => loadLocal(projectId))
  useEffect(() => {
    setLocal(loadLocal(projectId))
  }, [projectId])
  const runs = useQuery({
    queryKey: ['runs', projectId],
    queryFn: () =>
      api<
        {
          status: string
          stale: boolean
          steps?: Record<string, { status?: string }>
          result?: { main?: unknown } | null
        }[]
      >(`/projects/${projectId}/runs`),
    staleTime: 5000,
  })
  const dataRunOk = !!runs.data?.some((r) => runUnlocksProposal(r))
  const runsSettled = runs.isFetched
  const dataBackend = stages.find((s) => s.key === 'data')?.status
  // 首次拉取中：若 overview 已标 data failed/completed，暂按可解锁处理，避免 /proposal 深链被误踢
  const unlockHint =
    dataRunOk || (!runs.isFetched && (dataBackend === 'failed' || dataBackend === 'completed'))
  const flow = useMemo(
    () =>
      deriveFlow(stages, local, { dataRunOk: unlockHint }).map((s) =>
        s.key === 'proposal' && s.status === 'locked' && isShowcaseProject(title)
          ? { ...s, status: 'active' as const }
          : s,
      ),
    [stages, local, unlockHint, title],
  )
  const uiRef = useRef<StageUi | null>(null)
  const [uiSig, setUiSig] = useState('')
  const update = useCallback(
    (l: LocalFlow) => {
      saveLocal(projectId, l)
      setLocal(l)
    },
    [projectId],
  )
  const value: FlowCtx = {
    projectId,
    flow,
    local,
    runsSettled,
    dataRunOk,
    uiRef,
    uiSig,
    setUiSig,
    confirm: (key) => {
      const wasEdit = !!local.editing[key]
      update(confirmStage(local, flow, key))
      return wasEdit
    },
    edit: (key) => update(startEdit(local, key)),
    cancel: (key) => update(cancelEdit(local, key)),
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useFlow() {
  const c = useContext(Ctx)
  if (!c) throw new Error('useFlow outside FlowProvider')
  return c
}

/** 当前阶段的流程状态；editable=进行中或需要更新（已确认的阶段只读，需先"修改此阶段"） */
export function useFlowStage(key: StageKey) {
  const { flow, local } = useFlow()
  const st = flow.find((s) => s.key === key)!
  return {
    ...st,
    editing: !!local.editing[key],
    editable: st.status === 'active' || st.status === 'stale',
  }
}

/** 页面声明主按钮 / 任务清单。函数取最新引用，签名变化时刷新外壳 */
/** 阅读层内嵌入的阶段页不接管卡底主按钮 */
export const ReaderCtx = createContext(false)

export function useStageUi(ui: StageUi) {
  const reader = useContext(ReaderCtx)
  const flowCtx = useFlow()
  const noop = useRef<StageUi | null>(null)
  const uiRef = reader ? noop : flowCtx.uiRef
  const setUiSig = reader ? (_: string) => {} : flowCtx.setUiSig
  const latest = useRef(ui)
  latest.current = ui
  uiRef.current = ui
  const sig = JSON.stringify(ui, (_, v) => (typeof v === 'function' ? 1 : v))
  useEffect(() => {
    uiRef.current = latest.current
    setUiSig(sig)
  }, [sig, uiRef, setUiSig])
  useEffect(
    () => () => {
      if (uiRef.current === latest.current) {
        uiRef.current = null
        setUiSig('')
      }
    },
    [uiRef, setUiSig],
  )
}
