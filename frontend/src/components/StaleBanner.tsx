import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api,type Stage } from '../api/client'
export default function StaleBanner(){
 const {id}=useParams()
 const query=useQuery({queryKey:['overview',id],queryFn:()=>api<{stages:Stage[]}>(`/projects/${id}/overview`),enabled:!!id})
 const stale=query.data?.stages.filter(s=>s.status==='stale')||[]
 return stale.length?<p className="notice" role="status">{stale.map(s=>s.label).join('、')}已过期。上游信息已变化，旧内容仍可查看；请按研究阶段重新生成或运行。</p>:null
}
