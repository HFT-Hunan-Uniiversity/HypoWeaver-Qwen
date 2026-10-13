/** PROTOTYPE · 各阶段的工作区内容（假数据）。见 docs/flow.md */
import { useState } from 'react'
import { STAGES, type Action, type State } from './flowMachine'

type D = (a: Action) => void

/* ---------------- 方向：对话 + 方向卡 ---------------- */
export interface DirCard {
  question: string
  vars: string[]
  region: string
  period: string
  keywords: string[]
  hint: string
  data: string
}
export interface DirState {
  idea: string
  asked: number
  card: DirCard
  chat: { who: 'ai' | 'me'; text: string }[]
}
export const emptyCard: DirCard = {
  question: '',
  vars: [],
  region: '',
  period: '',
  keywords: [],
  hint: '',
  data: '',
}
export const emptyDir: DirState = { idea: '', asked: 0, card: emptyCard, chat: [] }

const QS: { key: keyof DirCard; q: string; chips: string[] }[] = [
  { key: 'region', q: '研究哪个地区的企业？', chips: ['全国', '七个试点省市', '长三角'] },
  { key: 'period', q: '看哪段时间？', chips: ['2008–2020', '2013 年试点前后各 5 年', '2015 至今'] },
  {
    key: 'hint',
    q: '你想证明"碳交易导致绿色创新"（因果），还是看两者是否相关（关联）？',
    chips: ['想证明因果', '看关联就够', '不确定，帮我判断'],
  },
  {
    key: 'data',
    q: '手上有数据吗？',
    chips: ['有上市公司面板数据', '只有省级统计年鉴', '还没有数据'],
  },
]
export const EXAMPLES = [
  '碳交易会不会让企业更绿色？',
  '最低工资上涨是否减少了就业？',
  '数字普惠金融能否缓解农村贫困？',
]

export function dirMissing(c: DirCard): string[] {
  const m: string[] = []
  if (!c.question) m.push('研究问题')
  if (c.vars.length < 2) m.push('变量')
  if (!c.region || !c.period) m.push('范围')
  if (!c.hint) m.push('因果/关联')
  return m
}

function seed(idea: string): DirState {
  return {
    idea,
    asked: 0,
    card: {
      ...emptyCard,
      question: '碳排放权交易试点是否促进了企业绿色创新？',
      vars: ['碳交易试点 (X)', '绿色专利数量 (Y)'],
      keywords: ['碳排放权交易', '绿色创新', 'DID'],
    },
    chat: [
      { who: 'me', text: idea },
      { who: 'ai', text: '我把它整理成了右边的方向卡。还差几件事：' + QS[0].q },
    ],
  }
}
function answer(d: DirState, text: string): DirState {
  const q = QS[d.asked]
  const v =
    q.key === 'hint'
      ? text.includes('因果')
        ? '因果（需要准实验设计，如 DID）'
        : text.includes('关联')
          ? '关联（回归描述相关性）'
          : '建议先做关联，数据允许再升级为因果'
      : text
  const card = {
    ...d.card,
    [q.key]: v,
    keywords:
      q.key === 'region' && text.includes('试点')
        ? [...d.card.keywords, '试点省市']
        : d.card.keywords,
  }
  const asked = d.asked + 1
  const chat = [
    ...d.chat,
    { who: 'me' as const, text },
    {
      who: 'ai' as const,
      text: asked < QS.length ? QS[asked].q : '方向卡已完整。检查一下右边，没问题就点右上角确认。',
    },
  ]
  return { ...d, card, asked, chat }
}

function Direction({ s, dir, setDir }: { s: State; dir: DirState; setDir: (d: DirState) => void }) {
  const ro = s.stages[0].status === 'confirmed'
  const [draft, setDraft] = useState('')
  const c = dir.card
  const set = (k: keyof DirCard, v: string) =>
    setDir({
      ...dir,
      card: {
        ...c,
        [k]:
          k === 'vars' || k === 'keywords'
            ? v
                .split(/[,，]/)
                .map((x) => x.trim())
                .filter(Boolean)
            : v,
      },
    })
  if (!dir.idea && !ro)
    return (
      <div className="fp-empty2">
        <h3>先用一句话说说你想研究什么</h3>
        <p>
          不用写得很专业。系统会一次问你一个问题，把它整理成一张"方向卡"：研究问题、变量、范围、检索关键词。
        </p>
        <div className="fp-idea">
          <input
            placeholder="例如：碳交易会不会让企业更绿色？"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <button className="fp-btn-2" disabled={!draft} onClick={() => setDir(seed(draft))}>
            开始
          </button>
        </div>
        <p className="fp-hint">或者从一个例子开始：</p>
        <div className="fp-chips">
          {EXAMPLES.map((e) => (
            <button key={e} className="fp-chip" onClick={() => setDir(seed(e))}>
              {e}
            </button>
          ))}
        </div>
        <p className="fp-hint">
          也可以{' '}
          <a
            href="#"
            onClick={(e) => {
              e.preventDefault()
              setDir({
                ...emptyDir,
                idea: '（直接填写）',
                chat: [{ who: 'ai', text: '好的，直接在右边填写方向卡即可。' }],
              })
            }}
          >
            跳过对话，直接填方向卡
          </a>
        </p>
      </div>
    )
  const q = QS[dir.asked]
  return (
    <div className="fp-split">
      <div className="fp-card fp-chat">
        <div className="fp-label">和系统对话 · 一次一个问题</div>
        <div className="fp-msgs">
          {dir.chat.map((m, k) => (
            <div key={k} className={'fp-msg ' + m.who}>
              {m.text}
            </div>
          ))}
        </div>
        {q && !ro ? (
          <div className="fp-ask">
            <div className="fp-chips">
              {q.chips.map((ch) => (
                <button key={ch} className="fp-chip" onClick={() => setDir(answer(dir, ch))}>
                  {ch}
                </button>
              ))}
            </div>
            <div className="fp-idea">
              <input
                placeholder="或者自己写…"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
              />
              <button
                className="fp-btn-2"
                disabled={!draft}
                onClick={() => {
                  setDir(answer(dir, draft))
                  setDraft('')
                }}
              >
                发送
              </button>
            </div>
          </div>
        ) : null}
      </div>
      <div className="fp-card fp-dircard">
        <div className="fp-label">
          方向卡{' '}
          {dirMissing(c).length ? (
            <span className="fp-miss">还缺：{dirMissing(c).join('、')}</span>
          ) : (
            <span className="fp-ok">✓ 完整</span>
          )}
        </div>
        <Field label="研究问题" v={c.question} ro={ro} on={(v) => set('question', v)} />
        <div className="fp-field">
          <span>变量</span>
          {c.vars.length ? (
            <div className="fp-tags">
              {c.vars.map((v) => (
                <i key={v}>{v}</i>
              ))}
            </div>
          ) : (
            <Field label="" v="" ro={ro} ph="X, Y（逗号分隔）" on={(v) => set('vars', v)} />
          )}
        </div>
        <div className="fp-two">
          <Field label="地区" v={c.region} ro={ro} on={(v) => set('region', v)} />
          <Field label="时间" v={c.period} ro={ro} on={(v) => set('period', v)} />
        </div>
        <Field label="因果 / 关联" v={c.hint} ro={ro} on={(v) => set('hint', v)} />
        <Field label="手上数据" v={c.data} ro={ro} ph="可选" on={(v) => set('data', v)} />
        <div className="fp-field">
          <span>检索关键词</span>
          <div className="fp-tags kw">
            {c.keywords.map((v) => (
              <i key={v}>{v}</i>
            ))}
            {!c.keywords.length ? <em>根据问题自动生成</em> : null}
          </div>
        </div>
      </div>
    </div>
  )
}
function Field({
  label,
  v,
  ro,
  on,
  ph,
}: {
  label: string
  v: string
  ro: boolean
  on: (v: string) => void
  ph?: string
}) {
  return (
    <label className="fp-field">
      {label ? <span>{label}</span> : null}
      <input
        value={v}
        readOnly={ro}
        placeholder={ph ?? '待补充 · 可直接填写'}
        onChange={(e) => on(e.target.value)}
        className={v ? 'filled' : ''}
      />
    </label>
  )
}

/* ---------------- 文献 ---------------- */
const REL = ['试点 → 绿色专利', '试点 → 排放强度', '碳价 → 减排', '试点 → 排放转移']
const PAPERS = [
  {
    t: '碳排放权交易与企业绿色技术创新：来自试点政策的证据',
    y: 2021,
    src: '经济研究',
    rel: 0.92,
    c: '试点使企业绿色专利申请增加约 10%',
    r: 0,
  },
  {
    t: 'Emissions trading and green innovation in China',
    y: 2022,
    src: 'JEEM',
    rel: 0.88,
    c: '效应集中在重污染行业与国企',
    r: 0,
  },
  {
    t: '碳交易试点的减排效应与机制',
    y: 2020,
    src: '中国工业经济',
    rel: 0.81,
    c: '试点地区工业碳排放强度下降 12%',
    r: 1,
  },
  {
    t: 'Carbon price volatility and firm abatement',
    y: 2023,
    src: 'Energy Econ.',
    rel: 0.64,
    c: '碳价波动大时减排效果被削弱',
    r: 2,
  },
  {
    t: '试点政策是否导致碳泄漏？',
    y: 2019,
    src: '管理世界',
    rel: 0.58,
    c: '未发现显著的跨区域排放转移',
    r: 3,
  },
  {
    t: 'Market-based environmental regulation: a review',
    y: 2018,
    src: 'REEP',
    rel: 0.47,
    c: '综述：市场型规制总体促进创新',
    r: 0,
  },
]
function Literature({
  s,
  sel,
  setSel,
  d,
}: {
  s: State
  sel: number[]
  setSel: (v: number[]) => void
  d: D
}) {
  const st = s.stages[1]
  const ro = st.status === 'confirmed'
  if (st.step === 0 && !ro && !st.prefilled)
    return (
      <Empty
        d={d}
        s={s}
        title="这里会列出与你问题相关的论文"
        what="每篇会写明：和你问题的相关度、一句话结论、支持哪条变量关系。你只需勾选认可的证据。"
        example={PAPERS[0]}
        btn="检索文献"
      />
    )
  const cover = REL.map((r, k) => ({ r, n: sel.filter((i) => PAPERS[i].r === k).length }))
  return (
    <div className="fp-col">
      <div className="fp-strip">
        <div>
          <b>{PAPERS.length}</b> 篇相关论文<small>（检索 214 篇，去重筛选后）</small>
        </div>
        <div>
          来源 <span className="fp-pill">中文 3</span>
          <span className="fp-pill">英文 3</span>
        </div>
        <div>
          年份{' '}
          <span className="fp-bars">
            {[1, 1, 1, 1, 1, 1].map((h, k) => (
              <i key={k} style={{ height: 6 + k * 3 }} />
            ))}
          </span>
          <small>2018–2023</small>
        </div>
        <div>
          关键词命中 <span className="fp-pill">碳排放权交易 6</span>
          <span className="fp-pill">绿色创新 4</span>
          <span className="fp-pill">DID 3</span>
        </div>
      </div>
      <div className="fp-split">
        <div className="fp-list" data-scroll-region>
          {PAPERS.map((p, k) => (
            <label key={k} className={'fp-paper' + (sel.includes(k) ? ' on' : '')}>
              <input
                type="checkbox"
                disabled={ro}
                checked={sel.includes(k)}
                onChange={() => setSel(sel.includes(k) ? sel.filter((x) => x !== k) : [...sel, k])}
              />
              <div className="fp-paper-b">
                <div className="fp-paper-t">{p.t}</div>
                <div className="fp-paper-m">
                  <span>
                    {p.y} · {p.src}
                  </span>
                  <span className="fp-relbar">
                    <i style={{ width: p.rel * 60 }} />
                    相关度 {Math.round(p.rel * 100)}%
                  </span>
                  <span className="fp-tagr">支持：{REL[p.r]}</span>
                </div>
                <div className="fp-paper-c">结论：{p.c}</div>
              </div>
            </label>
          ))}
        </div>
        <div className="fp-card fp-side">
          <div className="fp-label">已选证据 · {sel.length} 篇</div>
          {cover.map((c) => (
            <div key={c.r} className={'fp-cov ' + (c.n ? 'ok' : 'miss')}>
              {c.n ? '✓' : '还缺'} {c.r}
              {c.n ? <small> · {c.n} 篇</small> : null}
            </div>
          ))}
          <p className="fp-hint">
            {cover.some((c) => !c.n)
              ? '缺的关系不影响继续，但候选假设会更少。'
              : '四条关系都有证据支持。'}
          </p>
        </div>
      </div>
    </div>
  )
}

/* ---------------- 候选 ---------------- */
const CANDS = [
  {
    h: '碳交易试点提升了企业绿色专利数量',
    v: ['试点×试点后', '绿色专利数'],
    ev: 3,
    data: '上市公司面板 2008–2020',
    score: 86,
    papers: ['经济研究 2021 · 绿色专利 +10%', 'JEEM 2022 · 重污染行业更明显', 'REEP 2018 · 综述'],
    risk: '需检验平行趋势',
    rec: '证据最多，你手上的面板数据可直接做 DID',
  },
  {
    h: '碳价越高，企业减排越多',
    v: ['碳价', '排放强度'],
    ev: 1,
    data: '试点碳价日度数据 + 企业排放',
    score: 61,
    papers: ['Energy Econ. 2023 · 碳价波动削弱减排'],
    risk: '碳价数据需另行收集；内生性较强',
  },
  {
    h: '试点导致排放向非试点地区转移',
    v: ['试点', '邻省排放'],
    ev: 1,
    data: '省级排放面板',
    score: 54,
    papers: ['管理世界 2019 · 未发现显著转移'],
    risk: '现有证据偏向不显著结论',
  },
]
function Candidates({
  s,
  pick,
  setPick,
  d,
}: {
  s: State
  pick: number
  setPick: (n: number) => void
  d: D
}) {
  const st = s.stages[2]
  const ro = st.status === 'confirmed'
  if (st.step === 0 && !ro && !st.prefilled)
    return (
      <Empty
        d={d}
        s={s}
        title="这里会出现 3 条可比较的候选假设"
        what="每条写明：假设表述、涉及变量、有几篇证据支持、需要什么数据、可检验性评分。系统会推荐一条并说明理由。"
        example={{ t: CANDS[0].h, c: `可检验性 ${CANDS[0].score} · 证据 ${CANDS[0].ev} 篇` }}
        btn="生成候选假设"
      />
    )
  return (
    <div className="fp-cands">
      {CANDS.map((c, k) => (
        <label key={k} className={'fp-cand' + (pick === k ? ' on' : '') + (c.rec ? ' rec' : '')}>
          {c.rec ? (
            <div className="fp-rec">系统推荐 · {c.rec}</div>
          ) : (
            <div className="fp-rec none">&nbsp;</div>
          )}
          <div className="fp-cand-h">
            <input
              type="radio"
              name="cand"
              disabled={ro}
              checked={pick === k}
              onChange={() => setPick(k)}
            />
            {c.h}
          </div>
          <dl>
            <dt>变量</dt>
            <dd className="fp-tags">
              {c.v.map((x) => (
                <i key={x}>{x}</i>
              ))}
            </dd>
            <dt>支持证据</dt>
            <dd>{c.ev} 篇</dd>
            <dt>需要数据</dt>
            <dd>{c.data}</dd>
            <dt>主要证据</dt>
            <dd>
              <ul className="fp-evl">
                {c.papers.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
            </dd>
            <dt>风险</dt>
            <dd className="fp-risk">{c.risk}</dd>
            <dt>可检验性</dt>
            <dd>
              <span className="fp-score">
                <i style={{ width: c.score + '%' }} />
              </span>{' '}
              {c.score}
            </dd>
          </dl>
        </label>
      ))}
    </div>
  )
}

/* ---------------- 计划 ---------------- */
function Plan({ s, d }: { s: State; d: D }) {
  const st = s.stages[3]
  if (st.step === 0 && st.status !== 'confirmed' && !st.prefilled)
    return (
      <Empty
        d={d}
        s={s}
        title="这里会出现一份研究计划草案"
        what="包括：变量怎么度量、用什么模型、做哪些稳健性检验、需要哪些数据列。"
        example={{
          t: '模型：双重差分（DID）',
          c: '因变量 绿色专利数；处理 试点×试点后；控制 规模、杠杆…',
        }}
        btn="起草研究计划"
      />
    )
  return (
    <div className="fp-plan">
      <div className="fp-card">
        <div className="fp-label">变量</div>
        <table className="fp-table">
          <tbody>
            <tr>
              <th>角色</th>
              <th>变量</th>
              <th>度量</th>
            </tr>
            <tr>
              <td>因变量</td>
              <td>绿色专利数</td>
              <td>ln(1+申请数)</td>
            </tr>
            <tr>
              <td>处理</td>
              <td>试点×试点后</td>
              <td>0/1</td>
            </tr>
            <tr>
              <td>控制</td>
              <td>规模、杠杆、ROA</td>
              <td>年报</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div className="fp-card">
        <div className="fp-label">模型</div>
        <p>双重差分（DID），企业与年份双向固定效应，标准误聚类到省份。</p>
        <div className="fp-label">结论强度上限</div>
        <p>因果（满足平行趋势时）</p>
      </div>
      <div className="fp-card">
        <div className="fp-label">稳健性检验</div>
        <ol className="fp-ol">
          <li>平行趋势 / 事件研究</li>
          <li>PSM-DID</li>
          <li>安慰剂检验（随机试点）</li>
        </ol>
        <div className="fp-label">需要的数据列</div>
        <div className="fp-tags">
          {['firm_id', 'year', 'province', 'green_patents', 'size'].map((x) => (
            <i key={x}>{x}</i>
          ))}
        </div>
      </div>
    </div>
  )
}

/* ---------------- 数据 ---------------- */
function Data({ s, d }: { s: State; d: D }) {
  const st = s.stages[4]
  const done = st.status === 'confirmed'
  const step = st.step
  if (step === 0 && !done)
    return (
      <div className="fp-empty2">
        <h3>上传数据表，系统会建议每个变量对应哪一列</h3>
        <p>支持 CSV / Excel。研究计划需要这些列：</p>
        <div className="fp-tags">
          {['firm_id', 'year', 'province', 'green_patents', 'pilot', 'size'].map((x) => (
            <i key={x}>{x}</i>
          ))}
        </div>
        <div className="fp-drop">把文件拖到这里</div>
        <div className="fp-chips">
          <button className="fp-chip" onClick={() => d({ type: 'primary' })}>
            上传数据
          </button>
          <button className="fp-chip" onClick={() => d({ type: 'primary' })}>
            用示例数据（碳交易 · 3,412 家企业）
          </button>
        </div>
      </div>
    )
  return (
    <div className="fp-plan">
      <div className="fp-card">
        <div className="fp-label">数据概况</div>
        <p>
          <b>carbon_panel.csv</b>
        </p>
        <p>3,412 家企业 × 13 年 · 44,356 行</p>
        <p className="fp-hint">缺失：green_patents 2.1%，size 0.4%</p>
      </div>
      <div className="fp-card" style={{ gridColumn: 'span 2' }}>
        <div className="fp-label">
          {step === 1 ? '系统建议的变量绑定 · 确认无误后点主按钮' : '变量绑定'}
        </div>
        <table className="fp-table">
          <tbody>
            <tr>
              <th>变量</th>
              <th>数据列</th>
              <th>依据</th>
              <th></th>
            </tr>
            <tr>
              <td>绿色专利数</td>
              <td>green_patents</td>
              <td>列名匹配</td>
              <td>{step === 1 ? '建议' : '✓'}</td>
            </tr>
            <tr>
              <td>是否试点</td>
              <td>pilot</td>
              <td>取值 0/1</td>
              <td>{step === 1 ? '建议' : '✓'}</td>
            </tr>
            <tr>
              <td>试点后</td>
              <td>post_2013</td>
              <td>由 year 生成</td>
              <td>{step === 1 ? '建议' : '✓'}</td>
            </tr>
            <tr>
              <td>规模</td>
              <td>size</td>
              <td>列名匹配</td>
              <td>{step === 1 ? '建议' : '✓'}</td>
            </tr>
          </tbody>
        </table>
        {step >= 3 || done ? (
          <p className="fp-result">
            检验结果：DID 系数 0.084（p=0.012）；平行趋势通过；结论强度：关联。
          </p>
        ) : step === 2 ? (
          <p className="fp-hint">绑定已确认。点右上角「运行检验」：主回归 + 2 项稳健性。</p>
        ) : null}
      </div>
      <div className="fp-card" style={{ gridColumn: 'span 3' }}>
        <div className="fp-label">数据预览 · 前 3 行（共 44,356 行）</div>
        <table className="fp-table">
          <tbody>
            <tr>
              {['firm_id', 'year', 'province', 'pilot', 'post_2013', 'green_patents', 'size'].map(
                (h) => (
                  <th key={h}>{h}</th>
                ),
              )}
            </tr>
            {[
              [600019, 2012, '上海', 1, 0, 14, 11.2],
              [600019, 2014, '上海', 1, 1, 21, 11.4],
              [898, 2014, '辽宁', 0, 1, 3, 10.8],
            ].map((r, k) => (
              <tr key={k}>
                {r.map((c, j) => (
                  <td key={j}>{c}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/* ---------------- 提案 ---------------- */
function Proposal({ s, d }: { s: State; d: D }) {
  const st = s.stages[5]
  if (st.step === 0 && st.status !== 'confirmed')
    return (
      <Empty
        d={d}
        s={s}
        title="这里会生成一份完整的研究提案"
        what="五节：研究背景、文献综述、假设、研究设计、初步结果。全部来自前面已确认的内容，自动保存。"
        example={{ t: '假设', c: 'H1：碳排放权交易试点提升了企业绿色专利数量……' }}
        btn="生成提案"
      />
    )
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
                <button
                  className="fp-btn-2"
                  onClick={() => d({ type: 'regenSection', section: sec })}
                >
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

/* ---------------- 空状态 ---------------- */
function Empty({
  s,
  d,
  title,
  what,
  example,
  btn,
}: {
  s: State
  d: D
  title: string
  what: string
  example: { t: string; c: string }
  btn: string
}) {
  const blocked = s.llm === 'unconfigured' || s.llm === 'failed'
  return (
    <div className="fp-empty2">
      <h3>{title}</h3>
      <p>{what}</p>
      <div className="fp-example">
        <small>示例</small>
        <b>{example.t}</b>
        <span>{example.c}</span>
      </div>
      {blocked ? (
        <p className="fp-hint">需要先处理右上角的模型问题。</p>
      ) : (
        <button className="fp-chip big" onClick={() => d({ type: 'primary' })}>
          {btn}
        </button>
      )}
    </div>
  )
}

export interface UiState {
  dir: DirState
  setDir: (d: DirState) => void
  sel: number[]
  setSel: (v: number[]) => void
  pick: number
  setPick: (n: number) => void
}
export function Content({ s, i, d, ui }: { s: State; i: number; d: D; ui: UiState }) {
  switch (STAGES[i].id) {
    case 'direction':
      return <Direction s={s} dir={ui.dir} setDir={ui.setDir} />
    case 'literature':
      return <Literature s={s} sel={ui.sel} setSel={ui.setSel} d={d} />
    case 'candidates':
      return <Candidates s={s} pick={ui.pick} setPick={ui.setPick} d={d} />
    case 'plan':
      return <Plan s={s} d={d} />
    case 'data':
      return <Data s={s} d={d} />
    default:
      return <Proposal s={s} d={d} />
  }
}
export const seedDir = seed
export const answerDir = answer
export const QCOUNT = QS.length
