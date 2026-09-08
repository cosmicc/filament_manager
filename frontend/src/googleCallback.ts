import { apiFetch } from './api/client'

/** Consume OAuth proof before telemetry starts; never persist codes or states. */
export async function completeGoogleCallback(): Promise<void> {
  if (window.location.pathname !== '/google/callback') return
  const params = new URLSearchParams(window.location.search)
  const code = params.get('code')
  const state = params.get('state')
  window.history.replaceState({}, '', '/settings')
  try {
    if (!code || !state || code.length > 8192 || state.length > 128 || params.has('error')) {
      throw new Error('Google authorization was not completed.')
    }
    await apiFetch('/settings/google/complete', {
      method: 'POST', body: JSON.stringify({ code, state }),
    })
    window.history.replaceState({}, '', '/settings?google=connected')
  } catch {
    window.history.replaceState({}, '', '/settings?google=failed')
  }
}
