import * as React from 'react'
import { createRoot } from 'react-dom/client'
import { ApplicationFailure } from './components/ApplicationFailure'
import { initializeBrowserTelemetry, notifyBrowserError } from './telemetry'
import './styles/tokens.css'
import './styles/global.css'

const rootElement = document.getElementById('root')
if (!rootElement) throw new Error('Application root is missing')
const root = createRoot(rootElement)

async function bootstrap(): Promise<void> {
  try {
    const [ErrorBoundary, { Application }] = await Promise.all([
      initializeBrowserTelemetry(React),
      import('./Application'),
    ])
    const application = <React.StrictMode><Application /></React.StrictMode>
    root.render(
      ErrorBoundary
        ? <ErrorBoundary FallbackComponent={ApplicationFailure}>{application}</ErrorBoundary>
        : application,
    )
  } catch (error) {
    notifyBrowserError(error, 'browser.bootstrap')
    root.render(<ApplicationFailure />)
  }
}

void bootstrap()
