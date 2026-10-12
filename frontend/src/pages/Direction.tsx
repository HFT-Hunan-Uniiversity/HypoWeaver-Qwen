import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, body, type Direction as DirectionType, type Project } from '../api/client'
import { ErrorNote, ProjectBack } from '../components/Shared'
function Editor({project}:{project:Project}){
 const [draft,setDraft]=useState<DirectionType>(project.direction),[saved,setSaved]=useState(false)
 const cache=useQueryClient()
 const mutation=useMutation({mutationFn:()=>api(`/projects/${project.id}`,body('PATCH',{direction:draft})),onSuccess:()=>{setSaved(true);cache.invalidateQueries({queryKey:['projects']});cache.invalidateQueries({queryKey:['overview',project.id]});cache.invalidateQueries({queryKey:['project',project.id]})}})
 const field=(key:keyof DirectionType,value:string|string[])=>{setSaved(false);setDraft({...draft,[key]:value})}
 return <form className="panel form" onSubmit={e=>{e.preventDefault();mutation.mutate()}}><label>研究方向<textarea required rows={3} value={draft.text} onChange={e=>field('text',e.target.value)} placeholder="你希望研究什么现象？"/></label><label>具体问题（可选）<textarea rows={3} value={draft.question} onChange={e=>field('question',e.target.value)}/></label><label>研究约束（每行一项）<textarea rows={3} value={draft.constraints.join('\n')} onChange={e=>field('constraints',e.target.value.split('\n'))}/></label><label>领域<input value={draft.domain} onChange={e=>field('domain',e.target.value)} placeholder="例如：绿色金融"/></label><ErrorNote error={mutation.error}/><div className="actions"><span role="status">{saved?'已保存':''}</span><button disabled={mutation.isPending}>{mutation.isPending?'正在保存…':'保存研究方向'}</button></div></form>
}
export default function Direction(){const {id}=useParams();const q=useQuery({queryKey:['project',id],queryFn:()=>api<Project>(`/projects/${id}`)});return <><ProjectBack/><h1>研究方向</h1><p className="muted">写下问题与边界，后续研究围绕这些信息展开。</p><ErrorNote error={q.error}/>{q.data?<Editor project={q.data}/>:q.isPending&&<p>正在读取…</p>}</>}
