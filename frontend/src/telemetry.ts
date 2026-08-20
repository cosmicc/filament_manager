import type { Breadcrumb, Client, Event } from '@bugsnag/js'
import type { BugsnagErrorBoundary } from '@bugsnag/plugin-react'

export interface BugsnagBrowserRuntimeConfig {
  enabled: boolean
  apiKey: string | null
  releaseStage: string
  browserPerformanceEnabled: boolean
}

export interface BrowserTelemetryModules {
  bugsnag: typeof import('@bugsnag/js')
  reactPlugin: typeof import('@bugsnag/plugin-react')
  performance?: typeof import('@bugsnag/browser-performance')
}

interface NetworkRequestInfo {
  url: string | null
  type?: string
  propagateTraceContext?: boolean
}

const DISABLED_CONFIG: BugsnagBrowserRuntimeConfig = Object.freeze({
  enabled: false,
  apiKey: null,
  releaseStage: 'production',
  browserPerformanceEnabled: false,
})
const API_KEY_PATTERN = /^[0-9a-f]{32}$/i
const RELEASE_STAGE_PATTERN = /^[A-Za-z0-9._-]{1,64}$/
const UUID_PATTERN = /\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/gi
const UUID_SEGMENT_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const LONG_IDENTIFIER_PATTERN = /\b(?:[0-9a-f]{32,}|[A-Za-z0-9_-]{40,})\b/g
const URL_PATTERN = /https?:\/\/[^\s"'<>]+/gi
const PATH_QUERY_PATTERN = /(\/[A-Za-z0-9._~!$&'()*+,;=:@%/-]+)\?[^\s"'<>]*/g
const SENSITIVE_KEY_PATTERN = /(?:api[_-]?key|authorization|cookie|csrf|database|password|secret|service[_-]?account|session|token)/i
const POLLING_PATH_PATTERN = /^\/api\/v1\/(?:build-plates|dashboard|diagnostics|jobs|notifications|printers|prints|spools|workstation-agents)(?:\/|$)/
const POLLING_URL_PATTERN = /\/api\/v1\/(?:build-plates|dashboard|diagnostics|jobs|notifications|printers|prints|spools|workstation-agents)(?:\/|$)/
const PLACEHOLDER_ORIGIN = 'https://filament-manager.invalid'
const METADATA_SECTIONS_TO_CLEAR = [
  'console',
  'error cause',
  'notify()',
  'request',
  'unhandledrejection',
  'user',
  'window onerror',
]
function discardSdkLog(message: string): void {
  void message
}

const quietLogger = {
  debug: discardSdkLog,
  info: discardSdkLog,
  warn: discardSdkLog,
  error: discardSdkLog,
}

let activeClient: Client | null = null

export function readBugsnagRuntimeConfig(
  runtimeConfig: unknown = typeof window === 'undefined'
    ? undefined
    : window.__FILAMENT_MANAGER_RUNTIME_CONFIG__,
): BugsnagBrowserRuntimeConfig {
  if (!runtimeConfig || typeof runtimeConfig !== 'object') return DISABLED_CONFIG
  const bugsnag = (runtimeConfig as Record<string, unknown>).bugsnag
  if (!bugsnag || typeof bugsnag !== 'object') return DISABLED_CONFIG
  const candidate = bugsnag as Record<string, unknown>
  const apiKey = typeof candidate.apiKey === 'string' ? candidate.apiKey.trim() : ''
  const releaseStage = typeof candidate.releaseStage === 'string'
    ? candidate.releaseStage.trim()
    : ''
  if (
    candidate.enabled !== true
    || !API_KEY_PATTERN.test(apiKey)
    || !RELEASE_STAGE_PATTERN.test(releaseStage)
  ) return DISABLED_CONFIG
  return {
    enabled: true,
    apiKey: apiKey.toLowerCase(),
    releaseStage,
    browserPerformanceEnabled: candidate.browserPerformanceEnabled === true,
  }
}

export function normalizeTelemetryPath(pathname: string): string {
  const segments = pathname
    .split('/')
    .filter(Boolean)
    .map((segment) => {
      if (UUID_SEGMENT_PATTERN.test(segment)) return ':id'
      if (/^\d+$/.test(segment) || /^[0-9a-f]{16,}$/i.test(segment)) return ':id'
      return segment.replace(/[^A-Za-z0-9._~-]/g, '_').slice(0, 80)
    })
  UUID_PATTERN.lastIndex = 0
  return `/${segments.join('/')}`.slice(0, 300) || '/'
}

export function sanitizeTelemetryText(value: unknown, limit = 500): string {
  const sanitized = String(value ?? '')
    .replace(URL_PATTERN, '[url]')
    .replace(PATH_QUERY_PATTERN, '$1?[redacted]')
    .replace(UUID_PATTERN, '[id]')
    .replace(LONG_IDENTIFIER_PATTERN, '[redacted]')
  UUID_PATTERN.lastIndex = 0
  LONG_IDENTIFIER_PATTERN.lastIndex = 0
  URL_PATTERN.lastIndex = 0
  PATH_QUERY_PATTERN.lastIndex = 0
  return sanitized.slice(0, limit) || 'Application error'
}

function sanitizedUrl(value: string): URL | null {
  try {
    const origin = typeof window === 'undefined' ? 'http://localhost' : window.location.origin
    return new URL(value, origin)
  } catch {
    return null
  }
}

function sanitizedAppUrl(value: string): string {
  const parsed = sanitizedUrl(value)
  const origin = typeof window === 'undefined' ? 'http://localhost' : window.location.origin
  if (!parsed || parsed.origin !== origin) return '[external-url]'
  return `${PLACEHOLDER_ORIGIN}${normalizeTelemetryPath(parsed.pathname)}`
}

function sanitizeMetadata(value: unknown, depth = 0): unknown {
  if (value === null || value === undefined || typeof value === 'boolean' || typeof value === 'number') {
    return value
  }
  if (typeof value === 'string') return sanitizeTelemetryText(value, 300)
  if (depth >= 2) return '[nested-data-removed]'
  if (Array.isArray(value)) return value.slice(0, 10).map((item) => sanitizeMetadata(item, depth + 1))
  if (typeof value !== 'object') return String(value).slice(0, 100)
  const sanitized: Record<string, unknown> = {}
  for (const [key, item] of Object.entries(value).slice(0, 30)) {
    const safeKey = key.replace(/[^A-Za-z0-9._-]/g, '_').slice(0, 64)
    if (!safeKey) continue
    sanitized[safeKey] = SENSITIVE_KEY_PATTERN.test(safeKey)
      ? '[REDACTED]'
      : sanitizeMetadata(item, depth + 1)
  }
  return sanitized
}

function containsPollingUrl(value: unknown): boolean {
  if (typeof value === 'string') {
    const parsed = sanitizedUrl(value)
    const origin = typeof window === 'undefined' ? 'http://localhost' : window.location.origin
    return Boolean(parsed && parsed.origin === origin && POLLING_PATH_PATTERN.test(parsed.pathname))
  }
  if (Array.isArray(value)) return value.some(containsPollingUrl)
  if (value && typeof value === 'object') return Object.values(value).some(containsPollingUrl)
  return false
}

export function sanitizeBreadcrumb(breadcrumb: Breadcrumb): boolean {
  if (containsPollingUrl(breadcrumb.metadata)) return false
  if (breadcrumb.type === 'error') {
    breadcrumb.message = 'Sanitized browser error'
    breadcrumb.metadata = {}
    return true
  }
  if (breadcrumb.type === 'navigation') {
    breadcrumb.message = 'Navigation'
    breadcrumb.metadata = sanitizeNavigationMetadata(breadcrumb.metadata)
    return true
  }
  breadcrumb.message = 'Network request'
  breadcrumb.metadata = sanitizeRequestMetadata(breadcrumb.metadata)
  return true
}

function sanitizeNavigationMetadata(metadata: Record<string, unknown>): Record<string, unknown> {
  const sanitized: Record<string, unknown> = {}
  for (const key of ['from', 'to']) {
    const value = metadata[key]
    if (typeof value === 'string') sanitized[key] = sanitizedAppUrl(value)
  }
  return sanitized
}

function sanitizeRequestMetadata(metadata: Record<string, unknown>): Record<string, unknown> {
  const sanitized: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(metadata)) {
    const normalizedKey = key.toLowerCase()
    if (['method', 'httpmethod', 'status', 'statuscode'].includes(normalizedKey)) {
      sanitized[key.slice(0, 32)] = typeof value === 'number'
        ? value
        : sanitizeTelemetryText(value, 32)
    } else if (['request', 'url'].includes(normalizedKey) && typeof value === 'string') {
      sanitized[key.slice(0, 32)] = sanitizedAppUrl(value)
    }
  }
  return sanitized
}

export function sanitizeBrowserEvent(event: Event): boolean {
  event.setUser()
  event.clearFeatureFlags()
  event.context = normalizeTelemetryPath(window.location.pathname)
  event.app = {
    releaseStage: event.app.releaseStage,
    type: event.app.type,
    version: event.app.version,
  }
  event.device = {
    osName: event.device.osName,
    osVersion: event.device.osVersion,
    runtimeVersions: event.device.runtimeVersions,
  }
  const requestUrl = typeof event.request.url === 'string' ? sanitizedAppUrl(event.request.url) : undefined
  event.request = {
    httpMethod: event.request.httpMethod,
    url: requestUrl,
  }
  if (event.response) {
    event.response.headers = {}
    delete event.response.body
  }
  for (const section of METADATA_SECTIONS_TO_CLEAR) event.clearMetadata(section)
  const reactMetadata = event.getMetadata('react')
  if (reactMetadata) {
    event.clearMetadata('react')
    event.addMetadata('react', sanitizeMetadata(reactMetadata) as Record<string, unknown>)
  }
  event.breadcrumbs = event.breadcrumbs.filter(sanitizeBreadcrumb)
  event.threads = []
  for (const error of event.errors) {
    error.errorClass = error.errorClass.replace(/[^A-Za-z0-9._$-]/g, '_').slice(0, 160)
    error.errorMessage = 'A sanitized browser error occurred; use local Diagnostics for details.'
    for (const frame of error.stacktrace) {
      frame.file = sanitizedAppUrl(frame.file)
      frame.code = undefined
    }
  }
  return true
}

export function sanitizeNetworkRequest<T extends NetworkRequestInfo>(request: T): T | null {
  if (!request.url) return null
  const parsed = sanitizedUrl(request.url)
  const origin = typeof window === 'undefined' ? 'http://localhost' : window.location.origin
  if (!parsed || parsed.origin !== origin || POLLING_PATH_PATTERN.test(parsed.pathname)) {
    return null
  }
  return {
    ...request,
    url: `${PLACEHOLDER_ORIGIN}${normalizeTelemetryPath(parsed.pathname)}`,
    propagateTraceContext: false,
  }
}

async function loadBrowserTelemetryModules(
  performanceEnabled: boolean,
): Promise<BrowserTelemetryModules> {
  const performanceModule = performanceEnabled
    ? import('@bugsnag/browser-performance')
    : Promise.resolve(undefined)
  const [bugsnagModule, reactPluginModule, loadedPerformanceModule] = await Promise.all([
    import('@bugsnag/js'),
    import('@bugsnag/plugin-react'),
    performanceModule,
  ])
  return {
    bugsnag: bugsnagModule,
    reactPlugin: reactPluginModule,
    performance: loadedPerformanceModule,
  }
}

export async function initializeBrowserTelemetry(
  ReactLibrary: typeof import('react'),
  config = readBugsnagRuntimeConfig(),
  loader = loadBrowserTelemetryModules,
): Promise<BugsnagErrorBoundary | undefined> {
  if (!config.enabled || config.apiKey === null) return undefined
  let modules: BrowserTelemetryModules
  let errorBoundary: BugsnagErrorBoundary | undefined
  try {
    modules = await loader(config.browserPerformanceEnabled)
    const Bugsnag = modules.bugsnag.default
    const BugsnagPluginReact = modules.reactPlugin.default
    const client = Bugsnag.start({
      apiKey: config.apiKey,
      appType: 'filament-manager-browser',
      appVersion: import.meta.env.VITE_APP_VERSION,
      autoTrackSessions: false,
      collectUserIp: false,
      enabledBreadcrumbTypes: ['error', 'navigation', 'request'],
      enabledReleaseStages: [config.releaseStage],
      generateAnonymousId: false,
      logger: null,
      maxBreadcrumbs: 20,
      maxEvents: 10,
      onBreadcrumb: sanitizeBreadcrumb,
      onError: sanitizeBrowserEvent,
      plugins: [new BugsnagPluginReact(ReactLibrary)],
      redactedKeys: [
        /api[_-]?key/i,
        /authorization/i,
        /cookie/i,
        /csrf/i,
        /database/i,
        /password/i,
        /secret/i,
        /service[_-]?account/i,
        /session/i,
        /token/i,
      ],
      releaseStage: config.releaseStage,
      reportUnhandledPromiseRejectionsAsHandled: false,
    })
    activeClient = client
    errorBoundary = client.getPlugin('react')?.createErrorBoundary()
  } catch {
    console.warn('[Filament Manager] Browser error monitoring could not start')
    return undefined
  }
  if (config.browserPerformanceEnabled && modules.performance) {
    try {
      const BugsnagPerformance = modules.performance.default
      const RoutingProvider = modules.performance.DefaultRoutingProvider
      BugsnagPerformance.start({
        apiKey: config.apiKey,
        appVersion: import.meta.env.VITE_APP_VERSION,
        bugsnag: modules.bugsnag.default,
        enabledReleaseStages: [config.releaseStage],
        generateAnonymousId: false,
        logger: quietLogger,
        networkRequestCallback: sanitizeNetworkRequest,
        releaseStage: config.releaseStage,
        routingProvider: new RoutingProvider((url) => normalizeTelemetryPath(url.pathname)),
        sendPageAttributes: { referrer: false, title: false, url: false },
        serviceName: 'filament-manager-browser',
        settleIgnoreUrls: [POLLING_URL_PATTERN],
      })
    } catch {
      console.warn('[Filament Manager] Browser performance monitoring could not start')
    }
  }
  return errorBoundary
}

export function notifyBrowserError(error: unknown, context: string): void {
  if (!activeClient) return
  const reportable = error instanceof Error ? error : new Error('A non-Error browser failure occurred')
  activeClient.notify(reportable, (event) => {
    event.context = sanitizeTelemetryText(context, 160)
  })
}
