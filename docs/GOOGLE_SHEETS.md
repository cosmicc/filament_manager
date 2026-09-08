# Google Sheets publication

Use **Settings → Google integration** to connect your Google account. The worker creates a native spreadsheet named **Filament Manager** in that account's Drive. This is an optional, one-way view of the app—not a backup or another place to edit canonical records.

## Guided setup (0.8.0)

Open **Settings → Google integration → Guided setup**. The four steps link directly to Google project creation, both required APIs, consent/client configuration, and a secure credentials upload. The guide displays a copyable redirect URI. Google still requires its project and consent steps; the app cannot create those on your behalf.

Create a **Web application** OAuth client, download its JSON, and upload it in the final step. The app checks that the file contains the exact redirect URI and stores the client secret encrypted. Then choose **Connect Google**, approve access, and wait for **Last published** and **Open spreadsheet**. Keep `GOOGLE_ENABLED=false`; that switch is for legacy service-account publishing only.

No client-secret environment variables or redeployment are needed for guided setup. On first credential save, the server initializes a private Fernet key at `<application data directory>/credentials/integration.key`. Web and worker must share that persistent directory and run under the same application UID. Back up this key separately from database archives: the archives contain ciphertext, not the key. A missing key never regenerates while stored encrypted credentials exist. Restore the correct key before saving credentials again.

Replacing the uploaded client disconnects the existing grant and invalidates pending consent attempts. Reconnect with the same Google account to retain access to the existing workbook. Neither replacing credentials nor disconnecting deletes the spreadsheet.

## Existing environment-based setup

Existing OAuth client/key variables remain supported until you explicitly upload a client through Guided setup. An existing explicit `GOOGLE_TOKEN_ENCRYPTION_KEY` remains the encryption authority; do not remove or replace it during adoption. The manual alternative is:

1. Create or select a project in [Google Cloud Console](https://console.cloud.google.com/). Enable the **Google Drive API** and **Google Sheets API**.
2. Configure Google Auth Platform branding, audience and consent. Add the scope `https://www.googleapis.com/auth/drive.file`. It permits access only to files created or explicitly opened with this app; the app does not request your whole Drive, email or profile.
3. Create an OAuth client of type **Web application**. Add the exact **authorized redirect URI** shown in Settings: your configured public app URL followed by `/google/callback`. Use HTTPS except for localhost development. Do not use the workstation-agent URL or add wildcard redirect URIs.
4. Set these stack variables in your private deployment environment:

   - `GOOGLE_OAUTH_CLIENT_ID`: the web client's ID.
   - `GOOGLE_OAUTH_CLIENT_SECRET`: its secret.
   - `GOOGLE_TOKEN_ENCRYPTION_KEY`: one persistent Fernet key. Generate it locally with `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'` in the app virtual environment, then store it securely. Never post the output in logs or support tickets.

   Keep `GOOGLE_ENABLED=false` for this OAuth mode. That older switch enables the separate service-account mode. The stack supplies the equivalent `FILAMENT_MANAGER_GOOGLE_*` variables to both web and worker; direct non-Docker deployments use those prefixed names.
5. Redeploy web and worker together. Sign in to Filament Manager, open Settings, choose **Connect Google**, and approve access. Return to this same signed-in browser session.
6. Wait for **Last published** and **Open spreadsheet**. **Sync now** requests a fresh publication; the worker normally checks within 30 seconds and waits while a print is in progress.

For an External consent screen in **Testing**, add your Google account as a test user. Google normally expires these offline grants after seven days. Switch the consent audience's publishing status to **In production** for ongoing personal synchronization; Google may display an unverified-app warning or require additional project checks. A Workspace administrator may also restrict OAuth access. See [Google's OAuth server flow](https://developers.google.com/identity/protocols/oauth2/web-server) and [scope guidance](https://developers.google.com/workspace/sheets/api/scopes).

## Workbook contents

The workbook contains Dashboard, Spools, Filaments, Templates, Template History, Print Profiles, Build Plates, Plate Sides, 3D Printers, Nozzles, Nozzle Events, Mesh Calibration, Manufacturers, Locations, Colors, Fillers and Finishes, Measurements, Usage, Calibration, Calibration Steps, Print History, Print Segments, Print Assessments, and Settings and Evidence.

- Current and archived records are included. Profile/template history and original print settings stay intact.
- **Settings and Evidence** expands every included nested value into source, record, field, setting and value columns. It retains sparse overrides, resolved settings, captured templates, Cura settings, calibration results and print evidence as literal text or numbers. Filter by record and field to compare them. No spreadsheet formula is executed from app data.
- The Dashboard links to every table, summarizes record counts and remaining filament, and charts non-archived spools by material. Workshop Navy headers, alternating rows, frozen headings, column filters and linked record UUIDs support navigation. Technical UUID columns are hidden but can be unhidden.
- Use Google Sheets **Find** and **Data → Filter views** for independent searches and analysis. Managed sheets display a warning before edits. Google file owners retain edit permissions; the app does not make a Sheet owner technically read-only.
- Account/session credentials, integration configuration, security/audit logs, operational queues, workstation recovery files, images, thumbnails, G-code and videos are not exported. Business notes are included: avoid placing secrets in inventory notes. Credential/connection-like keys inside structured evidence are explicitly marked as excluded.

## Synchronization and recovery

Canonical changes trigger existing background publication events; a complete content comparison every `GOOGLE_PUBLISH_INTERVAL_SECONDS` (30 by default) catches changes across all included tables, including deletions. Rapid events are coalesced, unchanged data avoids Google writes, and **Sync now** forces a complete refresh. Automatic publication waits while canonical print history reports an in-progress print. No new printer API requests are added.

Values are first uploaded into private-to-the-workbook hidden staging tabs, then copied into the existing managed tab IDs in a single atomic Sheets batch. Old rows are removed, ordinary tab links remain stable, unrelated tabs stay untouched, and a failed staging upload retains the last successful contents. Staging tabs are not a confidentiality boundary: anyone with workbook access can unhide them. Interrupted staging is cleaned up on retry. Very large datasets fail explicitly at two-million exported-cell or 32 MiB serialized-content safety limits rather than silently omitting records; Google's total workbook limit also applies. Requests are paced to at most 48 per minute to leave quota headroom.

Transient errors have a persisted one-minute-to-one-hour retry delay shared by all Google jobs. Settings shows the last safe error; Diagnostics retains job health. **Sync now** can retry after fixing setup or access. Reconnect with the same Google account after a revoked/expired grant. If the spreadsheet was deleted, restore it from Drive trash. Do not rename managed tabs; copy data into a separate analysis tab or workbook instead. Changes in Sheets are never imported, and unsupported manual edits are overwritten on the next changed or forced publication—not detected continuously.

**Disconnect** stops publication and deletes the stored grant from the active app database; it retains uploaded client credentials and does not delete the workbook or revoke backups. You can separately remove the app under your Google Account's third-party permissions. Retain the encryption key with protected deployment backups: losing it requires restoring that key, not merely reconnecting. Replacing it is not automatic key rotation. Database backups contain encrypted Google grants and must remain private. Restoring a backup may restore an old connection; review Settings before resuming the worker.

Keep the app's strict session cookies. The OAuth return page completes through an authenticated, CSRF-protected same-origin request and removes its temporary query before telemetry starts. Production application request logs omit queries. Configure your reverse proxy/access logs to omit query strings on `/google/callback`; never record authorization codes, tokens or request bodies.

## Existing service-account deployments

The existing `GOOGLE_ENABLED=true`, spreadsheet ID and service-account JSON configuration remains supported and now publishes the complete workbook to that explicitly configured file. It does not create a personal-Drive file. Existing unowned tabs (including the old Inventory tab) are preserved; rename an unmanaged tab if its name conflicts with a new managed table. The old Inventory tab is a retained legacy snapshot, not the current Spools table. To move to OAuth, disable the service-account publisher, follow Guided setup, and connect Google. The app creates a new app-owned workbook in your personal Drive, leaving the legacy workbook untouched. Do not mix both modes.

Live sign-in requires your own OAuth project and Google consent. Automated tests exercise PostgreSQL, authorization, formatting requests and failures without using an operator's Google account.
