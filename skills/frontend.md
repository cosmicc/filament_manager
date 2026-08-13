# Frontend Design and Accessibility Skill

- React, TypeScript, and Vite are the required frontend stack.
- Use the approved Workshop Navy light/dark palette in `docs/design/palette.png`; do not invent another palette.
- Use `docs/design/concepts/` as the layout and density reference. Preserve desktop data tables and use purpose-built mobile flows rather than squeezed tables.
- Navigation: Dashboard, Spools, Filaments, Profiles, Templates, Calibration Wizard, Build Plates, Printers, Labels, Integrations, Cura Workstations, Activity, Settings.
- Templates exposes complete reusable generic material revisions and publication. Filaments creates product-specific draft profiles from published templates, provides a full product/settings detail editor, and Spools creates physical inventory from canonical products. Profile edits always create new draft versions.
- The Cura Workstations page shows pairing and authoritative-library takeover only to Administrators, uses explicit Arch Linux/Windows labels, reports last contact, every detected Cura machine, unmanaged material count, synchronization state, and warnings. The takeover warning must state that user material files are backed up and replaced and bundled materials are hidden.
- Use semantic HTML, visible focus states, keyboard navigation, 44px mobile touch targets, accessible labels, and icons plus text for status.
- Respect `prefers-reduced-motion`. Keep motion purposeful and restrained.
- The exact seven calibration steps may not be renamed or reordered. Size and Hole Calibration follows Retraction and shows both calculated Cura expansion values plus the X/Y divergence warning. Preserve `P1` through `P5` as the initial physical plate set and naturally order exact Side A `P<number>` then optional Side B `P<number>b` meshes.
- Build Plates groups sides beneath a physical plate, exposes all physical metadata plus per-side material/finish/notes, and makes the active side explicit. Moonraker state synchronizes automatically; Operators may edit metadata and select available sides but may not directly create integration-controlled records.
- Named filament colors use real swatches and a case-insensitive remembered sample. Choosing a new sample must clearly explain that all matching existing and future filaments change together.
- Spools shows the free-text bucket/location in the table and detail panel. Administrators and Operators can edit or clear it from the detail panel; explain that Filament Manager will synchronize the canonical value to Spoolman.
- All record creation and editing uses the shared accessible modal shell and visible `EditorSection` groups with a consistent header, scrollable body, and footer actions. Do not hide editable options in `<details>` or page-specific fold-down forms. Persistent multi-step workflows may remain in-page but must use the same visible grouped sections.
- Operational Moonraker state on Dashboard, Spools, Build Plates, and Printers refreshes every 15 seconds. Printer information refreshes server-side every 5 minutes; show freshness rather than a required manual synchronization action.
- Use shared tokens and components. Do not create one-off color, spacing, radius, or typography values when a token exists.
- Theme choice persists locally, defaults to system preference, and remains available from the application shell.
- Keep same-origin navigation dependency-light through the shared History API router unless a reviewed feature requires a larger routing dependency.
