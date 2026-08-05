# Frontend Design and Accessibility Skill

- React, TypeScript, and Vite are the required frontend stack.
- Use the approved Workshop Navy light/dark palette in `docs/design/palette.png`; do not invent another palette.
- Use `docs/design/concepts/` as the layout and density reference. Preserve desktop data tables and use purpose-built mobile flows rather than squeezed tables.
- Navigation: Dashboard, Spools, Filaments, Profiles, Calibration Wizard, Build Plates, Printers, Labels, Integrations, Cura Workstations, Activity, Settings.
- The Cura Workstations page shows pairing only to Administrators, uses explicit Arch Linux/Windows labels, reports last contact and every detected Cura machine, and keeps deployment status and warnings visible to all authenticated roles.
- Use semantic HTML, visible focus states, keyboard navigation, 44px mobile touch targets, accessible labels, and icons plus text for status.
- Respect `prefers-reduced-motion`. Keep motion purposeful and restrained.
- The exact six calibration steps and P1-P5 build-plate identifiers may not be renamed or reordered.
- Use shared tokens and components. Do not create one-off color, spacing, radius, or typography values when a token exists.
- Theme choice persists locally, defaults to system preference, and remains available from the application shell.
- Keep same-origin navigation dependency-light through the shared History API router unless a reviewed feature requires a larger routing dependency.
