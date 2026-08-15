import useSWR from 'swr'

export interface ClaimCitationFinding {
  id: string
  sentenceId: string
  sectionId: string
  sectionTitle: string
  paragraphId: string
  citationId?: string | null
  referenceId: string
  claimText: string
  citationText: string
  workTitle?: string | null
  sourceUrl?: string | null
  providers: string[]
  priorityScore?: number | null
  classification: 'supported' | 'weak' | 'contradicted' | 'unverifiable'
  confidence: number
  explanation: string
  evidenceText?: string | null
}

interface ClaimCitationReviewResponse {
  paperId: string
  status: 'not_started' | 'queued' | 'running' | 'completed' | 'failed'
  findings: ClaimCitationFinding[]
  total: number
  completed: number
  error?: string | null
}

async function fetchReview(url: string): Promise<ClaimCitationReviewResponse> {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`The API returned HTTP ${response.status}.`)
  return response.json() as Promise<ClaimCitationReviewResponse>
}

export function useClaimCitationReview(paperId: string) {
  return useSWR<ClaimCitationReviewResponse>(
    `/api/papers/${paperId}/claim-citation-review`,
    fetchReview,
    {
      keepPreviousData: true,
      refreshInterval: (latest) =>
        latest?.status === 'completed' || latest?.status === 'failed' ? 0 : 1_500,
      revalidateOnFocus: true,
    },
  )
}
