import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { WheelEvent } from 'react'
import { App } from './App'
import { AuthProvider } from './context/AuthContext'
import { RouterProvider } from './context/RouterContext'
import { ThemeProvider } from './context/ThemeContext'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 20_000, retry: 1, refetchOnWindowFocus: false },
    mutations: { retry: 0 },
  },
})

export function Application() {
  const preserveNumberValueWhileScrolling = (event: WheelEvent<HTMLDivElement>) => {
    const target = event.target
    if (target instanceof HTMLInputElement && target.type === 'number' && document.activeElement === target) {
      // A focused number input consumes wheel gestures as value changes. Blur
      // during capture so the same gesture continues to scroll its container.
      target.blur()
    }
  }

  return (
    <div className="application-root" onWheelCapture={preserveNumberValueWhileScrolling}>
      <QueryClientProvider client={queryClient}>
        <RouterProvider>
          <ThemeProvider>
            <AuthProvider>
              <App />
            </AuthProvider>
          </ThemeProvider>
        </RouterProvider>
      </QueryClientProvider>
    </div>
  )
}
