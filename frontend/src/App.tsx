import { lazy, Suspense } from 'react'
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import AppShell from './components/shell/AppShell'
import StageLayout from './components/shell/StageLayout'
const Projects = lazy(() => import('./pages/Projects'))
const Settings = lazy(() => import('./pages/Settings'))
const Overview = lazy(() => import('./pages/Overview'))
const Direction = lazy(() => import('./pages/Direction'))
const Literature = lazy(() => import('./pages/Literature'))
const Candidates = lazy(() => import('./pages/Candidates'))
const Plan = lazy(() => import('./pages/Plan'))
const Data = lazy(() => import('./pages/Data'))
const Proposal = lazy(() => import('./pages/Proposal'))
// PROTOTYPE 一次性路由，见 docs/flow.md
const FlowPrototype = import.meta.env.DEV
  ? lazy(() => import('./prototype/flow/FlowPrototype'))
  : null

/** 旧链接 /p/:id/analysis → 数据与检验 · 运行结果 */
function AnalysisRedirect() {
  const { pathname, search } = useLocation()
  const params = new URLSearchParams(search)
  params.set('tab', 'results')
  return <Navigate replace to={`${pathname.replace(/\/analysis$/, '/data')}?${params}`} />
}

const loading = (
  <p role="status" className="loading-line">
    正在加载研究页面…
  </p>
)

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {FlowPrototype && (
          <Route
            path="/prototype/flow"
            element={
              <Suspense fallback={loading}>
                <FlowPrototype />
              </Suspense>
            }
          />
        )}
        <Route element={<AppShell />}>
          <Route
            path="/"
            element={
              <Suspense fallback={loading}>
                <Projects />
              </Suspense>
            }
          />
          <Route
            path="/settings"
            element={
              <Suspense fallback={loading}>
                <Settings />
              </Suspense>
            }
          />
          <Route path="/p/:id/analysis" element={<AnalysisRedirect />} />
          <Route element={<StageLayout />}>
            <Route
              path="/p/:id"
              element={
                <Suspense fallback={loading}>
                  <Overview />
                </Suspense>
              }
            />
            {(
              [
                ['direction', <Direction />],
                ['literature', <Literature />],
                ['candidates', <Candidates />],
                ['plan', <Plan />],
                ['data', <Data />],
                ['proposal', <Proposal />],
              ] as const
            ).map(([path, el]) => (
              <Route
                key={path}
                path={`/p/:id/${path}`}
                element={<Suspense fallback={loading}>{el}</Suspense>}
              />
            ))}
          </Route>
          <Route
            path="*"
            element={
              <div className="product-page">
                <h1>页面不存在</h1>
                <p>请从项目列表重新进入研究。</p>
                <Link to="/">返回项目列表</Link>
              </div>
            }
          />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
