# Roadmap

- **Calibration candidate measurements and graphs**

  Extend each calibration step beyond its selected result so every tested candidate and its structured observation remain available permanently. For example, a retraction test should retain the tested distance, stringing severity, and surface-defect result for every tower segment before recording the selected distance.

  Use those measurements to graph relationships such as pressure advance versus corner quality, flow versus dimensional accuracy, temperature versus stringing or bridging, retraction versus stringing, and speed versus print-quality score.

- **Deeper material-profile hierarchy**

  Extend the current template-to-product-profile inheritance into optional material-family, manufacturer-material, color, printer, nozzle, and named-profile layers. Settings should inherit downward unless explicitly overridden at a more specific layer.

  Example hierarchy:

  ```text
  PLA defaults
      -> Polymaker PolyLite PLA
          -> Black
              -> FLSUN printer
                  -> 0.6 mm nozzle
                      -> Named profile
  ```

- **Filament environmental tracking**

  Add drying state, last-dried time, drying temperature and duration, dryer identity, and humidity before/after drying. Use this history for drying recommendations, alerts, and eventual correlation with print defects.

  Introduce a first-class dry-box model that can associate a spool with an NFC reader, load cell, humidity sensor, temperature sensor, heater, and printer. Expose its loaded spool, measured mass, remaining filament, humidity, temperature, and drying state.

- **Generic device ingestion API**

  Add authenticated registration, telemetry, and event ingestion APIs for supported adapters rather than building a separate server integration for every device type. Candidate devices include scales, NFC readers, dry boxes, humidity sensors, barcode scanners, dryers, cameras, and temperature probes.

  Candidate endpoints:

  ```text
  /api/v1/devices
  /api/v1/devices/{id}/telemetry
  /api/v1/devices/{id}/events
  ```

- **Filament-consumption prediction and quantity preflight**

  Compare Cura-predicted use with Spoolman-recorded use and future scale measurements to calculate bounded, reviewable correction factors by relevant material/profile scope.

  Use corrected estimates for a configurable quantity preflight that explains whether a selected spool has enough filament for the job. Include material, nozzle, build plate, profile, mesh, and future drying-state evidence in a clear ready, warning, or blocked result without silently changing inventory or profiles.

- **Consolidate Filaments and Print Settings navigation**

  Keep separate canonical product and material-profile models, but move the remaining profile summaries, Cura export, comparison, and tuning entry points into each filament detail workflow so the one-printer interface no longer presents overlapping catalog destinations.

- **Detailed Cura profile drift review**

  Expand current checksum-based managed-library repair into a review that identifies locally changed approved settings and shows exact canonical-versus-local differences. Provide safe actions to restore canonical state, accept approved changes through the existing managed-edit workflow, or retain an explicitly reviewed exception.

- **Named profile branches**

  Support multiple sparse variants beneath one base material profile, such as Quality, Fast, Strong, Dimensional, Vase, or Prototype. Each branch should override only the settings that differ from its base and remain explicit when selected for Cura synchronization and print-history attribution.

- **Material property database**

  Extend material records with selection and safety properties such as glass-transition and heat-deflection temperatures, recommended nozzle type, abrasiveness, hygroscopicity, UV and chemical resistance, flexibility, strength, food-contact notes, and bounded drying limits.

  Add inventory-aware filtering for questions such as which owned materials are suitable outdoors or for a required service temperature.

- **Nozzle wear tracking**

  Extend physical-nozzle usage with abrasive-filament totals and a material-weighted wear index. Add reviewable maintenance alerts based on nozzle construction, filament abrasiveness, and completed usage.

- **Printer component lifecycle**

  Track replaceable components such as Bowden tubes, extruder gears, belts, fans, heater cartridges, and thermistors with installation/removal history and maintenance schedules based on time, runtime, or filament throughput.

- **Expanded build-plate lifecycle analytics**

  Add plate-side print count, hours used, wash and IPA-clean distinctions, adhesive use, surface-damage history, and mesh-variance trends. Correlate those facts with recorded adhesion failures without rewriting historical print state.

- **Automatic build-plate recommendation**

  Recommend a physical plate and side using material compatibility, surface properties, temperature limits, condition, maintenance state, mesh freshness, and recorded outcomes. Keep the recommendation advisory until enough trustworthy data exists.

- **Print failure analytics**

  Aggregate recorded outcomes and defect tags by printer, material, manufacturer, color, profile, nozzle, plate, temperature, future humidity, and other supported dimensions. Show sample sizes and avoid implying causation from weak correlations.

- **Automatic profile recommendations**

  Calculate reviewable candidate settings from sufficiently large sets of successful prints, beginning with transparent statistics such as medians and ranges. Never change a profile silently; require explicit approval before saving a recommendation.

- **Configurable QR label templates**

  Add printable label templates that can include the QR code, human spool ID, manufacturer, material, color, diameter, and current net mass. Keep generated links authenticated and safe to scan from a phone.

- **Mobile-first scanner mode**

  Add a focused `/scan` workflow for phone cameras and USB scanners. After a scan, show a large spool summary with context-appropriate Load, Weigh, Dry, and View actions.

- **Purchasing and broader cost analytics**

  Add purchase metadata such as shipping, order and delivery dates, lot, and sale pricing. Build rollups for cost per successful print, failed-print waste, material cost by period, and monthly filament consumption while preserving the immutable captured cost basis of historical prints.

- **Reorder management**

  Add per-product minimum inventory targets, low-stock recommendations, average-use calculations, and estimated supply duration. Keep ordering advisory unless an external purchasing integration is explicitly added later.

- **Public API contract and SDK**

  Formalize the existing internal versioned API as a supported external contract, fill remaining resource gaps, document stability and authentication expectations, and generate a maintained Python SDK from the OpenAPI specification.

- **Outgoing webhooks**

  Add authenticated, signed, retryable webhooks for events such as low/loaded/empty spools, print lifecycle changes, completed calibrations, profile changes, and offline devices. Keep payloads bounded and free of credentials or private upstream details.

- **Domain observability metrics**

  Expand the existing HTTP Prometheus instrumentation with bounded domain metrics for inventory mass, filament use, print outcomes, projection health, Spoolman reconciliation, Cura-agent health, and future device freshness. Avoid unbounded identifier labels.

- **Multi-printer Moonraker integration**

  Replace the current exact one-printer deployment contract with explicitly configured, independently authenticated printers. Scope Moonraker state, Spoolman coordination, profiles, nozzles, plates, preflight, jobs, health, and diagnostics by printer without allowing cross-printer state changes.
