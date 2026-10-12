import type { Estimate } from '../api/analysis'
export const num=(n:number|undefined|null,digits=4)=>n===null||n===undefined||!Number.isFinite(n)?'—':n.toFixed(digits)
export const pvalue=(n:number|undefined|null)=>n===null||n===undefined?'—':n<.0001?'< 0.0001':n.toFixed(4)
export default function ResultTable({rows}:{rows:(Partial<Estimate>&{label:string})[]}){
 return <div className="table-scroll"><table><thead><tr><th>模型</th><th>系数</th><th>标准误</th><th>p 值</th><th>95% 置信区间</th><th>观测数</th></tr></thead><tbody>{rows.map((r,i)=><tr key={i}><td>{r.label}</td><td>{num(r.coef)}</td><td>{num(r.se)}</td><td>{pvalue(r.p)}</td><td>{r.ci?`${num(r.ci[0])} 至 ${num(r.ci[1])}`:'—'}</td><td>{r.n_obs?.toLocaleString()||'—'}</td></tr>)}</tbody></table></div>
}
