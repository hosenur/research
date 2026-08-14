import { createRootRoute, Link, Outlet } from '@tanstack/react-router'
import { FileText } from 'lucide-react'

function RootLayout() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-ink/10">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-5 sm:px-8">
          <Link
            to="/"
            className="pressable flex items-center gap-2.5 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-coral/50"
          >
            <span className="grid size-8 place-items-center rounded-lg bg-ink text-paper shadow-sm">
              <FileText aria-hidden="true" size={16} strokeWidth={2} />
            </span>
            <span className="font-display text-xl font-semibold tracking-[-0.03em]">Folio</span>
          </Link>

          <div className="flex items-center gap-2 text-sm text-ink/55">
            <span className="size-2 rounded-full bg-sage shadow-[0_0_0_4px_rgba(96,130,109,0.12)]" />
            <span className="hidden sm:inline">GROBID connected</span>
          </div>
        </div>
      </header>

      <main>
        <Outlet />
      </main>
    </div>
  )
}

export const Route = createRootRoute({ component: RootLayout })
