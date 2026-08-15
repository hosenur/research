import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from 'react'
import {
  ArrowCounterClockwiseIcon as RotateCcw,
  ArrowSquareOutIcon as ExternalLink,
  BooksIcon,
  ChatCenteredTextIcon,
  ClipboardTextIcon,
  FilePdfIcon,
  RowsIcon,
} from '@phosphor-icons/react'
import { AgentChat } from '@/components/agent/AgentChat'
import { ExportControl } from '@/components/agent/ExportPanel'
import { ManuscriptNavigationToolbar } from '@/components/agent/ManuscriptNavigationToolbar'
import { MatchedReferencesPanel } from '@/components/agent/MatchedReferencesPanel'
import {
  PaperManuscript,
  type ManuscriptFocus,
} from '@/components/agent/PaperManuscript'
import {
  ReviewInbox,
  type ReviewCategory,
} from '@/components/agent/ReviewInbox'
import { SectionReviewPanel } from '@/components/agent/SectionReviewPanel'
import { Button } from '@/components/ui/button'
import {
  Sidebar,
  SidebarContent,
  SidebarInset,
  SidebarProvider,
} from '@/components/ui/sidebar'
import { Tab, TabList, TabPanel, Tabs } from '@/components/ui/tabs'
import { useCitationAudit } from '@/hooks/use-citation-audit'
import { useClaimCitationReview } from '@/hooks/use-claim-citation-review'
import { useManuscriptEdits } from '@/hooks/use-manuscript-edits'
import { useOpenAlexEnrichment } from '@/hooks/use-paper'
import {
  missingReferenceSource,
  preferredMissingReferenceCandidate,
  type PaperAgentSelectionContext,
  type ManuscriptSelection,
} from '@/lib/manuscript-focus'
import type { PaperJson } from '@/lib/paper'

type WorkspaceTab = 'review' | 'agent' | 'references'

const reviewCategoryLabels: Record<ReviewCategory, string> = {
  missing: 'Missing references',
  dismissed: 'Dismissed citations',
  weak: 'Weak citations',
  contradicted: 'Contradicted citations',
  unverifiable: 'Uncertain citations',
  supported: 'Supported citations',
}

function referenceTitle(reference: PaperJson['references'][number]) {
  return (
    reference.openalex?.title?.trim() ||
    reference.csl?.title?.trim() ||
    reference.rawText?.split(/[.?]/)[0]?.trim() ||
    reference.id
  )
}

function referenceUrl(reference: PaperJson['references'][number]) {
  const doi = reference.openalex?.doi ?? reference.csl?.DOI
  return (
    reference.openalex?.landingPageUrl ||
    (doi ? (doi.startsWith('http') ? doi : `https://doi.org/${doi}`) : null)
  )
}

interface PaperWorkspaceProps {
  documentRevision: number
  filename: string
  onReset: () => void
  paper: PaperJson
  paperId: string
  paperRevision: number
  pdfUrl: string
}

export function PaperWorkspace({
  documentRevision,
  filename,
  onReset,
  paper,
  paperId,
  paperRevision,
  pdfUrl,
}: PaperWorkspaceProps) {
  const [showPdf, setShowPdf] = useState(false)
  const [activeWorkspaceTab, setActiveWorkspaceTab] = useState<WorkspaceTab>('agent')
  const [activeReviewCategory, setActiveReviewCategory] =
    useState<ReviewCategory>('missing')
  const [manuscriptFocus, setManuscriptFocus] = useState<ManuscriptFocus | null>(null)
  const [agentSelection, setAgentSelection] =
    useState<PaperAgentSelectionContext | null>(null)
  const focusTimer = useRef<number | null>(null)
  const { enrichment, paper: currentPaper } = useOpenAlexEnrichment({
    initialRevision: documentRevision,
    paper,
    paperId,
  })
  const citationAudit = useCitationAudit(paperId)
  const claimCitationReview = useClaimCitationReview(paperId)
  const manuscriptEdits = useManuscriptEdits(paperId)

  const navigation = useMemo(() => {
    if (activeWorkspaceTab === 'agent') {
      return { key: 'agent', label: 'Agent', targets: [] as ManuscriptSelection[] }
    }

    const referencesById = new Map(
      currentPaper.references.map((reference) => [reference.id, reference]),
    )
    const paragraphOrderById = new Map<string, number>()
    for (const section of currentPaper.sections) {
      for (const paragraph of section.paragraphs) {
        paragraphOrderById.set(paragraph.id, paragraphOrderById.size)
      }
    }
    const inManuscriptOrder = (targets: ManuscriptSelection[]) =>
      [...targets].sort((left, right) => {
        const paragraphDifference =
          (paragraphOrderById.get(left.paragraphId) ?? Number.MAX_SAFE_INTEGER) -
          (paragraphOrderById.get(right.paragraphId) ?? Number.MAX_SAFE_INTEGER)
        if (paragraphDifference !== 0) return paragraphDifference
        return (left.startOffset ?? 0) - (right.startOffset ?? 0)
      })
    const sentenceOffsetsById = new Map(
      currentPaper.sections.flatMap((section) =>
        section.paragraphs.flatMap((paragraph) =>
          (paragraph.sentences ?? []).map(
            (sentence) =>
              [
                `${paragraph.id}:${sentence.id}`,
                { startOffset: sentence.startOffset, endOffset: sentence.endOffset },
              ] as const,
          ),
        ),
      ),
    )

    if (activeWorkspaceTab === 'references') {
      const matchedReferenceIds = new Set(
        currentPaper.references
          .filter(
            (reference) =>
              reference.openalexStatus === 'matched' && reference.openalex != null,
          )
          .map((reference) => reference.id),
      )
      const targets = currentPaper.sections.flatMap((section) =>
        section.paragraphs.flatMap((paragraph) => {
          let cursor = 0
          return paragraph.nodes.flatMap((node) => {
            const startOffset = cursor
            const value = node.type === 'text' ? node.text : node.rawText
            cursor += value.length
            if (node.type !== 'citation') return []
            const references = node.items
              .map((item) => item.sourceId)
              .filter((sourceId) => matchedReferenceIds.has(sourceId))
              .map((sourceId) => referencesById.get(sourceId))
              .filter((reference) => reference != null)
            if (!references.length) return []
            const sentence = paragraph.sentences?.find(
              (item) => item.startOffset <= startOffset && startOffset < item.endOffset,
            )
            return [
              {
                paragraphId: paragraph.id,
                startOffset: sentence?.startOffset ?? startOffset,
                endOffset: sentence?.endOffset ?? cursor,
                text: node.rawText,
                source: {
                  title: referenceTitle(references[0]),
                  url: referenceUrl(references[0]),
                },
                context: {
                  kind: 'reference',
                  label: referenceTitle(references[0]),
                  referenceId: references[0].id,
                  citationId: node.id ?? undefined,
                  paragraphId: paragraph.id,
                  text: node.rawText,
                },
              } satisfies ManuscriptSelection,
            ]
          })
        }),
      )
      return {
        key: 'references',
        label: 'References',
        targets: inManuscriptOrder(targets),
      }
    }

    const missingSelection = (
      finding: (typeof citationAudit.findings)[number],
    ): ManuscriptSelection => {
      const candidate = preferredMissingReferenceCandidate(finding.sourceCandidates)
      return {
        paragraphId: finding.paragraphId,
        startOffset: finding.startOffset,
        endOffset: finding.endOffset,
        text: finding.sourceText,
        source: missingReferenceSource(finding.sourceCandidates),
        context: {
          kind: 'missing',
          label: candidate?.work.title ?? finding.claimText,
          findingId: finding.id,
          candidateId: candidate?.id,
          paragraphId: finding.paragraphId,
          text: finding.sourceText,
        },
      }
    }
    const appliedReferenceIdsByParagraph = new Map(
      currentPaper.sections.flatMap((section) =>
        section.paragraphs.map(
          (paragraph) =>
            [
              paragraph.id,
              new Set(
                paragraph.nodes.flatMap((node) =>
                  node.type === 'citation'
                    ? node.items.map((item) => item.sourceId)
                    : [],
                ),
              ),
            ] as const,
        ),
      ),
    )

    if (activeReviewCategory === 'missing') {
      const targets = citationAudit.findings
        .filter(
          (finding) =>
            !finding.sourceCandidates.some((candidate) =>
              appliedReferenceIdsByParagraph
                .get(finding.paragraphId)
                ?.has(`source-${candidate.work.id}`),
            ),
        )
        .map(missingSelection)
      return {
        key: `review:${activeReviewCategory}`,
        label: reviewCategoryLabels[activeReviewCategory],
        targets: inManuscriptOrder(targets),
      }
    }

    if (activeReviewCategory === 'dismissed') {
      return {
        key: `review:${activeReviewCategory}`,
        label: reviewCategoryLabels[activeReviewCategory],
        targets: inManuscriptOrder(citationAudit.dismissedFindings.map(missingSelection)),
      }
    }

    const targets = (claimCitationReview.data?.findings ?? [])
      .filter((finding) => finding.classification === activeReviewCategory)
      .map((finding) => {
        const offsets = sentenceOffsetsById.get(
          `${finding.paragraphId}:${finding.sentenceId}`,
        )
        return {
          paragraphId: finding.paragraphId,
          startOffset: offsets?.startOffset,
          endOffset: offsets?.endOffset,
          text: finding.claimText,
          source: {
            title:
              finding.workTitle?.trim() ||
              (referencesById.has(finding.referenceId)
                ? referenceTitle(referencesById.get(finding.referenceId)!)
                : finding.referenceId),
            url:
              finding.sourceUrl ||
              (referencesById.has(finding.referenceId)
                ? referenceUrl(referencesById.get(finding.referenceId)!)
                : null),
          },
          context: {
            kind: 'existing',
            label: finding.workTitle?.trim() || finding.referenceId,
            findingId: finding.id,
            referenceId: finding.referenceId,
            citationId: finding.citationId ?? undefined,
            paragraphId: finding.paragraphId,
            text: finding.claimText,
            classification: finding.classification,
          },
        } satisfies ManuscriptSelection
      })
    return {
      key: `review:${activeReviewCategory}`,
      label: reviewCategoryLabels[activeReviewCategory],
      targets: inManuscriptOrder(targets),
    }
  }, [
    activeReviewCategory,
    activeWorkspaceTab,
    citationAudit.dismissedFindings,
    citationAudit.findings,
    claimCitationReview.data?.findings,
    currentPaper,
  ])

  useEffect(
    () => () => {
      if (focusTimer.current != null) window.clearTimeout(focusTimer.current)
    },
    [],
  )

  useEffect(() => {
    setManuscriptFocus(null)
    if (focusTimer.current != null) window.clearTimeout(focusTimer.current)
  }, [navigation.key])

  function focusManuscriptNode(selection: ManuscriptSelection) {
    if (selection.context) setAgentSelection(selection.context)
    const token = Date.now()
    setManuscriptFocus({ ...selection, highlighted: true, token })
    const node = document.getElementById(`node-${selection.paragraphId}`)
    node?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    if (focusTimer.current != null) window.clearTimeout(focusTimer.current)
    focusTimer.current = window.setTimeout(
      () =>
        setManuscriptFocus((current) =>
          current?.token === token ? { ...current, highlighted: false } : current,
        ),
      4_100,
    )
  }

  const browseManuscriptTarget = useCallback((selection: ManuscriptSelection) => {
    if (selection.context) setAgentSelection(selection.context)
  }, [])

  return (
    <section aria-label="Research paper workspace" className="workspace-enter min-h-dvh w-full bg-bg">
      <SidebarProvider
        className="min-h-dvh lg:h-dvh lg:overflow-hidden"
        style={{ '--sidebar-width': 'clamp(21rem,30vw,29rem)' } as CSSProperties}
      >
        <SidebarInset className="min-h-0 min-w-0">
          <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-border bg-overlay px-3 sm:px-4">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-fg">{filename}</p>
              <p className="text-xs text-muted-fg">Authoritative manuscript · revision {paperRevision}</p>
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              <ExportControl paperId={paperId} revision={paperRevision} />
              <Button
                aria-label={showPdf ? 'Hide original PDF' : 'Show original PDF'}
                intent={showPdf ? 'secondary' : 'outline'}
                onPress={() => setShowPdf((current) => !current)}
                size="sq-sm"
              >
                {showPdf ? <RowsIcon /> : <FilePdfIcon />}
              </Button>
              <Button
                aria-label="Open PDF in a new tab"
                intent="plain"
                onPress={() => window.open(pdfUrl, '_blank', 'noopener,noreferrer')}
                size="sq-sm"
              >
                <ExternalLink />
              </Button>
              <Button intent="outline" onPress={onReset} size="sm">
                <RotateCcw />
                New paper
              </Button>
            </div>
          </header>

          <div className={showPdf ? 'grid min-h-0 flex-1 lg:grid-cols-2' : 'min-h-0 flex-1'}>
            <div className="h-full min-h-0 overflow-y-auto bg-bg">
              <ManuscriptNavigationToolbar
                activeSelection={manuscriptFocus}
                categoryKey={navigation.key}
                label={navigation.label}
                onBrowse={browseManuscriptTarget}
                onSelect={focusManuscriptNode}
                targets={navigation.targets}
              />
              <PaperManuscript focus={manuscriptFocus} paper={currentPaper} />
            </div>
            {showPdf ? (
              <div className="min-h-[36rem] border-l border-border bg-muted p-2 lg:min-h-0">
                <object
                  aria-label={`Original PDF: ${filename}`}
                  className="size-full overflow-hidden rounded-lg border border-border bg-overlay"
                  data={pdfUrl}
                  type="application/pdf"
                >
                  <div className="grid size-full place-items-center p-8 text-center text-sm text-muted-fg">
                    <Button onPress={() => window.open(pdfUrl, '_blank')} size="sm">
                      <ExternalLink />
                      Open PDF
                    </Button>
                  </div>
                </object>
              </div>
            ) : null}
          </div>
        </SidebarInset>

        <Sidebar
          aria-label="Paper context"
          className="max-lg:w-full lg:border-l lg:border-sidebar-border"
          collapsible="none"
          side="right"
        >
          <SidebarContent className="overflow-hidden p-2">
            <Tabs
              className="min-h-0 flex-1 gap-2 self-stretch"
              onSelectionChange={(key) => {
                const tab = String(key) as WorkspaceTab
                if (tab === 'review' || tab === 'agent' || tab === 'references') {
                  setActiveWorkspaceTab(tab)
                }
              }}
              selectedKey={activeWorkspaceTab}
            >
              <TabList aria-label="Paper tools" className="shrink-0 px-2">
                <Tab id="agent"><ChatCenteredTextIcon />Agent</Tab>
                <Tab id="review"><ClipboardTextIcon />Review</Tab>
                <Tab id="references"><BooksIcon />References</Tab>
              </TabList>
              <TabPanel className="min-h-0 overflow-hidden" id="agent">
                <AgentChat
                  className="h-full min-h-0"
                  edits={manuscriptEdits}
                  paper={currentPaper}
                  paperId={paperId}
                  revision={paperRevision}
                  selectionContext={agentSelection}
                />
              </TabPanel>
              <TabPanel className="min-h-0 overflow-hidden" id="review">
                <div className="flex h-full min-h-0 flex-col">
                {(currentPaper.extraction?.preflight.pageCount ?? 0) > 80 ? (
                  <SectionReviewPanel paperId={paperId} sections={currentPaper.sections} />
                ) : null}
                <div className="min-h-0 flex-1">
                  <ReviewInbox
                    edits={manuscriptEdits}
                    missing={citationAudit}
                    existing={claimCitationReview.data}
                    onCategoryChange={setActiveReviewCategory}
                    onFindingSelect={focusManuscriptNode}
                    paper={currentPaper}
                    selectedCategory={activeReviewCategory}
                  />
                </div>
                </div>
              </TabPanel>
              <TabPanel className="min-h-0 overflow-hidden" id="references">
                <MatchedReferencesPanel
                  enrichment={enrichment}
                  references={currentPaper.references}
                />
              </TabPanel>
            </Tabs>
          </SidebarContent>
        </Sidebar>
      </SidebarProvider>
    </section>
  )
}
