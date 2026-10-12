import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart, Bar, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { api } from '../api/client'
import { ErrorNote } from './Shared'
interface LandscapeData {
  sample_label: string
  n_cards: number
  unknown_year: number
  years: { year: number; count: number }[]
  venues: { name: string; count: number }[]
  keywords: { name: string; count: number }[]
  edges: { source: string; target: string; count: number }[]
  methods: { name: string; count: number }[]
  top_cited: { id: string; title: string; cited_by: number }[]
}
function Network({ data }: { data: LandscapeData }) {
  const points = useMemo(() => {
    const nodes = data.keywords.map((k, i) => ({
      ...k,
      x: 360 + 220 * Math.cos((i * 2 * Math.PI) / data.keywords.length),
      y: 200 + 130 * Math.sin((i * 2 * Math.PI) / data.keywords.length),
    }))
    for (let step = 0; step < 120; step++) {
      const force = nodes.map((n) => ({ x: (360 - n.x) * 0.006, y: (200 - n.y) * 0.006 }))
      nodes.forEach((a, i) =>
        nodes.forEach((b, j) => {
          if (i >= j) return
          const dx = a.x - b.x,
            dy = a.y - b.y,
            d = Math.max(10, Math.hypot(dx, dy))
          const f = 9000 / (d * d * d)
          force[i].x += dx * f
          force[i].y += dy * f
          force[j].x -= dx * f
          force[j].y -= dy * f
        }),
      )
      data.edges.forEach((e) => {
        const i = nodes.findIndex((n) => n.name === e.source),
          j = nodes.findIndex((n) => n.name === e.target)
        if (i < 0 || j < 0) return
        const dx = nodes[j].x - nodes[i].x,
          dy = nodes[j].y - nodes[i].y
        const length = Math.max(1, Math.hypot(dx, dy)),
          spring = ((length - 140) * 0.007) / length
        force[i].x += dx * spring
        force[i].y += dy * spring
        force[j].x -= dx * spring
        force[j].y -= dy * spring
      })
      nodes.forEach((n, i) => {
        n.x = Math.max(75, Math.min(645, n.x + force[i].x))
        n.y = Math.max(35, Math.min(365, n.y + force[i].y))
      })
    }
    return nodes
  }, [data])
  return (
    <svg
      viewBox="0 0 720 400"
      role="img"
      aria-label="关键词共现网络，节点大小表示出现次数，连线表示共同出现"
    >
      <title>本次纳入证据的关键词共现网络</title>
      {data.edges.map((e) => {
        const a = points.find((n) => n.name === e.source)!,
          b = points.find((n) => n.name === e.target)!
        return (
          <line
            key={e.source + e.target}
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            stroke="#aac9bd"
            strokeWidth={Math.min(4, 1 + e.count / 5)}
          >
            <title>
              {e.source} / {e.target}：{e.count}
            </title>
          </line>
        )
      })}
      {points.map((p) => (
        <g key={p.name}>
          <circle cx={p.x} cy={p.y} r={5 + Math.sqrt(p.count) * 1.4} fill="#397d6a" />
          <text
            x={p.x}
            y={p.y - 13 - Math.sqrt(p.count)}
            textAnchor="middle"
            fontSize="12"
            fill="#304d43"
          >
            {p.name.length > 22 ? p.name.slice(0, 20) + '…' : p.name}
          </text>
          <title>
            {p.name}：{p.count} 篇
          </title>
        </g>
      ))}
    </svg>
  )
}
function Bars({ data, name }: { data: Record<string, string | number>[]; name: string }) {
  return (
    <div style={{ height: 260, width: '100%', minWidth: 0 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 10, right: 12, bottom: 35, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey={name} interval={0} angle={-25} textAnchor="end" tick={{ fontSize: 10 }} />
          <YAxis allowDecimals={false} width={35} />
          <Tooltip />
          <Bar dataKey="count" name="文献数" fill="#397d6a" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
export default function Landscape({ projectId }: { projectId: string }) {
  const q = useQuery({
    queryKey: ['landscape', projectId],
    queryFn: () => api<LandscapeData>(`/projects/${projectId}/landscape`),
  })
  if (q.error) return <ErrorNote error={q.error} />
  if (!q.data?.n_cards)
    return (
      <section className="panel">
        <h2>文献概况</h2>
        <p className="muted">纳入文献后，将显示本次样本的年度、期刊、关键词和方法分布。</p>
      </section>
    )
  const d = q.data
  return (
    <section className="panel">
      <h2>文献概况</h2>
      <p className="sample-note">
        {d.sample_label} · {d.n_cards} 条纳入证据（含补充文献）。这些分布不代表整个学科的趋势。
      </p>
      <div className="chart-grid">
        <article>
          <h3>年度分布</h3>
          <Bars data={d.years} name="year" />
          <small>年份未知：{d.unknown_year} 条</small>
        </article>
        <article>
          <h3>主要期刊 · 前 10 位</h3>
          <ol className="venue-list">
            {d.venues.map((v) => (
              <li key={v.name}>
                <span>{v.name}</span>
                <strong>{v.count}</strong>
              </li>
            ))}
          </ol>
        </article>
        <article>
          <h3>关键词共现</h3>
          <Network data={d} />
          <details>
            <summary>查看关键词频次</summary>
            {d.keywords.map((k) => (
              <p key={k.name}>
                {k.name}：{k.count}
              </p>
            ))}
          </details>
        </article>
        <article>
          <h3>方法关键词提及</h3>
          <Bars data={d.methods} name="name" />
          <small>按标题、摘要及摘录中的关键词计数，不代表论文实际采用该方法。</small>
        </article>
      </div>
      <details>
        <summary>高被引文献与年度计数</summary>
        {d.top_cited.map((c) => (
          <p key={c.id}>
            {c.title} · 被引 {c.cited_by}
          </p>
        ))}
        <p>{d.years.map((y) => `${y.year} 年：${y.count}`).join('；')}</p>
      </details>
    </section>
  )
}
