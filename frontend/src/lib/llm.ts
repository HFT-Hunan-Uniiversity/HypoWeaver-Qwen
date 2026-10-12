import { useQuery } from '@tanstack/react-query'
import { api, ApiError } from '../api/client'

export interface LlmSettings {
  configured: boolean
  model: string
  /** 可切换的千问模型；后端未提供时为空 */
  models: string[]
  /** 后端是否已提供 GET/PUT /api/settings/llm */
  switchable: boolean
}

export const FALLBACK_MODELS = ['qwen-plus', 'qwen-max', 'qwen-turbo']

async function loadLlm(): Promise<LlmSettings> {
  try {
    const r = await api<{
      configured?: boolean
      model?: string
      models?: string[]
      available_models?: string[]
    }>('/settings/llm')
    return {
      configured: !!r.configured,
      model: r.model || '',
      models: r.models || r.available_models || [],
      switchable: true,
    }
  } catch (e) {
    // 接口未落地：回退到既有的 /settings/status
    if (!(e instanceof ApiError) || e.status !== 404) throw e
    const s = await api<{ configured: boolean; model: string }>('/settings/status')
    return { configured: s.configured, model: s.model, models: [], switchable: false }
  }
}

export function useLlm() {
  return useQuery({ queryKey: ['llm'], queryFn: loadLlm, staleTime: 30000 })
}
