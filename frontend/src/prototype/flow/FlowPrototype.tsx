/** PROTOTYPE · 一次性页面 · 路由 /prototype/flow · 不连后端，全部是假数据。见 docs/flow.md */
import { useEffect, useReducer, useState } from 'react'
import {
  STAGES,
  initial,
  nextStage,
  primaryOf,
  reduce,
  type State,
  type Llm,
  type Primary,
} from './flowMachine'
import { Content, emptyDir, seedDir, answerDir, QCOUNT, dirMissing, type DirState } from './stages'
import './flow-prototype.css'

function upTo(n: number, extra: Partial<State> = {}, cur?: { step: number }): State {
  const s = initial()
  s.stages = s.stages.map((x, i) =>
    i < n
      ? { ...x, status: 'confirmed', version: 1, step: STAGES[i].steps.length - 1 }
      : i === n
        ? { ...x, status: 'active', step: cur?.step ?? 0 }
        : x,
  )
  s.introSeen = STAGES.map(() => true)
  s.view = n
  return { ...s, ...extra, log: '场景：' + (extra.log ?? '') }
}

const SCENES: Record<string, () => State> = {
  fresh: () => ({ ...initial(), log: '新项目' }),
  intro: () => ({
    ...upTo(0),
    introSeen: STAGES.map(() => false),
    introOpen: true,
    log: '首次进入方向',
  }),
  'direction-empty': () => upTo(0, { log: '方向：空状态' }),
  'direction-chat': () => upTo(0, { log: '方向：对话中' }),
  'direction-complete': () => upTo(0, { log: '方向：方向卡完整' }),
  'overview-mid': () => ({ ...upTo(3), view: 'overview', log: '概览：做到研究计划' }),
  progress: () => upTo(1, { running: { stage: 1, done: 2 }, log: '检索中' }),
  'literature-results': () => upTo(1, { log: '检索完成' }, { step: 1 }),
  'candidates-results': () => upTo(2, { log: '候选已生成' }, { step: 1 }),
  'plan-draft': () => upTo(3, { log: '计划草案' }, { step: 1 }),
  'data-empty': () => upTo(4, { log: '数据：空状态' }),
  'proposal-empty': () => upTo(5, { log: '提案：空状态' }),
  'data-binding': () => upTo(4, { log: '数据已上传，待确认绑定' }, { step: 1 }),
  'llm-unconfigured': () => upTo(2, { llm: 'unconfigured', log: '模型未配置' }),
  'llm-failed': () =>
    upTo(2, {
      llm: 'failed',
      failReason: '模型返回超时（第 3 项），可以重试',
      log: '模型调用失败',
    }),
  'edit-dialog': () => {
    const s = upTo(5, { log: '编辑已确认的文献' }, { step: 0 })
    return { ...s, view: 1, dialog: { stage: 1, downstream: 3 } }
  },
  stale: () => {
    const s = upTo(5, { log: '文献改为 v2，下游需要更新' })
    s.stages[1] = { ...s.stages[1], version: 2 }
    for (const i of [2, 3, 4]) s.stages[i] = { ...s.stages[i], status: 'stale', step: 0 }
    return { ...s, view: 1 }
  },
  'stale-redo': () => {
    const s = SCENES.stale()
    s.stages[2] = { ...s.stages[2], step: 1, prefilled: true }
    return { ...s, view: 2, log: '重做候选假设（预填）' }
  },
  'proposal-failed': () =>
    upTo(
      5,
      {
        sectionFailures: [{ section: '研究设计', reason: '模型输出缺少变量定义' }],
        log: '提案部分失败',
      },
      { step: 1 },
    ),
  'proposal-confirmed': () => {
    const s = upTo(5, { log: '提案已确认' })
    s.stages[5] = { ...s.stages[5], status: 'confirmed', version: 1, step: 2 }
    return s
  },
}

const params = new URLSearchParams(location.search)
function dirFor(scene: string): DirState {
  if (scene === 'fresh' || scene === 'intro' || scene === 'direction-empty') return emptyDir
  let d = seedDir('碳交易会不会让企业更绿色？')
  const n = scene === 'direction-chat' ? 2 : QCOUNT
  const ans = ['七个试点省市', '2008–2020', '想证明因果', '有上市公司面板数据']
  for (let k = 0; k < n; k++) d = answerDir(d, ans[k])
  return d
}
const freeze = params.has('freeze')

export default function FlowPrototype() {
  const sceneKey = params.get('scene') ?? 'fresh'
  const [s, dispatch] = useReducer(reduce, undefined, () => (SCENES[sceneKey] ?? SCENES.fresh)())
  const [showState, setShowState] = useState(false)
  const [dir, setDir] = useState<DirState>(() => dirFor(sceneKey))
  const early = [
    'fresh',
    'intro',
    'direction-empty',
    'direction-chat',
    'direction-complete',
    'progress',
  ].includes(sceneKey)
  const [sel, setSel] = useState<number[]>(() =>
    sceneKey === 'literature-results' ? [0, 2] : early ? [] : [0, 1, 2],
  )
  const [pick, setPick] = useState<number>(() =>
    sceneKey === 'candidates-results' || early ? -1 : 0,
  )
  const ui = { dir, setDir, sel, setSel, pick, setPick }
  useEffect(() => {
    if (!s.running || freeze) return
    const t = setTimeout(() => dispatch({ type: 'tick' }), 600)
    return () => clearTimeout(t)
  }, [s.running, s.llm])
  useEffect(() => {
    const h = (e: Event) => dispatch({ type: 'regenSection', section: (e as CustomEvent).detail })
    window.addEventListener('fp-regen', h)
    return () => window.removeEventListener('fp-regen', h)
  }, [])
  let p: Primary = primaryOf(s)
  let onPrimary = () => dispatch({ type: 'primary' })
  if (typeof s.view === 'number' && !s.running && s.stages[s.view].status !== 'confirmed') {
    const v = s.view
    const step = s.stages[v].step
    if (v === 0) {
      const miss = dirMissing(dir.card)
      if (!dir.idea)
        p = {
          label: '确认方向并检索文献',
          tone: 'go',
          disabled: true,
          reason: '先在下方写一句想法',
        }
      else if (miss.length)
        p = {
          label: '确认方向并检索文献',
          tone: 'go',
          disabled: true,
          reason: '方向卡还缺：' + miss.join('、'),
        }
      else {
        p = { label: s.editing === 0 ? '确认方向' : '确认方向并检索文献', tone: 'go' }
        onPrimary = () => {
          dispatch({ type: 'primary' })
          if (s.editing !== 0 && s.llm === 'ok') dispatch({ type: 'primary' })
        }
      }
    } else if ((v === 1 || v === 2) && step === 1) {
      const ok = v === 1 ? sel.length > 0 : pick >= 0
      if (ok) {
        p = { label: '确认并进入下一阶段', tone: 'go' }
        onPrimary = () => {
          dispatch({ type: 'primary' })
          dispatch({ type: 'primary' })
        }
      } else {
        p = { ...p, reason: v === 1 ? '在下方勾选至少一篇证据' : '在下方选一条假设' }
        onPrimary = () => {}
      }
    }
  }
  const i = s.view
  const next = nextStage(s)

  return (
    <div className="fp-root">
      <div className="fp-proto-tag">原型 · 假数据</div>
      <header className="fp-bar">
        <button
          className={'fp-stage fp-ov' + (i === 'overview' ? ' on' : '')}
          onClick={() => dispatch({ type: 'goto', view: 'overview' })}
        >
          概览
        </button>
        {STAGES.map((d, k) => {
          const st = s.stages[k]
          return (
            <button
              key={d.id}
              className={`fp-stage ${st.status}` + (i === k ? ' on' : '')}
              disabled={st.status === 'locked'}
              title={st.status === 'locked' ? '完成前面的阶段后解锁' : undefined}
              onClick={() => dispatch({ type: 'goto', view: k })}
            >
              <span className="fp-num">
                {st.status === 'confirmed' ? '✓' : st.status === 'locked' ? '🔒' : k + 1}
              </span>
              {d.name}
              {st.status === 'stale' ? <span className="fp-dot" title="需要更新" /> : null}
              {st.version > 1 ? <span className="fp-ver">v{st.version}</span> : null}
            </button>
          )
        })}
        <div className="fp-primary-wrap">
          {p.reason ? <span className="fp-reason">{p.reason}</span> : null}
          <button
            className={'fp-primary ' + p.tone}
            disabled={p.disabled}
            onClick={onPrimary}
            data-primary
          >
            {p.label} →
          </button>
        </div>
      </header>

      {i === 'overview' ? (
        <main className="fp-main">
          <div className="fp-next">
            <div className="fp-eyebrow">下一步</div>
            {next === null ? (
              <h2>全部完成 · 可以导出提案</h2>
            ) : (
              <h2>
                阶段 {next + 1} · {STAGES[next].name}：
                {s.stages[next].status === 'stale' ? '上游已修改，需要更新' : STAGES[next].todo}
              </h2>
            )}
            <button
              className={'fp-primary ' + p.tone}
              onClick={() => dispatch({ type: 'primary' })}
            >
              {p.label} →
            </button>
          </div>
          <div className="fp-summary">
            {STAGES.map((d, k) => (
              <div key={d.id} className={'fp-sum ' + s.stages[k].status}>
                <b>{d.name}</b>
                <span>
                  {
                    {
                      locked: '未解锁',
                      active: '进行中',
                      confirmed: `已确认 v${s.stages[k].version}`,
                      stale: '需要更新',
                    }[s.stages[k].status]
                  }
                </span>
              </div>
            ))}
          </div>
        </main>
      ) : (
        <main className="fp-main">
          <div className="fp-head">
            <h1>
              {STAGES[i].name}
              <button
                className="fp-help"
                title="这一阶段做什么"
                onClick={() => dispatch({ type: 'openIntro' })}
              >
                ?
              </button>
            </h1>
            <p className="fp-todo">
              {s.stages[i].status === 'confirmed'
                ? `已确认 v${s.stages[i].version}。`
                : STAGES[i].todo}
            </p>
            {s.stages[i].status === 'confirmed' && i !== 5 ? (
              <button className="fp-btn-2" onClick={() => dispatch({ type: 'askEdit' })}>
                编辑此阶段
              </button>
            ) : null}
          </div>
          {(() => {
            const checks = STAGES[i].steps.filter((t) => t.check)
            if (checks.length < 2) return null
            const st = s.stages[i]
            return (
              <ol className="fp-checklist">
                {STAGES[i].steps.map((t, k) =>
                  t.check ? (
                    <li
                      key={k}
                      className={
                        st.status === 'confirmed' &&
                        !(STAGES[i].id === 'proposal' && t.kind === 'export' && !s.exported)
                          ? 'done'
                          : k < st.step
                            ? 'done'
                            : k === st.step
                              ? 'now'
                              : ''
                      }
                    >
                      {t.check}
                    </li>
                  ) : null,
                )}
              </ol>
            )
          })()}
          {s.stages[i].status === 'stale' || s.stages[i].prefilled ? (
            <div className="fp-banner">
              上游阶段已修改。下面预填了上一版内容，按主按钮依次更新即可。
            </div>
          ) : null}
          {s.introOpen ? (
            <div className="fp-intro">
              <b>这一阶段做什么</b>
              <p>{STAGES[i].intro}</p>
              <button className="fp-btn-2" onClick={() => dispatch({ type: 'dismissIntro' })}>
                知道了
              </button>
            </div>
          ) : null}
          <div className="fp-work">
            {s.running && s.running.stage === i ? (
              <div className="fp-progress">
                <h2>{STAGES[i].steps[s.stages[i].step].progress!.title}…</h2>
                <p>
                  已完成 {s.running.done}/{STAGES[i].steps[s.stages[i].step].progress!.items.length}
                  ，完成后会自动显示结果。
                </p>
                <ul>
                  {STAGES[i].steps[s.stages[i].step].progress!.items.map((it, k) => (
                    <li
                      key={it}
                      className={k < s.running!.done ? 'done' : k === s.running!.done ? 'now' : ''}
                    >
                      {it}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <Content s={s} i={i} d={dispatch} ui={ui} />
            )}
            <details className="fp-ref">
              <summary>参考信息</summary>
              <p>上游内容、方法说明等放在这里，默认折叠。</p>
            </details>
          </div>
        </main>
      )}

      {s.dialog ? (
        <div className="fp-modal">
          <div className="fp-dialog">
            <h3>编辑「{STAGES[s.dialog.stage].name}」？</h3>
            <p>修改后，后面 {s.dialog.downstream} 个阶段需要更新。没受影响的内容会保留并预填。</p>
            <div className="fp-dialog-act">
              <button className="fp-btn-2" onClick={() => dispatch({ type: 'cancelEdit' })}>
                取消
              </button>
              <button className="fp-primary warn" onClick={() => dispatch({ type: 'confirmEdit' })}>
                继续编辑
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <footer className="fp-dev">
        <span>原型控制：</span>
        <select value={sceneKey} onChange={(e) => (location.search = '?scene=' + e.target.value)}>
          {Object.keys(SCENES).map((k) => (
            <option key={k}>{k}</option>
          ))}
        </select>
        <select
          value={s.llm}
          onChange={(e) => dispatch({ type: 'setLlm', llm: e.target.value as Llm })}
        >
          <option value="ok">模型：正常</option>
          <option value="unconfigured">模型：未配置</option>
          <option value="fail-next">模型：下次失败</option>
          <option value="failed">模型：已失败</option>
        </select>
        <label>
          <input
            type="checkbox"
            checked={s.failSectionNext}
            onChange={(e) => dispatch({ type: 'setFailSection', on: e.target.checked })}
          />{' '}
          提案某节失败
        </label>
        <button onClick={() => dispatch({ type: 'reopenProject' })}>重新打开项目</button>
        <button onClick={() => setShowState(!showState)}>状态</button>
        <span className="fp-log">{s.log}</span>
        {showState ? (
          <div className="fp-state">
            {STAGES.map((d, k) => (
              <div key={d.id}>
                {d.name}: {s.stages[k].status} · 第 {s.stages[k].step + 1} 步 · v
                {s.stages[k].version}
                {s.stages[k].prefilled ? ' · 预填' : ''}
              </div>
            ))}
            <div>
              编辑中: {s.editing === null ? '无' : STAGES[s.editing].name} · 模型: {s.llm}
            </div>
          </div>
        ) : null}
      </footer>
    </div>
  )
}
