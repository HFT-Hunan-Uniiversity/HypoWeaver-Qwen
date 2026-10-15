import React from 'react'
import ReactDOM from 'react-dom/client'
import { MutationCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import './styles/tokens.css'
import './styles/app.css'
import './styles/shell.css'
import './styles/skin.css'
import './styles/one-screen.css'
import './styles/flow.css'
import './styles/claws.css'
import './styles/notebook.css'
const client = new QueryClient({
  mutationCache: new MutationCache({
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['overview'] })
    },
  }),
  defaultOptions: { queries: { retry: false } },
})
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
)
