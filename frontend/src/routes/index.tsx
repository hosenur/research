import { useRef, useState, type ChangeEvent, type DragEvent } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { PaperProcessingSteps } from '../components/ui/PaperProcessingSteps'
import {
  MissingWorks,
  type MissingWorkReportJson,
} from '../components/ui/MissingWorks'
import {
  OpenAlexResults,
  type EnrichedReference,
} from '../components/ui/OpenAlexResults'
import {
  ArrowDownToLine,
  Check,
  ChevronDown,
  Copy,
  FileCode2,
  FileText,
  LoaderCircle,
  RefreshCcw,
  Search,
  UploadCloud,
  X,
} from 'lucide-react'

const MAX_PDF_BYTES = 50 * 1024 * 1024

type ParseState =
  | { kind: 'idle' }
  | { kind: 'parsing'; uploadProgress: number }
  | { kind: 'success'; paper: PaperJson }
  | { kind: 'enriching'; paper: PaperJson }
  | { kind: 'reviewing'; paper: PaperJson }
  | { kind: 'error'; message: string }

interface PaperJson {
  title: string
  abstract?: string | null
  sections: unknown[]
  references: EnrichedReference[]
  unresolvedReferenceIds?: string[]
  warnings?: string[]
}

function enrichmentSummary(paper: PaperJson) {
  const counts = { matched: 0, unmatched: 0, error: 0, skipped: 0 }
  for (const reference of paper.references) {
    if (reference.openalexStatus && reference.openalexStatus in counts) {
      counts[reference.openalexStatus] += 1
    }
  }
  return counts
}

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function ParserPage() {
  const inputRef = useRef<HTMLInputElement>(null)
  const activeRequestRef = useRef<XMLHttpRequest | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [parseState, setParseState] = useState<ParseState>({ kind: 'idle' })
  const [copied, setCopied] = useState(false)
  const [showJson, setShowJson] = useState(false)
  const [missingWorks, setMissingWorks] = useState<MissingWorkReportJson | null>(null)

  function chooseFile(nextFile?: File) {
    if (!nextFile) return

    if (nextFile.type !== 'application/pdf' && !nextFile.name.toLowerCase().endsWith('.pdf')) {
      setFile(null)
      setParseState({ kind: 'error', message: 'Choose a PDF research paper.' })
      return
    }

    if (nextFile.size > MAX_PDF_BYTES) {
      setFile(null)
      setParseState({ kind: 'error', message: 'PDF files must be 50 MB or smaller.' })
      return
    }

    setFile(nextFile)
    setParseState({ kind: 'idle' })
  }

  function handleInput(event: ChangeEvent<HTMLInputElement>) {
    chooseFile(event.target.files?.[0])
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setIsDragging(false)
    chooseFile(event.dataTransfer.files[0])
  }

  async function parsePaper() {
    if (!file || parseState.kind === 'parsing') return

    setParseState({ kind: 'parsing', uploadProgress: 0 })
    const body = new FormData()
    body.append('file', file)

    try {
      const paper = await new Promise<PaperJson>((resolve, reject) => {
        const request = new XMLHttpRequest()
        activeRequestRef.current = request
        request.open('POST', '/api/papers/parse')
        request.setRequestHeader('Accept', 'application/json')

        request.upload.addEventListener('progress', (event) => {
          if (!event.lengthComputable) return
          const uploadProgress = Math.min(
            99,
            Math.round((event.loaded / event.total) * 100),
          )
          setParseState({ kind: 'parsing', uploadProgress })
        })
        request.upload.addEventListener('load', () => {
          setParseState({ kind: 'parsing', uploadProgress: 100 })
        })

        request.addEventListener('load', () => {
          activeRequestRef.current = null
          let payload: unknown
          try {
            payload = JSON.parse(request.responseText)
          } catch {
            reject(
              new Error(
                `The API returned ${request.getResponseHeader('content-type') || 'an unknown format'} instead of Paper JSON.`,
              ),
            )
            return
          }

          if (request.status < 200 || request.status >= 300) {
            const detail =
              typeof payload === 'object' && payload !== null && 'detail' in payload
                ? String(payload.detail)
                : `Parsing failed with HTTP ${request.status}.`
            reject(new Error(detail))
            return
          }

          resolve(payload as PaperJson)
        })
        request.addEventListener('error', () => {
          activeRequestRef.current = null
          reject(new Error('Could not reach the paper parser.'))
        })
        request.addEventListener('abort', () => {
          activeRequestRef.current = null
          reject(new DOMException('Upload cancelled.', 'AbortError'))
        })
        request.send(body)
      })
      setParseState({ kind: 'success', paper })
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return
      setParseState({
        kind: 'error',
        message: error instanceof Error ? error.message : 'Could not parse this paper.',
      })
    }
  }

  function currentPaper() {
    if (
      parseState.kind === 'success' ||
      parseState.kind === 'enriching' ||
      parseState.kind === 'reviewing'
    ) {
      return parseState.paper
    }
    return null
  }

  function formattedJson() {
    const paper = currentPaper()
    if (!paper) return ''
    return JSON.stringify(paper, null, 2)
  }

  async function enrichPaper() {
    const paper = currentPaper()
    if (!paper || parseState.kind === 'enriching') return

    setParseState({ kind: 'enriching', paper })
    try {
      const response = await fetch('/api/papers/enrich', {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(paper),
      })
      const payload = await response.json()
      if (!response.ok) {
        const detail =
          typeof payload === 'object' && payload !== null && 'detail' in payload
            ? String(payload.detail)
            : `OpenAlex lookup failed with HTTP ${response.status}.`
        throw new Error(detail)
      }
      setParseState({ kind: 'success', paper: payload as PaperJson })
    } catch (error) {
      setParseState({
        kind: 'success',
        paper,
      })
      window.alert(error instanceof Error ? error.message : 'Could not reach OpenAlex.')
    }
  }

  async function findMissingWorks() {
    const paper = currentPaper()
    if (!paper || parseState.kind === 'reviewing' || parseState.kind === 'enriching') return

    setParseState({ kind: 'reviewing', paper })
    try {
      const response = await fetch('/api/papers/missing-works', {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(paper),
      })
      const payload = await response.json()
      if (!response.ok) {
        const detail =
          typeof payload === 'object' && payload !== null && 'detail' in payload
            ? String(payload.detail)
            : `Missing-work search failed with HTTP ${response.status}.`
        throw new Error(detail)
      }
      setMissingWorks(payload as MissingWorkReportJson)
      setParseState({ kind: 'success', paper })
    } catch (error) {
      setParseState({ kind: 'success', paper })
      window.alert(error instanceof Error ? error.message : 'Could not search OpenAlex.')
    }
  }

  function downloadJson() {
    if (!currentPaper() || !file) return

    const json = new Blob([formattedJson()], { type: 'application/json' })
    const url = URL.createObjectURL(json)
    const link = document.createElement('a')
    link.href = url
    link.download = `${file.name.replace(/\.pdf$/i, '')}.json`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  async function copyJson() {
    if (!currentPaper()) return
    await navigator.clipboard.writeText(formattedJson())
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1600)
  }

  function reset() {
    activeRequestRef.current?.abort()
    setFile(null)
    setParseState({ kind: 'idle' })
    setCopied(false)
    setShowJson(false)
    setMissingWorks(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-14 sm:px-8 sm:py-20">
      <section className="mx-auto max-w-3xl text-center">
        <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-ink/10 bg-white/60 px-3 py-1.5 text-xs font-medium tracking-wide text-ink/60 shadow-sm backdrop-blur">
          <FileCode2 aria-hidden="true" size={14} />
          PDF to structured JSON
        </div>
        <h1 className="font-display text-balance text-5xl font-semibold leading-[0.98] tracking-[-0.055em] text-ink sm:text-7xl">
          Turn research papers into data.
        </h1>
        <p className="mx-auto mt-6 max-w-xl text-pretty text-base leading-7 text-ink/60 sm:text-lg">
          Upload an academic PDF. Folio uses GROBID to extract its metadata, sections,
          citations, and bibliography into a structured Paper JSON model.
        </p>
      </section>

      <section className="mx-auto mt-12 max-w-3xl sm:mt-16">
        <div className="rounded-[28px] border border-ink/10 bg-white/65 p-3 shadow-[0_24px_80px_rgba(42,38,31,0.08)] backdrop-blur-sm sm:p-4">
          <div
            role="button"
            tabIndex={0}
            onClick={() => inputRef.current?.click()}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') inputRef.current?.click()
            }}
            onDragEnter={(event) => {
              event.preventDefault()
              setIsDragging(true)
            }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={(event) => {
              if (!event.currentTarget.contains(event.relatedTarget as Node)) setIsDragging(false)
            }}
            onDrop={handleDrop}
            data-dragging={isDragging}
            className="upload-zone group grid min-h-72 cursor-pointer place-items-center rounded-[20px] border border-dashed border-ink/20 bg-paper/70 p-7 text-center outline-none transition-[border-color,background-color,transform] duration-200 ease-out focus-visible:border-coral focus-visible:ring-4 focus-visible:ring-coral/10 data-[dragging=true]:scale-[0.99] data-[dragging=true]:border-coral data-[dragging=true]:bg-coral/5 sm:min-h-80"
          >
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf,.pdf"
              className="sr-only"
              onChange={handleInput}
            />

            {!file ? (
              <div>
                <span className="mx-auto grid size-14 place-items-center rounded-2xl border border-ink/10 bg-white text-ink shadow-sm transition-transform duration-200 ease-out group-data-[dragging=true]:scale-95">
                  <UploadCloud aria-hidden="true" size={23} />
                </span>
                <p className="mt-5 font-display text-xl font-semibold tracking-[-0.025em]">
                  Drop your paper here
                </p>
                <p className="mt-2 text-sm text-ink/50">or click to browse · PDF up to 50 MB</p>
              </div>
            ) : (
              <div
                className={`w-full ${parseState.kind === 'success' || parseState.kind === 'enriching' || parseState.kind === 'reviewing' ? 'max-w-2xl' : 'max-w-md'}`}
                onClick={(event) => event.stopPropagation()}
              >
                <div className="flex items-center gap-4 rounded-2xl border border-ink/10 bg-white p-4 text-left shadow-sm">
                  <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-coral/10 text-coral">
                    <FileText aria-hidden="true" size={20} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold">{file.name}</p>
                    <p className="mt-1 text-xs text-ink/45">{formatBytes(file.size)} · PDF document</p>
                  </div>
                  <button
                    type="button"
                    onClick={reset}
                    aria-label="Remove selected file"
                    className="pressable grid size-9 shrink-0 place-items-center rounded-lg text-ink/40 outline-none transition-colors duration-150 ease-out hover:bg-ink/5 hover:text-ink focus-visible:ring-2 focus-visible:ring-coral/40"
                  >
                    <X aria-hidden="true" size={17} />
                  </button>
                </div>

                {parseState.kind === 'parsing' ? (
                  <PaperProcessingSteps
                    uploadProgress={parseState.uploadProgress}
                  />
                ) : parseState.kind !== 'success' && parseState.kind !== 'enriching' && parseState.kind !== 'reviewing' ? (
                  <button
                    type="button"
                    onClick={parsePaper}
                    className="pressable mt-4 inline-flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-ink px-5 text-sm font-semibold text-paper shadow-sm outline-none transition-[transform,background-color] duration-150 ease-out hover:bg-ink/90 focus-visible:ring-4 focus-visible:ring-ink/15"
                  >
                    Parse with GROBID
                    <FileCode2 aria-hidden="true" size={17} />
                  </button>
                ) : null}

                {(parseState.kind === 'success' || parseState.kind === 'enriching' || parseState.kind === 'reviewing') && (
                  <div className="result-card mt-4 overflow-hidden rounded-2xl border border-sage/25 bg-sage/8 text-left">
                    <div className="flex items-start gap-3">
                      <div className="flex w-full items-start gap-3 p-4">
                        <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-sage text-white">
                          {parseState.kind === 'enriching' ? (
                            <LoaderCircle aria-hidden="true" className="animate-spin" size={15} />
                          ) : (
                            <Check aria-hidden="true" size={15} strokeWidth={2.5} />
                          )}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-semibold">
                            {parseState.paper.title || 'Paper parsed successfully'}
                          </p>
                          <p className="mt-1 text-xs leading-5 text-ink/55">
                            {parseState.paper.sections.length} sections ·{' '}
                            {parseState.paper.references.length} references
                            {parseState.paper.references.some((item) => item.openalexStatus) ? (
                              <>
                                {' '}
                                · {enrichmentSummary(parseState.paper).matched} on OpenAlex
                              </>
                            ) : null}
                          </p>
                        </div>
                      </div>
                    </div>

                    {parseState.paper.references.some((item) => item.openalexStatus) ? (
                      <OpenAlexResults references={parseState.paper.references} />
                    ) : null}

                    {missingWorks ? <MissingWorks report={missingWorks} /> : null}

                    <div className="border-t border-ink/10">
                      <button
                        type="button"
                        onClick={() => setShowJson((value) => !value)}
                        className="pressable flex h-10 w-full items-center justify-between px-4 text-xs font-medium text-ink/45 outline-none hover:bg-ink/4 hover:text-ink focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-coral/30"
                      >
                        Paper JSON
                        <ChevronDown
                          aria-hidden="true"
                          size={14}
                          className={`transition-transform duration-200 ease-[cubic-bezier(0.23,1,0.32,1)] ${showJson ? 'rotate-180' : ''}`}
                        />
                      </button>
                      {showJson ? (
                        <div className="border-t border-ink/10 bg-[#1f201d]">
                          <div className="flex items-center justify-end border-b border-white/10 px-4 py-2">
                            <button
                              type="button"
                              onClick={copyJson}
                              className="pressable inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-white/65 outline-none transition-[transform,background-color,color] duration-150 ease-out hover:bg-white/8 hover:text-white focus-visible:ring-2 focus-visible:ring-white/30"
                            >
                              {copied ? <Check aria-hidden="true" size={14} /> : <Copy aria-hidden="true" size={14} />}
                              {copied ? 'Copied' : 'Copy'}
                            </button>
                          </div>
                          <pre className="max-h-[22rem] overflow-auto p-4 font-mono text-[12px] leading-5 text-[#e6e3da] [scrollbar-color:rgba(255,255,255,0.2)_transparent]">
                            <code>{formattedJson()}</code>
                          </pre>
                        </div>
                      ) : null}
                    </div>

                    <div className="grid grid-cols-2 gap-2 p-4">
                      <button
                        type="button"
                        onClick={enrichPaper}
                        disabled={parseState.kind === 'enriching'}
                        className="pressable inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-ink px-4 text-sm font-semibold text-paper outline-none transition-[transform,background-color] duration-150 ease-out hover:bg-ink/90 focus-visible:ring-4 focus-visible:ring-ink/15 disabled:opacity-60"
                      >
                        {parseState.kind === 'enriching' ? (
                          <LoaderCircle aria-hidden="true" className="animate-spin" size={16} />
                        ) : (
                          <Search aria-hidden="true" size={16} />
                        )}
                        {parseState.kind === 'enriching' ? 'Looking up…' : 'Look up on OpenAlex'}
                      </button>
                      <button
                        type="button"
                        onClick={findMissingWorks}
                        disabled={parseState.kind === 'enriching' || parseState.kind === 'reviewing'}
                        className="pressable inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-sage px-4 text-sm font-semibold text-white outline-none transition-[transform,background-color] duration-150 ease-out hover:bg-sage/90 focus-visible:ring-4 focus-visible:ring-sage/20 disabled:opacity-60"
                      >
                        {parseState.kind === 'reviewing' ? (
                          <LoaderCircle aria-hidden="true" className="animate-spin" size={16} />
                        ) : (
                          <Search aria-hidden="true" size={16} />
                        )}
                        {parseState.kind === 'reviewing' ? 'Searching…' : 'Find missing work'}
                      </button>
                      <button
                        type="button"
                        onClick={downloadJson}
                        className="pressable inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-ink/10 bg-white px-4 text-sm font-semibold outline-none transition-[transform,background-color] duration-150 ease-out hover:bg-ink/5 focus-visible:ring-4 focus-visible:ring-ink/10"
                      >
                        <ArrowDownToLine aria-hidden="true" size={16} />
                        Download JSON
                      </button>
                      <button
                        type="button"
                        onClick={reset}
                        className="pressable inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-ink/10 bg-white px-4 text-sm font-semibold outline-none transition-[transform,background-color] duration-150 ease-out hover:bg-ink/5 focus-visible:ring-4 focus-visible:ring-ink/10"
                      >
                        <RefreshCcw aria-hidden="true" size={15} />
                        Parse another
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {parseState.kind === 'error' && (
            <div className="result-card mx-2 mt-3 rounded-xl border border-red-900/10 bg-red-500/5 px-4 py-3 text-sm text-red-900">
              {parseState.message}
            </div>
          )}
        </div>

        <div className="mt-6 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-ink/40">
          <span>Local processing</span>
          <span aria-hidden="true">·</span>
          <span>No account required</span>
          <span aria-hidden="true">·</span>
          <span>Structured Paper JSON</span>
        </div>
      </section>
    </div>
  )
}

export const Route = createFileRoute('/')({ component: ParserPage })
