import { expect, test } from '@playwright/test'

const user = {
  id: 'administrator-id',
  username: 'admin',
  display_name: 'Administrator',
  role: 'administrator',
  is_active: true,
  must_change_password: false,
  record_version: 1,
}

const printer = {
  id: 'printer-id',
  printer_code: 'printer-1',
  name: 'Workshop Printer',
  nozzle_diameter_mm: '0.4',
  active_plate_id: 'plate-id',
  active_plate_surface_id: 'surface-b-id',
  status: 'connected',
  last_seen_at: '2026-08-11T14:00:00Z',
  record_version: 2,
}

const plate = {
  id: 'plate-id',
  plate_code: 'P4',
  display_name: 'Flexible P4',
  description: 'Double-sided spring-steel plate',
  manufacturer: 'Workshop',
  product_name: 'Spring Steel 235',
  shape: 'rectangular',
  dimensions_mm: { width: '235', depth: '235', thickness: '1.2' },
  magnetic: true,
  flexible: true,
  condition: 'good',
  status: 'active',
  preferred_materials: [],
  max_bed_temp_c: '120',
  last_cleaned_at: null,
  cleaning_due_after_prints: 10,
  cleaning_due_after_days: 7,
  mesh_due_after_prints: 30,
  mesh_due_after_days: 30,
  notes: null,
  image_url: null,
  image_version: 0,
  record_version: 3,
  completed_print_count: 4,
  surfaces: [
    {
      id: 'surface-a-id',
      build_plate_id: 'plate-id',
      side: 'a',
      surface_code: 'P4',
      klipper_mesh_profile: 'P4',
      surface_material: 'PEI',
      texture: 'textured',
      mesh_available: true,
      last_mesh_checked_at: '2026-08-11T14:00:00Z',
      last_mesh_calibrated_at: null,
      notes: null,
      record_version: 1,
      completed_print_count: 3,
    },
    {
      id: 'surface-b-id',
      build_plate_id: 'plate-id',
      side: 'b',
      surface_code: 'P4b',
      klipper_mesh_profile: 'P4b',
      surface_material: 'PEX',
      texture: 'smooth',
      mesh_available: false,
      last_mesh_checked_at: '2026-08-11T14:00:00Z',
      last_mesh_calibrated_at: null,
      notes: null,
      record_version: 1,
      completed_print_count: 1,
    },
  ],
}

test.beforeEach(async ({ page }) => {
  await page.route('**/runtime-config.js', (route) => route.fulfill({
    contentType: 'application/javascript',
    body: 'window.__FILAMENT_MANAGER_RUNTIME_CONFIG__={bugsnag:{enabled:false}};',
  }))
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: user }))
  await page.route('**/api/v1/build-plates', (route) => route.fulfill({ json: route.request().method() === 'POST' ? {
    ...plate,
    id: 'plate-five-id',
    plate_code: 'P5',
    display_name: 'Build Plate P5',
    active_plate_surface_id: null,
    surfaces: [{ ...plate.surfaces[0], id: 'surface-five-id', build_plate_id: 'plate-five-id', surface_code: 'P5', klipper_mesh_profile: 'P5', mesh_available: false }],
  } : [plate] }))
  await page.route('**/api/v1/build-plates/maintenance/status', (route) => route.fulfill({ json: [{ build_plate_id: plate.id, cleaning_due: false, cleaning_prints_since: 2, cleaning_due_at: null, surfaces: [] }] }))
  await page.route('**/api/v1/build-plates/maintenance/events**', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/notifications**', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/printers', (route) => route.fulfill({ json: [printer] }))
})

test('groups both sides under one physical plate on desktop and mobile', async ({ page }) => {
  await page.goto('/plates')

  await expect(page.getByRole('heading', { name: 'Flexible P4' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'P4', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'P4b', exact: true })).toBeVisible()
  await expect(page.getByText('PEX', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Active side', exact: true })).toBeDisabled()
  await expect(page.getByText('Automatic Moonraker synchronization is on.')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Synchronize with Moonraker' })).toHaveCount(0)
  await expect(page.getByText('Completed prints').first()).toBeVisible()
  await expect(page.getByText('No matching Klipper heatmap profile')).toBeVisible()
  await expect(page.getByText(/Create and save the exact.*P4b.*bed-mesh profile/)).toBeVisible()
  await page.getByRole('button', { name: 'Add build plate' }).click()
  await expect(page.getByRole('dialog', { name: 'Edit P5' })).toBeVisible()
  await page.keyboard.press('Escape')
  const plateCard = page.locator('.build-plate-card').first()
  const editPlateButton = page.getByRole('button', { name: 'Edit physical plate' })
  await expect(editPlateButton).toBeVisible()
  expect((await editPlateButton.boundingBox())?.width).toBeLessThan((await plateCard.boundingBox())?.width ?? 0)
  await page.screenshot({ path: '../docs/design/validation/build-plates-v040.png', fullPage: true })

  await editPlateButton.click()
  const editor = page.getByRole('dialog', { name: 'Edit P4' })
  await expect(editor).toBeVisible()
  await expect(editor.getByRole('heading', { name: 'Identity' })).toBeVisible()
  await expect(editor.getByRole('heading', { name: 'Geometry' })).toBeVisible()
  await expect(editor.getByRole('heading', { name: 'Condition and use' })).toBeVisible()
  await expect(editor.getByRole('heading', { name: 'Maintenance reminders' })).toBeVisible()
  await expect(editor.getByLabel('Width (mm)')).toBeVisible()
  await expect(editor.getByLabel('Depth (mm)')).toBeVisible()
  await expect(editor.getByLabel('Diameter (mm)')).toHaveCount(0)
  await expect(editor.getByRole('option', { name: 'Other' })).toHaveCount(0)
  await editor.getByLabel('Shape').selectOption('round')
  await expect(editor.getByLabel('Diameter (mm)')).toBeVisible()
  await expect(editor.getByLabel('Width (mm)')).toHaveCount(0)
  await expect(editor.getByLabel('Depth (mm)')).toHaveCount(0)
  await page.keyboard.press('Escape')
  await expect(editor).toBeHidden()

  await page.setViewportSize({ width: 390, height: 844 })
  await page.waitForTimeout(250)
  await expect(page.getByRole('heading', { name: 'Flexible P4' })).toBeVisible()
  await expect(
    page.getByRole('paragraph').filter({ hasText: 'Double-sided spring-steel plate' }),
  ).toBeVisible()
  await expect(page.getByRole('button', { name: 'Select P4' })).toBeVisible()
  await page.screenshot({ path: '../docs/design/validation/build-plates-mobile-v040.png', fullPage: true })
})
