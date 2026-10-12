import { Link, useParams } from 'react-router-dom'
import StaleBanner from './StaleBanner'
import type { Stage } from '../api/client'
export function ErrorNote({error}:{error:Error|null}) {return error?<p role="alert" className="error">{error.message}</p>:null}
export function StageStepper({stages}:{stages:Stage[]}) {
 const {id}=useParams()
 const labels:Record<string,string>={not_started:'未开始',running:'进行中',completed:'已完成',stale:'已过期',draft:'待审阅',ready:'已绑定',failed:'需处理',awaiting_selection:'待选择'}
 return <nav className="steps" aria-label="研究阶段">{stages.map((s,i)=><Link to={`/p/${id}/${s.key}`} key={s.key}><span className="step-number">0{i+1}</span><strong>{s.label}</strong><small>{labels[s.status]||s.status}</small></Link>)}</nav>
}
export function ProjectBack(){const {id}=useParams();return <><Link className="back" to={`/p/${id}`}>← 项目总览</Link><StaleBanner/></>}
