import { useEffect, useMemo, useRef, useState } from 'react'
import useSWR from 'swr'
import useSWRMutation from 'swr/mutation'

export interface CitationAuditFinding {
  id: string
  sentenceId: string
  sectionId: string
  sectionTitle: string
  paragraphId: string
  sentenceText: string
  sourceText: string
  claimText: string
  claimType: string
  confidence: number
  explanation: string
  detectedBy: Array<'verbal-heuristic' | 'ai'>
  heuristicReasons: string[]
  startOffset: number
  endOffset: number
  sourceSearchStatus: 'not_started' | 'queued' | 'running' | 'completed' | 'failed'
  sourceSearchError?: string | null
  sourceCandidates: CitationSourceCandidate[]
  revision: number
}

export interface CitationSourceCandidate {
  id: string
  rank: number
  score: number
  reason: string
  supportStatus: 'not_started' | 'running' | 'verified' | 'rejected' | 'failed'
  supportsClaim?: boolean | null
  supportConfidence?: number | null
  supportExplanation?: string | null
  supportEvidence?: string | null
  decision: 'pending' | 'accepted' | 'rejected'
  work: {
    id: string
    title: string
    year?: number | null
    abstract?: string | null
    doi?: string | null
    arxivId?: string | null
    authors: Array<{ name?: string }>
    landingPageUrl?: string | null
    citedByCount?: number | null
    providers: Array<'openalex' | 'semantic-scholar'>
    providerIds: Record<string, string>
  }
}

interface CitationAuditResponse {
  status: 'not_started' | 'queued' | 'running' | 'completed' | 'failed'
  revision: number
  progress: {
    totalSentences: number
    heuristicCandidates: number
    priorityTotal: number
    priorityCompleted: number
    discoveryTotal: number
    discoveryCompleted: number
  }
  findings: CitationAuditFinding[]
  sourceSearchPending: number
  error?: string | null
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

async function decideJson<T>(url: string, { arg }: { arg: { findingId: string; candidateId: string; decision: 'accepted' | 'rejected' } }): Promise<T> {
  const endpoint = `${url}/findings/${arg.findingId}/candidates/${arg.candidateId}/decision`
  const response = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision: arg.decision }) })
  if (!response.ok) throw new Error(`The API returned HTTP ${response.status}.`)
  return response.json() as Promise<T>
}

async function feedbackJson<T>(url: string, { arg }: { arg: { findingId: string; candidateId?: string; feedback: 'false_positive' | 'needs_review'; note?: string } }): Promise<T> {
  const response = await fetch(`${url}/findings/${arg.findingId}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      feedback: arg.feedback,
      candidateId: arg.candidateId,
      note: arg.note,
    }),
  })
  if (!response.ok) throw new Error(`The API returned HTTP ${response.status}.`)
  return response.json() as Promise<T>
}

export function useCitationAudit(paperId: string) {
  const [revision, setRevision] = useState(1)
  const [findings, setFindings] = useState<CitationAuditFinding[]>([])
  const url = `/api/papers/${paperId}/citation-audit`
  const start = useSWRMutation<{ auditId: string }>(url, postJson)
  const decision = useSWRMutation(url, decideJson)
  const feedback = useSWRMutation(url, feedbackJson)
  const startedRef = useRef(false)

  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true
    void start.trigger()
  }, [start])

  const poll = useSWR<CitationAuditResponse>(
    start.error ? null : [url, revision],
    ([endpoint, afterRevision]: [string, number]) =>
      fetchJson(`${endpoint}?afterRevision=${afterRevision}`),
    {
      keepPreviousData: true,
      refreshInterval: (latest) =>
        (latest?.status === 'completed' && latest.sourceSearchPending === 0) ||
        latest?.status === 'failed'
          ? 0
          : 1_200,
      revalidateOnFocus: true,
    },
  )

  useEffect(() => {
    const payload = poll.data
    if (!payload) return
    if (payload.findings.length) {
      setFindings((current) => {
        const merged = new Map(current.map((finding) => [finding.id, finding]))
        for (const finding of payload.findings) merged.set(finding.id, finding)
        return [...merged.values()].sort((left, right) => left.revision - right.revision)
      })
    }
    if (payload.revision > revision) setRevision(payload.revision)
  }, [poll.data, revision])

  const payload = poll.data
  const failed = Boolean(start.error || (poll.error && !payload) || payload?.status === 'failed')
  const progress = payload?.progress ?? {
    totalSentences: 0,
    heuristicCandidates: 0,
    priorityTotal: 0,
    priorityCompleted: 0,
    discoveryTotal: 0,
    discoveryCompleted: 0,
  }
  const completedBatches = progress.priorityCompleted + progress.discoveryCompleted
  const totalBatches = progress.priorityTotal + progress.discoveryTotal
  const percentage = totalBatches ? Math.round((completedBatches / totalBatches) * 100) : 0

  return useMemo(
    () => ({
      error:
        payload?.error ??
        (start.error instanceof Error ? start.error.message : null) ??
        (poll.error instanceof Error ? poll.error.message : null),
      findings,
      percentage,
      progress,
      status: failed ? ('failed' as const) : (payload?.status ?? 'queued'),
      decideCandidate: (findingId: string, candidateId: string, value: 'accepted' | 'rejected') =>
        decision.trigger({ findingId, candidateId, decision: value }).then(() => poll.mutate()),
      reportFinding: (findingId: string, value: 'false_positive' | 'needs_review') =>
        feedback.trigger({ findingId, feedback: value }).then(() => poll.mutate()),
      decisionPending: decision.isMutating || feedback.isMutating,
    }),
    [decision.isMutating, failed, feedback, findings, payload?.error, payload?.status, percentage, poll.error, progress, start.error],
  )
}
