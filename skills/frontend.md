# Frontend Design and Accessibility Skill

- React, TypeScript, and Vite are the required frontend stack.
- Use the approved Workshop Navy light/dark palette in `docs/design/palette.png`; do not invent another palette.
- Use `docs/design/concepts/` as the layout and density reference. Preserve desktop data tables and use purpose-built mobile flows rather than squeezed tables.
- Navigation: Dashboard, Spools, Filaments, Profiles, Templates, Calibration Wizard, Build Plates, Printers, Labels, Integrations, Cura Workstations, Activity, Settings.
- Templates exposes complete reusable generic material revisions and publication. Filaments creates product-specific draft profiles from published templates, and Spools creates physical inventory from canonical products.
- The Cura Workstations page shows pairing and authoritative-library takeover only to Administrators, uses explicit Arch Linux/Windows labels, reports last contact, every detected Cura machine, unmanaged material count, synchronization state, and warnings. The takeover warning must state that user material files are backed up and replaced and bundled materials are hidden.
- Use semantic HTML, visible focus states, keyboard navigation, 44px mobile touch targets, accessible labels, and icons plus text for status.
- Respect `prefers-reduced-motion`. Keep motion purposeful and restrained.
- The exact six calibration steps may not be renamed or reordered. Preserve `P1` through `P5` as the initial physical plate set and naturally order exact Side A `P<number>` then optional Side B `P<number>b` meshes.
- Build Plates groups sides beneath a physical plate, exposes plate description plus per-side material/finish/notes, and makes the active side explicit. Synchronization is Administrator-only; Operators may select available sides but may not import integration-controlled records.
- Spools shows the free-text bucket/location in the table and detail panel. Administrators and Operators can edit or clear it from the detail panel; explain that Filament Manager will synchronize the canonical value to Spoolman.
- Use shared tokens and components. Do not create one-off color, spacing, radius, or typography values when a token exists.
- Theme choice persists locally, defaults to system preference, and remains available from the application shell.
- Keep same-origin navigation dependency-light through the shared History API router unless a reviewed feature requires a larger routing dependency.
