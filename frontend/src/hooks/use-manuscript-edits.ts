import { useCallback, useEffect, useState } from 'react'
import useSWR, { useSWRConfig } from 'swr'
import useSWRMutation from 'swr/mutation'

export interface EditOperation {
  id: string
  position: number
  operationType:
    | 'replace_text'
    | 'insert_citation'
    | 'remove_citation'
    | 'restore_revision'
    | 'citation_change'
  nodeIds: string[]
  beforeText: string
  afterText: string
  rationale: string
  validationStatus: 'valid' | 'invalid'
  validationError?: string | null
  approved: boolean
  bibliographyChange?: {
    action: 'add' | 'reuse' | 'remove' | 'retain' | 'update'
    referenceId: string
    citationMarker?: string | null
    beforeText?: string | null
    afterText?: string | null
  } | null
  bibliographyChanges?: Array<{
    action: 'add' | 'reuse' | 'remove' | 'retain' | 'update'
    referenceId: string
    citationMarker?: string | null
    beforeText?: string | null
    afterText?: string | null
  }>
}

export interface EditProposal {
  id: string
  paperId: string
  baseRevision: number
  command: string
  status: 'planned' | 'approved' | 'rejected' | 'conflict' | 'invalid'
  summary: string
  warnings: string[]
  operations: EditOperation[]
  approvedRevision?: number | null
}

async function jsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(body?.detail ?? `The API returned HTTP ${response.status}.`)
  }
  return response.json() as Promise<T>
}

async function fetchJson<T>(url: string): Promise<T> {
  return jsonResponse<T>(await fetch(url))
}

function isActionableProposal(proposal: EditProposal | null | undefined) {
  return (
    proposal?.status === 'planned' &&
    proposal.operations.some((operation) => operation.validationStatus === 'valid')
  )
}

async function approveEdit(
  url: string,
  { arg }: { arg: { proposalId: string; operationIds: string[] } },
) {
  return jsonResponse<EditProposal>(
    await fetch(`${url}/${arg.proposalId}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ operationIds: arg.operationIds }),
    }),
  )
}

async function discardEdit(
  url: string,
  { arg }: { arg: { proposalId: string } },
) {
  return jsonResponse<EditProposal>(
    await fetch(`${url}/${arg.proposalId}/discard`, { method: 'POST' }),
  )
}

export function useManuscriptEdits(paperId: string) {
  const { mutate: mutateGlobal } = useSWRConfig()
  const [proposal, setProposal] = useState<EditProposal | null>(null)
  const editsUrl = `/api/papers/${paperId}/edits`
  const approve = useSWRMutation(editsUrl, approveEdit)
  const discard = useSWRMutation(editsUrl, discardEdit)
  const {
    data: latestProposal,
    error: latestError,
    mutate: mutateLatest,
  } = useSWR<EditProposal | null>(`${editsUrl}/latest`, fetchJson)

  useEffect(() => {
    setProposal(isActionableProposal(latestProposal) ? latestProposal ?? null : null)
  }, [latestProposal])

  const refreshProposal = useCallback(async () => {
    const next = await mutateLatest()
    setProposal(isActionableProposal(next) ? next ?? null : null)
    return next
  }, [mutateLatest])

  return {
    approve: async (operationIds: string[]) => {
      if (!proposal) return
      const approved = await approve.trigger({ proposalId: proposal.id, operationIds })
      setProposal(null)
      await Promise.all([
        mutateGlobal(`/api/papers/${paperId}`),
        mutateGlobal(`/api/papers/${paperId}/citation-audit`),
        mutateGlobal(`/api/papers/${paperId}/claim-citation-review`),
        mutateGlobal(`/api/papers/${paperId}/pipeline`),
        mutateLatest(approved, { revalidate: false }),
      ])
      return approved
    },
    discard: async () => {
      if (!proposal) return
      const rejected = await discard.trigger({ proposalId: proposal.id })
      setProposal(null)
      await mutateLatest()
      return rejected
    },
    error: approve.error ?? discard.error ?? latestError,
    isApproving: approve.isMutating,
    isDiscarding: discard.isMutating,
    proposal,
    refreshProposal,
  }
}

export type ManuscriptEditFlow = ReturnType<typeof useManuscriptEdits>
