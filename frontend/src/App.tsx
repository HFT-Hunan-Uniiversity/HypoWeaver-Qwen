import { lazy,Suspense } from 'react'
import { BrowserRouter,Link,Route,Routes } from 'react-router-dom'
const Projects=lazy(()=>import('./pages/Projects'))
const Settings=lazy(()=>import('./pages/Settings'))
const Overview=lazy(()=>import('./pages/Overview'))
const Direction=lazy(()=>import('./pages/Direction'))
const Literature=lazy(()=>import('./pages/Literature'))
const Candidates=lazy(()=>import('./pages/Candidates'))
const Plan=lazy(()=>import('./pages/Plan'))
const Data=lazy(()=>import('./pages/Data'))
const Analysis=lazy(()=>import('./pages/Analysis'))
const Proposal=lazy(()=>import('./pages/Proposal'))
export default function App(){
 return <BrowserRouter><a className="skip-link" href="#main-content">跳到正文</a><header><Link className="brand" to="/">HypoWeaver <span>研究工作台</span></Link><nav aria-label="工作台导航"><Link to="/">研究项目</Link>　<Link to="/settings">设置</Link></nav></header><main id="main-content"><Suspense fallback={<p role="status" className="panel">正在加载研究页面…</p>}><Routes><Route path="/" element={<Projects/>}/><Route path="/settings" element={<Settings/>}/><Route path="/p/:id" element={<Overview/>}/><Route path="/p/:id/direction" element={<Direction/>}/><Route path="/p/:id/literature" element={<Literature/>}/><Route path="/p/:id/candidates" element={<Candidates/>}/><Route path="/p/:id/plan" element={<Plan/>}/><Route path="/p/:id/data" element={<Data/>}/><Route path="/p/:id/analysis" element={<Analysis/>}/><Route path="/p/:id/proposal" element={<Proposal/>}/><Route path="*" element={<><h1>页面不存在</h1><p>请从项目列表重新进入研究。</p><Link to="/">返回项目列表</Link></>}/></Routes></Suspense></main><footer>HypoWeaver · 文献有出处，数字可复核，结论有边界。</footer></BrowserRouter>
}
