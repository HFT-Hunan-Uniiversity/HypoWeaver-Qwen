import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Literature from './pages/Literature'
import Settings from './pages/Settings'
import Projects from './pages/Projects'
import Overview from './pages/Overview'
import Direction from './pages/Direction'
import { ProjectBack } from './components/Shared'
import './styles/app.css'
const client=new QueryClient({defaultOptions:{queries:{retry:false}}})
function PendingStage(){return <><ProjectBack/><h1>此阶段尚未开放</h1><p className="muted">功能按执行计划逐步接入，当前可创建项目并编辑研究方向。</p></>}
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={client}><BrowserRouter><header><Link className="brand" to="/">HypoWeaver <span>研究工作台</span></Link><nav><Link to="/">研究项目</Link>　<Link to="/settings">设置</Link></nav></header><main><Routes><Route path="/" element={<Projects/>}/><Route path="/settings" element={<Settings/>}/><Route path="/p/:id" element={<Overview/>}/><Route path="/p/:id/direction" element={<Direction/>}/><Route path="/p/:id/literature" element={<Literature/>}/><Route path="/p/:id/:stage" element={<PendingStage/>}/><Route path="*" element={<><h1>页面不存在</h1><Link to="/">返回项目列表</Link></>}/></Routes></main><footer>HypoWeaver · 文献有出处，数字可复核，结论有边界。</footer></BrowserRouter></QueryClientProvider></React.StrictMode>)
