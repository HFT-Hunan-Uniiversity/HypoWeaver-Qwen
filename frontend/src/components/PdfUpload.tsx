import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { ErrorNote } from './Shared'
export default function PdfUpload({projectId}:{projectId:string}){
 const cache=useQueryClient(),[file,setFile]=useState<File|null>(null),[message,setMessage]=useState('')
 const upload=useMutation({mutationFn:()=>{const data=new FormData();data.append('file',file!);return api<{message:string}>(`/projects/${projectId}/evidence/pdf`,{method:'POST',body:data})},onSuccess:r=>{setMessage(r.message);cache.invalidateQueries({queryKey:['evidence',projectId]})}})
 return <section className="panel"><h2>补充论文 PDF</h2><p className="muted">提取文字与元数据；标题和年份可在证据卡中修正。单个文件最多 30 MB，扫描件需先完成 OCR。</p><input type="file" accept=".pdf,application/pdf" aria-label="选择论文 PDF" onChange={e=>{setMessage('');setFile(e.target.files?.[0]||null)}}/><ErrorNote error={upload.error}/>{message&&<p role="status">{message}</p>}<button disabled={!file||upload.isPending} onClick={()=>upload.mutate()}>{upload.isPending?'正在提取…':'上传并提取'}</button></section>
}
