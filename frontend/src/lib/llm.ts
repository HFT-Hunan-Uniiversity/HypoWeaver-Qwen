import { useQuery } from '@tanstack/react-query'
import { api, ApiError } from '../api/client'

export interface LlmSettings {
  configured: boolean
  /** 当前千问模型名（后端字段 llm_model） */
  llm_model: string
  /** 后端是否已提供 GET/PUT /api/settings/llm */
  switchable: boolean
}

/** 可选千问模型：前端内置默认列表 */
export const QWEN_MODELS = ['qwen-plus', 'qwen-max', 'qwen-turbo', 'qwen-long']

async function loadLlm(): Promise<LlmSettings> {
  try {
    const r = await api<{ configured?: boolean; llm_model?: string | null }>('/settings/llm')
    return { configured: !!r.configured, llm_model: r.llm_model || '', switchable: true }
  } catch (e) {
    // 接口未落地：回退到既有的 /settings/status
    if (!(e instanceof ApiError) || e.status !== 404) throw e
    const s = await api<{ configured: boolean; model: string }>('/settings/status')
    return { configured: s.configured, llm_model: s.model, switchable: false }
  }
}

export function useLlm() {
  return useQuery({ queryKey: ['llm'], queryFn: loadLlm, staleTime: 30000 })
}
