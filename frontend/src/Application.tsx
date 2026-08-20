import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
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
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider>
        <ThemeProvider>
          <AuthProvider>
            <App />
          </AuthProvider>
        </ThemeProvider>
      </RouterProvider>
    </QueryClientProvider>
  )
}
