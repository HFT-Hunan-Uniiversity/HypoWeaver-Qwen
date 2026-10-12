import { useSearchParams } from 'react-router-dom'

/** 把子页签/分节状态写入 URL（?tab= / ?sec=），刷新与分享链接时保持位置。 */
export function useUrlParam<T extends string>(key: string, fallback: T, allowed?: readonly T[]) {
  const [params, setParams] = useSearchParams()
  const raw = params.get(key) as T | null
  const value = raw && (!allowed || allowed.includes(raw)) ? raw : fallback
  const set = (v: T) =>
    setParams(
      (p) => {
        const n = new URLSearchParams(p)
        if (v === fallback) n.delete(key)
        else n.set(key, v)
        return n
      },
      { replace: true },
    )
  return [value, set] as const
}
