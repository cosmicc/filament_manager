import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { BugsnagSourceMapUploaderPlugin } from '@bugsnag/vite-plugin-bugsnag'
import { readFileSync } from 'node:fs'

const packageJson = JSON.parse(
  readFileSync(new URL('./package.json', import.meta.url), 'utf8'),
) as { version: string }
const bugsnagUploadApiKey = process.env.BUGSNAG_UPLOAD_API_KEY?.trim()
if (bugsnagUploadApiKey && !/^[0-9a-f]{32}$/i.test(bugsnagUploadApiKey)) {
  throw new Error('BUGSNAG_UPLOAD_API_KEY must be 32 hexadecimal characters')
}
const bugsnagBuildPlugins = bugsnagUploadApiKey
  ? [
      BugsnagSourceMapUploaderPlugin({
        apiKey: bugsnagUploadApiKey,
        appVersion: packageJson.version,
        base: '*',
        overwrite: true,
      }),
    ]
  : []

export default defineConfig({
  plugins: [react(), ...bugsnagBuildPlugins],
  build: {
    // Hidden maps keep production bundles identical while the runtime image removes the map files.
    sourcemap: 'hidden',
  },
  define: {
    'import.meta.env.VITE_APP_VERSION': JSON.stringify(packageJson.version),
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8080',
      '/health': 'http://127.0.0.1:8080',
      '/metrics': 'http://127.0.0.1:8080',
      '/runtime-config.js': 'http://127.0.0.1:8080',
    },
  },
})
