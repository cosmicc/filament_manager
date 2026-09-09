# 0.8.1 upgrade notes

This version is a testing release. No live printer configuration or firmware restart is needed for these changes.

## Known development dependency findings

This testing release retains the existing dependencies at the operator's explicit request. The frontend audit reports GHSA-82fw-gwwq-j7x9 in Vitest/@vitest/mocker and GHSA-2883-xcg3-v3hh in js-yaml (two moderate findings and one high, including the parent dependency). These development dependencies are not shipped in the static frontend runtime. Do not expose development/test servers to untrusted networks. The audit gate remains enabled and may fail CI; publication is an explicit exception for this version, not a clean security-audit result.

## Inventory and settings

- Existing spools start with **Unknown** spool type. Select a known design in spool settings; use **New Spool Type** for another design. Choices are remembered immediately.
- Tare suggestions require the same manufacturer, spool type and purchased filament capacity, including archived evidence. Unknown designs/manufacturers are not pooled. Suggestions are never applied automatically.
- Spoolman's shared filament tare is cleared when a product's packaging design is unknown or ambiguous. Each physical spool's own tare is unchanged.
- Density silently follows each print profile's linked template. Migration `fa012b3c4d56` appends corrected current profiles, retaining old profile/print snapshots and all other custom settings. Cura receives the new state through normal closed-Cura synchronization.
- The product's creation-template density mirror follows that template for physical inventory calculations. Legacy product-density fields remain accepted for compatibility but cannot override a linked template.

## History

Last completed and last other print dates use recorded print starts (or exact spool-change segment starts), not synchronization times. Other includes cancelled, failed and interrupted jobs; unresolved or in-progress records do not establish terminal-use dates. Missing attribution remains **No recorded print**.

Print settings show saved print evidence first. When a summary value is missing, the print's immutable app profile may supply it with **Captured app settings (not measured)**. This does not claim that a calibration tower maintained one setting throughout its print, change inspection decisions, or use today's template. Unknown Cura profile names remain **Not recorded**.

Printer duration totals come from Moonraker's [history totals API](https://moonraker.readthedocs.io/en/latest/external_api/history/#get-job-totals). Total print time and longest print exclude pauses. Moonraker can reset these counters; the app displays its latest successful receipt rather than inventing lifetime totals. Refresh happens alongside history synchronization, deferred during printing/pauses. A failed refresh retains the previous values and timestamp.

Display rounding does not change stored settings or exported historical archives. Database snapshots and machine-bound values keep their required precision.

## Deployment

Back up the canonical database before upgrading and update web and worker together. Startup runs the forward migration automatically. Downgrade refuses to discard entered spool types; use the pre-upgrade backup for a full rollback. Historical snapshots appended during upgrade remain retained on a schema downgrade.
