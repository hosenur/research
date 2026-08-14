import { Streamdown } from 'streamdown'

export function ChatMarkdown({
  children,
  streaming = false,
}: {
  children: string
  streaming?: boolean
}) {
  return (
    <Streamdown
      className="text-sm/6 text-fg [&_:first-child]:mt-0 [&_:last-child]:mb-0"
      isAnimating={streaming}
    >
      {children}
    </Streamdown>
  )
}
