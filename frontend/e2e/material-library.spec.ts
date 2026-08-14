import { expect, test } from '@playwright/test'

const user = {
  id: 'administrator-id', username: 'admin', display_name: 'Administrator',
  role: 'administrator', is_active: true, must_change_password: false, record_version: 1,
}

const printer = {
  id: 'printer-id', printer_code: 'printer-1', name: 'Workshop Printer',
  nozzle_diameter_mm: '0.4', active_plate_id: null, active_plate_surface_id: null,
  status: 'connected', last_seen_at: '2026-08-11T14:00:00Z', record_version: 1,
}

const settings = {
  chamber_temp_c: null, extruder_temp_c: '210', bed_temp_c: '60', flow_percent: '100',
  print_speed_mm_s: '120', outer_wall_speed_mm_s: '60', inner_wall_speed_mm_s: '90',
  infill_speed_mm_s: '110', top_bottom_speed_mm_s: '70', initial_layer_speed_mm_s: '30',
  travel_speed_mm_s: '200', support_speed_mm_s: '80', retraction_distance_mm: '0.8',
  retraction_speed_mm_s: '40', cooling_enabled: true, cooling_min_percent: '30',
  cooling_max_percent: '100', support_overhang_angle_deg: '55',
  tree_max_branch_angle_deg: '40', pressure_advance: '0.035',
  filament_density_g_cm3: '1.24', preferred_build_plate_surface_id: null,
  cura_extensions: { retraction_enable: true, klipper_smooth_time_enable: true },
}

const template = {
  id: 'template-id', name: 'Template PLA', material_type: 'PLA',
  description: 'Starting settings for ordinary PLA', printer_id: printer.id,
  nozzle_diameter_mm: '0.4', filament_diameter_mm: '1.75', active: true,
  source_workstation_agent_id: null, source_cura_material_id: null,
  record_version: 2, created_at: '2026-08-11T12:00:00Z', updated_at: '2026-08-11T13:00:00Z',
  revisions: [{
    id: 'revision-id', material_template_id: 'template-id', version: 1,
    status: 'published', settings, checksum: 'a'.repeat(64),
    published_at: '2026-08-11T13:00:00Z', record_version: 2,
    created_at: '2026-08-11T12:00:00Z',
  }],
}

const filament = {
  id: 'd1e1d7ce-f0bc-46f5-86b2-d2c74f272f00', vendor_id: null, vendor_name: null, material_type: 'PLA',
  filler: null, finish: null, color_name: 'Blue', color_hex: '2F80A5',
  product_name: 'Workshop PLA', diameter_mm: '1.75', tolerance_mm: null,
  density_g_cm3: '1.24', nominal_net_mass_g: '1000', notes: null,
  material_template_revision_id: 'revision-id', record_version: 1,
}

const comparisonProfile = {
  ...settings,
  id: 'comparison-profile-id', filament_product_id: filament.id, printer_id: printer.id,
  nozzle_diameter_mm: '0.4', version: 1, status: 'published',
  extruder_temp_c: '215', flow_percent: '100.000',
  cura_extensions: { ...settings.cura_extensions, retraction_enable: false },
  cura_settings: { material_print_temperature: '215', retraction_enable: false },
  published_at: '2026-08-11T13:00:00Z', checksum: 'b'.repeat(64), record_version: 1,
  base_template_revision_id: 'revision-id', setting_overrides: {}, override_keys: [],
  override_count: 0, inheritance_status: 'inherited', base_template_id: template.id,
  base_template_name: template.name, base_template_version: 1, base_template_settings: settings,
  latest_template_revision_id: 'revision-id', latest_template_version: 1,
  template_update_changes: [],
}

const differentScopeProfile = {
  ...comparisonProfile,
  id: 'different-scope-profile-id', nozzle_diameter_mm: '0.6', version: 2,
  extruder_temp_c: '220', record_version: 2,
}

const spool = {
  id: 'spool-id', spool_code: 'PLA-BLUE-01', filament_product_id: filament.id,
  material_type: 'PLA', filler: null, finish: null, color_name: 'Blue',
  color_hex: '2F80A5', vendor_name: null, product_name: 'Workshop PLA',
  nominal_net_mass_g: '1000', tare_mass_g: '200', remaining_mass_expected_g: '800',
  remaining_mass_measured_g: '800', remaining_mass_effective_g: '800',
  remaining_percent: '80', weight_confidence: 'measured', status: 'in_stock',
  location: 'Bucket 3', spoolman_id: 7, active_printer_id: null, last_measurement_at: '2026-08-11T14:00:00Z',
  notes: null, archived: false, record_version: 3, completed_print_count: 6,
}

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: user }))
  await page.route('**/api/v1/printers', (route) => route.fulfill({ json: [printer] }))
  await page.route('**/api/v1/build-plates', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/notifications**', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/filament-colors', (route) => route.fulfill({ json: [
    { id: 'blue-id', name: 'Blue', normalized_name: 'blue', color_hex: '2F80A5', record_version: 1 },
  ] }))
})

test('template library is usable at desktop and mobile sizes', async ({ page }) => {
  await page.route('**/api/v1/profiles/templates?include_inactive=true', (route) => route.fulfill({ json: [template] }))
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/filaments', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/profiles/cura-settings/catalog', (route) => route.fulfill({ json: [
    { key: 'retraction_enable', label: 'Enable Retraction', value_type: 'boolean', unit: null, editable: true },
    { key: 'klipper_smooth_time_enable', label: 'Enable Klipper Smooth Time', value_type: 'boolean', unit: null, editable: true },
  ] }))
  await page.goto('/templates')
  await expect(page.getByRole('heading', { name: 'Template PLA' })).toBeVisible()
  await expect(page.getByText('Workshop Printer')).toBeVisible()
  await page.getByRole('button', { name: 'New revision' }).click()
  await expect(page.getByRole('dialog', { name: 'New Template PLA revision' })).toBeVisible()
  await expect(page.getByLabel('Printing temperature (°C)')).toHaveValue('210')
  await expect(page.getByRole('heading', { name: /Additional Cura Material Settings/ })).toBeVisible()
  await expect(page.getByText('Enable Klipper Smooth Time', { exact: true })).toBeVisible()

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('dialog', { name: 'New Template PLA revision' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save new revision' })).toBeVisible()
})

test('comparison shows only differences and warns across profile scopes', async ({ page }) => {
  await page.route('**/api/v1/profiles/templates?include_inactive=true', (route) => route.fulfill({ json: [template] }))
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: [comparisonProfile, differentScopeProfile] }))
  await page.route('**/api/v1/filaments', (route) => route.fulfill({ json: [filament] }))
  await page.route('**/api/v1/workstation-agents', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/profiles/cura-settings/catalog', (route) => route.fulfill({ json: [
    { key: 'retraction_enable', label: 'Enable Retraction', value_type: 'boolean', unit: null, editable: true },
    { key: 'klipper_smooth_time_enable', label: 'Enable Klipper Smooth Time', value_type: 'boolean', unit: null, editable: true },
  ] }))
  await page.route('**/api/v1/prints/profile-statistics**', (route) => route.fulfill({ json: {
    [comparisonProfile.id]: { rated_prints: 12, ratings: { successful: 10, failed: 2 }, success_rate_percent: '83.3', low_sample: false },
    [differentScopeProfile.id]: { rated_prints: 3, ratings: { successful: 3 }, success_rate_percent: '100.0', low_sample: true },
  } }))

  await page.goto('/templates')
  await page.getByRole('button', { name: 'Compare settings' }).click()
  const dialog = page.getByRole('dialog', { name: 'Compare material settings' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByText('2 setting differences')).toBeVisible()
  await expect(dialog.getByText('Printing temperature', { exact: true })).toBeVisible()
  await expect(dialog.getByText('Enable Retraction', { exact: true })).toBeVisible()
  await expect(dialog.getByText('Flow', { exact: true })).toHaveCount(0)
  await expect(dialog.getByText('All selected printer and nozzle scopes match.')).toBeVisible()
  await expect(dialog.getByText('83.3%')).toBeVisible()

  await dialog.getByRole('checkbox', { name: /profile v2/ }).check()
  await expect(dialog.getByRole('alert')).toContainText('nozzle diameter differ')
  await page.setViewportSize({ width: 390, height: 844 })
  await dialog.getByText('220 °C', { exact: true }).scrollIntoViewIfNeeded()
  await expect(dialog.getByText('220 °C', { exact: true })).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Close comparison' })).toBeVisible()
  await dialog.getByRole('button', { name: 'Close comparison' }).click()

  await page.goto('/profiles')
  await page.getByRole('button', { name: 'Compare settings', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Compare material settings' })).toBeVisible()
})

test('filament creation requires and submits a published template', async ({ page }) => {
  let submitted: Record<string, unknown> | null = null
  await page.route('**/api/v1/profiles/templates', (route) => route.fulfill({ json: [template] }))
  await page.route('**/api/v1/vendors', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/filaments', async (route) => {
    if (route.request().method() === 'POST') {
      submitted = route.request().postDataJSON() as Record<string, unknown>
      await route.fulfill({ status: 201, json: filament })
    } else await route.fulfill({ json: [] })
  })
  await page.goto('/filaments')
  await page.getByRole('button', { name: 'Add filament' }).click()
  await page.getByLabel('Product name').fill('Workshop PLA')
  await page.getByLabel('Color name', { exact: true }).fill('Blue')
  await page.getByRole('button', { name: 'Create filament' }).click()
  await expect.poll(() => submitted?.material_template_revision_id).toBe('revision-id')
  await expect.poll(() => submitted?.material_type).toBe('PLA')
  await expect(page.getByText(/draft profile linked to its published template base/)).toBeVisible()
})

test('filament details remember colors and save Cura edits as a new version', async ({ page }) => {
  let currentFilament = filament
  let filamentUpdate: Record<string, unknown> | null = null
  let profileRevision: Record<string, unknown> | null = null
  const profile = {
    ...settings,
    id: 'profile-id', filament_product_id: filament.id, printer_id: printer.id,
    nozzle_diameter_mm: '0.4', version: 1, status: 'draft',
    cura_extensions: { ...settings.cura_extensions, xy_offset: '0.05' },
    cura_settings: { material_print_temperature: '210', xy_offset: '0.05' },
    published_at: null, checksum: null, record_version: 1,
    base_template_revision_id: 'revision-id',
    setting_overrides: { extruder_temp_c: '210', cura_extensions: { xy_offset: '0.05' } },
    override_keys: ['extruder_temp_c', 'xy_offset'], override_count: 2,
    inheritance_status: 'customized', base_template_id: template.id,
    base_template_name: template.name, base_template_version: 1,
    base_template_settings: settings, latest_template_revision_id: 'revision-id',
    latest_template_version: 1, template_update_changes: [],
  }
  await page.route(`**/api/v1/filaments/${filament.id}`, async (route) => {
    if (route.request().method() === 'PATCH') {
      filamentUpdate = route.request().postDataJSON() as Record<string, unknown>
      currentFilament = {
        ...currentFilament,
        color_name: String(filamentUpdate.color_name),
        color_hex: String(filamentUpdate.color_hex),
        record_version: 2,
      }
    }
    await route.fulfill({ json: currentFilament })
  })
  await page.route('**/api/v1/vendors', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: [profile] }))
  await page.route('**/api/v1/profiles/cura-settings/catalog', (route) => route.fulfill({ json: [
    { key: 'xy_offset', label: 'Horizontal Expansion', value_type: 'number', unit: 'mm', editable: true },
    { key: 'hole_xy_offset', label: 'Hole Horizontal Expansion', value_type: 'number', unit: 'mm', editable: true },
  ] }))
  await page.route('**/api/v1/profiles/profile-id/revisions', async (route) => {
    profileRevision = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({ status: 201, json: { ...profile, id: 'profile-v2', version: 2 } })
  })

  await page.goto(`/filaments/${filament.id}`)
  await expect(page.getByRole('heading', { name: 'Workshop PLA' })).toBeVisible()
  await expect(page.getByText('Template PLA · v1')).toBeVisible()
  await page.getByRole('button', { name: 'Edit', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Edit filament product' })).toBeVisible()
  await page.getByLabel('Color name', { exact: true }).fill('Red')
  await page.getByLabel('Screen color sample').fill('#ff0000')
  await page.getByRole('button', { name: 'Save filament' }).click()
  await expect.poll(() => filamentUpdate?.color_name).toBe('Red')
  await expect.poll(() => filamentUpdate?.color_hex).toBe('FF0000')

  await page.getByRole('button', { name: 'Edit as new version' }).click()
  await expect(page.getByText('Customized · Template: 210')).toBeVisible()
  await page.getByLabel('Printing temperature (°C)').fill('215')
  await page.getByRole('button', { name: 'Save new draft version' }).click()
  await expect.poll(() => (profileRevision?.settings as Record<string, unknown>)?.extruder_temp_c).toBe('215')
  await expect.poll(() => (profileRevision?.settings as Record<string, unknown>)?.cura_extensions).toEqual({ xy_offset: '0.05' })
})

test('template updates require confirmation for one linked filament', async ({ page }) => {
  let templateUpdate: Record<string, unknown> | null = null
  const profileWithUpdate = {
    ...comparisonProfile,
    id: 'profile-with-update', filament_product_id: filament.id,
    base_template_revision_id: 'revision-id',
    setting_overrides: { filament_density_g_cm3: '1.24' },
    override_keys: ['filament_density_g_cm3'], override_count: 1,
    inheritance_status: 'customized', base_template_id: template.id,
    base_template_name: template.name, base_template_version: 1,
    base_template_settings: settings, latest_template_revision_id: 'revision-2',
    latest_template_version: 2,
    template_update_changes: [{
      key: 'extruder_temp_c', current_value: '215', proposed_value: '220', overridden: false,
    }],
  }
  await page.route(`**/api/v1/filaments/${filament.id}`, (route) => route.fulfill({ json: filament }))
  await page.route('**/api/v1/vendors', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: [profileWithUpdate] }))
  await page.route('**/api/v1/profiles/cura-settings/catalog', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/profiles/profile-with-update/template-base', async (route) => {
    templateUpdate = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({ status: 201, json: { ...profileWithUpdate, id: 'profile-v2', version: 2 } })
  })

  await page.goto(`/filaments/${filament.id}`)
  await expect(page.getByText('Template PLA v2 is available')).toBeVisible()
  await page.getByRole('button', { name: 'Review template update' }).click()
  const dialog = page.getByRole('dialog', { name: 'Update Template PLA base' })
  await expect(dialog.getByText('215')).toBeVisible()
  await expect(dialog.getByText('220')).toBeVisible()
  await dialog.getByRole('button', { name: 'Confirm v2' }).click()
  await expect.poll(() => templateUpdate?.target_template_revision_id).toBe('revision-2')
  await expect(page.getByText(/saved as a reviewable draft profile/)).toBeVisible()
})

test('spool creation is available without opening Spoolman', async ({ page }) => {
  let submitted: Record<string, unknown> | null = null
  await page.route('**/api/v1/filaments', (route) => route.fulfill({ json: [filament] }))
  await page.route('**/api/v1/spools?**', async (route) => {
    if (route.request().method() === 'POST') {
      submitted = route.request().postDataJSON() as Record<string, unknown>
      await route.fulfill({ status: 201, json: {} })
    } else await route.fulfill({ json: { items: [], total: 0, limit: 200, offset: 0 } })
  })
  await page.route('**/api/v1/spools', async (route) => {
    submitted = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({ status: 201, json: {} })
  })
  await page.goto('/spools')
  await page.getByRole('button', { name: 'Add spool' }).click()
  await page.getByLabel('Spool code').fill('PLA-BLUE-01')
  await page.getByRole('button', { name: 'Create spool' }).click()
  await expect.poll(() => submitted?.filament_product_id).toBe(filament.id)
  await expect.poll(() => submitted?.spool_code).toBe('PLA-BLUE-01')
})

test('free-text bucket location is editable from Filament Manager', async ({ page }) => {
  let submitted: Record<string, unknown> | null = null
  let currentSpool = spool
  await page.route('**/api/v1/filaments', (route) => route.fulfill({ json: [filament] }))
  await page.route('**/api/v1/spools?**', (route) => route.fulfill({
    json: { items: [currentSpool], total: 1, limit: 200, offset: 0 },
  }))
  await page.route('**/api/v1/spools/spool-id', async (route) => {
    submitted = route.request().postDataJSON() as Record<string, unknown>
    currentSpool = { ...spool, location: 'Bucket 12', record_version: 4 }
    await route.fulfill({ json: currentSpool })
  })

  await page.goto('/spools')
  await page.getByText('PLA-BLUE-01', { exact: true }).click()
  await expect(page.getByText('Bucket 3', { exact: true }).last()).toBeVisible()
  await page.getByRole('button', { name: 'Edit location' }).click()
  await page.getByLabel('Bucket or location').fill('Bucket 12')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: 'Save location' }).click()

  await expect.poll(() => submitted?.expected_version).toBe(3)
  await expect.poll(() => submitted?.location).toBe('Bucket 12')
  await expect(page.getByText('Bucket 12', { exact: true }).last()).toBeVisible()
})

test('existing Cura materials require an explicit takeover warning', async ({ page }) => {
  const agent = {
    id: 'agent-id', agent_code: 'WS-TEST', display_name: 'Arch Cura', hostname: 'workstation',
    platform: 'arch_linux', architecture: 'x86_64', agent_version: '0.1.2', enabled: true,
    cura_management_enabled: false, capabilities: { unmanaged_material_count: 18 },
    cura_installations: [{ installation_id: 'cura-id', version: '5.13', channel: 'Linux Cura', path_hint: 'Linux Cura user data / 5.13', setting_version: 27, managed_library_checksum: null, machines: [] }],
    cura_materials: [], last_seen_at: '2026-08-11T14:00:00Z', last_error: null,
    record_version: 1, created_at: '2026-08-11T12:00:00Z',
  }
  let accepted = false
  await page.route('**/api/v1/workstation-agents', (route) => route.fulfill({ json: [agent] }))
  await page.route('**/api/v1/cura-deployments', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/profiles/templates?include_inactive=true', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/workstation-agents/agent-id', async (route) => {
    accepted = true
    await route.fulfill({ json: { ...agent, cura_management_enabled: true, record_version: 2 } })
  })
  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toContain('back up and replace every user material file')
    await dialog.accept()
  })
  await page.goto('/workstations')
  await expect(page.getByText('18', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Manage and synchronize Cura' }).click()
  await expect.poll(() => accepted).toBe(true)
})

test('reported Cura material can be preserved as a draft before takeover', async ({ page }) => {
  const material = {
    source_id: 'b'.repeat(64), installation_id: 'cura-id', name: 'Polymaker PETG · PolyLite',
    brand: 'Polymaker', material_type: 'PETG', color_name: 'Black',
    settings: {
      default_material_print_temperature: '225', default_material_bed_temperature: '70',
      material_flow: '98.5', klipper_pressure_advance_factor: '0.035',
    },
  }
  const agent = {
    id: 'agent-id', agent_code: 'WS-TEST', display_name: 'Arch Cura', hostname: 'workstation',
    platform: 'arch_linux', architecture: 'x86_64', agent_version: '0.2.0', enabled: true,
    cura_management_enabled: false, capabilities: { unmanaged_material_count: 1 },
    cura_installations: [{ installation_id: 'cura-id', version: '5.13', channel: 'Linux Cura', path_hint: 'Linux Cura user data / 5.13', setting_version: 27, managed_library_checksum: null, machines: [] }],
    cura_materials: [material], last_seen_at: '2026-08-13T14:00:00Z', last_error: null,
    record_version: 1, created_at: '2026-08-13T12:00:00Z',
  }
  let submitted: Record<string, unknown> | null = null
  let importedTemplates: Record<string, unknown>[] = []
  await page.route('**/api/v1/workstation-agents', (route) => route.fulfill({ json: [agent] }))
  await page.route('**/api/v1/cura-deployments', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/profiles/templates**', async (route) => {
    if (route.request().method() === 'POST') {
      submitted = route.request().postDataJSON() as Record<string, unknown>
      importedTemplates = [{
        ...template,
        id: 'imported-template-id',
        name: 'Template PETG',
        material_type: 'PETG',
        source_workstation_agent_id: agent.id,
        source_cura_material_id: material.source_id,
        revisions: [{ ...template.revisions[0], id: 'imported-revision-id', status: 'draft', published_at: null, checksum: null }],
      }]
      await route.fulfill({ status: 201, json: importedTemplates[0] })
    } else await route.fulfill({ json: importedTemplates })
  })

  await page.goto('/workstations')
  await expect(page.getByRole('heading', { name: 'Preserve selected Cura materials before synchronization' })).toBeVisible()
  await page.getByRole('checkbox', { name: /Polymaker PETG · PolyLite/ }).check()
  await page.getByRole('button', { name: 'Review selected imports (1)' }).click()
  await expect(page.getByRole('dialog', { name: 'Preserve selected Cura material' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Family template' })).toHaveClass(/active/)
  await page.getByLabel('Filament density').fill('1.27')
  await page.getByRole('button', { name: 'Import draft' }).click()

  await expect.poll(() => submitted?.source_id).toBe(material.source_id)
  await expect.poll(() => submitted?.filament_density_g_cm3).toBe('1.27')
  await expect(page.getByText(/preserved as a draft template/i)).toBeVisible()
  await expect(page.getByRole('link', { name: 'Review and publish' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Manage and synchronize Cura' })).toBeDisabled()
})
