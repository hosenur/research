export interface OpenAlexWorkJson {
  id: string
  doi?: string | null
  title?: string | null
  year?: number | null
  abstract?: string | null
  citedByCount?: number | null
  landingPageUrl?: string | null
  matchMethod: 'doi' | 'arxiv' | 'title' | 'search'
  confidence: 'high' | 'medium'
}

export interface PaperReferenceJson {
  id: string
  rawText?: string | null
  csl?: {
    title?: string | null
    DOI?: string | null
  } | null
  openalex?: OpenAlexWorkJson | null
  openalexStatus?: 'matched' | 'unmatched' | 'error' | 'skipped' | null
  openalexError?: string | null
  [key: string]: unknown
}

export interface PaperTextNodeJson {
  type: 'text'
  text: string
}

export interface PaperCitationNodeJson {
  type: 'citation'
  id?: string | null
  rawText: string
  items: Array<{
    sourceId: string
    confidence: 'high' | 'medium' | 'low'
  }>
  resolution: {
    status: 'resolved' | 'partial' | 'ambiguous' | 'unresolved'
    confidence: 'high' | 'medium' | 'low'
  }
  warnings?: string[]
}

export interface PaperParagraphJson {
  id: string
  nodes: Array<PaperTextNodeJson | PaperCitationNodeJson>
  sentences?: Array<{
    id: string
    startOffset: number
    endOffset: number
  }>
}

export interface PaperSectionJson {
  id: string
  title: string
  number?: string | null
  paragraphs: PaperParagraphJson[]
}

export interface PaperJson {
  title: string
  abstract?: string | null
  authors?: Array<{ given?: string | null; family?: string | null; literal?: string | null }>
  year?: number | null
  sections: PaperSectionJson[]
  references: PaperReferenceJson[]
  unresolvedReferenceIds?: string[]
  warnings?: string[]
  citationStyleDetection?: {
    family: string
    confidence: 'high' | 'medium' | 'low'
    needsConfirmation: boolean
  } | null
  extraction?: {
    durationMs: number
    preflight: { pageCount?: number | null; ocrRecommended: boolean }
    quality: {
      status: 'usable' | 'warning' | 'unusable'
      bodyCharacters: number
      sectionCount: number
      sentenceCount: number
      citationCount: number
      referenceCount: number
      parsedReferenceCount: number
      resolvedTargetRatio: number
      warnings: string[]
    }
  } | null
  [key: string]: unknown
}

export interface PaperDocumentJson {
  id: string
  revision: number
  paper: PaperJson
}

export interface PaperLifecycleJson {
  id: string
  filename: string
  status: 'uploaded' | 'parsing' | 'ready' | 'failed'
  revision: number
  manuscriptRevision: number
  paper?: PaperJson | null
  error?: string | null
  sourceUrl: string
  retrievalMode: 'unavailable' | 'provisional' | 'authoritative'
}
