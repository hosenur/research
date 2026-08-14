import {
  ArrowPathIcon as Processing,
  CheckCircleIcon as Complete,
  ExclamationTriangleIcon as Warning,
  ArrowTopRightOnSquareIcon as ExternalLink,
  BookOpenIcon as Source,
  SparklesIcon as Ai,
  CheckIcon,
  XMarkIcon,
} from '@heroicons/react/24/solid'
import { Badge } from '@/components/ui/badge'
import { Card, CardAction, CardContent, CardHeader } from '@/components/ui/card'
import { Link } from '@/components/ui/link'
import type { CitationAuditFinding } from '@/hooks/use-citation-audit'
import { twMerge } from 'tailwind-merge'
import { Button } from '@/components/ui/button'

interface CitationAuditPanelProps {
  className?: string
  error: string | null
  findings: CitationAuditFinding[]
  percentage: number
  status: 'not_started' | 'queued' | 'running' | 'completed' | 'failed'
  onCandidateDecision?: (findingId: string, candidateId: string, decision: 'accepted' | 'rejected') => void
  onFindingFeedback?: (findingId: string, feedback: 'false_positive' | 'needs_review') => void
  decisionPending?: boolean
}

export function CitationAuditPanel({
  className,
  error,
  findings,
  percentage,
  status,
  onCandidateDecision,
  onFindingFeedback,
  decisionPending = false,
}: CitationAuditPanelProps) {
  const running = status === 'not_started' || status === 'queued' || status === 'running'
  const sourceSearching = findings.some((finding) =>
    ['not_started', 'queued', 'running'].includes(finding.sourceSearchStatus),
  )
  const busy = running || sourceSearching
  return (
    <Card
      className={twMerge(
        'min-h-0 overflow-hidden bg-overlay shadow-overlay [--gutter:--spacing(4)]',
        className,
      )}
    >
      <CardHeader
        title="Likely missing citations"
        description={
          running
            ? 'Verifying likely claims while scanning the complete paper'
            : sourceSearching
              ? 'Searching the local library, OpenAlex, and Semantic Scholar'
            : status === 'completed'
              ? `${findings.length} high-confidence ${findings.length === 1 ? 'finding' : 'findings'}`
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
            <Badge intent={findings.length ? 'warning' : 'success'}>
              {findings.length ? <Warning data-slot="icon" /> : <Complete data-slot="icon" />}
              {findings.length ? 'Review suggested' : 'No findings'}
            </Badge>
          ) : (
            <Badge intent="danger">Scan incomplete</Badge>
          )}
        </CardAction>
      </CardHeader>

      {findings.length ? (
        <CardContent className="min-h-0 flex-1 overflow-y-auto border-t px-4 py-0">
          <ol className="divide-y divide-border">
            {findings.map((finding) => (
              <li className="py-3.5" key={finding.id}>
                <div className="flex items-start justify-between gap-3">
                  <p className="text-xs font-medium text-muted-fg">{finding.sectionTitle}</p>
                  <Badge intent="outline">
                    <Ai data-slot="icon" />
                    {Math.round(finding.confidence * 100)}%
                  </Badge>
                </div>
                <p className="mt-1.5 text-sm/6 font-medium text-fg">“{finding.claimText}”</p>
                <p className="mt-1 text-xs/5 text-muted-fg">{finding.explanation}</p>
                {onFindingFeedback ? (
                  <div className="mt-2 flex gap-1.5">
                    <Button
                      size="sm"
                      intent="secondary"
                      isDisabled={decisionPending}
                      onClick={() => onFindingFeedback(finding.id, 'false_positive')}
                    >
                      Not a missing citation
                    </Button>
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
                      {finding.sourceCandidates.slice(0, 3).map((candidate) => (
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
                            <p className="mt-2 text-[11px]/4 text-muted-fg">{candidate.supportExplanation}</p>
                          ) : null}
                          {candidate.supportEvidence ? (
                            <p className="mt-1 border-l-2 border-border pl-2 text-[11px]/4 text-muted-fg">“{candidate.supportEvidence}”</p>
                          ) : null}
                          {onCandidateDecision ? (
                            <div className="mt-2 flex gap-1.5">
                              <Button size="sm" intent={candidate.decision === 'accepted' ? 'success' : 'secondary'} isDisabled={decisionPending} onClick={() => onCandidateDecision(finding.id, candidate.id, 'accepted')}>
                                <CheckIcon data-slot="icon" /> {candidate.decision === 'accepted' ? 'Accepted' : 'Use source'}
                              </Button>
                              <Button size="sm" intent={candidate.decision === 'rejected' ? 'danger' : 'secondary'} isDisabled={decisionPending} onClick={() => onCandidateDecision(finding.id, candidate.id, 'rejected')}>
                                <XMarkIcon data-slot="icon" />
                              </Button>
                            </div>
                          ) : null}
                        </li>
                      ))}
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
            ))}
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
  )
}
