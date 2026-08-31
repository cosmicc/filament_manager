import { expect, test } from '@playwright/test'

const printerState = {
  printer_name: 'Workshop Printer',
  connection_status: 'connected',
  operational_status: 'idle',
  klipper_state: 'ready',
  print_state: 'standby',
  filename: null,
  progress_percent: null,
  nozzle_temperature_c: '24',
  nozzle_target_c: '0',
  bed_temperature_c: '23',
  bed_target_c: '0',
  chamber_temperature_c: null,
  chamber_target_c: null,
  print_job_id: null,
  thumbnail_url: null,
  estimated_duration_seconds: null,
  print_duration_seconds: null,
  predicted_filament_weight_g: null,
  actual_filament_weight_g: null,
  actual_filament_cost: null,
  predicted_filament_cost: null,
  cost_currency: null,
  cost_complete: false,
  checked_at: '2026-08-27T20:00:00Z',
}

test('dashboard replaces its rendered operational snapshot within ten seconds', async ({ page }) => {
  let dashboardRequests = 0
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const json = path.endsWith('/auth/me')
      ? { id: 'admin-id', username: 'admin', display_name: 'Administrator', role: 'administrator', is_active: true, must_change_password: false, record_version: 1 }
      : path.endsWith('/notifications')
        ? []
        : path.endsWith('/dashboard')
          ? (++dashboardRequests === 1
              ? {
                  total_spools: 8,
                  needs_weighing: 1,
                  low_spools: 0,
                  empty_spools: 0,
                  active_spool: null,
                  active_plate: null,
                  active_plate_surface: null,
                  printer_state: printerState,
                }
              : {
                  total_spools: 9,
                  needs_weighing: 1,
                  low_spools: 0,
                  empty_spools: 0,
                  active_spool: {
                    spool_code: 'S009',
                    status: 'active',
                    vendor_name: 'Polymaker',
                    material_type: 'PLA',
                    color_name: 'Blue',
                    color_mode: 'solid',
                    color_hexes: ['#2457A6'],
                    color_hex: '#2457A6',
                    remaining_mass_effective_g: '750',
                    remaining_percent: '75',
                    weight_confidence: 'high',
                  },
                  active_plate: {
                    plate_code: 'P2',
                    display_name: 'Smooth PEI',
                    image_url: null,
                    condition: 'good',
                  },
                  active_plate_surface: {
                    surface_code: 'P2',
                    side: 'a',
                    surface_material: 'PEI',
                  },
                  printer_state: {
                    ...printerState,
                    operational_status: 'paused',
                    print_state: 'paused',
                    filename: 'updated-part.gcode',
                    progress_percent: '51',
                  },
                })
          : []
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(json) })
  })

  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Workshop Printer' })).toBeVisible()
  await expect(page.getByText('No active spool')).toBeVisible()

  await expect(page.getByText('updated-part.gcode')).toBeVisible({ timeout: 12_000 })
  await expect(page.getByText('S009')).toBeVisible()
  await expect(page.getByText('Smooth PEI')).toBeVisible()
  await expect(page.getByText('9', { exact: true })).toBeVisible()
  expect(dashboardRequests).toBeGreaterThanOrEqual(2)
})
