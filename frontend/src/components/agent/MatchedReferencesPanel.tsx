import {
  ArrowSquareOutIcon as ExternalLink,
  CheckCircleIcon as Complete,
  LinkIcon as Match,
  SpinnerGapIcon as Processing,
} from '@phosphor-icons/react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardHeader } from '@/components/ui/card'
import type { EnrichmentState } from '@/hooks/use-paper'
import type { PaperReferenceJson } from '@/lib/paper'

interface MatchedReferencesPanelProps {
  enrichment: EnrichmentState
  references: PaperReferenceJson[]
}

function referenceTitle(reference: PaperReferenceJson) {
  return (
    reference.openalex?.title ||
    reference.csl?.title ||
    reference.rawText?.split(/[.?]/)[0]?.trim() ||
    'Untitled reference'
  )
}

function matchDescription(reference: PaperReferenceJson) {
  const work = reference.openalex
  if (!work) return null
  const method = work.matchMethod === 'arxiv' ? 'arXiv' : work.matchMethod.toUpperCase()
  return [work.year, method, `${work.confidence} confidence`].filter(Boolean).join(' · ')
}

export function MatchedReferencesPanel({
  enrichment,
  references,
}: MatchedReferencesPanelProps) {
  const running =
    enrichment.status === 'starting' ||
    enrichment.status === 'queued' ||
    enrichment.status === 'running'
  const matched = references.filter(
    (reference) => reference.openalexStatus === 'matched' && reference.openalex,
  )

  return (
    <Card className="min-h-[20rem] overflow-hidden bg-overlay shadow-overlay [--gutter:--spacing(4)] lg:min-h-0">
      <CardHeader
        title="Matched references"
        description={
          running
            ? `Checking ${enrichment.completed} of ${enrichment.total} references`
            : enrichment.status === 'completed'
              ? `${matched.length} of ${enrichment.total} references matched`
              : 'Reference matching could not be completed'
        }
      >
        <CardAction>
          {running ? (
            <Badge intent="info">
              <Processing className="animate-spin" data-slot="icon" />
              Matching
            </Badge>
          ) : enrichment.status === 'completed' ? (
            <Badge intent="success">
              <Complete data-slot="icon" />
              {matched.length} matched
            </Badge>
          ) : (
            <Badge intent="danger">Unavailable</Badge>
          )}
        </CardAction>
      </CardHeader>

      {matched.length ? (
        <CardContent className="min-h-0 flex-1 overflow-y-auto border-t px-4 py-0">
          <ol className="divide-y divide-border">
            {matched.map((reference) => {
              const work = reference.openalex
              const href = work?.landingPageUrl || work?.id
              return (
                <li className="py-3.5" key={reference.id}>
                  <div className="flex items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 text-xs font-medium text-success">
                        <Match className="size-3.5" />
                        Matched
                      </div>
                      <p className="mt-1.5 text-sm/6 font-medium text-fg">
                        {referenceTitle(reference)}
                      </p>
                      {work ? (
                        <p className="mt-1 text-xs/5 text-muted-fg">
                          {matchDescription(reference)}
                        </p>
                      ) : null}
                    </div>
                    {href ? (
                      <Button
                        aria-label={`Open ${referenceTitle(reference)}`}
                        intent="plain"
                        onPress={() => window.open(href, '_blank', 'noopener,noreferrer')}
                        size="sq-xs"
                      >
                        <ExternalLink />
                      </Button>
                    ) : null}
                  </div>
                </li>
              )
            })}
          </ol>
        </CardContent>
      ) : enrichment.status === 'completed' ? (
        <CardContent className="border-t px-4 py-4 text-sm text-muted-fg">
          No bibliography entries could be matched.
        </CardContent>
      ) : null}
    </Card>
  )
}
