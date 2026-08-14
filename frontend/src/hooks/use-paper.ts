import { useCallback, useEffect, useRef, useState } from 'react'
import useSWR from 'swr'
import useSWRMutation from 'swr/mutation'
import type { OpenAlexWorkJson, PaperDocumentJson, PaperJson } from '@/lib/paper'

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
    status: 'matched' | 'unmatched' | 'error' | 'skipped'
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

async function parsePaperMutation(
  url: string,
  { arg }: { arg: ParsePaperArgument },
): Promise<PaperDocumentJson> {
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
      const document = payload as PaperDocumentJson
      if (!document.id || !document.paper) {
        reject(new Error('The API returned an invalid paper document.'))
        return
      }
      resolve(document)
    })
    request.addEventListener('error', () => {
      arg.requestRef.current = null
      reject(new Error('Could not process this paper.'))
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
  const mutation = useSWRMutation('/api/papers/parse', parsePaperMutation)
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

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`The API returned HTTP ${response.status}.`)
  return response.json() as Promise<T>
}

async function postJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { method: 'POST' })
  if (!response.ok) throw new Error(`The API returned HTTP ${response.status}.`)
  return response.json() as Promise<T>
}

export function useOpenAlexEnrichment({
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
    `/api/papers/${paperId}/enrichments/openalex`,
    postJson,
  )
  const startedRef = useRef(false)

  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true
    void start.trigger()
  }, [start])

  const statusUrl = `/api/papers/${paperId}/enrichments/openalex`
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
