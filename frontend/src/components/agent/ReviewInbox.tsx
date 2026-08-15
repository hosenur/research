import { useMemo, useState } from 'react'
import {
  ArrowSquareOutIcon,
  ArrowUUpLeftIcon,
  CheckCircleIcon,
  SpinnerGapIcon,
  WarningDiamondIcon,
  WarningIcon,
} from '@phosphor-icons/react'
import { CitationAuditPanel } from '@/components/agent/CitationAuditPanel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Link } from '@/components/ui/link'
import { Tab, TabList, TabPanel, Tabs } from '@/components/ui/tabs'
import type { CitationAuditFinding } from '@/hooks/use-citation-audit'
import type { ClaimCitationFinding } from '@/hooks/use-claim-citation-review'
import type { ManuscriptEditFlow } from '@/hooks/use-manuscript-edits'
import {
  missingReferenceSource,
  preferredMissingReferenceCandidate,
  type ManuscriptSelection,
} from '@/lib/manuscript-focus'
import type { PaperJson } from '@/lib/paper'

export type ReviewCategory =
  | 'missing'
  | 'dismissed'
  | ClaimCitationFinding['classification']

interface ReviewInboxProps {
  edits: ManuscriptEditFlow
  missing: {
    error: string | null
    dismissedFindings: CitationAuditFinding[]
    findings: CitationAuditFinding[]
    percentage: number
    status: 'not_started' | 'queued' | 'running' | 'completed' | 'failed'
    decideCandidate: (findingId: string, candidateId: string, value: 'accepted' | 'rejected') => unknown
    removeCandidateSource: (findingId: string, candidateId: string) => unknown
    reportFinding: (findingId: string, value: 'false_positive' | 'needs_review') => unknown
    decisionPending: boolean
  }
  existing?: {
    status: 'not_started' | 'queued' | 'running' | 'completed' | 'failed'
    findings: ClaimCitationFinding[]
    error?: string | null
  }
  onCategoryChange: (category: ReviewCategory) => void
  onFindingSelect: (selection: ManuscriptSelection) => void
  paper: PaperJson
  selectedCategory: ReviewCategory
}

function DismissedCitationsPanel({
  decisionPending,
  findings,
  onFindingSelect,
  onRestore,
}: {
  decisionPending: boolean
  findings: CitationAuditFinding[]
  onFindingSelect: ReviewInboxProps['onFindingSelect']
  onRestore: (findingId: string, value: 'needs_review') => unknown | Promise<unknown>
}) {
  const [restoreError, setRestoreError] = useState<string | null>(null)

  async function restoreFinding(findingId: string) {
    setRestoreError(null)
    try {
      await onRestore(findingId, 'needs_review')
    } catch (error) {
      setRestoreError(
        error instanceof Error ? error.message : 'The citation finding could not be restored.',
      )
    }
  }

  return (
    <Card className="h-full min-h-0 overflow-hidden bg-overlay shadow-overlay">
      <CardHeader
        title="Dismissed citations"
        description={`${findings.length} ${findings.length === 1 ? 'dismissed finding' : 'dismissed findings'}`}
      />
      <CardContent className="min-h-0 flex-1 overflow-y-auto border-t px-4 py-0">
        {restoreError ? (
          <div
            className="mt-4 rounded-lg border border-danger/30 bg-danger-subtle px-3 py-3 text-sm/6 text-danger-subtle-fg"
            role="alert"
          >
            {restoreError}
          </div>
        ) : null}
        {findings.length ? (
          <ol className="divide-y divide-border">
            {findings.map((finding) => (
              <li className="py-5" key={finding.id}>
                <p className="text-xs font-medium text-muted-fg">{finding.sectionTitle}</p>
                <p className="mt-1.5 text-sm/6 font-medium text-fg">
                  “{finding.claimText}”
                </p>
                <p className="mt-1 text-xs/5 text-muted-fg">{finding.explanation}</p>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <Button
                    intent="outline"
                    onPress={() => {
                      const candidate = preferredMissingReferenceCandidate(
                        finding.sourceCandidates,
                      )
                      onFindingSelect({
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
                      })
                    }}
                    size="sm"
                  >
                    View in manuscript
                  </Button>
                  <Button
                    intent="secondary"
                    isDisabled={decisionPending}
                    onPress={() => void restoreFinding(finding.id)}
                    size="sm"
                  >
                    <ArrowUUpLeftIcon data-slot="icon" />
                    Restore to Missing
                  </Button>
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <p className="py-5 text-sm text-muted-fg">No citation findings have been dismissed.</p>
        )}
      </CardContent>
    </Card>
  )
}

const groups = [
  { id: 'weak', label: 'Weak' },
  { id: 'contradicted', label: 'Contradicted' },
  { id: 'unverifiable', label: 'Uncertain' },
  { id: 'supported', label: 'Supported' },
] as const

function ClaimCitationGroup({
  classification,
  findings,
  onFindingSelect,
  sentenceOffsetsById,
}: {
  classification: ClaimCitationFinding['classification']
  findings: ClaimCitationFinding[]
  onFindingSelect: ReviewInboxProps['onFindingSelect']
  sentenceOffsetsById: ReadonlyMap<string, { startOffset: number; endOffset: number }>
}) {
  const selected = findings.filter((finding) => finding.classification === classification)
  const intent = classification === 'supported' ? 'success' : classification === 'contradicted' ? 'danger' : 'warning'
  return (
    <Card className="h-full min-h-0 overflow-hidden bg-overlay shadow-overlay">
      <CardHeader
        title={`${classification === 'unverifiable' ? 'Uncertain' : classification[0].toUpperCase() + classification.slice(1)} citation support`}
        description={`${selected.length} ${selected.length === 1 ? 'claim/citation pair' : 'claim/citation pairs'}`}
      />
      <CardContent className="min-h-0 flex-1 overflow-y-auto border-t px-4 py-0">
        {selected.length ? (
          <ol className="divide-y divide-border">
            {selected.map((finding) => (
              <li className="py-4" key={finding.id}>
                <div className="flex items-start justify-between gap-2">
                  <p className="text-xs font-medium text-muted-fg">{finding.sectionTitle} · {finding.referenceId}</p>
                  <Badge intent={intent}>
                    {classification === 'supported' ? <CheckCircleIcon data-slot="icon" /> : classification === 'contradicted' ? <WarningDiamondIcon data-slot="icon" /> : <WarningIcon data-slot="icon" />}
                    {Math.round(finding.confidence * 100)}%
                  </Badge>
                </div>
                <p className="mt-2 text-sm/6 font-medium text-fg">“{finding.claimText}”</p>
                <p className="mt-1 text-xs/5 text-muted-fg">{finding.explanation}</p>
                {finding.evidenceText ? (
                  <p className="mt-2 border-l-2 border-border pl-2 text-xs/5 text-muted-fg">“{finding.evidenceText}”</p>
                ) : null}
                <div className="mt-3 flex flex-col items-start gap-2">
                  {finding.sourceUrl ? (
                    <Link
                      className="inline-flex max-w-full items-start gap-1 text-xs/5 [overflow-wrap:anywhere]"
                      href={finding.sourceUrl}
                      rel="noreferrer"
                      target="_blank"
                    >
                      {finding.workTitle ?? 'Provider source'}
                      <ArrowSquareOutIcon data-slot="icon" />
                    </Link>
                  ) : (
                    <span className="text-xs text-muted-fg">No linkable provider record</span>
                  )}
                  <Button
                    intent="outline"
                    onPress={() => {
                      const offsets = sentenceOffsetsById.get(
                        `${finding.paragraphId}:${finding.sentenceId}`,
                      )
                      onFindingSelect({
                        paragraphId: finding.paragraphId,
                        startOffset: offsets?.startOffset,
                        endOffset: offsets?.endOffset,
                        text: finding.claimText,
                        source: {
                          title: finding.workTitle?.trim() || finding.referenceId,
                          url: finding.sourceUrl,
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
                      })
                    }}
                    size="xs"
                  >
                    View in manuscript
                  </Button>
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <p className="py-5 text-sm text-muted-fg">No {classification} claim/citation pairs.</p>
        )}
      </CardContent>
    </Card>
  )
}

export function ReviewInbox({
  edits,
  existing,
  missing,
  onCategoryChange,
  onFindingSelect,
  paper,
  selectedCategory,
}: ReviewInboxProps) {
  const running = !existing || ['not_started', 'queued', 'running'].includes(existing.status)
  const sentenceOffsetsById = useMemo(
    () =>
      new Map(
        paper.sections.flatMap((section) =>
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
      ),
    [paper],
  )
  const appliedReferenceIdsByParagraph = useMemo(
    () =>
      new Map(
        paper.sections.flatMap((section) =>
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
      ),
    [paper],
  )
  const openMissingCount = useMemo(
    () =>
      missing.findings.filter(
        (finding) =>
          !finding.sourceCandidates.some((candidate) =>
            appliedReferenceIdsByParagraph
              .get(finding.paragraphId)
              ?.has(`source-${candidate.work.id}`),
          ),
      ).length,
    [appliedReferenceIdsByParagraph, missing.findings],
  )
  return (
    <Tabs
      className="h-full min-h-0 gap-2 self-stretch"
      onSelectionChange={(key) => {
        const category = String(key) as ReviewCategory
        if (
          category === 'missing' ||
          category === 'dismissed' ||
          groups.some((group) => group.id === category)
        ) {
          onCategoryChange(category)
        }
      }}
      selectedKey={selectedCategory}
    >
      <TabList aria-label="Review finding groups" className="shrink-0 px-2">
        <Tab id="missing">Missing {openMissingCount || ''}</Tab>
        <Tab id="dismissed">
          Dismissed Citations {missing.dismissedFindings.length || ''}
        </Tab>
        {groups.map((group) => (
          <Tab id={group.id} key={group.id}>
            {group.label} {existing?.findings.filter((item) => item.classification === group.id).length || ''}
          </Tab>
        ))}
      </TabList>
      <TabPanel className="min-h-0 overflow-hidden" id="missing">
        <CitationAuditPanel
          className="h-full"
          appliedReferenceIdsByParagraph={appliedReferenceIdsByParagraph}
          edits={edits}
          error={missing.error}
          findings={missing.findings}
          percentage={missing.percentage}
          status={missing.status}
          onCandidateDecision={missing.decideCandidate}
          onCandidateRemoval={missing.removeCandidateSource}
          onFindingFeedback={missing.reportFinding}
          onFindingSelect={onFindingSelect}
          decisionPending={missing.decisionPending}
        />
      </TabPanel>
      <TabPanel className="min-h-0 overflow-hidden" id="dismissed">
        <DismissedCitationsPanel
          decisionPending={missing.decisionPending}
          findings={missing.dismissedFindings}
          onFindingSelect={onFindingSelect}
          onRestore={missing.reportFinding}
        />
      </TabPanel>
      {groups.map((group) => (
        <TabPanel className="min-h-0 overflow-hidden" id={group.id} key={group.id}>
          {running ? (
            <Card className="bg-overlay shadow-overlay">
              <CardHeader title="Checking existing citations" description="Provider abstracts are being matched to cited claims." />
              <CardContent className="flex items-center gap-2 border-t px-4 py-4 text-sm text-muted-fg">
                <SpinnerGapIcon className="animate-spin" /> Review continues in the background.
              </CardContent>
            </Card>
          ) : (
            <ClaimCitationGroup
              classification={group.id}
              findings={existing.findings}
              onFindingSelect={onFindingSelect}
              sentenceOffsetsById={sentenceOffsetsById}
            />
          )}
        </TabPanel>
      ))}
    </Tabs>
  )
}
