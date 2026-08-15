import { useState } from 'react'
import {
  ArrowUpRightIcon as ArrowUpRight,
  CaretDownIcon as ChevronDown,
} from '@phosphor-icons/react'

export type OpenAlexStatus = 'matched' | 'unmatched' | 'ambiguous' | 'error' | 'skipped'

export interface OpenAlexWorkJson {
  id: string
  doi?: string | null
  title?: string | null
  year?: number | null
  abstract?: string | null
  citedByCount?: number | null
  landingPageUrl?: string | null
  matchMethod?: 'doi' | 'arxiv' | 'title'
  confidence?: 'high' | 'medium'
}

export interface EnrichedReference {
  id: string
  rawText?: string
  csl?: { title?: string | null; DOI?: string | null } | null
  openalexStatus?: OpenAlexStatus | null
  openalex?: OpenAlexWorkJson | null
  openalexError?: string | null
}

type Filter = 'all' | OpenAlexStatus

const FILTERS: { id: Filter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'matched', label: 'Matched' },
  { id: 'unmatched', label: 'Unmatched' },
  { id: 'ambiguous', label: 'Ambiguous' },
  { id: 'error', label: 'Errors' },
  { id: 'skipped', label: 'Skipped' },
]

const STATUS_STYLES: Record<OpenAlexStatus, string> = {
  matched: 'bg-sage/12 text-sage',
  unmatched: 'bg-coral/12 text-coral',
  ambiguous: 'bg-amber-500/10 text-amber-800',
  error: 'bg-red-500/10 text-red-800',
  skipped: 'bg-ink/6 text-ink/50',
}

function countsFor(references: EnrichedReference[]) {
  const counts = {
    all: references.length,
    matched: 0,
    unmatched: 0,
    ambiguous: 0,
    error: 0,
    skipped: 0,
  }
  for (const reference of references) {
    if (reference.openalexStatus) counts[reference.openalexStatus] += 1
  }
  return counts
}

function localTitle(reference: EnrichedReference) {
  return reference.csl?.title || reference.rawText?.split(/[.?]/)[0]?.trim() || reference.id
}

function formatCitations(count: number | null | undefined) {
  if (count == null) return null
  if (count >= 1000) return `${(count / 1000).toFixed(count >= 10000 ? 0 : 1)}k citations`
  return `${count} citation${count === 1 ? '' : 's'}`
}

function matchLabel(work: OpenAlexWorkJson) {
  const method = work.matchMethod === 'arxiv' ? 'arXiv' : work.matchMethod === 'doi' ? 'DOI' : 'title'
  return `${method} · ${work.confidence || 'medium'}`
}

function Abstract({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  const compact = text.length > 220
  return (
    <div className="mt-2">
      <p className="text-[13px] leading-5 text-ink/60">
        {open || !compact ? text : `${text.slice(0, 220).trimEnd()}…`}
      </p>
      {compact ? (
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="pressable mt-1.5 inline-flex items-center gap-1 text-xs font-medium text-ink/45 outline-none hover:text-ink focus-visible:ring-2 focus-visible:ring-coral/30"
        >
          {open ? 'Show less' : 'Show abstract'}
          <ChevronDown
            aria-hidden="true"
            className={`size-3.5 transition-transform duration-200 ease-[cubic-bezier(0.23,1,0.32,1)] ${open ? 'rotate-180' : ''}`}
          />
        </button>
      ) : null}
    </div>
  )
}

function ReferenceRow({ reference, index }: { reference: EnrichedReference; index: number }) {
  const status = reference.openalexStatus || 'skipped'
  const work = reference.openalex
  const href = work?.landingPageUrl || work?.id

  return (
    <article
      className="openalex-row border-t border-ink/8 px-4 py-3.5"
      style={{ animationDelay: `${Math.min(index, 8) * 35}ms` }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold leading-5 text-ink">
            {work?.title || localTitle(reference)}
          </p>
          {work?.title && localTitle(reference) !== work.title ? (
            <p className="mt-0.5 truncate text-xs text-ink/40">From paper: {localTitle(reference)}</p>
          ) : null}
        </div>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold capitalize ${STATUS_STYLES[status]}`}
        >
          {status}
        </span>
      </div>

      {work ? (
        <>
          <p className="mt-1.5 text-xs text-ink/45">
            {[work.year, formatCitations(work.citedByCount), matchLabel(work)]
              .filter(Boolean)
              .join(' · ')}
          </p>
          {work.abstract ? <Abstract text={work.abstract} /> : null}
          {href ? (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="pressable mt-2 inline-flex items-center gap-1 text-xs font-medium text-sage outline-none hover:text-sage/80 focus-visible:ring-2 focus-visible:ring-sage/30"
            >
              Open in OpenAlex
              <ArrowUpRight aria-hidden="true" className="size-3.5" />
            </a>
          ) : null}
        </>
      ) : (
        <p className="mt-1.5 text-xs leading-5 text-ink/45">
          {reference.openalexError || 'No OpenAlex record attached.'}
          {reference.openalexError?.includes('rate-limited')
            ? ' Try again in a minute.'
            : ''}
        </p>
      )}
    </article>
  )
}

export function OpenAlexResults({ references }: { references: EnrichedReference[] }) {
  const [filter, setFilter] = useState<Filter>('all')
  const counts = countsFor(references)
  const visible = references.filter((reference) => filter === 'all' || reference.openalexStatus === filter)

  return (
    <div className="openalex-panel border-t border-ink/10 bg-white/70">
      <div className="flex items-center justify-between gap-3 px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-[0.1em] text-ink/45">OpenAlex</p>
        <p className="text-xs tabular-nums text-ink/40">
          {counts.matched}/{counts.all} matched
        </p>
      </div>

      <div className="flex gap-1 overflow-x-auto px-3 pb-3">
        {FILTERS.filter((item) => item.id === 'all' || counts[item.id] > 0).map((item) => {
          const active = filter === item.id
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setFilter(item.id)}
              className={`pressable inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full px-3 text-xs font-medium outline-none transition-[background-color,color] duration-150 ease-[cubic-bezier(0.23,1,0.32,1)] focus-visible:ring-2 focus-visible:ring-coral/30 ${
                active ? 'bg-ink text-paper' : 'bg-ink/5 text-ink/55 hover:bg-ink/8 hover:text-ink'
              }`}
            >
              {item.label}
              <span className={active ? 'text-paper/60' : 'text-ink/35'}>{counts[item.id]}</span>
            </button>
          )
        })}
      </div>

      <div className="max-h-[28rem] overflow-auto [scrollbar-color:rgba(41,39,32,0.2)_transparent]">
        {visible.length ? (
          visible.map((reference, index) => (
            <ReferenceRow key={reference.id} reference={reference} index={index} />
          ))
        ) : (
          <p className="px-4 py-6 text-sm text-ink/45">Nothing in this group.</p>
        )}
      </div>
    </div>
  )
}
