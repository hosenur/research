import { createRootRoute, Outlet } from '@tanstack/react-router'

function RootLayout() {
  return (
    <main className="min-h-dvh">
      <Outlet />
    </main>
  )
}

export const Route = createRootRoute({ component: RootLayout })
