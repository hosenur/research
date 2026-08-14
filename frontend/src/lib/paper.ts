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

export interface PaperJson {
  title: string
  abstract?: string | null
  sections: unknown[]
  references: PaperReferenceJson[]
  unresolvedReferenceIds?: string[]
  warnings?: string[]
  [key: string]: unknown
}

export interface PaperDocumentJson {
  id: string
  revision: number
  paper: PaperJson
}
