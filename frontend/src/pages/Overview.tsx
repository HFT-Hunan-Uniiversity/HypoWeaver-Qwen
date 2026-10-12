import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, type Project, type Stage } from '../api/client'
import StaleBanner from '../components/StaleBanner'
import { ErrorNote, StageStepper } from '../components/Shared'
export default function Overview() {
  const { id } = useParams()
  const q = useQuery({
    queryKey: ['overview', id],
    queryFn: () => api<{ project: Project; stages: Stage[] }>(`/projects/${id}/overview`),
  })
  if (q.isPending) return <p>正在读取项目…</p>
  if (!q.data) return <ErrorNote error={q.error} />
  return (
    <>
      <Link className="back" to="/">
        ← 所有项目
      </Link>
      <p className="eyebrow">研究项目总览</p>
      <h1>{q.data.project.title}</h1>
      <StageStepper stages={q.data.stages} />
      <StaleBanner />
      <section className="overview-grid">
        {q.data.stages.map((s) => (
          <Link className="panel" key={s.key} to={`/p/${id}/${s.key}`}>
            <h2>{s.label}</h2>
            <p>{s.summary}</p>
            <span>进入阶段 →</span>
          </Link>
        ))}
      </section>
      <Link className="button" to={`/p/${id}/analysis`}>
        查看统计检验 →
      </Link>
      <section className="panel">
        <p className="eyebrow">从这里开始</p>
        <h2>明确你想回答的问题</h2>
        <p>
          {q.data.project.direction.text ||
            '填写研究方向、具体问题与约束，为后续检索和方案提供依据。'}
        </p>
        <Link className="button" to={`/p/${id}/direction`}>
          编辑研究方向 →
        </Link>
      </section>
    </>
  )
}
