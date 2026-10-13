import type { Estimate } from '../api/analysis'
/**
 * 统一数值格式：整数原样；|x| < 0.001 或 ≥ 1e6 用科学计数法（4 位有效数字，如 7.757e-4），
 * 其余保留 4 位有效数字。保证数值卡、表格不出现被截断的长小数。
 */
export function fmtNumber(n: number): string {
  if (Number.isInteger(n) && Math.abs(n) < 1e15) return String(n)
  const a = Math.abs(n)
  if (a !== 0 && (a < 1e-3 || a >= 1e6)) return n.toExponential(3).replace('e+', 'e')
  return String(Number(n.toPrecision(4)))
}
export const num = (n: number | undefined | null, digits?: number) =>
  n === null || n === undefined || !Number.isFinite(n)
    ? '—'
    : digits === undefined
      ? fmtNumber(n)
      : n.toFixed(digits)
export const pvalue = (n: number | undefined | null) => num(n)
export default function ResultTable({ rows }: { rows: (Partial<Estimate> & { label: string })[] }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>模型</th>
            <th>系数</th>
            <th>标准误</th>
            <th>p 值</th>
            <th>95% 置信区间</th>
            <th>观测数</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td>{r.label}</td>
              <td>{num(r.coef)}</td>
              <td>{num(r.se)}</td>
              <td>{pvalue(r.p)}</td>
              <td>{r.ci ? `${num(r.ci[0])} 至 ${num(r.ci[1])}` : '—'}</td>
              <td>{r.n_obs?.toLocaleString() || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
