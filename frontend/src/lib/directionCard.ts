/**
 * 方向卡 ↔ 后端 Direction 的映射。
 * 后端只有 text / question / constraints / domain 四个字段（无"澄清对话"接口），
 * 方向卡的结构化字段以"前缀：值"的形式存入 constraints，未带前缀的约束原样保留。
 */
import type { Direction } from '../api/client'

export interface DirCard {
  idea: string
  question: string
  vars: string[]
  region: string
  period: string
  claim: string
  data: string
  keywords: string[]
  domain: string
  other: string[]
}
const P = {
  vars: '变量：',
  region: '地区：',
  period: '时间：',
  claim: '结论类型：',
  data: '数据：',
  keywords: '关键词：',
} as const
const split = (s: string) =>
  s
    .split(/[、,，;；]/)
    .map((x) => x.trim())
    .filter(Boolean)

export function fromDirection(d: Direction): DirCard {
  const c: DirCard = {
    idea: d.text || '',
    question: d.question || '',
    vars: [],
    region: '',
    period: '',
    claim: '',
    data: '',
    keywords: [],
    domain: d.domain || '',
    other: [],
  }
  for (const raw of d.constraints || []) {
    const line = raw.trim()
    if (!line) continue
    if (line.startsWith(P.vars)) c.vars = split(line.slice(P.vars.length))
    else if (line.startsWith(P.keywords)) c.keywords = split(line.slice(P.keywords.length))
    else if (line.startsWith(P.region)) c.region = line.slice(P.region.length)
    else if (line.startsWith(P.period)) c.period = line.slice(P.period.length)
    else if (line.startsWith(P.claim)) c.claim = line.slice(P.claim.length)
    else if (line.startsWith(P.data)) c.data = line.slice(P.data.length)
    else c.other.push(line)
  }
  return c
}

export function toDirection(c: DirCard): Direction {
  const constraints = [
    c.vars.length ? P.vars + c.vars.join('、') : '',
    c.region ? P.region + c.region : '',
    c.period ? P.period + c.period : '',
    c.claim ? P.claim + c.claim : '',
    c.data ? P.data + c.data : '',
    c.keywords.length ? P.keywords + c.keywords.join('、') : '',
    ...c.other,
  ].filter(Boolean)
  return { text: c.idea, question: c.question, constraints, domain: c.domain }
}

/** 方向卡还缺什么（决定主按钮是否可用） */
export function cardMissing(c: DirCard): string[] {
  const m: string[] = []
  if (!c.question.trim()) m.push('研究问题')
  if (c.vars.length < 2) m.push('至少两个变量')
  if (!c.region.trim() || !c.period.trim()) m.push('范围')
  if (!c.claim.trim()) m.push('因果/关联')
  return m
}

/** 检索关键词：显式关键词优先，否则由变量 + 地区推导 */
export function searchTerms(c: DirCard): string[] {
  if (c.keywords.length) return c.keywords
  return [...c.vars.map((v) => v.replace(/[（(].*?[)）]/g, '').trim()), c.domain].filter(Boolean)
}

/** 澄清问题（后端暂无对话接口：前端固定问题序列，选项 + 自由输入） */
export interface ClarifyQ {
  key: 'vars' | 'region' | 'period' | 'claim' | 'data'
  q: string
  chips: string[]
  hint?: string
}
export const CLARIFY: ClarifyQ[] = [
  {
    key: 'vars',
    q: '你关心的"原因"和"结果"分别是什么？用顿号分开，例如：碳交易试点、绿色专利数量',
    chips: [],
    hint: '原因、结果（可再加机制变量）',
  },
  { key: 'region', q: '研究哪个地区或对象？', chips: ['全国', '部分试点省市', '某一省份', '跨国'] },
  { key: 'period', q: '看哪段时间？', chips: ['近 10 年', '2010–2020', '2015 年至今'] },
  {
    key: 'claim',
    q: '你想证明因果关系，还是看两者是否相关就够了？',
    chips: ['想证明因果', '看关联就够', '不确定，帮我判断'],
  },
  {
    key: 'data',
    q: '手上已经有数据了吗？',
    chips: ['已有面板数据', '准备用公开数据', '还没有数据'],
  },
]
export function nextQuestion(c: DirCard): ClarifyQ | undefined {
  return CLARIFY.find((q) => (q.key === 'vars' ? c.vars.length < 2 : !c[q.key].trim()))
}
export function applyAnswer(c: DirCard, q: ClarifyQ, text: string): DirCard {
  if (q.key === 'vars') {
    const vars = split(text)
    return { ...c, vars, keywords: c.keywords.length ? c.keywords : vars }
  }
  if (q.key === 'claim') {
    const v = text.includes('因果')
      ? '因果（需要准实验设计）'
      : text.includes('关联')
        ? '关联'
        : '先做关联，数据允许再升级为因果'
    return { ...c, claim: v }
  }
  return { ...c, [q.key]: text }
}
export const EXAMPLE_IDEAS = [
  '碳交易会不会让企业更绿色？',
  '最低工资上涨是否减少了就业？',
  '数字普惠金融能否缓解农村贫困？',
]
