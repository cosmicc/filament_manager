# Passkey sign-in

Passkeys let you sign in from a supported phone or computer using a fingerprint, face, device PIN, password manager, or capable security key. Your password remains available.

## Set up a passkey

1. Open Filament Manager at its configured HTTPS address and sign in.
2. Open **Settings → Passkeys → Add passkey**.
3. Name it (for example, **My phone**), confirm your current password, and select **Create passkey**.
4. Follow your browser or password manager’s setup prompt.

Add another passkey for a backup device or security key if desired. Complete the required initial password replacement before enrolling.

On the login page, use **Sign in with passkey**. Compatible browsers can offer a passkey in username autofill. A browser where you previously registered or used a passkey also attempts sign-in once automatically. You still approve any device verification requested by the browser. Cancelling keeps password login available.

## Manage and recover access

Settings lists names, added dates, and last use. **Remove** requires your current password and signs out other browser sessions. Removing one passkey leaves your password and other passkeys available.

A synchronized passkey may work on other devices through your password manager. Filament Manager stores its public credential only; it never receives a private key, fingerprint, or face data. If a device is lost, sign in with your password or another passkey and remove the lost credential.

## Deployment and troubleshooting

- Set `FILAMENT_MANAGER_BASE_URL` to the exact public HTTPS address used in the browser, including a nonstandard port when applicable. Use a certificate trusted by the device. HTTP `localhost` is supported for development; ordinary HTTP LAN addresses cannot use passkeys.
- Passkeys are bound to the configured hostname. Accessing a different alias/IP address will not use them. After moving to another hostname, sign in with your password and register new passkeys there.
- Unsupported browsers retain password login. Clearing browser storage disables recognition until the next successful passkey sign-in; the manual button remains available. Browsers control which passkeys appear, including cross-device prompts.
- When a prompt expires or another tab replaces a pending request, retry. A cancelled automatic request does not repeatedly prompt on the same page.
- Upgrade web and worker together after backing up the database. Startup applies migration `fe456f789012`; existing passwords and sessions remain valid. No workstation-agent or printer-macro upgrade is needed.
- Downgrade refuses to discard registered passkeys. Remove them before downgrading or restore a pre-upgrade backup. Offline restore retains registered public credentials but clears browser sessions and pending passkey requests.
