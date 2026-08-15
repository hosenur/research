import { useMemo, useState } from 'react'
import { ArrowUturnLeftIcon } from '@heroicons/react/24/solid'
import {
  ArrowSquareOutIcon,
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
import type { PaperJson } from '@/lib/paper'

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
  onFindingSelect: (
    paragraphId: string,
    startOffset?: number,
    endOffset?: number,
    text?: string,
  ) => void
  paper: PaperJson
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
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    intent="outline"
                    onPress={() =>
                      onFindingSelect(
                        finding.paragraphId,
                        finding.startOffset,
                        finding.endOffset,
                        finding.sourceText,
                      )
                    }
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
                    <ArrowUturnLeftIcon data-slot="icon" />
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
}: {
  classification: ClaimCitationFinding['classification']
  findings: ClaimCitationFinding[]
  onFindingSelect: ReviewInboxProps['onFindingSelect']
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
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Button
                    intent="outline"
                    onPress={() =>
                      onFindingSelect(
                        finding.paragraphId,
                        undefined,
                        undefined,
                        finding.claimText,
                      )
                    }
                    size="xs"
                  >
                    View in manuscript
                  </Button>
                  {finding.sourceUrl ? (
                    <Link href={finding.sourceUrl} rel="noreferrer" target="_blank">
                      {finding.workTitle ?? 'Provider source'}
                      <ArrowSquareOutIcon data-slot="icon" />
                    </Link>
                  ) : (
                    <span className="text-xs text-muted-fg">No linkable provider record</span>
                  )}
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

export function ReviewInbox({ edits, existing, missing, onFindingSelect, paper }: ReviewInboxProps) {
  const running = !existing || ['not_started', 'queued', 'running'].includes(existing.status)
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
    <Tabs className="h-full min-h-0 gap-2 self-stretch" defaultSelectedKey="missing">
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
            <ClaimCitationGroup classification={group.id} findings={existing.findings} onFindingSelect={onFindingSelect} />
          )}
        </TabPanel>
      ))}
    </Tabs>
  )
}
