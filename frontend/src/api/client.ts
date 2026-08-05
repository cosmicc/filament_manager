export class ApiClientError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message)
    this.name = 'ApiClientError'
  }
}

function cookieValue(name: string): string | undefined {
  const prefix = `${encodeURIComponent(name)}=`
  const entry = document.cookie.split('; ').find((item) => item.startsWith(prefix))
  return entry ? decodeURIComponent(entry.slice(prefix.length)) : undefined
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrf = cookieValue('fm_csrf')
    if (csrf) headers.set('X-CSRF-Token', csrf)
  }
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers,
    credentials: 'include',
  })
  if (response.status === 204) return undefined as T
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiClientError(
      response.status,
      body?.code ?? 'request_failed',
      body?.message ?? 'The request could not be completed',
    )
  }
  return body as T
}

export function idempotencyKey(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`
}

