import { llmHeaders } from '../lib/llmKey'
export class ApiError extends Error {
  status: number
  code: string
  constructor(message: string, status: number, code = '') {
    super(message)
    this.status = status
    this.code = code
  }
}
/** 409 或 llm_not_configured：需要模型但未配置 */
export function isModelMissing(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 409 || error.code === 'llm_not_configured')
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch('/api' + path, {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...llmHeaders(),
      ...options.headers,
    },
  })
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new ApiError(
      data?.error?.message || data?.detail?.message || `请求失败（${response.status}）`,
      response.status,
      data?.error?.code || data?.detail?.code || '',
    )
  }
  return response.status === 204 ? (undefined as T) : response.json()
}
export const body = (method: string, data?: unknown): RequestInit => ({
  method,
  body: data === undefined ? undefined : JSON.stringify(data),
})
export interface Direction {
  text: string
  question: string
  constraints: string[]
  domain: string
}
export interface Project {
  id: string
  title: string
  direction: Direction
  updated_at: string
  selected_candidate_id?: string | null
  /** 案例标记：'carbon' 启用碳市场约束；null 为通用项目 */
  case?: 'carbon' | (string & {}) | null
  completed?: boolean
}
export interface Stage {
  key: string
  label: string
  status: string
  summary?: string
}
