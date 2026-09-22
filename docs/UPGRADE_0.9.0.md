# 0.9.0 testing release

Back up the canonical database and upgrade web/worker together. Migration `fc234d5e6f78` adds G-code archives; it does not rewrite historical settings. No live printer changes are installed automatically.

## Material settings and Cura

The six new Support values start blank: Support Top Distance, Support X/Y Distance, Support Roof Density, Branch Density, Tip Diameter, and Support Roof Thickness. Set a template default to propagate it to inheriting filaments; explicit filament overrides survive. Cura still owns support/roof enablement and machine-dependent validity limits.

Tree Maximum Branch Angle and Retract at Layer Change are no longer app-managed. The agent cleans up the retired branch-angle override after backup. Cura owns Retract at Layer Change: its existing and future local quality-profile choices are preserved, and this release does **not** force it off. Legacy immutable snapshots retain their original evidence.

Upgrade each workstation agent to **0.9.0 (renderer 28)** with Cura closed. Push app settings, wait for success, reopen Cura, and re-slice. The plugin captures the selected Cura quality name when slicing starts and adds an inert comment to the resulting G-code. Imported/pre-existing G-code is not relabelled. The app also decodes Cura's existing embedded settings correctly; older files without reliable profile evidence remain unknown.

## Saved print files

New prints retain a compressed exact copy using the existing inspection download, without another printer-file request. Originals larger than **100 MB** are inspected under existing limits but not archived. Files remain until their history record is deleted and increase canonical database/backup size; there is no automatic expiry.

Print details offer a read-only, paginated text viewer and an exact-byte download. Access requires an authenticated app session. Files may contain slicer comments and other operator data; treat backups/downloads as private. G-code is never executed, rewritten, sent back to the printer, or exported to Sheets.

For older records, **Retrieve verified original** requires a reachable idle printer and an exact match with the original inspection checksum. A reused filename is not sufficient. If there is no recorded checksum, the file is missing/changed, or the limit is exceeded, retrieval is refused.

## Unfinished history

The idle history pass revisits older unfinished jobs even after newer jobs complete. Actual Moonraker outcomes remain authoritative. If a record cannot be recovered, open it and use **Close stale entry**, then confirm. The app refuses while printing, paused, or unable to verify idle state. This closes only the local history record as interrupted/unknown; it never cancels a printer job, invents a completion/end time, or subtracts predicted filament use.

Start-to-finish duration uses verified start/end timestamps and remains unavailable when either is unknown. Moonraker's print and total counters remain separately visible. Printer totals show their readable duration beneath numeric hours.

Downgrade refuses to discard any saved G-code. Restore a verified pre-upgrade backup instead. Applying the separate QQ-S M240 macro requires the idle installation and camera checks in [Pause and park setup](PAUSE_PARK_SETUP.md#m240-camera-snapshots).
