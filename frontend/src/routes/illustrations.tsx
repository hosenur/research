import { useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { MultiFileDiff } from '@pierre/diffs/react'
import {
  ArrowDownIcon as ArrowDown,
  ArrowRightIcon as ArrowRight,
  ArrowsRightLeftIcon as Split,
  BookOpenIcon as BookOpen,
  CheckCircleIcon as CircleDot,
  CheckIcon as Check,
  CircleStackIcon as Database,
  CodeBracketIcon as Braces,
  DocumentIcon as FileJson,
  DocumentTextIcon as FileText,
  FingerPrintIcon as Fingerprint,
  MagnifyingGlassIcon as Search,
  MapPinIcon as MapPin,
  ShareIcon as GitMerge,
  ShieldCheckIcon as ShieldCheck,
  SparklesIcon as Sparkles,
} from '@heroicons/react/24/solid'

export const Route = createFileRoute('/illustrations')({
  component: IllustrationsPage,
})

type Status = 'implemented' | 'planned'
type PipelineStage = 'pdf' | 'tei' | 'paper-json' | 'openalex' | 'review'

const examplePaper = {
  title: 'Tracing Citations Through Research Pipelines',
  abstract:
    'This synthetic survey demonstrates how citation text becomes structured, source-linked data.',
  firstClaim: 'Learning long-range dependencies remains difficult in recurrent networks',
  secondClaim: 'Attention-based and encoder-decoder approaches address sequence modeling',
  missingClaim:
    'Self-attention can reduce the number of sequential operations required for sequence modeling.',
  references: [
    {
      label: '1',
      sourceId: 'b0',
      author: 'Bahdanau et al.',
      title: 'Neural machine translation by jointly learning to align and translate',
    },
    {
      label: '2',
      sourceId: 'b1',
      author: 'Cho et al.',
      title: 'Learning phrase representations using RNN encoder-decoder for statistical machine translation',
    },
    {
      label: '3',
      sourceId: 'b2',
      author: 'Hochreiter et al.',
      title: 'Gradient flow in recurrent nets: the difficulty of learning long-term dependencies',
    },
  ],
} as const

const firstCitationStart = examplePaper.firstClaim.length
const firstCitationEnd = firstCitationStart + '[3]'.length
const secondCitationStart =
  firstCitationEnd + '. '.length + examplePaper.secondClaim.length
const secondCitationEnd = secondCitationStart + '[1, 2]'.length
const firstSentenceEnd = firstCitationEnd + '.'.length
const secondSentenceStart = firstSentenceEnd + ' '.length
const secondSentenceEnd = secondCitationEnd + '.'.length

const beforeEnrichmentReference = {
  id: 'b0',
  rawText:
    'Dzmitry Bahdanau, Kyunghyun Cho, and Yoshua Bengio. Neural machine translation by jointly learning to align and translate. CoRR, abs/1409.0473, 2014.',
  csl: {
    id: 'b0',
    type: 'report',
    title: examplePaper.references[0].title,
    author: [
      { given: 'Dzmitry', family: 'Bahdanau' },
      { given: 'Kyunghyun', family: 'Cho' },
      { given: 'Yoshua', family: 'Bengio' },
    ],
    issued: { 'date-parts': [[2014]] },
    URL: 'https://arxiv.org/abs/1409.0473',
    archive: 'arXiv',
    archive_location: '1409.0473',
  },
  status: 'parsed',
  rawFields: {
    title: examplePaper.references[0].title,
    authors: [
      { given: 'Dzmitry', family: 'Bahdanau', literal: null },
      { given: 'Kyunghyun', family: 'Cho', literal: null },
      { given: 'Yoshua', family: 'Bengio', literal: null },
    ],
    date: '2014',
    yearLabel: '2014',
    identifiers: { arxiv: '1409.0473' },
  },
  warnings: [],
  openalex: null,
  openalexStatus: null,
  openalexError: null,
  source: {
    sourceId: 'b0',
    coordinates: [{ page: 1, x: 72.1, y: 630, width: 451.2, height: 16.2 }],
  },
} as const

const afterEnrichmentReference = {
  ...beforeEnrichmentReference,
  openalex: {
    id: 'https://openalex.org/W…',
    doi: null,
    title: examplePaper.references[0].title,
    year: 2014,
    abstract: 'Illustrative abstract reconstructed from the OpenAlex response.',
    citedByCount: 1234,
    landingPageUrl: 'https://openalex.org/W…',
    matchMethod: 'title',
    confidence: 'medium',
  },
  openalexStatus: 'matched',
  openalexError: null,
} as const

const pdfTextProjection = `${examplePaper.title}

Abstract
${examplePaper.abstract}

Introduction
${examplePaper.firstClaim}[3].
${examplePaper.secondClaim}[1, 2].

Citation review
${examplePaper.missingClaim}

References
${examplePaper.references
  .map(
    (reference) =>
      `[${reference.label}] ${reference.author} ${reference.title}.`,
  )
  .join('\n')}`

const teiProjection = `<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt>
        <title level="a" type="main">${examplePaper.title}</title>
      </titleStmt>
    </fileDesc>
    <profileDesc>
      <abstract><p>${examplePaper.abstract}</p></abstract>
    </profileDesc>
  </teiHeader>
  <text>
    <body>
      <div xml:id="section-introduction">
        <head>Introduction</head>
        <p xml:id="paragraph-introduction" coords="1,72.1,188.4,451.2,48.7">
          <s xml:id="sentence-introduction-1" coords="1,72.1,188.4,451.2,21.4">${examplePaper.firstClaim}<ref xml:id="citation-ref-1" type="bibr" target="#b2" coords="1,498.2,188.4,18.1,9.7">[3]</ref>.</s>
          <s xml:id="sentence-introduction-2" coords="1,72.1,215.7,451.2,21.4">${examplePaper.secondClaim}<ref xml:id="citation-ref-2a" type="bibr" target="#b0" coords="1,472.4,215.7,16.2,9.7">[1,</ref><ref xml:id="citation-ref-2b" type="bibr" target="#b1" coords="1,489.0,215.7,14.8,9.7">2]</ref>.</s>
        </p>
      </div>
      <div xml:id="section-review">
        <head>Citation review</head>
        <p xml:id="paragraph-review" coords="1,72.1,272.6,451.2,35.4">
          <s xml:id="sentence-review-1" coords="1,72.1,272.6,451.2,21.4">${examplePaper.missingClaim}</s>
        </p>
      </div>
    </body>
    <back>
      <div type="references">
        <listBibl>
${examplePaper.references
  .map(
    (reference) =>
      `          <biblStruct status="extracted" xml:id="${reference.sourceId}" coords="1,72.1,${610 + Number(reference.label) * 20}.0,451.2,16.2">
            <note type="raw_reference">[${reference.label}] ${reference.author} ${reference.title}.</note>
            <monogr><title level="m" type="main">${reference.title}</title></monogr>
          </biblStruct>`,
  )
  .join('\n')}
        </listBibl>
      </div>
    </back>
  </text>
</TEI>`

const paperJsonProjection = {
  title: examplePaper.title,
  abstract: examplePaper.abstract,
  authors: [],
  year: null,
  identifiers: {},
  citationStyle: 'numeric',
  citationStyleDetection: {
    family: 'numeric',
    syntaxes: ['square-bracket'],
    confidence: 'medium',
    cslCandidates: [
      {
        id: 'ieee',
        label: 'IEEE',
        score: 0.72,
        reason: 'Square-bracket citations and numbered references are IEEE-like.',
      },
      {
        id: 'vancouver',
        label: 'Vancouver',
        score: 0.52,
        reason: 'Some Vancouver variants also use bracketed numbers.',
      },
    ],
    needsConfirmation: true,
    evidence: { numericSquare: 2, referenceBracketNumbered: 3 },
    reasons: ['Numeric punctuation alone cannot uniquely identify a publisher style.'],
  },
  sections: [
    {
      id: 'section-1',
      title: 'Introduction',
      number: null,
      paragraphs: [
        {
          id: 'paragraph-1',
          nodes: [
            { type: 'text', text: examplePaper.firstClaim },
            {
              type: 'citation',
              id: 'paragraph-1-citation-1',
              rawText: '[3]',
              items: [
                {
                  sourceId: 'b2',
                  prefix: null,
                  suffix: null,
                  locator: null,
                  label: null,
                  suppressAuthor: false,
                  authorOnly: false,
                  resolutionMethod: 'bibliography-target',
                  confidence: 'high',
                },
              ],
              anchor: {
                paragraphId: 'paragraph-1',
                startOffset: firstCitationStart,
                endOffset: firstCitationEnd,
              },
              form: 'numeric',
              resolution: {
                status: 'resolved',
                confidence: 'high',
                methods: ['bibliography-target'],
                candidateSourceIds: [],
                unresolvedSourceIds: [],
              },
              unresolvedFragments: [],
              warnings: [],
              sourceSpans: [
                {
                  sourceId: 'citation-ref-1',
                  coordinates: [{ page: 1, x: 498.2, y: 188.4, width: 18.1, height: 9.7 }],
                },
              ],
            },
            { type: 'text', text: `. ${examplePaper.secondClaim}` },
            {
              type: 'citation',
              id: 'paragraph-1-citation-2',
              rawText: '[1, 2]',
              items: [
                {
                  sourceId: 'b0',
                  prefix: null,
                  suffix: null,
                  locator: null,
                  label: null,
                  suppressAuthor: false,
                  authorOnly: false,
                  resolutionMethod: 'bibliography-target',
                  confidence: 'high',
                },
                {
                  sourceId: 'b1',
                  prefix: null,
                  suffix: null,
                  locator: null,
                  label: null,
                  suppressAuthor: false,
                  authorOnly: false,
                  resolutionMethod: 'bibliography-target',
                  confidence: 'high',
                },
              ],
              anchor: {
                paragraphId: 'paragraph-1',
                startOffset: secondCitationStart,
                endOffset: secondCitationEnd,
              },
              form: 'numeric',
              resolution: {
                status: 'resolved',
                confidence: 'high',
                methods: ['bibliography-target'],
                candidateSourceIds: [],
                unresolvedSourceIds: [],
              },
              unresolvedFragments: [],
              warnings: [],
              sourceSpans: [
                {
                  sourceId: 'citation-ref-2a',
                  coordinates: [{ page: 1, x: 472.4, y: 215.7, width: 16.2, height: 9.7 }],
                },
                {
                  sourceId: 'citation-ref-2b',
                  coordinates: [{ page: 1, x: 489, y: 215.7, width: 14.8, height: 9.7 }],
                },
              ],
            },
            { type: 'text', text: '.' },
          ],
          sentences: [
            {
              id: 'paragraph-1-sentence-1',
              startOffset: 0,
              endOffset: firstSentenceEnd,
              source: {
                sourceId: 'sentence-introduction-1',
                coordinates: [{ page: 1, x: 72.1, y: 188.4, width: 451.2, height: 21.4 }],
              },
            },
            {
              id: 'paragraph-1-sentence-2',
              startOffset: secondSentenceStart,
              endOffset: secondSentenceEnd,
              source: {
                sourceId: 'sentence-introduction-2',
                coordinates: [{ page: 1, x: 72.1, y: 215.7, width: 451.2, height: 21.4 }],
              },
            },
          ],
          source: {
            sourceId: 'paragraph-introduction',
            coordinates: [{ page: 1, x: 72.1, y: 188.4, width: 451.2, height: 48.7 }],
          },
        },
      ],
      source: { sourceId: 'section-introduction', coordinates: [] },
    },
    {
      id: 'section-2',
      title: 'Citation review',
      number: null,
      paragraphs: [
        {
          id: 'paragraph-2',
          nodes: [{ type: 'text', text: examplePaper.missingClaim }],
          sentences: [
            {
              id: 'paragraph-2-sentence-1',
              startOffset: 0,
              endOffset: examplePaper.missingClaim.length,
              source: {
                sourceId: 'sentence-review-1',
                coordinates: [{ page: 1, x: 72.1, y: 272.6, width: 451.2, height: 21.4 }],
              },
            },
          ],
          source: {
            sourceId: 'paragraph-review',
            coordinates: [{ page: 1, x: 72.1, y: 272.6, width: 451.2, height: 35.4 }],
          },
        },
      ],
      source: { sourceId: 'section-review', coordinates: [] },
    },
  ],
  references: examplePaper.references.map((reference) => ({
    id: reference.sourceId,
    rawText: `${reference.author} ${reference.title}.`,
    csl: { id: reference.sourceId, type: 'article', title: reference.title },
    status: 'parsed',
    rawFields: {
      title: reference.title,
      label: reference.label,
    },
    warnings: [],
    openalex: null,
    openalexStatus: null,
    openalexError: null,
    source: {
      sourceId: reference.sourceId,
      coordinates: [
        {
          page: 1,
          x: 72.1,
          y: 610 + Number(reference.label) * 20,
          width: 451.2,
          height: 16.2,
        },
      ],
    },
  })),
  extraction: {
    provider: 'document-extraction',
    extractorVersion: '0.9.0',
    processedAt: '2026-08-14T10:30:00Z',
    durationMs: 4280,
    pdfSha256: 'f4c2…8a91',
    teiSha256: '72bd…44ef',
    teiArtifactId: 'f4c2e3d18a91b632-72bd901244ef16ac',
    requestOptions: {
      consolidateHeader: '0',
      consolidateCitations: '0',
      includeRawCitations: '1',
      segmentSentences: '1',
      generateIDs: '1',
      teiCoordinates: ['ref', 'biblStruct', 's', 'figure', 'formula'],
    },
    preflight: {
      pageCount: 1,
      selectableTextCharacters: 1248,
      sampledPages: 1,
      encrypted: false,
      ocrRecommended: false,
      warnings: [],
    },
    quality: {
      status: 'usable',
      bodyCharacters: secondSentenceEnd + examplePaper.missingClaim.length,
      sectionCount: 2,
      sentenceCount: 3,
      citationCount: 2,
      referenceCount: 3,
      parsedReferenceCount: 3,
      resolvedTargetRatio: 1,
      warnings: [],
    },
    ocrApplied: false,
    recoverySteps: [],
  },
  unresolvedReferenceIds: [],
  warnings: [],
}

const missingWorkReport = {
  claim: examplePaper.missingClaim,
  sectionTitle: 'Citation review',
  status: 'searched',
  suggestedWork: {
    title: 'Attention Is All You Need',
    authors: ['Ashish Vaswani', 'Noam Shazeer', 'Niki Parmar'],
    year: 2017,
    provider: 'OpenAlex',
    verdict: 'candidate',
    reason:
      'Directly analyzes the sequential-operation advantage of self-attention.',
  },
}

const citationFields = [
  { name: 'id', value: 'paragraph-1-citation-1', icon: Fingerprint, tone: 'coral' },
  { name: 'rawText', value: '[3]', icon: FileText, tone: 'ink' },
  { name: 'items[]', value: 'b2 · bibliography-target', icon: BookOpen, tone: 'sage' },
  { name: 'anchor', value: 'paragraph-1 · offsets', icon: MapPin, tone: 'coral' },
  { name: 'form', value: 'numeric', icon: Braces, tone: 'ink' },
  { name: 'resolution', value: 'resolved · high', icon: ShieldCheck, tone: 'sage' },
  { name: 'sourceSpans[]', value: 'TEI id · PDF box', icon: MapPin, tone: 'sage' },
] as const

const sourceFields = [
  ['identity', 'Stable internal source ID'],
  ['bibliographic', 'CSL title, authors, date, venue'],
  ['identifiers', 'DOI, OpenAlex ID, arXiv, PMID'],
  ['provenance', 'Which provider supplied each value'],
  ['quality', 'Match status, confidence, warnings'],
] as const

function StatusPill({ status }: { status: Status }) {
  const implemented = status === 'implemented'
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] ${
        implemented
          ? 'border-sage/20 bg-sage/10 text-sage'
          : 'border-coral/20 bg-coral/10 text-coral'
      }`}
    >
      {implemented ? <Check className="size-3" /> : <Sparkles className="size-3" />}
      {implemented ? 'Implemented' : 'Next'}
    </span>
  )
}

function FlowArrow({ planned = false }: { planned?: boolean }) {
  return (
    <div className="flex min-h-10 items-center justify-center" aria-hidden="true">
      <div
        className={`hidden h-px flex-1 sm:block ${
          planned
            ? 'border-t border-dashed border-coral/50'
            : 'bg-gradient-to-r from-ink/15 via-ink/35 to-ink/15'
        }`}
      />
      <span
        className={`grid size-8 shrink-0 place-items-center rounded-full border bg-paper shadow-sm ${
          planned ? 'border-dashed border-coral/45 text-coral' : 'border-ink/15 text-ink/55'
        }`}
      >
        <ArrowRight className="hidden size-4 sm:block" />
        <ArrowDown className="size-4 sm:hidden" />
      </span>
      <div
        className={`hidden h-px flex-1 sm:block ${
          planned
            ? 'border-t border-dashed border-coral/50'
            : 'bg-gradient-to-r from-ink/15 via-ink/35 to-ink/15'
        }`}
      />
    </div>
  )
}

function PipelineCard({
  stage,
  number,
  title,
  subtitle,
  icon: Icon,
  selected,
  onSelect,
}: {
  stage: PipelineStage
  number: string
  title: string
  subtitle: string
  icon: typeof FileText
  selected: boolean
  onSelect: (stage: PipelineStage) => void
}) {
  return (
    <button
      type="button"
      aria-controls="pipeline-structure"
      aria-pressed={selected}
      onClick={() => onSelect(stage)}
      className={`pressable relative min-w-0 rounded-2xl border p-4 text-left shadow-sm outline-none backdrop-blur transition-[background-color,border-color,box-shadow] duration-150 focus-visible:ring-2 focus-visible:ring-coral/50 ${
        selected
          ? 'border-coral/30 bg-white ring-4 ring-coral/[0.07]'
          : 'border-ink/10 bg-white/65'
      }`}
    >
      <div className="mb-5 flex items-start justify-between gap-3">
        <span
          className={`grid size-9 place-items-center rounded-xl ${
            selected ? 'bg-coral text-white' : 'bg-ink/[0.06] text-ink/65'
          }`}
        >
          <Icon className="size-4.5" />
        </span>
        <span className="flex items-center gap-1.5 font-mono text-[10px] font-semibold tracking-[0.16em] text-ink/30">
          {selected ? <CircleDot className="size-3 text-coral" /> : null}
          {number}
        </span>
      </div>
      <p className="font-display text-sm font-semibold tracking-[-0.02em]">{title}</p>
      <p className="mt-1 text-xs leading-5 text-ink/50">{subtitle}</p>
      <p className={`mt-3 font-mono text-[9px] uppercase tracking-[0.13em] ${selected ? 'text-coral' : 'text-ink/25'}`}>
        {selected ? 'Viewing structure' : 'Click to inspect'}
      </p>
    </button>
  )
}

function CodeLine({
  indent = 0,
  name,
  value,
  muted = false,
  inverse = false,
}: {
  indent?: number
  name?: string
  value: string
  muted?: boolean
  inverse?: boolean
}) {
  return (
    <div
      className={`grid grid-cols-[minmax(0,1fr)_auto] gap-3 py-1 font-mono text-[11px] leading-5 ${
        inverse
          ? muted ? 'text-paper/35' : 'text-paper/70'
          : muted ? 'text-ink/35' : 'text-ink/70'
      }`}
      style={{ paddingLeft: `${indent * 12}px` }}
    >
      <span className="min-w-0 truncate">
        {name ? <span className="text-coral">{name}</span> : null}
        {name ? <span className={inverse ? 'text-paper/25' : 'text-ink/30'}>: </span> : null}
        <span>{value}</span>
      </span>
    </div>
  )
}

function PaperPreview({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`mx-auto w-full max-w-md bg-[#fffefb] text-[#302e28] shadow-[0_14px_40px_rgba(41,39,32,0.13)] ${compact ? 'p-4 sm:p-5' : 'p-6 sm:p-8'}`}>
      <div className="border-b border-ink/10 pb-4 text-center">
        <p className={`${compact ? 'text-base' : 'text-xl'} font-semibold leading-tight`}>
          {examplePaper.title}
        </p>
        <p className="mt-2 text-[8px] tracking-wide text-ink/45">SYNTHETIC RESEARCH DOCUMENT · FOR PIPELINE ILLUSTRATION</p>
      </div>

      <div className={`mt-4 ${compact ? 'space-y-3' : 'grid gap-5 sm:grid-cols-[0.7fr_1.3fr]'}`}>
        <div>
          <p className="text-center font-serif text-[9px] font-bold uppercase tracking-wider">Abstract</p>
          <p className="mt-2 font-serif text-[8px] leading-[1.65] text-ink/65">
            {examplePaper.abstract}
          </p>
        </div>
        <div>
          <p className="font-serif text-[10px] font-bold">1. Introduction</p>
          <p className="mt-2 font-serif text-[8px] leading-[1.7] text-ink/65">
            {examplePaper.firstClaim}
            <mark className="mx-0.5 rounded bg-coral/15 px-1 py-0.5 font-sans font-semibold text-coral">[3]</mark>
            . {examplePaper.secondClaim}
            <mark className="mx-0.5 rounded bg-coral/15 px-1 py-0.5 font-sans font-semibold text-coral">[1, 2]</mark>
            .
          </p>
          {!compact ? (
            <>
              <p className="mt-3 font-serif text-[10px] font-bold">2. Citation review</p>
              <p className="mt-2 font-serif text-[8px] leading-[1.7] text-ink/65">
                {examplePaper.missingClaim}
              </p>
            </>
          ) : null}
        </div>
      </div>

      <div className="mt-5 border-t border-ink/10 pt-3">
        <p className="font-serif text-[9px] font-bold">References</p>
        {examplePaper.references.map((reference, index) => (
          <p key={reference.sourceId} className={`${index === 0 ? 'mt-1' : ''} font-serif text-[7px] leading-4 text-ink/50`}>
            <span className="font-bold text-coral">[{reference.label}]</span>{' '}
            {reference.author} {reference.title}.
          </p>
        ))}
      </div>
    </div>
  )
}

function XmlStructure() {
  return (
    <div className="overflow-hidden rounded-xl bg-[#282720] text-paper shadow-lg shadow-ink/5">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-paper/40">fulltext.tei.xml · complete illustrated sample</span>
        <Braces className="size-3.5 text-coral" />
      </div>
      <pre className="max-h-[620px] overflow-auto p-4 font-mono text-[10px] leading-6 text-paper/70 sm:p-5 sm:text-[11px]"><code>{teiProjection}</code></pre>
    </div>
  )
}

function StructureHeader({ label, title, detail }: { label: string; title: string; detail: string }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3 border-b border-ink/[0.07] pb-5">
      <div>
        <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-coral">{label}</p>
        <h3 className="mt-1 font-display text-xl font-semibold tracking-[-0.03em]">{title}</h3>
      </div>
      <p className="max-w-md text-xs leading-5 text-ink/45">{detail}</p>
    </div>
  )
}

function ExtractionStep({
  number,
  title,
  detail,
  optional = false,
}: {
  number: string
  title: string
  detail: string
  optional?: boolean
}) {
  return (
    <div className={`rounded-xl border p-3 ${optional ? 'border-dashed border-coral/25 bg-coral/[0.04]' : 'border-ink/[0.08] bg-white/65'}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[9px] font-semibold text-coral">{number}</span>
        {optional ? <span className="font-mono text-[8px] uppercase tracking-[0.12em] text-coral/70">conditional</span> : null}
      </div>
      <p className="mt-2 font-display text-sm font-semibold text-ink/75">{title}</p>
      <p className="mt-1 text-[11px] leading-4 text-ink/45">{detail}</p>
    </div>
  )
}

function TransformationDiff({
  title,
  detail,
  before,
  after,
  beforeName,
  afterName,
}: {
  title: string
  detail: string
  before: string | null
  after: string
  beforeName: string
  afterName: string
}) {
  return (
    <div className="mt-6 overflow-hidden rounded-2xl border border-ink/[0.09] bg-white shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-ink/[0.08] bg-paper/55 px-4 py-4 sm:px-5">
        <div>
          <p className="font-mono text-[9px] font-semibold uppercase tracking-[0.14em] text-coral">
            Data diff
          </p>
          <h4 className="mt-1 font-display text-sm font-semibold text-ink/80">{title}</h4>
        </div>
        <p className="max-w-lg text-xs leading-5 text-ink/45">{detail}</p>
      </div>
      <div className="max-h-[620px] overflow-auto bg-white">
        <MultiFileDiff
          oldFile={
            before === null
              ? null
              : { name: beforeName, contents: before }
          }
          newFile={{ name: afterName, contents: after }}
          options={{
            diffStyle: 'split',
            diffIndicators: 'bars',
            lineDiffType: 'word',
            overflow: 'scroll',
            themeType: 'light',
            theme: 'github-light',
            expandUnchanged: true,
            stickyHeader: true,
          }}
          disableWorkerPool
        />
      </div>
    </div>
  )
}

function PipelineStructure({ stage }: { stage: PipelineStage }) {
  if (stage === 'pdf') {
    return (
      <div>
        <StructureHeader
          label="01 · Input structure"
          title="A sample research PDF"
          detail="The rendered paper contains citation markers that are visible to the reader, but their relationships are not structured yet."
        />
        <div className="rounded-2xl bg-ink/[0.035] p-4 sm:p-7">
          <div className="mb-4 flex items-center justify-between text-[10px] text-ink/40">
            <span className="inline-flex items-center gap-2 font-mono"><FileText className="size-3.5" /> sample-paper.pdf</span>
            <span>1 illustrated page · citations highlighted</span>
          </div>
          <PaperPreview />
        </div>
        <div className="mt-4 flex items-start gap-3 rounded-xl border border-ink/[0.08] bg-paper/55 p-4">
          <CircleDot className="mt-0.5 size-3.5 shrink-0 text-coral" />
          <p className="text-xs leading-5 text-ink/50">
            This is the baseline artifact, so there is no earlier data state to diff. The first comparison begins after document extraction produces TEI.
          </p>
        </div>
      </div>
    )
  }

  if (stage === 'tei') {
    return (
      <div>
        <StructureHeader
          label="02 · Extraction structure"
          title="PDF → quality-gated TEI"
          detail="The boundary includes preflight, conditional OCR, evidence-rich extraction, recovery passes, immutable TEI storage, and an explicit quality report."
        />
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-6">
          <ExtractionStep number="01" title="Preflight" detail="Pages, encryption, and selectable text." />
          <ExtractionStep number="02" title="OCR" detail="Only for scanned or text-poor PDFs." optional />
          <ExtractionStep number="03" title="Full extraction" detail="Sentences, IDs, coordinates, raw refs." />
          <ExtractionStep number="04" title="Recovery" detail="Flavor or reference-only retry." optional />
          <ExtractionStep number="05" title="Quality gate" detail="Counts, target ratio, warnings." />
          <ExtractionStep number="06" title="Persist TEI" detail="Hash-addressed raw artifact." />
        </div>

        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div className="overflow-hidden rounded-2xl border border-ink/[0.08] bg-[#282720] text-paper">
            <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
              <span className="font-mono text-[10px] uppercase tracking-[0.13em] text-paper/40">Request · processFulltextDocument</span>
              <span className="rounded-md bg-sage/15 px-2 py-1 font-mono text-[9px] text-[#b9d3c1]">consolidation off</span>
            </div>
            <pre className="overflow-auto p-4 font-mono text-[10px] leading-5 text-paper/70"><code>{JSON.stringify({
              consolidateHeader: '0',
              consolidateCitations: '0',
              includeRawCitations: '1',
              segmentSentences: '1',
              generateIDs: '1',
              teiCoordinates: ['ref', 'biblStruct', 's', 'figure', 'formula'],
            }, null, 2)}</code></pre>
          </div>
          <div className="rounded-2xl border border-ink/[0.08] bg-paper/55 p-4">
            <p className="font-mono text-[10px] uppercase tracking-[0.13em] text-ink/35">Recovery policy</p>
            <div className="mt-3 space-y-2">
              {[
                ['Scanned PDF', 'OCR → retry full text'],
                ['Empty body', 'article/light-ref flavor'],
                ['Citations, no bibliography', 'processReferences → merge TEI'],
                ['HTTP 503 or timeout', 'bounded retry with backoff'],
              ].map(([condition, action]) => (
                <div key={condition} className="grid grid-cols-[minmax(0,0.8fr)_16px_minmax(0,1fr)] items-center gap-2 rounded-lg border border-ink/[0.06] bg-white/60 px-3 py-2 text-[11px]">
                  <span className="font-medium text-ink/65">{condition}</span>
                  <ArrowRight className="size-3 text-coral" />
                  <span className="text-ink/45">{action}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-4 grid items-center gap-4 lg:grid-cols-[1fr_54px_1.15fr]">
          <div className="rounded-2xl border border-ink/[0.08] bg-ink/[0.025] p-4">
            <p className="mb-4 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.12em] text-ink/40">
              <span>Div 1 · PDF input</span><FileText className="size-3.5" />
            </p>
            <PaperPreview compact />
          </div>
          <div className="flex flex-col items-center gap-2 text-coral" aria-hidden="true">
            <span className="rounded-full border border-coral/20 bg-coral/[0.07] px-2 py-1 font-mono text-[9px]">Extraction</span>
            <ArrowRight className="hidden size-4.5 lg:block" />
            <ArrowDown className="size-4.5 lg:hidden" />
          </div>
          <div className="rounded-2xl border border-ink/[0.08] bg-ink/[0.025] p-4">
            <p className="mb-4 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.12em] text-ink/40">
              <span>Div 2 · TEI output</span><Braces className="size-3.5" />
            </p>
            <XmlStructure />
          </div>
        </div>
        <TransformationDiff
          title="Rendered text becomes tagged TEI"
          detail="This is a cross-format transformation. Green lines are newly extracted structure; red lines are the plain-text projection it replaces."
          before={pdfTextProjection}
          after={teiProjection}
          beforeName="sample-paper.txt"
          afterName="fulltext.tei.xml"
        />
      </div>
    )
  }

  if (stage === 'paper-json') {
    return (
      <div>
        <StructureHeader
          label="03 · Application structure"
          title="TEI → Paper JSON"
          detail="The TEI is read in order. Inline ref elements become citation nodes, and bibliography xml:id values become their sourceId links."
        />
        <div className="grid items-center gap-4 lg:grid-cols-[1fr_52px_1fr]">
          <div className="rounded-2xl border border-ink/[0.08] bg-ink/[0.025] p-4">
            <p className="mb-4 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.12em] text-ink/40">
              <span>Input · TEI XML</span><Braces className="size-3.5" />
            </p>
            <XmlStructure />
          </div>
          <div className="flex flex-col items-center gap-2 text-coral" aria-hidden="true">
            <span className="rounded-full border border-coral/20 bg-coral/[0.07] px-2 py-1 font-mono text-[9px]">parse</span>
            <ArrowRight className="hidden size-4.5 lg:block" />
            <ArrowDown className="size-4.5 lg:hidden" />
          </div>
          <div className="overflow-hidden rounded-2xl bg-[#282720] text-paper">
            <div className="flex items-center justify-between border-b border-white/10 px-4 py-3 font-mono text-[10px] uppercase tracking-[0.13em] text-paper/40">
              <span>Output · paper.json · complete illustrated sample</span><FileJson className="size-3.5 text-coral" />
            </div>
            <pre className="max-h-[620px] overflow-auto p-5 font-mono text-[10px] leading-5 text-paper/70"><code>{JSON.stringify(paperJsonProjection, null, 2)}</code></pre>
          </div>
        </div>
        <TransformationDiff
          title="TEI becomes the application Paper model"
          detail="The diff makes the format boundary explicit: XML elements and targets are replaced by JSON sections, CitationNodes, offsets, and Reference objects."
          before={teiProjection}
          after={JSON.stringify(paperJsonProjection, null, 2)}
          beforeName="fulltext.tei.xml"
          afterName="paper.json"
        />
        <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ['Paragraph.sentences[]', 'Sentence IDs and half-open offsets support claim-level review.'],
            ['source / sourceSpans[]', 'Source IDs and PDF coordinates survive normalization.'],
            ['Paper.extraction', 'Version, hashes, options, OCR, recovery, and TEI artifact ID.'],
            ['extraction.quality', 'Usability, counts, resolved-target ratio, and visible warnings.'],
          ].map(([field, description]) => (
            <div key={field} className="rounded-xl border border-sage/15 bg-sage/[0.055] p-3">
              <p className="font-mono text-[10px] font-semibold text-sage">{field}</p>
              <p className="mt-2 text-[11px] leading-4 text-ink/50">{description}</p>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (stage === 'openalex') {
    return (
      <div>
        <StructureHeader
          label="04 · Enrichment structure"
          title="Paper.references[] → OpenAlex matches"
          detail="Every item in Paper.references is a Reference object. OpenAlex data is attached to that same object; it is not a CitationNode or a separate Source node."
        />
        <div className="mb-5 grid gap-2 sm:grid-cols-3">
          <div className="rounded-xl border border-ink/[0.08] bg-paper/60 p-3">
            <p className="font-mono text-[9px] uppercase tracking-[0.13em] text-ink/35">Containing path</p>
            <p className="mt-1 font-mono text-xs font-semibold text-ink/70">Paper.references[0]</p>
          </div>
          <div className="rounded-xl border border-sage/20 bg-sage/[0.07] p-3">
            <p className="font-mono text-[9px] uppercase tracking-[0.13em] text-sage">Object model</p>
            <p className="mt-1 font-display text-sm font-semibold text-ink/75">Reference</p>
          </div>
          <div className="rounded-xl border border-coral/15 bg-coral/[0.06] p-3">
            <p className="font-mono text-[9px] uppercase tracking-[0.13em] text-coral">Not this type</p>
            <p className="mt-1 text-xs font-medium text-ink/65">CitationNode · Canonical Source</p>
          </div>
        </div>

        <div className="mb-5 rounded-2xl border border-ink/[0.08] bg-paper/50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="font-mono text-[9px] uppercase tracking-[0.13em] text-ink/35">Collection being mapped</p>
              <p className="mt-1 text-xs text-ink/55">Three Reference objects · at most two OpenAlex requests at once</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {examplePaper.references.map((reference, index) => (
                <span key={reference.sourceId} className="rounded-lg border border-ink/[0.08] bg-white px-2.5 py-1.5 font-mono text-[10px] text-ink/60">
                  references[{index}] · {reference.sourceId}
                </span>
              ))}
            </div>
          </div>
        </div>

        <TransformationDiff
          title="The same Reference object before and after enrichment"
          detail="This is the most literal diff in the pipeline. Unchanged bibliographic fields remain visible while the new OpenAlex payload and match status are highlighted."
          before={JSON.stringify(beforeEnrichmentReference, null, 2)}
          after={JSON.stringify(afterEnrichmentReference, null, 2)}
          beforeName="reference.before.json"
          afterName="reference.enriched.json"
        />

        <div className="mt-4 grid gap-2 sm:grid-cols-3">
          <div className="rounded-xl border border-sage/15 bg-sage/[0.06] p-3">
            <p className="font-mono text-[9px] text-ink/35">openalex</p>
            <p className="mt-1 text-xs font-medium text-ink/65"><span className="text-ink/35">null</span> → OpenAlexWork object</p>
          </div>
          <div className="rounded-xl border border-sage/15 bg-sage/[0.06] p-3">
            <p className="font-mono text-[9px] text-ink/35">openalexStatus</p>
            <p className="mt-1 text-xs font-medium text-ink/65"><span className="text-ink/35">null</span> → matched</p>
          </div>
          <div className="rounded-xl border border-ink/[0.08] bg-paper/55 p-3">
            <p className="font-mono text-[9px] text-ink/35">All other Reference fields</p>
            <p className="mt-1 text-xs font-medium text-ink/65">Preserved unchanged</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div>
      <StructureHeader
        label="05 · Review structure"
        title="A missing-work finding"
        detail="The review layer keeps the original claim beside the suggested work and the reason it may support that claim."
      />
      <div className="grid gap-4 lg:grid-cols-[0.8fr_1.2fr]">
        <div className="rounded-2xl border border-ink/[0.08] bg-paper/60 p-5">
          <p className="font-mono text-[10px] uppercase tracking-[0.13em] text-ink/35">ClaimQuery</p>
          <blockquote className="mt-4 border-l-2 border-coral pl-4 font-serif text-sm leading-6 text-ink/70">
            “{examplePaper.missingClaim}”
          </blockquote>
          <div className="mt-4"><CodeLine name="sectionTitle" value='"Citation review"' /><CodeLine name="status" value='"searched"' /></div>
        </div>
        <div className="rounded-2xl border border-coral/20 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><p className="font-mono text-[10px] uppercase tracking-[0.13em] text-coral">Suggested missing work</p><h4 className="mt-2 font-display text-base font-semibold">Attention Is All You Need</h4><p className="mt-1 text-xs text-ink/45">Vaswani et al. · 2017 · OpenAlex</p></div>
            <span className="inline-flex items-center gap-1 rounded-full bg-sage/10 px-2.5 py-1 text-[10px] font-semibold text-sage"><ShieldCheck className="size-3" />Candidate</span>
          </div>
          <div className="mt-5 rounded-xl bg-paper/70 p-4"><p className="font-mono text-[9px] uppercase tracking-[0.13em] text-ink/35">Reason</p><p className="mt-2 text-xs leading-5 text-ink/60">Directly analyzes the sequential-operation advantage of self-attention.</p></div>
        </div>
      </div>
      <TransformationDiff
        title="Review creates a separate result artifact"
        detail="The Paper object is not rewritten here. The all-green file indicates that the reviewer produced a new MissingWorkReport from the claim query."
        before={null}
        after={JSON.stringify(missingWorkReport, null, 2)}
        beforeName=""
        afterName="missing-work-report.json"
      />
    </div>
  )
}

function IllustrationsPage() {
  const [selectedStage, setSelectedStage] = useState<PipelineStage>('pdf')

  return (
    <div className="w-full px-5 py-12 sm:px-8 sm:py-16 xl:px-10">
      <section className="mx-auto max-w-3xl text-center">
        <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-ink/10 bg-white/60 px-3 py-1.5 text-xs font-medium tracking-wide text-ink/60 shadow-sm backdrop-blur">
          <GitMerge aria-hidden="true" className="size-3.5" />
          Data transformation map
        </div>
        <h1 className="font-display text-4xl font-semibold tracking-[-0.045em] text-balance sm:text-5xl">
          From PDF fragments to traceable citations.
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-base leading-7 text-ink/55 sm:text-lg">
          A visual map of the structured paper data, what the citation schema now preserves,
          and the source model we should build next.
        </p>
        <div className="mt-7 flex flex-wrap items-center justify-center gap-4 text-xs text-ink/50">
          <span className="inline-flex items-center gap-2">
            <span className="h-px w-8 bg-ink/40" /> Working in the codebase
          </span>
          <span className="inline-flex items-center gap-2">
            <span className="w-8 border-t border-dashed border-coral/60" /> Planned transformation
          </span>
        </div>
      </section>

      <section className="mt-14 rounded-[28px] border border-ink/10 bg-white/35 p-4 shadow-sm sm:p-6">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3 px-1">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink/40">Whole pipeline</p>
            <h2 className="mt-1 font-display text-xl font-semibold tracking-[-0.03em]">One paper, five representations</h2>
          </div>
          <StatusPill status="implemented" />
        </div>

        <div className="grid items-stretch sm:grid-cols-[1fr_42px_1fr_42px_1fr_42px_1fr_42px_1fr]">
          <PipelineCard stage="pdf" number="01" title="PDF" subtitle="Human-readable research paper" icon={FileText} selected={selectedStage === 'pdf'} onSelect={setSelectedStage} />
          <FlowArrow />
          <PipelineCard stage="tei" number="02" title="TEI XML" subtitle="Document structure and bibliography targets" icon={Braces} selected={selectedStage === 'tei'} onSelect={setSelectedStage} />
          <FlowArrow />
          <PipelineCard stage="paper-json" number="03" title="Paper JSON" subtitle="Sections, citations, and references" icon={FileJson} selected={selectedStage === 'paper-json'} onSelect={setSelectedStage} />
          <FlowArrow />
          <PipelineCard stage="openalex" number="04" title="OpenAlex" subtitle="External identity and metadata match" icon={Search} selected={selectedStage === 'openalex'} onSelect={setSelectedStage} />
          <FlowArrow />
          <PipelineCard stage="review" number="05" title="Review" subtitle="Missing-work findings for the user" icon={ShieldCheck} selected={selectedStage === 'review'} onSelect={setSelectedStage} />
        </div>

        <div id="pipeline-structure" className="mt-6 rounded-2xl border border-ink/10 bg-white/65 p-4 shadow-sm sm:p-6">
          <PipelineStructure stage={selectedStage} />
        </div>
      </section>

      <section className="mt-20">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-coral">Transformation 01</p>
            <h2 className="mt-2 font-display text-3xl font-semibold tracking-[-0.04em]">TEI ref → citation occurrence</h2>
          </div>
          <StatusPill status="implemented" />
        </div>

        <div className="mt-7 grid items-center gap-4 lg:grid-cols-[0.82fr_64px_1.35fr]">
          <article className="overflow-hidden rounded-2xl border border-ink/10 bg-[#282720] text-paper shadow-lg shadow-ink/5">
            <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
              <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-paper/45">TEI XML</span>
              <span className="flex gap-1.5" aria-hidden="true">
                <span className="size-1.5 rounded-full bg-coral" />
                <span className="size-1.5 rounded-full bg-paper/25" />
              </span>
            </div>
            <pre className="overflow-x-auto p-5 font-mono text-[12px] leading-7 text-paper/75"><code><span className="text-coral">&lt;ref</span>{'\n'}  <span className="text-paper/45">xml:id</span>=<span className="text-[#a9c5b1]">&quot;citation-ref-1&quot;</span>{'\n'}  <span className="text-paper/45">type</span>=<span className="text-[#a9c5b1]">&quot;bibr&quot;</span>{'\n'}  <span className="text-paper/45">target</span>=<span className="text-[#a9c5b1]">&quot;#b2&quot;</span>{'\n'}  <span className="text-paper/45">coords</span>=<span className="text-[#a9c5b1]">&quot;1,498.2,188.4,18.1,9.7&quot;</span><span className="text-coral">&gt;</span>{'\n'}  [3]{'\n'}<span className="text-coral">&lt;/ref&gt;</span></code></pre>
            <div className="grid grid-cols-2 border-t border-white/10 text-[11px]">
              <div className="border-r border-white/10 px-4 py-3 text-paper/40">Visible text</div>
              <div className="px-4 py-3 text-[#a9c5b1]">Bibliography target</div>
            </div>
          </article>

          <div className="flex flex-col items-center gap-2 text-center text-[10px] font-semibold uppercase tracking-[0.12em] text-ink/35">
            <span className="rounded-full border border-ink/10 bg-white/60 px-2 py-1">parse</span>
            <FlowArrow />
            <span>enrich</span>
          </div>

          <article className="rounded-2xl border border-ink/10 bg-white/70 p-5 shadow-sm backdrop-blur sm:p-6">
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <p className="font-mono text-[10px] uppercase tracking-[0.15em] text-ink/35">Canonical output</p>
                <h3 className="mt-1 font-display text-lg font-semibold">CitationNode</h3>
              </div>
              <span className="rounded-lg bg-sage/10 px-2 py-1 font-mono text-[10px] text-sage">paragraph-1-citation-1</span>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {citationFields.map(({ name, value, icon: Icon, tone }) => (
                <div key={name} className="flex min-w-0 items-center gap-3 rounded-xl border border-ink/[0.08] bg-paper/55 p-3">
                  <span
                    className={`grid size-8 shrink-0 place-items-center rounded-lg ${
                      tone === 'coral'
                        ? 'bg-coral/10 text-coral'
                        : tone === 'sage'
                          ? 'bg-sage/10 text-sage'
                          : 'bg-ink/[0.06] text-ink/55'
                    }`}
                  >
                    <Icon className="size-4" />
                  </span>
                  <span className="min-w-0">
                    <span className="block font-mono text-[10px] text-ink/40">{name}</span>
                    <span className="block truncate text-xs font-medium text-ink/75">{value}</span>
                  </span>
                </div>
              ))}
            </div>
          </article>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-4">
          {[
            ['referenceIds[]', 'items[]', 'One cluster can carry source-specific locators and matching evidence.'],
            ['implicit position', 'anchor', 'The citation points back to exact paragraph offsets.'],
            ['implicit match', 'resolution', 'Status, method, confidence, and candidates become inspectable.'],
            ['anonymous node', 'stable id', 'Every occurrence can be selected, edited, and audited.'],
          ].map(([from, to, detail]) => (
            <div key={to} className="rounded-xl border border-ink/[0.08] bg-white/45 p-4">
              <div className="flex items-center gap-2 font-mono text-[11px]">
                <span className="text-ink/35 line-through decoration-ink/20">{from}</span>
                <ArrowRight className="size-3 text-coral" />
                <span className="font-semibold text-coral">{to}</span>
              </div>
              <p className="mt-3 text-xs leading-5 text-ink/50">{detail}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mt-20">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-coral">Transformation 02</p>
            <h2 className="mt-2 font-display text-3xl font-semibold tracking-[-0.04em]">Two source shapes → one source record</h2>
          </div>
          <StatusPill status="planned" />
        </div>

        <div className="mt-7 overflow-hidden rounded-[28px] border border-ink/10 bg-white/40 p-5 shadow-sm sm:p-7">
          <div className="grid items-center gap-5 lg:grid-cols-[1fr_100px_1.15fr]">
            <div className="grid gap-3">
              <article className="rounded-2xl border border-ink/10 bg-white/75 p-4 shadow-sm">
                <div className="flex items-center gap-3">
                  <span className="grid size-9 place-items-center rounded-xl bg-ink/[0.06] text-ink/60"><BookOpen className="size-4" /></span>
                  <div>
                    <p className="font-display text-sm font-semibold">Parsed Reference</p>
                    <p className="text-[11px] text-ink/40">Structured reference + CSL</p>
                  </div>
                </div>
                <div className="mt-4 border-t border-ink/[0.07] pt-3">
                  <CodeLine name="id" value='"b0"' />
                  <CodeLine name="rawText" value='"Bahdanau et al…"' />
                  <CodeLine name="csl" value="{ title, author, DOI }" />
                  <CodeLine name="status" value='"parsed"' />
                </div>
              </article>

              <div className="flex items-center gap-3 px-5 text-ink/25" aria-hidden="true">
                <div className="h-px flex-1 border-t border-dashed border-ink/20" />
                <CircleDot className="size-3.5" />
                <div className="h-px flex-1 border-t border-dashed border-ink/20" />
              </div>

              <article className="rounded-2xl border border-ink/10 bg-white/75 p-4 shadow-sm">
                <div className="flex items-center gap-3">
                  <span className="grid size-9 place-items-center rounded-xl bg-sage/10 text-sage"><Database className="size-4" /></span>
                  <div>
                    <p className="font-display text-sm font-semibold">OpenAlex Work</p>
                    <p className="text-[11px] text-ink/40">External enrichment</p>
                  </div>
                </div>
                <div className="mt-4 border-t border-ink/[0.07] pt-3">
                  <CodeLine name="id" value='"W…"' />
                  <CodeLine name="matchMethod" value='"title"' />
                  <CodeLine name="citedByCount" value="<number>" />
                  <CodeLine name="confidence" value='"medium"' />
                </div>
              </article>
            </div>

            <div className="flex flex-col items-center gap-3 text-coral" aria-hidden="true">
              <div className="hidden h-24 border-l border-dashed border-coral/35 lg:block" />
              <span className="grid size-11 place-items-center rounded-full border border-dashed border-coral/50 bg-paper shadow-sm"><GitMerge className="size-4.5" /></span>
              <span className="text-[10px] font-semibold uppercase tracking-[0.14em]">normalize</span>
              <ArrowRight className="hidden size-4.5 lg:block" />
              <ArrowDown className="size-4.5 lg:hidden" />
              <div className="hidden h-24 border-l border-dashed border-coral/35 lg:block" />
            </div>

            <article className="rounded-2xl border border-coral/25 bg-[#fffaf6] p-5 shadow-lg shadow-coral/5 sm:p-6">
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-center gap-3">
                  <span className="grid size-10 place-items-center rounded-xl bg-coral text-white shadow-sm"><Sparkles className="size-4.5" /></span>
                  <div>
                    <p className="font-display text-lg font-semibold">Canonical Source</p>
                    <p className="text-xs text-ink/45">The next stable contract</p>
                  </div>
                </div>
                <span className="rounded-md border border-coral/15 bg-coral/[0.07] px-2 py-1 font-mono text-[10px] text-coral">source-v1</span>
              </div>

              <div className="mt-6 space-y-2">
                {sourceFields.map(([name, description], index) => (
                  <div key={name} className="group flex items-center gap-3 rounded-xl border border-coral/10 bg-white/70 p-3">
                    <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-coral/[0.08] font-mono text-[10px] font-semibold text-coral">
                      {String(index + 1).padStart(2, '0')}
                    </span>
                    <span className="min-w-0">
                      <span className="block font-mono text-[10px] font-semibold text-ink/70">{name}</span>
                      <span className="block text-[11px] leading-4 text-ink/45">{description}</span>
                    </span>
                  </div>
                ))}
              </div>
            </article>
          </div>
        </div>
      </section>

      <section className="mt-20 pb-8">
        <div className="rounded-[28px] bg-ink p-6 text-paper shadow-xl shadow-ink/10 sm:p-8">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-paper/35">Resulting relationship</p>
              <h2 className="mt-2 max-w-2xl font-display text-2xl font-semibold tracking-[-0.035em] sm:text-3xl">
                Occurrences describe where a citation appears. Sources describe what it points to.
              </h2>
            </div>
            <Split className="size-6 text-coral" />
          </div>

          <div className="mt-8 grid items-center gap-3 md:grid-cols-[1fr_44px_1fr_44px_1fr]">
            <div className="rounded-2xl border border-white/10 bg-white/[0.055] p-4">
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-paper/35">Manuscript</span>
              <p className="mt-2 font-display font-semibold">Claim text</p>
              <p className="mt-1 text-xs leading-5 text-paper/45">The sentence a reader sees.</p>
            </div>
            <div className="flex justify-center text-paper/25"><ArrowRight className="hidden size-4 md:block" /><ArrowDown className="size-4 md:hidden" /></div>
            <div className="rounded-2xl border border-coral/25 bg-coral/10 p-4">
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-coral">Occurrence</span>
              <p className="mt-2 font-display font-semibold">CitationNode</p>
              <p className="mt-1 text-xs leading-5 text-paper/45">Anchor, locator, form, and resolution.</p>
            </div>
            <div className="flex justify-center text-paper/25"><ArrowRight className="hidden size-4 md:block" /><ArrowDown className="size-4 md:hidden" /></div>
            <div className="rounded-2xl border border-sage/30 bg-sage/15 p-4">
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-[#9ec1aa]">Identity</span>
              <p className="mt-2 font-display font-semibold">Canonical Source</p>
              <p className="mt-1 text-xs leading-5 text-paper/45">Metadata, identifiers, provenance, quality.</p>
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
