import { createFileRoute } from '@tanstack/react-router'
import {
  ArrowDownIcon,
  ArrowsInIcon as ArrowsPointingInIcon,
  CheckCircleIcon,
  CloudArrowDownIcon,
  CodeBlockIcon as CodeBracketSquareIcon,
  CubeTransparentIcon,
  DatabaseIcon as CircleStackIcon,
  FileMagnifyingGlassIcon as DocumentMagnifyingGlassIcon,
  FlaskIcon as BeakerIcon,
  ListIcon as QueueListIcon,
  ShareNetworkIcon as ShareIcon,
  WarningIcon as ExclamationTriangleIcon,
} from '@phosphor-icons/react'

import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
} from '@/components/ui/card'
import { UiProvider } from '@/components/ui/UiProvider'

export const Route = createFileRoute('/illustrations')({
  component: IllustrationsPage,
})

type ArchitectureStrength = 'Strong' | 'Worth exploring'

type ArchitectureCandidate = {
  id: string
  number: string
  title: string
  strength: ArchitectureStrength
  status?: 'implemented'
  category: 'in-process' | 'local-substitutable' | 'ports & adapters'
  icon: typeof DocumentMagnifyingGlassIcon
  files: readonly string[]
  problem: string
  solution: string
  wins: readonly string[]
  deletionTest: string
  beforeLabel: string
  before: readonly string[]
  callers: readonly string[]
  deepModule: string
  implementation: readonly string[]
  foundations: readonly string[]
}

const architectureCandidates: readonly ArchitectureCandidate[] = [
  {
    id: 'citation-source-fulfillment',
    number: '01',
    title: 'Collapse Citation Source fulfillment',
    strength: 'Strong',
    status: 'implemented',
    category: 'in-process',
    icon: DocumentMagnifyingGlassIcon,
    files: [
      'app/services/source_search.py:71–282',
      'app/workers/source_search.py:31–100',
      'app/repositories/citation_audits.py:373–545',
      'app/database/models.py:268–287',
      'alembic/versions/20260814_11_claim_search_identity.py',
    ],
    problem:
      'Citation Source state crosses five modules. Cache lookup uses claim hash plus version, but persistence makes claim hash alone unique, so a version bump can attempt a duplicate insert.',
    solution:
      'Deepen one Citation Source fulfillment module that owns a finding from queued through verified candidates; leave BullMQ as the adapter.',
    wins: [
      'locality: state transitions concentrate',
      'leverage: worker learns one interface',
      'One surface for retry and resume',
      'Delete shallow verification module',
    ],
    deletionTest:
      'Deleting SourceSupportVerifier moves its complete implementation into its sole caller. Absorb it. Deleting the proposed deep module would spread the full workflow back across the worker and persistence modules.',
    beforeLabel: 'State leaks into the worker',
    before: [
      'BullMQ adapter',
      'status + Paper SQL',
      'versioned cache SQL',
      'provider search + ranking',
      'support verification + save',
    ],
    callers: ['BullMQ adapter'],
    deepModule: 'Citation Source fulfillment',
    implementation: ['load + version', 'search + rank', 'verify support', 'commit state'],
    foundations: ['persistence', 'provider adapters', 'model adapter'],
  },
  {
    id: 'citation-audit-execution',
    number: '02',
    title: 'Deepen Citation Audit execution',
    strength: 'Strong',
    category: 'local-substitutable',
    icon: BeakerIcon,
    files: [
      'app/routers/papers.py:311–398',
      'app/workers/citation_audit.py:31–175',
      'app/services/citation_audit.py:176–534',
      'app/repositories/citation_audits.py:38–279',
      'app/database/models.py:96–197',
    ],
    problem:
      'The Citation Audit interface exposes lifecycle ordering. Worker failure records error text without a failed status, while polling prefers persisted running state over the failed job.',
    solution:
      'Put creation, rerun, two-lane execution, resume, completion, and Citation Source handoff inside one deep Citation Audit module.',
    wins: [
      'locality: one lifecycle owner',
      'leverage: every adapter agrees',
      'Interface hides transition order',
      'Tests hit resumability directly',
    ],
    deletionTest:
      'Persistence and model analysis both concentrate real complexity and should remain internal. The shallow part is the workflow interface that callers currently reconstruct from many operations.',
    beforeLabel: 'Callers carry the state machine',
    before: [
      'HTTP: create + reset + enqueue',
      'BullMQ: resume + two lanes',
      'analyzer: discover + verify',
      'persistence: transition methods',
      'Paper Chat: direct audit SQL',
    ],
    callers: ['HTTP adapter', 'BullMQ adapter', 'Paper Chat adapter'],
    deepModule: 'Citation Audit',
    implementation: ['batching', 'two lanes', 'resume rules', 'terminal state'],
    foundations: ['model analyzer', 'persistence', 'source handoff'],
  },
  {
    id: 'paper-job-control',
    number: '03',
    title: 'Collapse Paper job control',
    strength: 'Strong',
    category: 'in-process',
    icon: QueueListIcon,
    files: [
      'app/routers/papers.py:118–185',
      'app/routers/papers.py:219–308',
      'app/routers/papers.py:311–402',
      'app/dependencies.py:53–69',
      'app/workers/main.py:3–10',
    ],
    problem:
      'Three route paths know BullMQ job identity, retry policy, state mapping, progress defaults, retention, and rerun rules; the HTTP adapter also imports a worker function.',
    solution:
      'Deepen a concrete BullMQ-backed Paper job control module around stage identity, idempotent enqueueing, policy, and status projection. Do not invent a second queue adapter.',
    wins: [
      'locality: queue rules concentrate',
      'leverage: every job family',
      'Routes return domain state',
      'Tests stop assembling BullMQ',
    ],
    deletionTest:
      'The current queue getters and job-ID helpers are shallow: deleting them only inlines trivial construction. A deep Paper job control module would make deletion spread policy across every job family.',
    beforeLabel: 'Repeated queue knowledge',
    before: [
      'Paper index ID + options',
      'OpenAlex ID + retries',
      'Citation Audit rerun rules',
      'aggregate status mapping',
      'downstream enqueueing',
    ],
    callers: ['parse route', 'job routes', 'workers'],
    deepModule: 'Paper job control',
    implementation: ['stage identity', 'enqueue rules', 'retry policy', 'status projection'],
    foundations: ['concrete BullMQ implementation'],
  },
  {
    id: 'scholarly-provider-seam',
    number: '04',
    title: 'Complete the Scholarly Work provider seam',
    strength: 'Worth exploring',
    category: 'ports & adapters',
    icon: CloudArrowDownIcon,
    files: [
      'app/repositories/openalex.py:45–198',
      'app/repositories/semantic_scholar.py:25–93',
      'app/services/source_search.py:62–120',
      'app/repositories/scholarly_works.py:222–370',
      'app/services/openalex.py:30–107',
      'app/services/missing_works.py:180–238',
    ],
    problem:
      'The caller knows provider-specific methods, errors, and payloads. DOI, arXiv, title, and abstract normalization are duplicated and the implementations do not agree.',
    solution:
      'Make the existing OpenAlex and Semantic Scholar adapters meet at one normalized Scholarly Work seam, with canonical identity and cache handoff inside the deep module.',
    wins: [
      'Two adapters: seam is real',
      'locality: identity rules concentrate',
      'leverage: discovery and enrichment',
      'Adapter interface tests align',
    ],
    deletionTest:
      'Both provider modules hide transport retries and caching, so keep them as adapters. The missing depth is above them, where every provider-aware caller currently changes.',
    beforeLabel: 'Two adapters, no shared seam',
    before: [
      'caller branches by provider',
      'OpenAlex tuple + error',
      'Semantic Scholar dict + error',
      'provider-name parser switch',
      'canonical store',
    ],
    callers: ['Citation Source', 'Missing Work', 'OpenAlex enrichment'],
    deepModule: 'Scholarly Work',
    implementation: ['normalize identity', 'canonical work', 'cache handoff', 'provider result'],
    foundations: ['OpenAlex adapter', 'Semantic Scholar adapter'],
  },
  {
    id: 'paper-content-projections',
    number: '05',
    title: 'Deepen Paper content projections',
    strength: 'Worth exploring',
    category: 'in-process',
    icon: CodeBracketSquareIcon,
    files: [
      'app/services/citation_audit.py:206–311, 567–588',
      'app/services/missing_works.py:50–110, 135–148',
      'app/services/paper_index.py:15, 32–45',
      'app/services/paper_chat.py:184–240, 267–299',
      'app/schemas/paper.py:179–253, 323–348',
    ],
    problem:
      'Citation Audit, indexing, Missing Work, and Paper Chat independently traverse Paper nodes; indexing even imports its paragraph projection from Citation Audit.',
    solution:
      'Deepen one Paper content projection module for structural invariants, while keeping lossless, search-oriented, and model-oriented representations explicit.',
    wins: [
      'locality: traversal rules concentrate',
      'leverage: four domain callers',
      'Offsets stay explicitly lossless',
      'Tests verify projection invariants',
    ],
    deletionTest:
      'Deleting each current helper duplicates traversal into its caller. The parallel implementations show useful depth, but their differing semantics make this a careful consolidation rather than a mechanical merge.',
    beforeLabel: 'Four independent traversals',
    before: [
      'Citation Audit: lossless text',
      'Paper index: audit helper',
      'Missing Work: normalized text',
      'Paper Chat: citation counts',
    ],
    callers: ['Citation Audit', 'Paper index', 'Missing Work', 'Paper Chat'],
    deepModule: 'Paper content projections',
    implementation: ['lossless text', 'search text', 'model context', 'citation links'],
    foundations: ['Paper JSON'],
  },
]

function StrengthBadge({ strength }: { strength: ArchitectureStrength }) {
  return (
    <Badge intent={strength === 'Strong' ? 'success' : 'warning'}>
      {strength === 'Strong' ? <CheckCircleIcon data-slot="icon" /> : null}
      {strength}
    </Badge>
  )
}

function BeforeDiagram({
  label,
  nodes,
}: {
  label: string
  nodes: readonly string[]
}) {
  return (
    <figure className="rounded-2xl border border-red/15 bg-red-tint/45 p-4 sm:p-5">
      <figcaption className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-red">
        <ExclamationTriangleIcon className="size-4" />
        Before · {label}
      </figcaption>
      <ol className="mt-5 grid gap-2">
        {nodes.map((node, index) => (
          <li key={node}>
            <div className="flex items-center gap-3 rounded-xl border border-red/15 bg-white px-3 py-2.5 text-xs text-ink-2 shadow-xs">
              <span className="grid size-6 shrink-0 place-items-center rounded-md bg-red-tint font-mono text-[9px] font-semibold text-red">
                {String(index + 1).padStart(2, '0')}
              </span>
              <span>{node}</span>
            </div>
            {index < nodes.length - 1 ? (
              <div className="flex h-3 justify-center text-red/45" aria-hidden="true">
                <ArrowDownIcon className="size-3" />
              </div>
            ) : null}
          </li>
        ))}
      </ol>
    </figure>
  )
}

function AfterDiagram({ candidate }: { candidate: ArchitectureCandidate }) {
  return (
    <figure className="rounded-2xl border border-green/20 bg-green-tint/40 p-4 sm:p-5">
      <figcaption className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-green">
        <ArrowsPointingInIcon className="size-4" />
        After · one deep module
      </figcaption>

      <div className="mt-5 grid grid-cols-2 gap-1.5 sm:grid-cols-3">
        {candidate.callers.map((caller) => (
          <span
            key={caller}
            className="rounded-lg border border-dashed border-ink/15 bg-white/70 px-2 py-2 text-center text-[10px] font-medium text-ink-2"
          >
            {caller}
          </span>
        ))}
      </div>

      <div className="flex h-6 justify-center text-green/55" aria-hidden="true">
        <ArrowDownIcon className="size-4" />
      </div>

      <div className="rounded-2xl border-2 border-green/65 bg-ink p-4 text-paper shadow-lg shadow-ink/10">
        <p className="text-[9px] font-semibold uppercase tracking-[0.17em] text-[#9ec1aa]">
          Deep module
        </p>
        <h3 className="mt-1 font-display text-base font-semibold">
          {candidate.deepModule}
        </h3>
        <div className="mt-4 grid grid-cols-2 gap-1.5">
          {candidate.implementation.map((item) => (
            <span
              key={item}
              className="rounded-lg border border-white/10 bg-white/[0.055] px-2 py-2 text-center text-[10px] text-paper/55"
            >
              {item}
            </span>
          ))}
        </div>
      </div>

      <div className="flex h-6 justify-center text-green/55" aria-hidden="true">
        <ArrowDownIcon className="size-4" />
      </div>

      <div className="flex flex-wrap justify-center gap-1.5">
        {candidate.foundations.map((foundation) => (
          <span
            key={foundation}
            className="rounded-lg border border-ink/10 bg-white/75 px-2.5 py-1.5 text-center text-[10px] text-ink-2"
          >
            {foundation}
          </span>
        ))}
      </div>
    </figure>
  )
}

function CandidateCard({ candidate }: { candidate: ArchitectureCandidate }) {
  const Icon = candidate.icon

  return (
    <article id={candidate.id}>
      <Card className="gap-0 overflow-hidden rounded-[28px] border-ink/10 bg-white/55 py-0 text-ink shadow-card backdrop-blur">
        <CardHeader className="gap-0 px-5 py-5 sm:px-7 sm:py-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex min-w-0 items-start gap-4">
              <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-ink text-paper shadow-sm">
                <Icon className="size-5" />
              </span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-3">
                    Candidate {candidate.number}
                  </span>
                  <StrengthBadge strength={candidate.strength} />
                  {candidate.status === 'implemented' ? (
                    <Badge intent="success">Implemented</Badge>
                  ) : null}
                  <Badge intent="outline">{candidate.category}</Badge>
                </div>
                <h2 className="mt-3 font-display text-2xl font-semibold tracking-[-0.035em] sm:text-3xl">
                  {candidate.title}
                </h2>
              </div>
            </div>
          </div>

          <CardDescription className="mt-5 grid gap-1 text-ink-3 sm:grid-cols-2">
            {candidate.files.map((file) => (
              <code key={file} className="text-[10px] leading-5 sm:text-[11px]">
                {file}
              </code>
            ))}
          </CardDescription>
        </CardHeader>

        <CardContent className="border-t border-ink/[0.08] px-5 py-5 sm:px-7 sm:py-7">
          <div className="grid gap-4 lg:grid-cols-2">
            <BeforeDiagram label={candidate.beforeLabel} nodes={candidate.before} />
            <AfterDiagram candidate={candidate} />
          </div>

          <div className="mt-6 grid gap-5 border-t border-ink/[0.08] pt-6 lg:grid-cols-[1fr_1fr_1.15fr]">
            <div>
              <h3 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-3">
                Problem
              </h3>
              <p className="mt-2 text-sm leading-6 text-ink-2">{candidate.problem}</p>
            </div>
            <div>
              <h3 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-3">
                Solution
              </h3>
              <p className="mt-2 text-sm leading-6 text-ink-2">{candidate.solution}</p>
            </div>
            <div>
              <h3 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-3">
                Benefits
              </h3>
              <ul className="mt-2 grid gap-2 text-sm text-ink-2 sm:grid-cols-2 lg:grid-cols-1">
                {candidate.wins.map((win) => (
                  <li key={win} className="flex items-start gap-2">
                    <CheckCircleIcon className="mt-1 size-3.5 shrink-0 text-green" />
                    <span>{win}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </CardContent>

        <CardFooter className="border-t border-ink/[0.08] bg-inset/65 px-5 py-4 text-xs leading-5 text-ink-3 sm:px-7">
          <p>
            <strong className="font-semibold text-ink-2">Deletion test:</strong>{' '}
            {candidate.deletionTest}
          </p>
        </CardFooter>
      </Card>
    </article>
  )
}

function IllustrationsPage() {
  return (
    <UiProvider className="min-h-dvh bg-paper text-ink">
      <main className="mx-auto w-full max-w-6xl px-5 py-12 sm:px-8 sm:py-16 xl:px-10">
        <header className="border-b border-ink/10 pb-9">
          <div className="flex flex-col justify-between gap-7 sm:flex-row sm:items-end">
            <div className="max-w-3xl">
              <div className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-white/60 px-3 py-1.5 text-xs font-medium tracking-wide text-ink-2 shadow-xs">
                <CubeTransparentIcon className="size-3.5" />
                Backend architecture review
              </div>
              <h1 className="mt-5 font-display text-4xl font-semibold tracking-[-0.05em] text-balance sm:text-5xl">
                Deepen the modules that carry the Paper pipeline.
              </h1>
              <p className="mt-5 max-w-2xl text-base leading-7 text-ink-2 sm:text-lg">
                Five verified findings for improving locality, leverage, and testability.
                The first deepening is now implemented.
              </p>
            </div>

            <div className="shrink-0 text-xs leading-6 text-ink-3 sm:text-right">
              <p>Research Paper API</p>
              <p>14 August 2026</p>
              <p>Scope: app/</p>
            </div>
          </div>

          <div className="mt-8 flex flex-wrap gap-x-5 gap-y-2 text-[11px] text-ink-3">
            <span className="inline-flex items-center gap-2">
              <i className="size-3 rounded-sm border border-ink/30 bg-white" /> module
            </span>
            <span className="inline-flex items-center gap-2">
              <i className="w-5 border-t border-dashed border-ink/40" /> seam
            </span>
            <span className="inline-flex items-center gap-2">
              <i className="h-0.5 w-5 bg-red" /> leakage
            </span>
            <span className="inline-flex items-center gap-2">
              <i className="size-3 rounded-sm bg-ink" /> deep module
            </span>
          </div>
        </header>

        <section aria-labelledby="top-recommendation" className="mt-10">
          <Card className="gap-0 overflow-hidden rounded-[28px] border-green/25 bg-ink py-0 text-paper shadow-raised">
            <CardContent className="grid gap-7 px-6 py-7 sm:px-8 sm:py-9 lg:grid-cols-[1fr_auto] lg:items-end">
              <div>
                <Badge intent="success">First deepening completed</Badge>
                <h2
                  id="top-recommendation"
                  className="mt-4 font-display text-3xl font-semibold tracking-[-0.04em] sm:text-4xl"
                >
                  Citation Source fulfillment now has one owner.
                </h2>
                <p className="mt-4 max-w-3xl text-sm leading-6 text-paper/60">
                  One service now owns the lifecycle from running state through verified
                  candidates. The BullMQ worker calls one interface, and the versioned cache
                  identity is enforced consistently in code and in the database.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-2 text-center text-[10px] uppercase tracking-[0.12em] text-paper/45 sm:grid-cols-4 lg:grid-cols-2">
                <span className="rounded-lg border border-white/10 bg-white/[0.055] px-3 py-2">highest locality</span>
                <span className="rounded-lg border border-white/10 bg-white/[0.055] px-3 py-2">real defect</span>
                <span className="rounded-lg border border-white/10 bg-white/[0.055] px-3 py-2">one interface</span>
                <span className="rounded-lg border border-white/10 bg-white/[0.055] px-3 py-2">thin adapter</span>
              </div>
            </CardContent>
          </Card>
        </section>

        <section aria-label="Architecture candidates" className="mt-12 space-y-10">
          {architectureCandidates.map((candidate) => (
            <CandidateCard key={candidate.id} candidate={candidate} />
          ))}
        </section>

        <section aria-labelledby="not-a-candidate" className="mt-10 pb-4">
          <Card className="gap-0 rounded-[28px] border-ink/10 bg-white/50 py-0 text-ink shadow-card">
            <CardContent className="flex flex-col gap-5 px-6 py-7 sm:flex-row sm:items-center sm:justify-between sm:px-8">
              <div className="flex items-start gap-4">
                <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-green-tint text-green">
                  <CircleStackIcon className="size-5" />
                </span>
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-3">
                    Not a candidate
                  </p>
                  <h2
                    id="not-a-candidate"
                    className="mt-2 font-display text-2xl font-semibold tracking-[-0.035em]"
                  >
                    Keep Paper extraction deep.
                  </h2>
                  <p className="mt-3 max-w-3xl text-sm leading-6 text-ink-2">
                    <code>PaperService.parse_pdf</code> and <code>parse_tei</code> already hide
                    preflight, OCR, GROBID recovery, normalization, quality, and artifact
                    storage behind small interfaces. Their deletion would spread substantial
                    complexity, so file size alone is not a reason to split them.
                  </p>
                </div>
              </div>
              <Badge intent="success" className="shrink-0 self-start sm:self-center">
                <ShareIcon data-slot="icon" />
                Deletion test passes
              </Badge>
            </CardContent>
          </Card>
        </section>
      </main>
    </UiProvider>
  )
}
