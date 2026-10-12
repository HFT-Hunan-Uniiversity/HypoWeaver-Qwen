export async function api<T>(path:string, options:RequestInit={}):Promise<T> {
  const response = await fetch('/api'+path,{...options,headers:{...(options.body instanceof FormData?{}:{'Content-Type':'application/json'}),...options.headers}})
  if (!response.ok) {
    const data = await response.json().catch(()=>null)
    throw new Error(data?.error?.message || `请求失败（${response.status}）`)
  }
  return response.status===204 ? undefined as T : response.json()
}
export const body = (method:string, data?:unknown):RequestInit => ({method,body:data===undefined?undefined:JSON.stringify(data)})
export interface Direction {text:string;question:string;constraints:string[];domain:string}
export interface Project {id:string;title:string;direction:Direction;updated_at:string}
export interface Stage {key:string;label:string;status:string}
