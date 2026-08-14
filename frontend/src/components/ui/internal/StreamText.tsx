import { useEffect, useRef, useState } from 'react'

interface StreamTextProps {
  text: string
  charsPerTick?: number
  tickMs?: number
  blurTail?: number
  caret?: boolean
  className?: string
  onProgress?: (characters: number) => void
  onDone?: () => void
}

export function StreamText({
  text,
  charsPerTick = 2,
  tickMs = 9,
  blurTail = 6,
  caret = true,
  className,
  onProgress,
  onDone,
}: StreamTextProps) {
  const [visibleCharacters, setVisibleCharacters] = useState(0)
  const progressRef = useRef(onProgress)
  const doneRef = useRef(onDone)

  progressRef.current = onProgress
  doneRef.current = onDone

  useEffect(() => {
    setVisibleCharacters(0)
    let nextCharacter = 0
    const interval = window.setInterval(() => {
      nextCharacter = Math.min(nextCharacter + charsPerTick, text.length)
      setVisibleCharacters(nextCharacter)
      progressRef.current?.(nextCharacter)

      if (nextCharacter >= text.length) {
        window.clearInterval(interval)
        doneRef.current?.()
      }
    }, tickMs)

    return () => window.clearInterval(interval)
  }, [charsPerTick, text, tickMs])

  const streaming = visibleCharacters < text.length
  const visibleText = text.slice(0, visibleCharacters)
  const resolvedLength = streaming
    ? Math.max(0, visibleText.length - blurTail)
    : visibleText.length

  return (
    <span className={className}>
      {visibleText.slice(0, resolvedLength)}
      {resolvedLength < visibleText.length ? (
        <span className="stream-tail">
          {visibleText.slice(resolvedLength)}
        </span>
      ) : null}
      {caret ? (
        <span
          aria-hidden="true"
          className={`stream-caret${streaming ? ' is-streaming' : ''}`}
        />
      ) : null}
    </span>
  )
}
