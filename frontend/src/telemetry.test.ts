// @vitest-environment jsdom

import * as React from 'react'
import type { Breadcrumb } from '@bugsnag/js'
import { describe, expect, it, vi } from 'vitest'
import type { BrowserTelemetryModules } from './telemetry'
import {
  initializeBrowserTelemetry,
  normalizeTelemetryPath,
  readBugsnagRuntimeConfig,
  sanitizeBreadcrumb,
  sanitizeBrowserEvent,
  sanitizeNetworkRequest,
  sanitizeTelemetryText,
} from './telemetry'

const API_KEY = 'a'.repeat(32)

describe('Bugsnag browser privacy boundary', () => {
  it('stays disabled unless runtime configuration contains an enabled valid key', () => {
    expect(readBugsnagRuntimeConfig(undefined).enabled).toBe(false)
    expect(readBugsnagRuntimeConfig({
      bugsnag: { enabled: true, apiKey: 'invalid', releaseStage: 'testing' },
    }).enabled).toBe(false)
    expect(readBugsnagRuntimeConfig({
      bugsnag: {
        enabled: true,
        apiKey: API_KEY.toUpperCase(),
        releaseStage: 'testing',
        browserPerformanceEnabled: true,
      },
    })).toEqual({
      enabled: true,
      apiKey: API_KEY,
      releaseStage: 'testing',
      browserPerformanceEnabled: true,
    })
  })

  it('normalizes record identifiers and strips sensitive error text', () => {
    expect(normalizeTelemetryPath('/filaments/32747ed4-49f9-4ff4-8e91-1af70598cc37')).toBe(
      '/filaments/:id',
    )
    const sanitized = sanitizeTelemetryText(
      'Failed https://private.example/spools/32747ed4-49f9-4ff4-8e91-1af70598cc37?token=secret abcdefabcdefabcdefabcdefabcdefab',
    )
    expect(sanitized).not.toContain('private.example')
    expect(sanitized).not.toContain('32747ed4')
    expect(sanitized).not.toContain('abcdefabcdef')
  })

  it('drops polling and external spans while replacing the private app origin', () => {
    expect(sanitizeNetworkRequest({ url: '/api/v1/notifications?limit=100', type: 'fetch' })).toBeNull()
    expect(sanitizeNetworkRequest({ url: 'https://external.example/resource', type: 'fetch' })).toBeNull()
    expect(sanitizeNetworkRequest({
      url: '/api/v1/filaments/32747ed4-49f9-4ff4-8e91-1af70598cc37?details=true',
      type: 'fetch',
    })).toEqual({
      url: 'https://filament-manager.invalid/api/v1/filaments/:id',
      type: 'fetch',
      propagateTraceContext: false,
    })
  })

  it('discards polling breadcrumbs and redacts credential-shaped metadata', () => {
    const polling = {
      message: 'fetch',
      metadata: { request: '/api/v1/jobs?limit=100' },
      type: 'request',
      timestamp: new Date(),
    } as Breadcrumb
    expect(sanitizeBreadcrumb(polling)).toBe(false)

    const breadcrumb = {
      message: 'Failed https://private.example/path?token=secret',
      metadata: { authorization: 'Bearer secret', method: 'GET' },
      type: 'error',
      timestamp: new Date(),
    } as Breadcrumb
    expect(sanitizeBreadcrumb(breadcrumb)).toBe(true)
    expect(breadcrumb.message).not.toContain('private.example')
    expect(breadcrumb.metadata).toEqual({})
  })

  it('replaces raw browser exception messages at the final delivery boundary', () => {
    const event = {
      app: { releaseStage: 'testing', type: 'browser', version: '0.4.0' },
      device: { hostname: 'private-host', osName: 'Linux' },
      request: { url: 'http://localhost/private?password=secret', httpMethod: 'GET' },
      response: { headers: { authorization: 'secret' }, body: 'private response' },
      breadcrumbs: [],
      threads: [{ id: 'private-thread' }],
      errors: [{
        errorClass: 'TypeError',
        errorMessage: 'Submitted value was private-value',
        stacktrace: [{ file: 'http://localhost/assets/app.js', code: { 1: 'private code' } }],
      }],
      setUser: vi.fn(),
      clearFeatureFlags: vi.fn(),
      clearMetadata: vi.fn(),
      getMetadata: vi.fn(() => undefined),
    }

    expect(sanitizeBrowserEvent(
      event as unknown as Parameters<typeof sanitizeBrowserEvent>[0],
    )).toBe(true)
    expect(event.errors[0].errorMessage).toBe(
      'A sanitized browser error occurred; use local Diagnostics for details.',
    )
    expect(event.errors[0].errorMessage).not.toContain('private-value')
    expect(event.threads).toEqual([])
    expect(event.device).not.toHaveProperty('hostname')
  })

  it('does not load any Bugsnag bundle while monitoring is disabled', async () => {
    const loader = vi.fn()
    const boundary = await initializeBrowserTelemetry(
      React,
      {
        enabled: false,
        apiKey: null,
        releaseStage: 'production',
        browserPerformanceEnabled: false,
      },
      loader,
    )

    expect(boundary).toBeUndefined()
    expect(loader).not.toHaveBeenCalled()
  })

  it('disables error-session reporting while retaining sanitized errors', async () => {
    const start = vi.fn(() => ({
      getPlugin: vi.fn(() => ({ createErrorBoundary: vi.fn(() => undefined) })),
    }))
    const loader = vi.fn(async () => ({
      bugsnag: { default: { start } },
      reactPlugin: { default: vi.fn() },
    })) as unknown as (performanceEnabled: boolean) => Promise<BrowserTelemetryModules>

    await initializeBrowserTelemetry(
      React,
      {
        enabled: true,
        apiKey: API_KEY,
        releaseStage: 'testing',
        browserPerformanceEnabled: false,
      },
      loader,
    )

    expect(start).toHaveBeenCalledWith(expect.objectContaining({ autoTrackSessions: false }))
  })
})
