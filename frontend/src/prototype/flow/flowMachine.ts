/**
 * PROTOTYPE · 一次性代码 · 见 docs/flow.md
 * 纯状态机：不碰 DOM，可整体搬进真实前端。
 * 回答的问题：向导 + 锁定版本 + 下游"需要更新" + 唯一主按钮，这套状态模型走得通吗？
 */
export type StageId = 'direction' | 'literature' | 'candidates' | 'plan' | 'data' | 'proposal'
export type StageStatus = 'locked' | 'active' | 'confirmed' | 'stale'
export type StepKind = 'user' | 'run' | 'confirm' | 'export'
export interface Step {
  label: string
  kind: StepKind
  check?: string
  llm?: boolean
  progress?: { title: string; items: string[] }
}
export interface StageDef {
  id: StageId
  name: string
  todo: string
  intro: string
  steps: Step[]
}

const confirm: Step = { label: '确认并进入下一阶段', kind: 'confirm' }

export const STAGES: StageDef[] = [
  {
    id: 'direction',
    name: '方向',
    todo: '用一两句话写下你想研究的问题。',
    intro: '这里定下研究方向。写得越具体，后面检索到的文献越准。',
    steps: [confirm],
  },
  {
    id: 'literature',
    name: '文献',
    todo: '系统先检索文献，你再勾选能支持研究的证据。',
    intro: '系统会检索相关论文并摘出证据，你只需要勾选认可的证据。',
    steps: [
      {
        label: '检索文献',
        kind: 'run',
        llm: true,
        check: '检索文献',
        progress: {
          title: '正在检索文献',
          items: ['生成检索式', '检索数据库', '去重', '摘取证据', '评估相关性'],
        },
      },
      { label: '去勾选证据', kind: 'user', check: '勾选证据' },
      confirm,
    ],
  },
  {
    id: 'candidates',
    name: '候选假设',
    todo: '系统生成几条候选假设，你从中选一条。',
    intro: '系统会根据你勾选的证据提出几条可检验的假设，你挑一条最想做的。',
    steps: [
      {
        label: '生成候选假设',
        kind: 'run',
        llm: true,
        check: '生成候选',
        progress: {
          title: '正在生成候选假设',
          items: ['整理证据', '提出假设', '检查可检验性', '排序'],
        },
      },
      { label: '选择一个候选', kind: 'user', check: '选一条假设' },
      confirm,
    ],
  },
  {
    id: 'plan',
    name: '研究计划',
    todo: '系统起草研究计划，你检查后确认。',
    intro: '系统会把假设变成变量、模型和稳健性检验的计划。你看一遍，没问题就确认。',
    steps: [
      {
        label: '起草研究计划',
        kind: 'run',
        llm: true,
        progress: { title: '正在起草研究计划', items: ['定义变量', '选择模型', '设计稳健性检验'] },
      },
      confirm,
    ],
  },
  {
    id: 'data',
    name: '数据与检验',
    todo: '上传数据，确认系统建议的变量绑定，然后运行检验。',
    intro: '上传你的数据表，系统会建议每个变量对应哪一列。你确认后，系统运行检验。',
    steps: [
      { label: '上传数据', kind: 'user', check: '上传数据' },
      { label: '确认数据绑定', kind: 'user', check: '确认绑定' },
      {
        label: '运行检验',
        kind: 'run',
        check: '运行检验',
        progress: {
          title: '正在运行检验',
          items: ['读取数据', '主回归', '稳健性 1', '稳健性 2', '汇总结果'],
        },
      },
      confirm,
    ],
  },
  {
    id: 'proposal',
    name: '提案',
    todo: '系统生成提案，你检查后确认并导出。',
    intro: '系统把前面所有内容写成一份研究提案。内容自动保存，不需要手动保存。',
    steps: [
      {
        label: '生成提案',
        kind: 'run',
        llm: true,
        check: '生成提案',
        progress: {
          title: '正在生成提案',
          items: ['研究背景', '文献综述', '假设', '研究设计', '初步结果'],
        },
      },
      { label: '确认提案', kind: 'confirm', check: '确认提案' },
      { label: '导出', kind: 'export', check: '导出' },
    ],
  },
]

export type Llm = 'ok' | 'unconfigured' | 'fail-next' | 'failed'
export interface StageState {
  status: StageStatus
  step: number
  version: number
  prefilled: boolean
}
export interface State {
  view: 'overview' | number
  stages: StageState[]
  running: { stage: number; done: number } | null
  llm: Llm
  failReason: string | null
  dialog: { stage: number; downstream: number } | null
  editing: number | null
  introSeen: boolean[]
  introOpen: boolean
  sectionFailures: { section: string; reason: string }[]
  failSectionNext: boolean
  exported: boolean
  log: string
}

export type Action =
  | { type: 'primary' }
  | { type: 'goto'; view: 'overview' | number }
  | { type: 'tick' }
  | { type: 'askEdit' }
  | { type: 'cancelEdit' }
  | { type: 'confirmEdit' }
  | { type: 'dismissIntro' }
  | { type: 'openIntro' }
  | { type: 'setLlm'; llm: Llm }
  | { type: 'setFailSection'; on: boolean }
  | { type: 'regenSection'; section: string }
  | { type: 'reopenProject' }
  | { type: 'load'; state: State }

export function initial(): State {
  return {
    view: 'overview',
    stages: STAGES.map((_, i) => ({
      status: i === 0 ? 'active' : 'locked',
      step: 0,
      version: 0,
      prefilled: false,
    })),
    running: null,
    llm: 'ok',
    failReason: null,
    dialog: null,
    editing: null,
    introSeen: STAGES.map(() => false),
    introOpen: false,
    sectionFailures: [],
    failSectionNext: false,
    exported: false,
    log: '新项目',
  }
}

/** 第一个尚未完成（active / stale）的阶段 */
export function nextStage(s: State): number | null {
  const i = s.stages.findIndex((x) => x.status === 'active' || x.status === 'stale')
  return i < 0 ? null : i
}

export interface Primary {
  label: string
  reason?: string
  tone: 'go' | 'warn'
  disabled?: boolean
}

export function primaryOf(s: State): Primary {
  if (s.view === 'overview') {
    const n = nextStage(s)
    if (n === null) return { label: '查看提案', tone: 'go' }
    return { label: `前往：${STAGES[n].name}`, tone: 'go' }
  }
  const i = s.view
  const st = s.stages[i]
  if (s.running) return { label: '系统处理中…', tone: 'go', disabled: true }
  if (st.status === 'confirmed') {
    const n = nextStage(s)
    if (n === null)
      return { label: i === 5 ? (s.exported ? '再次导出' : '导出') : '查看提案', tone: 'go' }
    if (s.stages[n].status === 'stale') return { label: '更新下一阶段', tone: 'warn' }
    return { label: `前往：${STAGES[n].name}`, tone: 'go' }
  }
  const step = STAGES[i].steps[st.step]
  if (step.llm && s.llm === 'unconfigured')
    return { label: '去设置模型', tone: 'warn', reason: '还没有配置模型，无法' + step.label }
  if (step.llm && s.llm === 'failed')
    return { label: '重试', tone: 'warn', reason: s.failReason ?? '模型调用失败' }
  return { label: step.label, tone: 'go' }
}

function downstreamTouched(s: State, i: number) {
  return s.stages.slice(i + 1).filter((x) => x.status === 'confirmed' || x.status === 'stale')
    .length
}

function enter(s: State, view: 'overview' | number): State {
  if (view === 'overview') return { ...s, view, introOpen: false }
  return { ...s, view, introOpen: !s.introSeen[view] }
}

export function reduce(s: State, a: Action): State {
  switch (a.type) {
    case 'load':
      return a.state
    case 'goto': {
      if (a.view !== 'overview' && s.stages[a.view].status === 'locked')
        return { ...s, log: `「${STAGES[a.view].name}」还没解锁` }
      return {
        ...enter(s, a.view),
        log: `打开 ${a.view === 'overview' ? '概览' : STAGES[a.view].name}`,
      }
    }
    case 'reopenProject': {
      const n = s.stages.findIndex(
        (x, i) =>
          (x.status === 'active' || x.status === 'stale') &&
          STAGES[i].steps[x.step].kind === 'confirm' &&
          x.step > 0,
      )
      return {
        ...enter(s, n >= 0 ? n : 'overview'),
        log:
          n >= 0 ? `重新打开项目 → 直接进入待确认的「${STAGES[n].name}」` : '重新打开项目 → 概览',
      }
    }
    case 'dismissIntro':
      return {
        ...s,
        introOpen: false,
        introSeen: s.introSeen.map((v, i) => (i === s.view ? true : v)),
      }
    case 'openIntro':
      return { ...s, introOpen: true }
    case 'setLlm':
      return { ...s, llm: a.llm, failReason: null, log: `模型状态 → ${a.llm}` }
    case 'setFailSection':
      return { ...s, failSectionNext: a.on }
    case 'regenSection':
      return {
        ...s,
        sectionFailures: s.sectionFailures.filter((f) => f.section !== a.section),
        log: `已重新生成「${a.section}」`,
      }
    case 'askEdit': {
      if (typeof s.view !== 'number') return s
      return { ...s, dialog: { stage: s.view, downstream: downstreamTouched(s, s.view) } }
    }
    case 'cancelEdit':
      return { ...s, dialog: null }
    case 'confirmEdit': {
      if (!s.dialog) return s
      const i = s.dialog.stage
      const stages = s.stages.map((x, j) =>
        j === i
          ? {
              ...x,
              status: 'active' as const,
              step: STAGES[i].steps.findIndex((t) => t.kind === 'confirm'),
            }
          : x,
      )
      return {
        ...s,
        dialog: null,
        editing: i,
        stages,
        log: `正在编辑「${STAGES[i].name}」（草稿自动保存）`,
      }
    }
    case 'tick': {
      if (!s.running) return s
      const i = s.running.stage
      const step = STAGES[i].steps[s.stages[i].step]
      const m = step.progress!.items.length
      if (s.llm === 'fail-next' && s.running.done === 2) {
        return {
          ...s,
          running: null,
          llm: 'failed',
          failReason: '模型返回超时（第 3 项），可以重试',
          log: '系统任务失败',
        }
      }
      const done = s.running.done + 1
      if (done < m) return { ...s, running: { stage: i, done } }
      const stages = s.stages.map((x, j) => (j === i ? { ...x, step: x.step + 1 } : x))
      let sectionFailures = s.sectionFailures
      if (STAGES[i].id === 'proposal' && s.failSectionNext)
        sectionFailures = [{ section: '研究设计', reason: '模型输出缺少变量定义' }]
      return {
        ...s,
        running: null,
        stages,
        sectionFailures,
        log: `${step.progress!.title.replace('正在', '')}完成 → 轮到你`,
      }
    }
    case 'primary': {
      if (s.view === 'overview') {
        const n = nextStage(s)
        return enter(s, n ?? 5)
      }
      const i = s.view
      const st = s.stages[i]
      if (s.running) return s
      if (st.status === 'confirmed') {
        if (i === 5) return { ...s, exported: true, log: '已导出提案（模拟）' }
        const n = nextStage(s)
        if (n !== null && s.stages[n].status === 'stale') {
          const ns = {
            ...s,
            stages: s.stages.map((x, j) => (j === n ? { ...x, step: 0, prefilled: true } : x)),
          }
          return { ...enter(ns, n), log: `开始更新「${STAGES[n].name}」（上一版内容已预填）` }
        }
        return { ...enter(s, n ?? 5), log: `前往「${STAGES[n ?? 5].name}」` }
      }
      const step = STAGES[i].steps[st.step]
      if (step.llm && s.llm === 'unconfigured')
        return { ...s, log: '→ 跳到设置页配置模型（原型里点底部"模型：正常"模拟配好）' }
      if (step.kind === 'run')
        return {
          ...s,
          llm: s.llm === 'failed' ? 'ok' : s.llm,
          failReason: null,
          running: { stage: i, done: 0 },
          log: step.progress!.title,
        }
      if (step.kind === 'user')
        return {
          ...s,
          stages: s.stages.map((x, j) => (j === i ? { ...x, step: x.step + 1 } : x)),
          log: `完成：${step.check}`,
        }
      if (step.kind === 'confirm') {
        const wasEdit = s.editing === i
        const stages = s.stages.map((x, j) => {
          if (j === i)
            return {
              ...x,
              status: 'confirmed' as const,
              version: x.version + 1,
              prefilled: false,
              step: STAGES[i].id === 'proposal' ? 2 : x.step,
            }
          if (j > i && wasEdit && (x.status === 'confirmed' || x.status === 'stale'))
            return { ...x, status: 'stale' as const, prefilled: false, step: 0 }
          if (j === i + 1 && x.status === 'locked') return { ...x, status: 'active' as const }
          return x
        })
        const ns: State = {
          ...s,
          stages,
          editing: null,
          log:
            `「${STAGES[i].name}」已确认为 v${st.version + 1}` +
            (wasEdit ? '，下游标为需要更新' : ''),
        }
        if (wasEdit || i === 5 || stages.some((x) => x.status === 'stale')) return ns
        return enter(ns, i + 1)
      }
      return s
    }
  }
}
