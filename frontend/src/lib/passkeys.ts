/** Native WebAuthn transport, capability checks, and non-secret browser recognition. */
import { apiFetch, ApiClientError } from '../api/client'
import type { User } from '../api/types'

export const PASSKEY_BROWSER_KEY = 'filament-manager.passkey-browser.v1'

export interface SavedPasskey {
  id: string
  name: string
  created_at: string
  last_used_at: string | null
}

type EncodedDescriptor = Omit<PublicKeyCredentialDescriptor, 'id'> & { id: string }
type AuthenticationOptions = Omit<PublicKeyCredentialRequestOptions, 'challenge' | 'allowCredentials'> & {
  challenge: string
  allowCredentials?: EncodedDescriptor[]
}
type RegistrationOptions = Omit<PublicKeyCredentialCreationOptions, 'challenge' | 'user' | 'excludeCredentials'> & {
  challenge: string
  user: Omit<PublicKeyCredentialUserEntity, 'id'> & { id: string }
  excludeCredentials?: EncodedDescriptor[]
}

export function supportsPasskeys(): boolean {
  return window.isSecureContext && typeof PublicKeyCredential !== 'undefined' && Boolean(navigator.credentials)
}

export function recognizedPasskeyBrowser(): boolean {
  try { return localStorage.getItem(PASSKEY_BROWSER_KEY) === '1' } catch { return false }
}

export function rememberPasskeyBrowser(): void {
  // This flag only starts a browser prompt. The server must still verify every assertion.
  try { localStorage.setItem(PASSKEY_BROWSER_KEY, '1') } catch { /* Storage is optional. */ }
}

export async function supportsPasskeyAutofill(): Promise<boolean> {
  if (!supportsPasskeys() || typeof PublicKeyCredential.isConditionalMediationAvailable !== 'function') return false
  try { return await PublicKeyCredential.isConditionalMediationAvailable() } catch { return false }
}

function decode(value: string): ArrayBuffer {
  const normalized = value.replace(/-/g, '+').replace(/_/g, '/')
  const bytes = Uint8Array.from(atob(normalized), (char) => char.charCodeAt(0))
  return bytes.buffer
}

function encode(value: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(value))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function serialize(credential: Credential | null): Record<string, unknown> {
  if (!credential || credential.type !== 'public-key') throw new Error('Passkey request was cancelled.')
  const key = credential as PublicKeyCredential
  const response = key.response
  const base = { id: key.id, rawId: encode(key.rawId), type: key.type, clientExtensionResults: {} }
  if ('attestationObject' in response) {
    const registration = response as AuthenticatorAttestationResponse
    return { ...base, response: { clientDataJSON: encode(response.clientDataJSON), attestationObject: encode(registration.attestationObject) } }
  }
  const assertion = response as AuthenticatorAssertionResponse
  return { ...base, response: {
    clientDataJSON: encode(response.clientDataJSON), authenticatorData: encode(assertion.authenticatorData),
    signature: encode(assertion.signature), userHandle: assertion.userHandle ? encode(assertion.userHandle) : null,
  } }
}

export async function authenticatePasskey(signal: AbortSignal, conditional = false): Promise<User> {
  const options = await apiFetch<AuthenticationOptions>('/auth/passkeys/login/options', { method: 'POST', signal })
  signal.throwIfAborted()
  const credential = await navigator.credentials.get({
    publicKey: { ...options, challenge: decode(options.challenge), allowCredentials: options.allowCredentials?.map((item) => ({ ...item, id: decode(item.id) })) },
    mediation: conditional ? 'conditional' : 'optional', signal,
  })
  signal.throwIfAborted()
  const result = await apiFetch<{ user: User }>('/auth/passkeys/login/verify', {
    method: 'POST', signal, body: JSON.stringify({ credential: serialize(credential) }),
  })
  signal.throwIfAborted()
  rememberPasskeyBrowser()
  return result.user
}

export async function registerPasskey(name: string, password: string, signal: AbortSignal): Promise<SavedPasskey> {
  const options = await apiFetch<RegistrationOptions>('/auth/passkeys/register/options', {
    method: 'POST', signal, body: JSON.stringify({ name, current_password: password }),
  })
  signal.throwIfAborted()
  const credential = await navigator.credentials.create({ publicKey: {
    ...options, challenge: decode(options.challenge), user: { ...options.user, id: decode(options.user.id) },
    excludeCredentials: options.excludeCredentials?.map((item) => ({ ...item, id: decode(item.id) })),
  }, signal })
  signal.throwIfAborted()
  const result = await apiFetch<SavedPasskey>('/auth/passkeys/register/verify', {
    method: 'POST', signal, body: JSON.stringify({ credential: serialize(credential) }),
  })
  rememberPasskeyBrowser()
  return result
}

export function passkeyError(error: unknown): string {
  if (error instanceof ApiClientError) return error.message
  if (error instanceof DOMException) {
    if (['NotAllowedError', 'AbortError'].includes(error.name)) return 'Passkey sign-in was cancelled or timed out. Try again or use your password.'
    if (error.name === 'InvalidStateError') return 'This passkey may already be registered. Choose another passkey or device.'
    if (error.name === 'SecurityError') return 'Use the configured HTTPS address to access passkeys.'
  }
  return 'The passkey request could not be completed. Try again or use your password.'
}
