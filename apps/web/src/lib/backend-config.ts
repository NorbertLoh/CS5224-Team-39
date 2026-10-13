type Environment = Record<string, unknown>

export function usesAws(env: Environment = import.meta.env ?? {}) {
  const flag = env.VITE_USE_AWS
  if (flag === 'true') return true
  if (flag === undefined || flag === '' || flag === 'false') return false
  throw new Error('VITE_USE_AWS must be true or false.')
}

export function apiBaseUrl(env: Environment = import.meta.env ?? {}) {
  const aws = usesAws(env)
  const value = aws ? env.VITE_AWS_API_BASE_URL : env.VITE_LOCAL_API_BASE_URL ?? '/api/v1'
  if (typeof value !== 'string' || !value) throw new Error('Configure the AWS API URL.')
  if (!aws && value.startsWith('/') && !value.startsWith('//') && !/[\\?#]/.test(value)) return value.replace(/\/+$/, '')
  const url = new URL(value)
  const local = !aws && url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname)
  if ((!local && url.protocol !== 'https:') || url.username || url.password || url.search || url.hash) {
    throw new Error('API URLs require HTTPS, or localhost HTTP for local mode, without credentials/query.')
  }
  return value.replace(/\/+$/, '')
}
