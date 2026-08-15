export interface ManuscriptSource {
  title: string
  url?: string | null
}

export interface PaperAgentSelectionContext {
  kind: 'missing' | 'existing' | 'reference'
  label?: string
  findingId?: string
  candidateId?: string
  referenceId?: string
  citationId?: string
  paragraphId?: string
  text?: string
  classification?: 'supported' | 'weak' | 'contradicted' | 'unverifiable'
}

export interface ManuscriptSelection {
  paragraphId: string
  startOffset?: number
  endOffset?: number
  text?: string
  source?: ManuscriptSource
  context?: PaperAgentSelectionContext
}

interface MissingReferenceCandidate {
  id: string
  decision: 'pending' | 'accepted' | 'rejected'
  supportsClaim?: boolean | null
  work: {
    title: string
    landingPageUrl?: string | null
    doi?: string | null
    arxivId?: string | null
  }
}

export function preferredMissingReferenceCandidate(
  candidates: readonly MissingReferenceCandidate[],
) {
  return (
    candidates.find((candidate) => candidate.supportsClaim === true) ??
    candidates.find(
      (candidate) =>
        candidate.decision !== 'rejected' && candidate.supportsClaim !== false,
    ) ??
    candidates[0]
  )
}

function doiUrl(doi?: string | null) {
  if (!doi) return null
  return doi.startsWith('http') ? doi : `https://doi.org/${doi}`
}

export function missingReferenceSource(
  candidates: readonly MissingReferenceCandidate[],
): ManuscriptSource | undefined {
  const suggestedSource = preferredMissingReferenceCandidate(candidates)
  if (!suggestedSource) return undefined
  return {
    title: suggestedSource.work.title,
    url:
      suggestedSource.work.landingPageUrl ||
      doiUrl(suggestedSource.work.doi) ||
      (suggestedSource.work.arxivId
        ? `https://arxiv.org/abs/${suggestedSource.work.arxivId}`
        : null),
  }
}
