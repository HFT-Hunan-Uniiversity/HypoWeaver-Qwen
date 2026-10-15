import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, body, type Project } from '../api/client'
import { ErrorNote } from '../components/Shared'
import { useFlow, useFlowStage, useStageUi } from '../components/flow/FlowContext'
import {
  applyAnswer,
  cardMissing,
  EXAMPLE_IDEAS,
  fromDirection,
  nextQuestion,
  toDirection,
  type DirCard,
} from '../lib/directionCard'

const draftKey = (id: string) => `hw.dirdraft.${id}`

/** 研究方向：一句话想法 → 方向卡字段（两列）；澄清问题以卡内提示给出，可点选项直接填入。草稿自动保存在本机，确认时写入项目。 */
function Editor({ project }: { project: Project }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { confirm } = useFlow()
  const stage = useFlowStage('direction')
  const ro = !stage.editable
  const stored = (() => {
    try {
      return JSON.parse(localStorage.getItem(draftKey(project.id)) || 'null') as {
        card: DirCard
      } | null
    } catch {
      return null
    }
  })()
  const [card, setCard] = useState<DirCard>(
    () => (!ro && stored?.card) || fromDirection(project.direction),
  )
  const [input, setInput] = useState('')
  const [answerText, setAnswerText] = useState('')
  const [savedAt, setSavedAt] = useState<string>('')
  const [skipped, setSkipped] = useState(false)
  const q = nextQuestion(card)
  const missing = cardMissing(card)
  const started = !!card.idea || !!card.question || skipped

  // 草稿自动保存（本机）
  useEffect(() => {
    if (ro || !started) return
    const t = setTimeout(() => {
      localStorage.setItem(draftKey(project.id), JSON.stringify({ card }))
      setSavedAt(new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }))
    }, 500)
    return () => clearTimeout(t)
  }, [card, ro, started, project.id])

  const save = useMutation({
    mutationFn: () =>
      api(`/projects/${project.id}`, body('PATCH', { direction: toDirection(card) })),
    onSuccess: () => {
      localStorage.removeItem(draftKey(project.id))
      qc.invalidateQueries()
      const wasEdit = confirm('direction')
      if (!wasEdit) navigate(`/p/${project.id}/literature?auto=1`)
    },
  })

  useStageUi({
    primary: !started
      ? { label: '确认方向并检索文献', disabled: true, reason: '先写一句想法' }
      : missing.length
        ? {
            label: '确认方向并检索文献',
            disabled: true,
            reason: '方向卡还缺：' + missing.join('、'),
          }
        : {
            label: stage.editing ? '确认方向' : save.isPending ? '正在保存…' : '确认方向并检索文献',
            busy: save.isPending,
            error: save.error ? (save.error as Error).message : null,
            onClick: () => save.mutate(),
          },
  })

  const start = (idea: string) =>
    setCard({ ...card, idea, question: card.question || idea.replace(/[？?]$/, '') + '？' })
  const answer = (text: string) => {
    if (!q || !text.trim()) return
    setCard(applyAnswer(card, q, text.trim()))
    setAnswerText('')
  }
  const set = <K extends keyof DirCard>(k: K, v: DirCard[K]) => setCard({ ...card, [k]: v })
  const list = (s: string) =>
    s
      .split(/[、,，]/)
      .map((x) => x.trim())
      .filter(Boolean)

  if (!started && !ro)
    return (
      <section className="dir-start">
        <p className="nb-hint">
          先用一句话说说你想研究什么，不用写得很专业。系统会把它整理成方向卡：研究问题、变量、范围、检索关键词。
        </p>
        <form
          className="dir-idea"
          onSubmit={(e) => {
            e.preventDefault()
            if (input.trim()) start(input.trim())
            setInput('')
          }}
        >
          <input
            aria-label="你的研究想法"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="例如：碳交易会不会让企业更绿色？"
          />
          <button className="product-button" disabled={!input.trim()}>
            开始
          </button>
        </form>
        <div className="dir-chips">
          <span className="muted">例子：</span>
          {EXAMPLE_IDEAS.map((e) => (
            <button key={e} type="button" className="dir-chip" onClick={() => start(e)}>
              {e}
            </button>
          ))}
          <button type="button" className="link-button" onClick={() => setSkipped(true)}>
            直接填方向卡
          </button>
        </div>
      </section>
    )

  return (
    <section className="dir-card" aria-label="方向卡">
      <div className="dir-card__hd">
        {missing.length ? (
          <span className="dir-miss">还缺：{missing.join('、')}</span>
        ) : (
          <span className="dir-ok">✓ 方向卡完整</span>
        )}
        {!ro && savedAt && <small className="muted">草稿已自动保存 · {savedAt}</small>}
      </div>
      {!ro && q && (
        <div className="nb-hint dir-ask">
          <strong>还需澄清：</strong>
          {q.q}
          <div className="dir-chips">
            {q.chips.map((c) => (
              <button key={c} type="button" className="dir-chip" onClick={() => answer(c)}>
                {c}
              </button>
            ))}
            <form
              className="dir-idea is-inline"
              onSubmit={(e) => {
                e.preventDefault()
                answer(answerText)
              }}
            >
              <input
                aria-label={q.q}
                value={answerText}
                onChange={(e) => setAnswerText(e.target.value)}
                placeholder={q.hint || '自己填写'}
              />
              <button className="product-button" disabled={!answerText.trim()}>
                填入
              </button>
            </form>
          </div>
        </div>
      )}
      <div className="dir-grid">
        <Field
          label="研究问题"
          value={card.question}
          ro={ro}
          onChange={(v) => set('question', v)}
          area
        />
        <Field
          label="原始想法"
          value={card.idea}
          ro={ro}
          ph="一句话想法"
          onChange={(v) => set('idea', v)}
          area
        />
        <Field
          label="变量"
          value={card.vars.join('、')}
          ro={ro}
          ph="原因、结果（顿号分隔）"
          onChange={(v) => set('vars', list(v))}
          tags={card.vars}
        />
        <Field
          label="检索关键词"
          value={card.keywords.join('、')}
          ro={ro}
          ph="根据变量自动生成，可修改"
          onChange={(v) => set('keywords', list(v))}
          tags={card.keywords}
          kw
        />
        <Field label="地区 / 对象" value={card.region} ro={ro} onChange={(v) => set('region', v)} />
        <Field label="时间" value={card.period} ro={ro} onChange={(v) => set('period', v)} />
        <Field label="因果 / 关联" value={card.claim} ro={ro} onChange={(v) => set('claim', v)} />
        <Field
          label="领域"
          value={card.domain}
          ro={ro}
          ph="可选，例如：绿色金融"
          onChange={(v) => set('domain', v)}
        />
        <Field
          label="手上数据"
          value={card.data}
          ro={ro}
          ph="可选"
          onChange={(v) => set('data', v)}
        />
      </div>
      {card.other.length > 0 && <p className="muted">其他约束：{card.other.join('；')}</p>}
      <ErrorNote error={save.error} />
    </section>
  )
}

function Field(props: {
  label: string
  value: string
  ro: boolean
  onChange: (v: string) => void
  ph?: string
  area?: boolean
  tags?: string[]
  kw?: boolean
}) {
  const { label, value, ro, onChange, ph, area, tags, kw } = props
  const [focus, setFocus] = useState(false)
  const cls = `dir-input ${value ? 'is-filled' : ''}`
  return (
    <label className="dir-field">
      <span>{label}</span>
      {tags && tags.length > 0 && !focus ? (
        <button
          type="button"
          className={`dir-tags ${kw ? 'is-kw' : ''}`}
          disabled={ro}
          onClick={() => setFocus(true)}
          title={ro ? undefined : '点击编辑'}
        >
          {tags.map((t) => (
            <i key={t}>{t}</i>
          ))}
        </button>
      ) : area ? (
        <textarea
          className={cls}
          rows={2}
          readOnly={ro}
          value={value}
          placeholder={ph || '待补充 · 可直接填写'}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <input
          className={cls}
          readOnly={ro}
          value={value}
          autoFocus={focus}
          onBlur={() => setFocus(false)}
          placeholder={ph || '待补充 · 可直接填写'}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </label>
  )
}

export default function Direction() {
  const { id } = useParams()
  const q = useQuery({ queryKey: ['project', id], queryFn: () => api<Project>(`/projects/${id}`) })
  return (
    <>
      <ErrorNote error={q.error} />
      {q.data ? (
        <Editor key={q.data.id} project={q.data} />
      ) : (
        q.isPending && <p className="loading-line">正在读取…</p>
      )}
    </>
  )
}
