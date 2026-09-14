# 0.8.4 testing upgrade: build plate rankings

Back up the canonical database, then upgrade web and worker together. Startup applies
`fb123c4d5e67`. This changes compatibility ratings, not physical plate/mesh identities.

## Set ratings

- Open **Build plate ratings** on Templates or Build plates, select the material
  template, and click zero through five stars beside each whole physical plate.
  Both sides share the rating. Each click saves immediately.
- Open a filament and select **View / edit build plate ratings**. Ratings inherit
  the current linked template. Clicking a different rating creates an override for
  that filament; **Revert to Template** removes it. Overrides follow the filament
  across printers and template changes. Choose the printer scope to inspect its
  inherited defaults. Selecting the current inherited value also restores inheritance.
- Dashboard active spools and spool/filament details show the highest-rated active
  plates. Equal highest ratings are all recommended. A lower-rated active plate
  shows a warning; zero stars shows **Do NOT use** and blocks managed print start.
  Unrated is distinct from zero and remains allowed. Unavailable plates are not
  recommended. Ratings never automatically switch a physical plate.

## Existing side ratings

Equal side ratings and a single known side rating carry over to the whole plate.
**Conflicting side ratings reset to Unrated**, as requested, including a conflict
between zero and a positive rating. Review those combinations before printing;
Unrated does not block a print. Original maps and the reset plate IDs remain in
the migration audit. Captured print history is unchanged.

## Printer setup

Replace the app's included `filament-manager-macros.cfg` while idle and run
`FIRMWARE_RESTART`; verify macro version **0.8.4**. Keep the existing managed Cura
start boundary. The app evaluates the effective template/filament rating before
releasing a managed start, independently of warning-only settings inspection.
Zero stars offers cancellation, not a filament-weight override. Exact side
receipts still prevent a late physical plate change after approval.

No extra Moonraker polling or Cura-setting changes are introduced. Renderer 27
remains current. Fresh workstation installers are included but the ranking feature
does not require a Cura plugin replacement. Automated tests do not certify live
printer motion; verify the zero-star dialog in a supervised idle-printer test.
Unmanaged start G-code or direct printer-console commands can bypass managed
preflight and must not be used as an alternative safety boundary.

Google Sheets publishes template ratings and sparse filament overrides in
**Plate Ratings**, with whole-plate IDs and separate template/filament links.

## Rollback

Retain a pre-upgrade backup. Downgrade refuses to discard nonempty filament
overrides. After explicitly removing them, downgrade copies each whole-plate
rating onto both sides. It cannot recreate conflicting values that were reset;
use the backup or retained migration audit for those original values.
