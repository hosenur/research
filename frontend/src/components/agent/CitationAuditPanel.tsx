import { useRef, useState } from 'react'
import {
  ArrowSquareOutIcon as ExternalLink,
  BookOpenIcon as Source,
  CheckIcon,
  CheckCircleIcon as Complete,
  InfoIcon,
  SparkleIcon as Ai,
  SpinnerGapIcon as Processing,
  TrashIcon,
  WarningIcon as Warning,
  XIcon as XMarkIcon,
} from '@phosphor-icons/react'
import { Badge } from '@/components/ui/badge'
import { Card, CardAction, CardContent, CardHeader } from '@/components/ui/card'
import { Link } from '@/components/ui/link'
import type { CitationAuditFinding } from '@/hooks/use-citation-audit'
import { twMerge } from 'tailwind-merge'
import { Button } from '@/components/ui/button'
import { EditProposalThread } from '@/components/agent/EditCommandPanel'
import type { ManuscriptEditFlow } from '@/hooks/use-manuscript-edits'
import { Loader } from '@/components/ui/loader'
import {
  ModalBody,
  ModalContent,
  ModalDescription,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/components/ui/modal'
import { Tooltip, TooltipContent } from '@/components/ui/tooltip'
import {
  missingReferenceSource,
  preferredMissingReferenceCandidate,
  type ManuscriptSelection,
} from '@/lib/manuscript-focus'

interface ActiveSource {
  action: 'add' | 'remove'
  candidateId: string
  findingId: string
  paragraphId: string
  title: string
}

interface CitationAuditPanelProps {
  appliedReferenceIdsByParagraph?: ReadonlyMap<string, ReadonlySet<string>>
  className?: string
  edits?: ManuscriptEditFlow
  error: string | null
  findings: CitationAuditFinding[]
  percentage: number
  status: 'not_started' | 'queued' | 'running' | 'completed' | 'failed'
  onCandidateDecision?: (
    findingId: string,
    candidateId: string,
    decision: 'accepted' | 'rejected',
  ) => unknown | Promise<unknown>
  onCandidateRemoval?: (
    findingId: string,
    candidateId: string,
  ) => unknown | Promise<unknown>
  onFindingFeedback?: (
    findingId: string,
    feedback: 'false_positive' | 'needs_review',
  ) => unknown | Promise<unknown>
  onFindingSelect?: (selection: ManuscriptSelection) => void
  decisionPending?: boolean
}

export function CitationAuditPanel({
  appliedReferenceIdsByParagraph,
  className,
  edits,
  error,
  findings,
  percentage,
  status,
  onCandidateDecision,
  onCandidateRemoval,
  onFindingFeedback,
  onFindingSelect,
  decisionPending = false,
}: CitationAuditPanelProps) {
  const modalProposalId = useRef<string | null>(null)
  const [activeSource, setActiveSource] = useState<ActiveSource | null>(null)
  const [preparingProposal, setPreparingProposal] = useState(false)
  const [proposalError, setProposalError] = useState<string | null>(null)
  const [pendingDismissal, setPendingDismissal] = useState<CitationAuditFinding | null>(null)
  const [confirmingDismissal, setConfirmingDismissal] = useState(false)
  const [dismissalError, setDismissalError] = useState<string | null>(null)
  const running = status === 'not_started' || status === 'queued' || status === 'running'
  const sourceSearching = findings.some((finding) =>
    ['not_started', 'queued', 'running'].includes(finding.sourceSearchStatus),
  )
  const busy = running || sourceSearching
  const resolvedFindingIds = new Set(
    findings
      .filter((finding) =>
        finding.sourceCandidates.some((candidate) =>
          appliedReferenceIdsByParagraph
            ?.get(finding.paragraphId)
            ?.has(`source-${candidate.work.id}`),
        ),
      )
      .map((finding) => finding.id),
  )
  const openFindingCount = findings.length - resolvedFindingIds.size
  const activeProposalReady =
    activeSource != null &&
    edits?.proposal?.command ===
      `${activeSource.action === 'remove' ? 'Remove' : 'Use'} verified source ${activeSource.title}` &&
    edits.proposal.operations.some(
      (operation) =>
        operation.operationType ===
          (activeSource.action === 'remove' ? 'remove_citation' : 'insert_citation') &&
        operation.nodeIds.includes(activeSource.paragraphId),
    )
  const blockingProposal =
    activeSource != null && edits?.proposal != null && !activeProposalReady

  async function selectSource(source: ActiveSource, proposalReady: boolean) {
    setActiveSource(source)
    setProposalError(null)
    modalProposalId.current = proposalReady ? edits?.proposal?.id ?? null : null
    if (proposalReady) return
    if (edits?.proposal) {
      setProposalError(
        `A different change is awaiting review: “${edits.proposal.command}”. Approve or discard it before preparing another citation change.`,
      )
      return
    }
    setPreparingProposal(true)
    try {
      if (source.action === 'remove') {
        await onCandidateRemoval?.(source.findingId, source.candidateId)
      } else {
        await onCandidateDecision?.(source.findingId, source.candidateId, 'accepted')
      }
      const proposal = await edits?.refreshProposal()
      if (proposal?.status === 'planned') modalProposalId.current = proposal.id
    } catch (candidateError) {
      setProposalError(
        candidateError instanceof Error
          ? candidateError.message
          : `The citation ${source.action === 'remove' ? 'removal' : 'proposal'} could not be prepared.`,
      )
    } finally {
      setPreparingProposal(false)
    }
  }

  function finishProposal() {
    if (preparingProposal || edits?.isApproving || edits?.isDiscarding) return
    modalProposalId.current = null
    setActiveSource(null)
    setProposalError(null)
  }

  async function cancelProposal() {
    if (preparingProposal || edits?.isApproving || edits?.isDiscarding) return
    const shouldDiscard =
      edits?.proposal?.status === 'planned' &&
      edits.proposal.id === modalProposalId.current
    modalProposalId.current = null
    setActiveSource(null)
    setProposalError(null)
    if (shouldDiscard) await edits?.discard()
  }

  function closeDismissal() {
    if (confirmingDismissal) return
    setPendingDismissal(null)
    setDismissalError(null)
  }

  async function confirmDismissal() {
    if (!pendingDismissal || !onFindingFeedback) return
    setConfirmingDismissal(true)
    setDismissalError(null)
    try {
      await onFindingFeedback(pendingDismissal.id, 'false_positive')
      setPendingDismissal(null)
    } catch (feedbackError) {
      setDismissalError(
        feedbackError instanceof Error
          ? feedbackError.message
          : 'The citation finding could not be dismissed.',
      )
    } finally {
      setConfirmingDismissal(false)
    }
  }

  return (
    <>
      <Card
        className={twMerge(
          'min-h-0 overflow-hidden bg-overlay shadow-overlay [--gutter:--spacing(4)]',
          className,
        )}
      >
        <CardHeader
          title="Citation coverage findings"
          description={
            running
              ? 'Verifying likely claims while scanning the complete paper'
              : sourceSearching
                ? 'Searching the local library, OpenAlex, and Semantic Scholar'
                : status === 'completed'
                  ? `${openFindingCount} open · ${resolvedFindingIds.size} resolved`
                  : 'The scan could not be completed'
          }
        >
          <CardAction>
            {busy ? (
              <Badge intent="info">
                <Processing className="animate-spin" data-slot="icon" />
                {running ? `Reviewing · ${percentage}%` : 'Finding sources'}
              </Badge>
            ) : status === 'completed' ? (
              <Badge intent={openFindingCount ? 'warning' : 'success'}>
                {openFindingCount ? (
                  <Warning data-slot="icon" />
                ) : (
                  <Complete data-slot="icon" />
                )}
                {openFindingCount ? 'Review suggested' : 'All resolved'}
              </Badge>
            ) : (
              <Badge intent="danger">Scan incomplete</Badge>
            )}
          </CardAction>
        </CardHeader>

      {findings.length ? (
        <CardContent className="min-h-0 flex-1 overflow-y-auto border-t px-4 py-0">
          <ol className="divide-y divide-border">
            {findings.map((finding) => {
              const findingResolved = resolvedFindingIds.has(finding.id)
              return (
                <li className="py-5" key={finding.id}>
                <div className="flex items-start justify-between gap-3">
                  <p className="text-xs font-medium text-muted-fg">{finding.sectionTitle}</p>
                  {findingResolved ? (
                    <Badge intent="success">
                      <Complete data-slot="icon" />
                      Citation added
                    </Badge>
                  ) : (
                    <Badge intent="outline">
                      <Ai data-slot="icon" />
                      {Math.round(finding.confidence * 100)}%
                    </Badge>
                  )}
                </div>
                <p className="mt-1.5 text-sm/6 font-medium text-fg">“{finding.claimText}”</p>
                <p className="mt-1 text-xs/5 text-muted-fg">{finding.explanation}</p>
                {onFindingFeedback || onFindingSelect ? (
                  <div className="mt-2 flex gap-1.5">
                    {onFindingSelect ? (
                      <Button
                        size="sm"
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
                      >
                        View in manuscript
                      </Button>
                    ) : null}
                    {onFindingFeedback && !findingResolved ? (
                      <Button
                        size="sm"
                        intent="secondary"
                        isDisabled={decisionPending}
                        onPress={() => {
                          setDismissalError(null)
                          setPendingDismissal(finding)
                        }}
                      >
                        Not a missing citation
                      </Button>
                    ) : null}
                  </div>
                ) : null}
                {['not_started', 'queued', 'running'].includes(finding.sourceSearchStatus) ? (
                  <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-fg">
                    <Processing className="size-3 animate-spin" />
                    Looking for supporting research…
                  </p>
                ) : finding.sourceCandidates.length ? (
                  <div className="mt-3 space-y-2">
                    <p className="flex items-center gap-1.5 text-xs font-medium text-muted-fg">
                      <Source className="size-3.5" />
                      Suggested sources
                    </p>
                    <ol className="space-y-2">
                      {finding.sourceCandidates.slice(0, 3).map((candidate) => {
                        const citationApplied =
                          appliedReferenceIdsByParagraph
                            ?.get(finding.paragraphId)
                            ?.has(`source-${candidate.work.id}`) === true
                        const insertionProposal =
                          edits?.proposal?.command ===
                            `Use verified source ${candidate.work.title}` &&
                          edits?.proposal?.operations.some(
                            (operation) =>
                              operation.operationType === 'insert_citation' &&
                              operation.nodeIds.includes(finding.paragraphId),
                          ) === true
                        const removalProposal =
                          edits?.proposal?.command ===
                            `Remove verified source ${candidate.work.title}` &&
                          edits?.proposal?.operations.some(
                            (operation) =>
                              operation.operationType === 'remove_citation' &&
                              operation.nodeIds.includes(finding.paragraphId),
                          ) === true
                        return (
                          <li className="rounded-lg border border-border p-2.5" key={candidate.id}>
                            {candidate.work.landingPageUrl ? (
                            <Link
                              className="flex items-start justify-between gap-2 text-xs/5 text-fg hover:underline"
                              href={candidate.work.landingPageUrl}
                              rel="noreferrer"
                              target="_blank"
                            >
                              <span>{candidate.work.title}</span>
                              <ExternalLink className="mt-0.5 size-3 shrink-0 text-muted-fg" />
                            </Link>
                            ) : (
                              <p className="text-xs/5 text-fg">{candidate.work.title}</p>
                            )}
                            <p className="mt-1 text-[11px] text-muted-fg">
                            {[
                              candidate.work.year,
                              candidate.work.providers
                                .map((provider) =>
                                  provider === 'openalex' ? 'OpenAlex' : 'Semantic Scholar',
                                )
                                .join(' + '),
                            ]
                              .filter(Boolean)
                              .join(' · ')}
                            </p>
                            {candidate.supportExplanation ? (
                              <Tooltip delay={300}>
                                <Button className="mt-2" intent="plain" size="xs">
                                  <InfoIcon data-slot="icon" />
                                  Why this source?
                                </Button>
                                <TooltipContent className="max-w-sm" placement="top start">
                                  <strong>Why it supports the claim</strong>
                                  <p className="mt-1 text-pretty text-sm text-muted-fg">
                                    {candidate.supportExplanation}
                                  </p>
                                </TooltipContent>
                              </Tooltip>
                            ) : null}
                            {candidate.supportEvidence ? (
                              <div className="mt-2">
                                <p className="text-[10px] font-medium uppercase tracking-wide text-muted-fg">
                                  Evidence from provider abstract
                                </p>
                                <blockquote className="mt-1 text-[11px]/4 text-muted-fg">
                                  “{candidate.supportEvidence}”
                                </blockquote>
                              </div>
                            ) : null}
                            {onCandidateDecision ? (
                            <div className="mt-2 flex gap-1.5">
                              {citationApplied && onCandidateRemoval ? (
                                <Button
                                  size="sm"
                                  intent="danger"
                                  isDisabled={decisionPending}
                                  onPress={() =>
                                    void selectSource(
                                      {
                                        action: 'remove',
                                        candidateId: candidate.id,
                                        findingId: finding.id,
                                        paragraphId: finding.paragraphId,
                                        title: candidate.work.title,
                                      },
                                      removalProposal,
                                    )
                                  }
                                >
                                  <TrashIcon data-slot="icon" />
                                  Remove source
                                </Button>
                              ) : (
                                <Button
                                  size="sm"
                                  intent={insertionProposal ? 'success' : 'secondary'}
                                  isDisabled={decisionPending}
                                  onPress={() =>
                                    void selectSource(
                                      {
                                        action: 'add',
                                        candidateId: candidate.id,
                                        findingId: finding.id,
                                        paragraphId: finding.paragraphId,
                                        title: candidate.work.title,
                                      },
                                      insertionProposal,
                                    )
                                  }
                                >
                                  <CheckIcon data-slot="icon" />
                                  Use source
                                </Button>
                              )}
                              <Button
                                size="sm"
                                intent={candidate.decision === 'rejected' ? 'danger' : 'secondary'}
                                isDisabled={
                                  decisionPending ||
                                  citationApplied ||
                                  insertionProposal ||
                                  removalProposal
                                }
                                onPress={() =>
                                  onCandidateDecision(finding.id, candidate.id, 'rejected')
                                }
                              >
                                <XMarkIcon data-slot="icon" />
                              </Button>
                            </div>
                            ) : null}
                          </li>
                        )
                      })}
                    </ol>
                  </div>
                ) : finding.sourceSearchStatus === 'completed' ? (
                  <p className="mt-2 text-xs text-muted-fg">No strong source candidates found.</p>
                ) : finding.sourceSearchStatus === 'failed' ? (
                  <p className="mt-2 text-xs text-danger-subtle-fg">
                    Source search could not be completed.
                  </p>
                ) : null}
                </li>
              )
            })}
          </ol>
        </CardContent>
      ) : status === 'completed' ? (
        <CardContent className="border-t px-4 py-4 text-sm text-muted-fg">
          No high-confidence unsupported claims were detected.
        </CardContent>
      ) : status === 'failed' ? (
        <CardContent className="border-t px-4 py-4 text-sm text-danger-subtle-fg">
          {error || 'The citation audit stopped before it finished.'}
        </CardContent>
      ) : null}
      </Card>
      <ModalContent
        isDismissable={
          !preparingProposal && !edits?.isApproving && !edits?.isDiscarding
        }
        isOpen={activeSource != null}
        onOpenChange={(isOpen) => {
          if (!isOpen) void cancelProposal()
        }}
        size="2xl"
      >
        <ModalHeader>
          <ModalTitle>
            {blockingProposal ? 'Resolve current proposal' : 'Review citation proposal'}
          </ModalTitle>
          <ModalDescription>
            {blockingProposal
              ? 'Only one manuscript proposal can await approval at a time.'
              : activeSource
              ? activeSource.action === 'remove'
                ? `Confirm the exact manuscript change before removing ${activeSource.title}.`
                : `Confirm the exact manuscript change before citing ${activeSource.title}.`
              : 'Confirm the exact manuscript change before adding this source.'}
          </ModalDescription>
        </ModalHeader>
        <ModalBody className="pb-6">
          {preparingProposal ? (
            <div className="flex min-h-48 flex-col items-center justify-center gap-3 text-sm text-muted-fg">
              <Loader aria-label="Preparing citation proposal" className="size-5" />
              Preparing a safe citation diff…
            </div>
          ) : proposalError ? (
            <div className="space-y-4">
              <div
                className="rounded-lg border border-danger/30 bg-danger-subtle px-4 py-3 text-sm/6 text-danger-subtle-fg"
                role="alert"
              >
                {proposalError}
              </div>
              {blockingProposal && edits ? (
                <EditProposalThread edits={edits} onDecisionComplete={finishProposal} />
              ) : null}
            </div>
          ) : activeProposalReady && edits ? (
            <EditProposalThread edits={edits} onDecisionComplete={finishProposal} />
          ) : (
            <div className="flex min-h-48 flex-col items-center justify-center gap-3 text-sm text-muted-fg" role="status">
              <Loader aria-label="Loading citation proposal" className="size-5" />
              Loading the citation preview…
            </div>
          )}
        </ModalBody>
      </ModalContent>
      <ModalContent
        isDismissable={!confirmingDismissal}
        isOpen={pendingDismissal != null}
        onOpenChange={(isOpen) => {
          if (!isOpen) closeDismissal()
        }}
        role="alertdialog"
        size="md"
      >
        <ModalHeader>
          <ModalTitle>Dismiss this citation finding?</ModalTitle>
          <ModalDescription>
            Confirm that this claim does not need an external citation. You can restore it later
            from Dismissed Citations.
          </ModalDescription>
        </ModalHeader>
        <ModalBody>
          {pendingDismissal ? (
            <div className="rounded-lg border border-border bg-muted/40 px-3 py-3">
              <p className="text-xs font-medium text-muted-fg">
                {pendingDismissal.sectionTitle}
              </p>
              <p className="mt-1.5 text-sm/6 font-medium text-fg">
                “{pendingDismissal.claimText}”
              </p>
            </div>
          ) : null}
          {dismissalError ? (
            <div
              className="mt-3 rounded-lg border border-danger/30 bg-danger-subtle px-3 py-3 text-sm/6 text-danger-subtle-fg"
              role="alert"
            >
              {dismissalError}
            </div>
          ) : null}
        </ModalBody>
        <ModalFooter>
          <Button
            intent="outline"
            isDisabled={confirmingDismissal}
            onPress={closeDismissal}
          >
            Cancel
          </Button>
          <Button
            intent="warning"
            isDisabled={confirmingDismissal}
            onPress={() => void confirmDismissal()}
          >
            {confirmingDismissal ? 'Dismissing…' : 'Dismiss finding'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </>
  )
}
