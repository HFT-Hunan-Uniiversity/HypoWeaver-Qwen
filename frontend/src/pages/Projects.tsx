import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, body, type Project } from '../api/client'
import { ErrorNote } from '../components/Shared'
export default function Projects(){
 const query=useQuery({queryKey:['projects'],queryFn:()=>api<Project[]>('/projects')})
 const [open,setOpen]=useState(false),[title,setTitle]=useState(''),[deleting,setDeleting]=useState<Project|null>(null)
 const navigate=useNavigate(), cache=useQueryClient()
 const create=useMutation({mutationFn:()=>api<Project>('/projects',body('POST',{title})),onSuccess:p=>{cache.invalidateQueries({queryKey:['projects']});navigate(`/p/${p.id}`)}})
 const remove=useMutation({mutationFn:(id:string)=>api(`/projects/${id}`,body('DELETE')),onSuccess:()=>{setDeleting(null);cache.invalidateQueries({queryKey:['projects']})}})
 return <><div className="heading"><div><p className="eyebrow">RESEARCH WORKSPACE</p><h1>我的研究项目</h1><p className="muted">从一个问题出发，让文献、数据与判断相互印证。</p></div><button onClick={()=>setOpen(true)}>＋ 新建项目</button></div>
 <ErrorNote error={query.error||remove.error}/>{query.isPending?<p>正在读取项目…</p>:query.data?.length?<div className="project-list">{query.data.map(p=><article key={p.id}><div><Link className="project-title" to={`/p/${p.id}`}>{p.title}</Link><p className="muted">{p.direction.text||'尚未填写研究方向'}</p><small>更新于 {new Date(p.updated_at).toLocaleString('zh-CN')}</small></div><button className="quiet" disabled={remove.isPending} onClick={()=>setDeleting(p)}>删除</button></article>)}</div>:!query.error&&<div className="empty"><h2>把第一个研究问题放在这里</h2><p>创建项目后，依次整理文献、比较选题、制定方案并检验。</p><button onClick={()=>setOpen(true)}>新建研究项目</button></div>}
 {deleting&&<div className="overlay"><section className="dialog" role="dialog" aria-modal="true" aria-labelledby="delete-title"><h2 id="delete-title">删除项目</h2><p>确认删除“{deleting.title}”？项目内容将被删除。</p><ErrorNote error={remove.error}/><div className="actions"><button className="quiet" onClick={()=>setDeleting(null)}>取消</button><button disabled={remove.isPending} onClick={()=>remove.mutate(deleting.id)}>确认删除</button></div></section></div>}
 {open&&<div className="overlay"><section role="dialog" aria-modal="true" aria-labelledby="new-title" className="dialog"><h2 id="new-title">新建研究项目</h2><form onSubmit={e=>{e.preventDefault();create.mutate()}}><label>项目标题<input autoFocus required maxLength={200} value={title} onChange={e=>setTitle(e.target.value)} placeholder="例如：碳市场与企业绿色创新"/></label><ErrorNote error={create.error}/><div className="actions"><button type="button" className="quiet" onClick={()=>setOpen(false)}>取消</button><button disabled={create.isPending||!title.trim()}>{create.isPending?'正在创建…':'创建项目'}</button></div></form></section></div>}</>
}
