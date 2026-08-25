export interface ApiValidationError {
  field: string
  message: string
  type: string
}

export class ApiClientError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public validationErrors: ApiValidationError[] = [],
    public correlationId?: string,
  ) {
    super(message)
    this.name = 'ApiClientError'
  }
}

export function actionableApiError(error: unknown): string {
  if (!(error instanceof ApiClientError)) {
    return error instanceof Error ? error.message : 'The request could not be completed.'
  }
  const generic = error.message === 'The request could not be completed'
    || error.message === 'Request validation failed'
  const explanation = generic
    ? error.status === 0
      ? 'The application service could not be reached.'
      : error.status >= 500
        ? 'The server could not finish this request. Use the reference below to find the matching Diagnostics entry.'
        : 'The server rejected this request.'
    : error.message
  const details = [error.code, error.status ? `HTTP ${error.status}` : null, error.correlationId ? `reference ${error.correlationId}` : null]
    .filter(Boolean)
    .join(' · ')
  return details ? `${explanation} ${details}.` : explanation
}

export function validationMessagesFor(
  error: unknown,
  prefix = '',
): Record<string, string[]> {
  if (!(error instanceof ApiClientError) || error.code !== 'validation_error') return {}
  const messages: Record<string, string[]> = {}
  for (const issue of error.validationErrors) {
    const field = prefix && issue.field.startsWith(`${prefix}.`)
      ? issue.field.slice(prefix.length + 1)
      : issue.field
    messages[field] = [...(messages[field] ?? []), issue.message]
  }
  return messages
}

function cookieValue(name: string): string | undefined {
  const prefix = `${encodeURIComponent(name)}=`
  const entry = document.cookie.split('; ').find((item) => item.startsWith(prefix))
  return entry ? decodeURIComponent(entry.slice(prefix.length)) : undefined
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)
  const isFormData = typeof FormData !== 'undefined' && init.body instanceof FormData
  if (init.body && !isFormData && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrf = cookieValue('fm_csrf')
    if (csrf) headers.set('X-CSRF-Token', csrf)
  }
  let response: Response
  try {
    response = await fetch(`/api/v1${path}`, {
      ...init,
      headers,
      credentials: 'include',
    })
  } catch (error) {
    console.error('[Filament Manager API] Network request failed', {
      method,
      path,
      error: error instanceof Error ? error.message : 'Unknown network error',
    })
    throw new ApiClientError(0, 'network_error', 'The application service could not be reached')
  }
  const correlationId = response.headers.get('X-Request-ID')
  console.info('[Filament Manager API] Request completed', {
    method,
    path,
    status: response.status,
    correlationId,
  })
  if (response.status === 204) return undefined as T
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const validationErrors: ApiValidationError[] = Array.isArray(body?.errors)
      ? body.errors
        .filter((item: unknown): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
        .filter((item: Record<string, unknown>) => typeof item.field === 'string' && typeof item.message === 'string')
        .slice(0, 100)
        .map((item: Record<string, unknown>) => ({
          field: String(item.field).slice(0, 255),
          message: String(item.message).slice(0, 300),
          type: typeof item.type === 'string' ? item.type.slice(0, 96) : 'value_error',
        }))
      : []
    console.error('[Filament Manager API] Request rejected', {
      method,
      path,
      status: response.status,
      code: body?.code ?? 'request_failed',
      message: body?.message ?? 'The request could not be completed',
      correlationId: body?.correlation_id ?? correlationId,
    })
    throw new ApiClientError(
      response.status,
      body?.code ?? 'request_failed',
      body?.message ?? 'The request could not be completed',
      validationErrors,
      typeof body?.correlation_id === 'string' ? body.correlation_id : correlationId ?? undefined,
    )
  }
  return body as T
}

export function idempotencyKey(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`
}
