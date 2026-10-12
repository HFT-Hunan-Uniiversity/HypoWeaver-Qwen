import { Link } from 'react-router-dom'
import { isModelMissing } from '../api/client'

export function ErrorNote({ error }: { error: Error | null }) {
  if (!error) return null
  if (isModelMissing(error))
    return (
      <p role="alert" className="notice model-missing">
        模型尚未配置，此步骤暂不可用。<Link to="/settings">前往设置配置模型 →</Link>
        <small>{error.message}</small>
      </p>
    )
  return (
    <p role="alert" className="error">
      {error.message}
    </p>
  )
}
