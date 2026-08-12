import { expect, test } from '@playwright/test'

const user = {
  id: 'administrator-id',
  username: 'admin',
  display_name: 'Administrator',
  role: 'administrator',
  is_active: true,
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
  condition: 'good',
  status: 'active',
  preferred_materials: [],
  last_cleaned_at: null,
  notes: null,
  record_version: 3,
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
    },
    {
      id: 'surface-b-id',
      build_plate_id: 'plate-id',
      side: 'b',
      surface_code: 'P4b',
      klipper_mesh_profile: 'P4b',
      surface_material: 'PEX',
      texture: 'smooth',
      mesh_available: true,
      last_mesh_checked_at: '2026-08-11T14:00:00Z',
      last_mesh_calibrated_at: null,
      notes: null,
      record_version: 1,
    },
  ],
}

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: user }))
  await page.route('**/api/v1/build-plates', (route) => route.fulfill({ json: [plate] }))
  await page.route('**/api/v1/printers', (route) => route.fulfill({ json: [printer] }))
})

test('groups both sides under one physical plate on desktop and mobile', async ({ page }) => {
  await page.goto('/plates')

  await expect(page.getByRole('heading', { name: 'Flexible P4' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'P4', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'P4b', exact: true })).toBeVisible()
  await expect(page.getByText('PEX', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Active side' })).toBeDisabled()

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('heading', { name: 'Flexible P4' })).toBeVisible()
  await expect(
    page.getByRole('paragraph').filter({ hasText: 'Double-sided spring-steel plate' }),
  ).toBeVisible()
  await expect(page.getByRole('button', { name: 'Select P4' })).toBeVisible()
})
