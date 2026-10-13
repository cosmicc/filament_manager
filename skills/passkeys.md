# Passkey Authentication

## Trust and persistence

- Use the maintained `webauthn` verifier. Never implement production signature, CBOR, attestation, RP-hash, or counter verification yourself. `tests/test_passkeys.py` intentionally builds independent software-authenticator fixtures.
- Registration requires an authenticated Administrator session, valid CSRF, and fresh password confirmation. Refuse forced-password accounts through the existing dependency. Require discoverable credentials and user verification; accept platform, password-manager, and capable security-key passkeys without device/UA gating. Keep attestation `none` and never request identifying authenticator certificates.
- Derive RP ID and exact origin only from `FILAMENT_MANAGER_BASE_URL`. Require HTTPS (HTTP localhost development only); never trust Host/forwarded headers as credential scope. Origin guard applies to each ceremony POST. Removing a credential needs password/CSRF/exact origin but remains available over the existing session’s address even if WebAuthn is unavailable.
- Store only credential ID/public key, counter/backup flags, immutable RP ID, account ID, friendly name, and dates. Never store private keys or biometric data. General lists return UUID/name/dates only. Never include credentials, handles, assertions, challenges, or passwords in audit/logging/Sheets.
- Keep challenge state in PostgreSQL, independent of web-process lifetime. Bind login/enrollment separately to high-entropy Strict HttpOnly cookies containing unpersisted raw tokens; store only their hashes. Registration additionally binds account UUID/version and the initiating session hash. Expire after five minutes and clean expired records on new ceremonies. Lock and persist consumption before verification so failed attempts and concurrent replay cannot resurrect a challenge.
- Lock account before credential during verification/removal. Refresh enrollment account versions under the lock; revalidate ownership and credential existence after acquiring authentication locks. Require exact discoverable user handle, enabled/unlocked account, verified signature/RP/origin/challenge/UV, and the library’s counter checks. Preserve synced authenticators’ zero-counter support through the verifier.
- Both login methods use `services/browser_sessions.py`, with the same session and CSRF rotation/lifetimes and forced-password behavior. Passkey removal revokes all other browser sessions. Preserve password login and other passkeys. Rate-limit ceremony and password-confirmation attempts; bound returned failures without exception messages.
- Migration `fe456f789012` adds `passkeys` and `passkey_challenges`; keep Diagnostics at that head. Downgrade refuses nonempty credential storage. Offline restore revokes sessions and clears pending challenges. Keep credentials outside Google’s explicit business-data allowlist.

## Browser behavior

- Use native WebAuthn with bounded base64url JSON transport in `frontend/src/lib/passkeys.ts`. Do not gate by mobile detection or platform-authenticator availability; external/synced passkeys remain supported.
- Add `username webauthn` autocomplete and conditional mediation on compatible unrecognized browsers. On browsers with the non-secret `filament-manager.passkey-browser.v1` marker, make one normal automatic attempt per login-page mount. Set the marker only after server-verified enrollment/sign-in; storage failure must leave manual passkey and password login working. The marker is never authentication evidence.
- Browser privacy rules prevent silent enumeration of installed passkeys. Do not claim to discover them yourself or reveal server credential identifiers in unauthenticated options.
- Abort/settle pending ceremonies before manual passkey or password submission; prevent overlapping manual attempts. Abort on unmount. Automatic cancellation/failure is quiet; manual errors explain safe retry/password fallback. Keep password submission available during an automatic prompt.
- Settings owns friendly labels and dates, plus password-confirmed add/remove dialogs. Clear password state after success/cancel and use current-password autocomplete. A committed mutation must never become a failed save merely because list refresh failed. Reuse approved theme tokens and responsive touch spacing.

## Verification

- Run `tests/test_passkeys.py` with real PostgreSQL, independent P-256/none-attestation registration and signed assertions. Verify good login/rotation, rejected RP/origin/challenge/UV/signature/handle/browser cookie/expiry/replay, CSRF/password refusal, removed credentials, and password fallback.
- Check populated upgrade/metadata parity and refused downgrade. Run existing singleton account/session, backup/restore, and Diagnostics tests.
- Frontend tests cover recognized-browser automatic attempt, conditional mediation, unavailable readiness, quiet automatic failure/manual retry, pending cancellation/password fallback, and setup/removal.
- `frontend/e2e/passkeys.spec.ts` exercises native creation/get with Chromium’s virtual resident-key authenticator at desktop/mobile widths. API fixtures test browser transport/UI; the independent HTTP tests verify cryptography and session authorization. Screenshots are representative fixtures, not real operator credential data. Keep screenshots/reports under `/tmp`.
- Never claim physical Face ID, Touch ID, Windows Hello, Android, or Safari validation from a Chromium virtual-authenticator test. Verify those manually on the operator’s stable HTTPS hostname after deployment.
