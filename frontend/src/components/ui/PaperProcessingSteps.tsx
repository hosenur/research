import { useEffect, useState } from 'react'
import { Braces, Check, LoaderCircle, UploadCloud } from 'lucide-react'

interface PaperProcessingStepsProps {
  uploadProgress: number
}

function useElapsedTime() {
  const [seconds, setSeconds] = useState(0)

  useEffect(() => {
    const startedAt = performance.now()
    const interval = window.setInterval(() => {
      setSeconds(Math.floor((performance.now() - startedAt) / 1000))
    }, 1000)

    return () => window.clearInterval(interval)
  }, [])

  return seconds < 60
    ? `${seconds}s`
    : `${Math.floor(seconds / 60)}m ${seconds % 60}s`
}

export function PaperProcessingSteps({
  uploadProgress,
}: PaperProcessingStepsProps) {
  const elapsed = useElapsedTime()
  const uploadComplete = uploadProgress >= 100

  return (
    <div
      role="status"
      aria-live="polite"
      className="result-card mt-4 overflow-hidden rounded-2xl border border-ink/10 bg-white text-left shadow-sm"
    >
      <div className="flex items-center justify-between border-b border-ink/8 px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-[0.1em] text-ink/45">
          Processing paper
        </p>
        <span className="font-mono text-xs tabular-nums text-ink/40">
          {elapsed}
        </span>
      </div>

      <div className="p-4">
        <div className="grid grid-cols-[32px_1fr] gap-x-3">
          <div className="flex flex-col items-center">
            <span
              className={`grid size-8 place-items-center rounded-full transition-[background-color,color] duration-200 ease-out ${
                uploadComplete
                  ? 'bg-sage text-white'
                  : 'bg-coral/10 text-coral'
              }`}
            >
              {uploadComplete ? (
                <Check aria-hidden="true" size={15} strokeWidth={2.6} />
              ) : (
                <UploadCloud aria-hidden="true" size={15} />
              )}
            </span>
            <span className="my-1 h-8 w-px bg-ink/10" aria-hidden="true" />
          </div>

          <div className="min-w-0 pt-0.5">
            <div className="flex items-baseline justify-between gap-3">
              <p className="text-sm font-semibold text-ink">Upload PDF</p>
              <span className="font-mono text-xs tabular-nums text-ink/45">
                {uploadComplete ? 'Done' : `${uploadProgress}%`}
              </span>
            </div>
            <p className="mt-1 text-xs text-ink/45">
              Sending the document to the parser
            </p>
            <div className="mt-2 h-1 overflow-hidden rounded-full bg-ink/8">
              <span
                className="block h-full origin-left rounded-full bg-coral transition-transform duration-200 ease-out"
                style={{ transform: `scaleX(${uploadProgress / 100})` }}
              />
            </div>
          </div>

          <div className="flex items-start justify-center">
            <span
              className={`grid size-8 place-items-center rounded-full transition-[background-color,color] duration-200 ease-out ${
                uploadComplete
                  ? 'bg-ink text-paper'
                  : 'bg-ink/5 text-ink/25'
              }`}
            >
              {uploadComplete ? (
                <LoaderCircle
                  aria-hidden="true"
                  className="animate-spin"
                  size={15}
                />
              ) : (
                <Braces aria-hidden="true" size={15} />
              )}
            </span>
          </div>

          <div className="min-w-0 pt-0.5">
            <div className="flex items-baseline justify-between gap-3">
              <p
                className={`text-sm font-semibold transition-colors duration-200 ease-out ${
                  uploadComplete ? 'text-ink' : 'text-ink/35'
                }`}
              >
                Extract and structure
              </p>
              <span className="text-xs text-ink/40">
                {uploadComplete ? 'Working' : 'Waiting'}
              </span>
            </div>
            <p className="mt-1 text-xs leading-5 text-ink/45">
              GROBID reads the paper, then citations are normalized into Paper JSON
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
