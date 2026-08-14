import type { ReactNode } from 'react'

interface UiProviderProps {
  children: ReactNode
  className?: string
  dark?: boolean
}

export function UiProvider({
  children,
  className = '',
  dark = false,
}: UiProviderProps) {
  return (
    <div
      className={`ui-scope${dark ? ' dark' : ''}${className ? ` ${className}` : ''}`}
    >
      {children}
    </div>
  )
}
