/** PROTOTYPE · 一次性页面 · 路由 /prototype/flow · 不连后端，全部是假数据。见 docs/flow.md */
import { useEffect, useReducer, useState } from 'react'
import { STAGES, initial, nextStage, primaryOf, reduce, type State, type Llm } from './flowMachine'
import './flow-prototype.css'

function upTo(n: number, extra: Partial<State> = {}, cur?: { step: number }): State {
  const s = initial()
  s.stages = s.stages.map((x, i) =>
    i < n ? { ...x, status: 'confirmed', version: 1, step: STAGES[i].steps.length - 1 } : i === n ? { ...x, status: 'active', step: cur?.step ?? 0 } : x,
  )
  s.introSeen = STAGES.map(() => true)
  s.view = n
  return { ...s, ...extra, log: '场景：' + (extra.log ?? '') }
}

const SCENES: Record<string, () => State> = {
  fresh: () => ({ ...initial(), log: '新项目' }),
  intro: () => ({ ...upTo(0), introSeen: STAGES.map(() => false), introOpen: true, log: '首次进入方向' }),
  'overview-mid': () => ({ ...upTo(3), view: 'overview', log: '概览：做到研究计划' }),
  progress: () => upTo(1, { running: { stage: 1, done: 2 }, log: '检索中' }),
  'literature-results': () => upTo(1, { log: '检索完成' }, { step: 1 }),
  'data-binding': () => upTo(4, { log: '数据已上传，待确认绑定' }, { step: 1 }),
  'llm-unconfigured': () => upTo(2, { llm: 'unconfigured', log: '模型未配置' }),
  'llm-failed': () => upTo(2, { llm: 'failed', failReason: '模型返回超时（第 3 项），可以重试', log: '模型调用失败' }),
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
  'proposal-failed': () => upTo(5, { sectionFailures: [{ section: '研究设计', reason: '模型输出缺少变量定义' }], log: '提案部分失败' }, { step: 1 }),
  'proposal-confirmed': () => {
    const s = upTo(5, { log: '提案已确认' })
    s.stages[5] = { ...s.stages[5], status: 'confirmed', version: 1, step: 2 }
    return s
  },
}

const params = new URLSearchParams(location.search)
const freeze = params.has('freeze')

const MOCK: Record<string, string[]> = {
  literature: ['Zhang 2021 · 碳交易试点降低工业排放 12%', 'Li 2022 · 试点地区创新专利增加', 'Wang 2023 · 碳价波动对中小企业影响有限', 'Chen 2020 · 区域间存在排放转移'],
  candidates: ['H1 碳交易试点提升企业绿色专利数量', 'H2 碳价越高，减排效果越强', 'H3 试点导致排放向非试点地区转移'],
}

function Content({ s, i }: { s: State; i: number }) {
  const st = s.stages[i]
  const id = STAGES[i].id
  const step = st.step
  const done = st.status === 'confirmed'
  const ro = done
  if (id === 'direction')
    return (
      <div className="fp-card fp-grow">
        <label className="fp-label">研究方向</label>
        <textarea className="fp-textarea" readOnly={ro} defaultValue="碳排放权交易试点是否促进了企业的绿色创新？" />
        <p className="fp-hint">{ro ? '已确认，只读。' : '自动保存为草稿 · 刚刚'}</p>
      </div>
    )
  if (id === 'literature' || id === 'candidates') {
    if (step === 0 && !done && !st.prefilled) return <Empty text={id === 'literature' ? '还没有检索文献。点右上角主按钮开始。' : '还没有候选假设。点右上角主按钮生成。'} />
    const items = MOCK[id]
    return (
      <div className="fp-card fp-grow">
        <div className="fp-label">{id === 'literature' ? '勾选能支持研究的证据' : '选一条你想检验的假设'}</div>
        {items.map((t, k) => (
          <label key={t} className="fp-row">
            <input type={id === 'literature' ? 'checkbox' : 'radio'} name={id} disabled={ro} defaultChecked={(step > 1 || done || st.prefilled) && (id === 'literature' ? k < 2 : k === 0)} />
            {t}
          </label>
        ))}
      </div>
    )
  }
  if (id === 'plan') {
    if (step === 0 && !done && !st.prefilled) return <Empty text="还没有研究计划。点右上角主按钮让系统起草。" />
    return (
      <div className="fp-card fp-grow">
        <div className="fp-label">研究计划草案</div>
        <p>因变量：绿色专利数量；自变量：是否碳交易试点 × 试点后；模型：双重差分；稳健性：PSM-DID、安慰剂检验。</p>
      </div>
    )
  }
  if (id === 'data') {
    if (step === 0 && !done) return <Empty text="把数据表（CSV / Excel）拖到这里，或点右上角「上传数据」。" />
    return (
      <div className="fp-card fp-grow">
        <div className="fp-label">{step === 1 ? '系统建议的变量绑定，确认无误后点主按钮' : '变量绑定'}</div>
        <table className="fp-table">
          <tbody>
            <tr><th>变量</th><th>数据列</th><th></th></tr>
            <tr><td>绿色专利数量</td><td>green_patents</td><td>{step === 1 ? '建议' : '✓'}</td></tr>
            <tr><td>是否试点</td><td>pilot</td><td>{step === 1 ? '建议' : '✓'}</td></tr>
            <tr><td>试点后</td><td>post_2013</td><td>{step === 1 ? '建议' : '✓'}</td></tr>
          </tbody>
        </table>
        {step >= 3 || done ? <p className="fp-result">检验结果：DID 系数 0.084（p=0.012），结论强度：关联。</p> : null}
      </div>
    )
  }
  // proposal
  if (step === 0 && !done) return <Empty text="前面阶段都已确认。点右上角「生成提案」。" />
  const secs = ['研究背景', '文献综述', '假设', '研究设计', '初步结果']
  return (
    <div className="fp-card fp-grow fp-scroll">
      {secs.map((sec) => {
        const f = s.sectionFailures.find((x) => x.section === sec)
        return (
          <section key={sec} className={'fp-sec' + (f ? ' fp-sec-fail' : '')}>
            <h4>{sec}</h4>
            {f ? (
              <p>
                本节生成失败：{f.reason}{' '}
                <button className="fp-btn-2" data-act="regen" onClick={() => window.dispatchEvent(new CustomEvent('fp-regen', { detail: sec }))}>
                  重新生成本节
                </button>
              </p>
            ) : (
              <p>（模拟正文）{sec}的内容……</p>
            )}
          </section>
        )
      })}
      <p className="fp-hint">自动保存 · 无需手动保存{s.exported ? ' · 已导出' : ''}</p>
    </div>
  )
}

function Empty({ text }: { text: string }) {
  return <div className="fp-empty">{text}</div>
}

export default function FlowPrototype() {
  const sceneKey = params.get('scene') ?? 'fresh'
  const [s, dispatch] = useReducer(reduce, undefined, () => (SCENES[sceneKey] ?? SCENES.fresh)())
  const [showState, setShowState] = useState(false)
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
  const p = primaryOf(s)
  const i = s.view
  const next = nextStage(s)

  return (
    <div className="fp-root">
      <div className="fp-proto-tag">原型 · 假数据</div>
      <header className="fp-bar">
        <button className={'fp-stage fp-ov' + (i === 'overview' ? ' on' : '')} onClick={() => dispatch({ type: 'goto', view: 'overview' })}>
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
              <span className="fp-num">{st.status === 'confirmed' ? '✓' : st.status === 'locked' ? '🔒' : k + 1}</span>
              {d.name}
              {st.status === 'stale' ? <span className="fp-dot" title="需要更新" /> : null}
              {st.version > 1 ? <span className="fp-ver">v{st.version}</span> : null}
            </button>
          )
        })}
        <div className="fp-primary-wrap">
          {p.reason ? <span className="fp-reason">{p.reason}</span> : null}
          <button className={'fp-primary ' + p.tone} disabled={p.disabled} onClick={() => dispatch({ type: 'primary' })} data-primary>
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
                阶段 {next + 1} · {STAGES[next].name}：{s.stages[next].status === 'stale' ? '上游已修改，需要更新' : STAGES[next].todo}
              </h2>
            )}
            <button className={'fp-primary ' + p.tone} onClick={() => dispatch({ type: 'primary' })}>
              {p.label} →
            </button>
          </div>
          <div className="fp-summary">
            {STAGES.map((d, k) => (
              <div key={d.id} className={'fp-sum ' + s.stages[k].status}>
                <b>{d.name}</b>
                <span>{{ locked: '未解锁', active: '进行中', confirmed: `已确认 v${s.stages[k].version}`, stale: '需要更新' }[s.stages[k].status]}</span>
              </div>
            ))}
          </div>
        </main>
      ) : (
        <main className="fp-main">
          <div className="fp-head">
            <h1>
              {STAGES[i].name}
              <button className="fp-help" title="这一阶段做什么" onClick={() => dispatch({ type: 'openIntro' })}>
                ?
              </button>
            </h1>
            <p className="fp-todo">{s.stages[i].status === 'confirmed' ? `已确认 v${s.stages[i].version}。` : STAGES[i].todo}</p>
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
                    <li key={k} className={st.status === 'confirmed' && !(STAGES[i].id === 'proposal' && t.kind === 'export' && !s.exported) ? 'done' : k < st.step ? 'done' : k === st.step ? 'now' : ''}>
                      {t.check}
                    </li>
                  ) : null,
                )}
              </ol>
            )
          })()}
          {s.stages[i].status === 'stale' || s.stages[i].prefilled ? (
            <div className="fp-banner">上游阶段已修改。下面预填了上一版内容，按主按钮依次更新即可。</div>
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
                  已完成 {s.running.done}/{STAGES[i].steps[s.stages[i].step].progress!.items.length}，完成后会自动显示结果。
                </p>
                <ul>
                  {STAGES[i].steps[s.stages[i].step].progress!.items.map((it, k) => (
                    <li key={it} className={k < s.running!.done ? 'done' : k === s.running!.done ? 'now' : ''}>
                      {it}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <Content s={s} i={i} />
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
        <select value={s.llm} onChange={(e) => dispatch({ type: 'setLlm', llm: e.target.value as Llm })}>
          <option value="ok">模型：正常</option>
          <option value="unconfigured">模型：未配置</option>
          <option value="fail-next">模型：下次失败</option>
          <option value="failed">模型：已失败</option>
        </select>
        <label>
          <input type="checkbox" checked={s.failSectionNext} onChange={(e) => dispatch({ type: 'setFailSection', on: e.target.checked })} /> 提案某节失败
        </label>
        <button onClick={() => dispatch({ type: 'reopenProject' })}>重新打开项目</button>
        <button onClick={() => setShowState(!showState)}>状态</button>
        <span className="fp-log">{s.log}</span>
        {showState ? (
          <div className="fp-state">
            {STAGES.map((d, k) => (
              <div key={d.id}>
                {d.name}: {s.stages[k].status} · 第 {s.stages[k].step + 1} 步 · v{s.stages[k].version}
                {s.stages[k].prefilled ? ' · 预填' : ''}
              </div>
            ))}
            <div>编辑中: {s.editing === null ? '无' : STAGES[s.editing].name} · 模型: {s.llm}</div>
          </div>
        ) : null}
      </footer>
    </div>
  )
}
