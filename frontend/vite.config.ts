import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
// HW_API 可改代理目标（例如脚本后端 http://127.0.0.1:8001）；默认真实后端 :8000
const target = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env.HW_API || 'http://127.0.0.1:8000'
export default defineConfig({plugins:[react()], server:{port:5173, strictPort:true, proxy:{'/api':target}}})
