import { useCallback, useEffect, useRef, useState } from 'react'
import useSWR from 'swr'
import useSWRMutation from 'swr/mutation'
import type { OpenAlexWorkJson, PaperJson, PaperLifecycleJson } from '@/lib/paper'

interface EnrichmentResponse {
  status: 'not_started' | 'queued' | 'running' | 'completed' | 'failed'
  revision: number
  progress: {
    total: number
    completed: number
    matched: number
  }
  referenceUpdates: Array<{
    referenceId: string
    status: 'matched' | 'unmatched' | 'ambiguous' | 'error' | 'skipped'
    openalex?: OpenAlexWorkJson | null
    error?: string | null
  }>
}

export interface EnrichmentState {
  status: 'starting' | 'queued' | 'running' | 'completed' | 'failed'
  completed: number
  total: number
  matched: number
}

interface ParsePaperArgument {
  file: File
  onProgress: (progress: number) => void
  requestRef: React.MutableRefObject<XMLHttpRequest | null>
}

export type PaperUploadState =
  | { kind: 'upload' }
  | { kind: 'uploading'; file: File; uploadProgress: number }
  | { kind: 'error'; message: string }

const MAX_PDF_BYTES = 50 * 1024 * 1024

async function ingestPaperMutation(
  url: string,
  { arg }: { arg: ParsePaperArgument },
): Promise<PaperLifecycleJson> {
  return new Promise((resolve, reject) => {
    const body = new FormData()
    body.append('file', arg.file)
    const request = new XMLHttpRequest()
    arg.requestRef.current = request
    request.open('POST', url)
    request.setRequestHeader('Accept', 'application/json')
    request.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable) {
        arg.onProgress(Math.min(99, Math.round((event.loaded / event.total) * 100)))
      }
    })
    request.upload.addEventListener('load', () => arg.onProgress(100))
    request.addEventListener('load', () => {
      arg.requestRef.current = null
      const contentType =
        request.getResponseHeader('content-type') || 'an unknown format'
      let payload: unknown
      try {
        payload = JSON.parse(request.responseText)
      } catch {
        if (request.status < 200 || request.status >= 300) {
          reject(
            new Error(
              `Upload failed with HTTP ${request.status} (${contentType}).`,
            ),
          )
          return
        }
        reject(
          new Error(
            `The API returned ${contentType} instead of a paper lifecycle.`,
          ),
        )
        return
      }
      if (request.status < 200 || request.status >= 300) {
        const detail =
          typeof payload === 'object' && payload !== null && 'detail' in payload
            ? String(payload.detail)
            : `Upload failed with HTTP ${request.status}.`
        reject(new Error(detail))
        return
      }
      const lifecycle = payload as PaperLifecycleJson
      if (!lifecycle.id || !lifecycle.filename || !lifecycle.status) {
        reject(new Error('The API returned an invalid paper lifecycle.'))
        return
      }
      resolve(lifecycle)
    })
    request.addEventListener('error', () => {
      arg.requestRef.current = null
      reject(new Error('Could not upload this paper.'))
    })
    request.addEventListener('abort', () => {
      arg.requestRef.current = null
      reject(new DOMException('The paper upload was cancelled.', 'AbortError'))
    })
    request.send(body)
  })
}

export function useParsePaper() {
  const requestRef = useRef<XMLHttpRequest | null>(null)
  const mutation = useSWRMutation('/api/papers', ingestPaperMutation)
  const abort = useCallback(() => {
    requestRef.current?.abort()
    requestRef.current = null
  }, [])
  useEffect(() => abort, [abort])

  const parse = useCallback(
    (file: File, onProgress: (progress: number) => void) =>
      mutation.trigger({ file, onProgress, requestRef }),
    [mutation],
  )
  return { abort, error: mutation.error, isMutating: mutation.isMutating, parse }
}

export function usePaperUploadFlow(
  onUploaded: (lifecycle: PaperLifecycleJson) => void,
) {
  const [state, setState] = useState<PaperUploadState>({ kind: 'upload' })
  const mutation = useParsePaper()

  const reset = useCallback(() => {
    mutation.abort()
    setState({ kind: 'upload' })
  }, [mutation])

  const selectFile = useCallback(
    (file?: File | null) => {
      if (!file) return
      if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
        setState({ kind: 'error', message: 'Choose a PDF research paper.' })
        return
      }
      if (file.size > MAX_PDF_BYTES) {
        setState({ kind: 'error', message: 'PDF files must be 50 MB or smaller.' })
        return
      }

      setState({ kind: 'uploading', file, uploadProgress: 0 })
      void mutation
        .parse(file, (uploadProgress) =>
          setState({ kind: 'uploading', file, uploadProgress }),
        )
        .then(onUploaded)
        .catch((error: unknown) => {
          if (error instanceof DOMException && error.name === 'AbortError') return
          setState({
            kind: 'error',
            message: error instanceof Error ? error.message : 'Could not upload this paper.',
          })
        })
    },
    [mutation, onUploaded],
  )

  return { reset, selectFile, state }
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(payload?.detail ?? `The API returned HTTP ${response.status}.`)
  }
  return response.json() as Promise<T>
}

export function usePaperLifecycle(paperId: string) {
  return useSWR<PaperLifecycleJson>(`/api/papers/${paperId}`, fetchJson, {
    keepPreviousData: true,
    refreshInterval: (latest) =>
      latest?.status === 'ready' ? 0 : latest?.status === 'failed' ? 5_000 : 1_200,
    revalidateOnFocus: true,
  })
}

export function useObjectUrl(file: File | null) {
  const [url, setUrl] = useState('')

  useEffect(() => {
    if (!file) {
      setUrl('')
      return
    }
    const nextUrl = URL.createObjectURL(file)
    setUrl(nextUrl)
    return () => URL.revokeObjectURL(nextUrl)
  }, [file])

  return url
}

async function postJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { method: 'POST' })
  if (!response.ok) throw new Error(`The API returned HTTP ${response.status}.`)
  return response.json() as Promise<T>
}

export function useReferenceEvidence({
  initialRevision,
  paper,
  paperId,
}: {
  initialRevision: number
  paper: PaperJson
  paperId: string
}) {
  const [currentPaper, setCurrentPaper] = useState(paper)
  const [revision, setRevision] = useState(initialRevision)
  const start = useSWRMutation<{ jobId: string }>(
    `/api/papers/${paperId}/enrichments/reference-evidence`,
    postJson,
  )
  const startedRef = useRef(false)

  useEffect(() => {
    setCurrentPaper(paper)
  }, [paper])

  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true
    void start.trigger()
  }, [start])

  const statusUrl = `/api/papers/${paperId}/enrichments/reference-evidence`
  const poll = useSWR<EnrichmentResponse>(
    [statusUrl, revision],
    ([url, afterRevision]: [string, number]) =>
      fetchJson(`${url}?afterRevision=${afterRevision}`),
    {
      keepPreviousData: true,
      refreshInterval: (latest) =>
        latest?.status === 'completed' || latest?.status === 'failed' ? 0 : 1_200,
      revalidateOnFocus: true,
    },
  )

  useEffect(() => {
    const payload = poll.data
    if (!payload) return
    if (payload.referenceUpdates.length) {
      const updates = new Map(
        payload.referenceUpdates.map((update) => [update.referenceId, update]),
      )
      setCurrentPaper((current) => ({
        ...current,
        references: current.references.map((reference) => {
          const update = updates.get(reference.id)
          return update
            ? {
                ...reference,
                openalex: update.openalex ?? null,
                openalexStatus: update.status,
                openalexError: update.error ?? null,
              }
            : reference
        }),
      }))
    }
    if (payload.revision > revision) setRevision(payload.revision)
  }, [poll.data, revision])

  const failed = Boolean(start.error || (poll.error && !poll.data))
  const payload = poll.data
  const enrichment: EnrichmentState = {
    status: failed
      ? 'failed'
      : payload?.status === 'not_started'
        ? 'queued'
        : payload?.status ?? 'starting',
    completed: payload?.progress.completed ?? 0,
    total: payload?.progress.total ?? paper.references.length,
    matched: payload?.progress.matched ?? 0,
  }

  return { enrichment, paper: currentPaper }
}
