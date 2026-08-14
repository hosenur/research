import { useEffect, useState, type CSSProperties } from 'react'
import {
  ArrowPathIcon as RotateCcw,
  ArrowTopRightOnSquareIcon as ExternalLink,
} from '@heroicons/react/24/solid'
import { AgentChat } from '@/components/agent/AgentChat'
import { CitationAuditPanel } from '@/components/agent/CitationAuditPanel'
import { MatchedReferencesPanel } from '@/components/agent/MatchedReferencesPanel'
import { PaperPipelineStatus } from '@/components/agent/PaperPipelineStatus'
import { Button } from '@/components/ui/button'
import {
  Sidebar,
  SidebarContent,
  SidebarInset,
  SidebarProvider,
} from '@/components/ui/sidebar'
import { useOpenAlexEnrichment } from '@/hooks/use-paper'
import { useCitationAudit } from '@/hooks/use-citation-audit'
import type { PaperJson } from '@/lib/paper'

interface PaperWorkspaceProps {
  file: File
  onReset: () => void
  paper: PaperJson
  paperId: string
  paperRevision: number
}

export function PaperWorkspace({
  file,
  onReset,
  paper,
  paperId,
  paperRevision,
}: PaperWorkspaceProps) {
  const [pdfUrl, setPdfUrl] = useState('')
  const { enrichment, paper: currentPaper } = useOpenAlexEnrichment({
    initialRevision: paperRevision,
    paper,
    paperId,
  })
  const citationAudit = useCitationAudit(paperId)

  useEffect(() => {
    const nextUrl = URL.createObjectURL(file)
    setPdfUrl(nextUrl)
    return () => URL.revokeObjectURL(nextUrl)
  }, [file])

  return (
    <section
      aria-label="Research paper workspace"
      className="workspace-enter min-h-dvh w-full bg-bg"
    >
      <SidebarProvider
        className="min-h-dvh max-lg:flex-col lg:h-dvh lg:overflow-hidden"
        style={{ '--sidebar-width': 'clamp(18rem,31vw,40rem)' } as CSSProperties}
      >
        <Sidebar
          aria-label="PDF preview"
          className="max-lg:h-[40rem] max-lg:w-full lg:border-r lg:border-sidebar-border"
          collapsible="none"
          side="left"
        >
          <SidebarContent className="overflow-hidden p-2">
            {pdfUrl ? (
              <div className="relative min-h-0 flex-1 overflow-hidden rounded-lg border border-sidebar-border bg-muted">
                <div className="absolute right-2 top-2 z-10 flex items-center gap-1.5 rounded-lg border border-border bg-overlay/95 p-1 shadow-sm backdrop-blur-sm">
                  <Button
                    aria-label="Open PDF in a new tab"
                    intent="plain"
                    isDisabled={!pdfUrl}
                    onPress={() => window.open(pdfUrl, '_blank', 'noopener,noreferrer')}
                    size="sq-xs"
                  >
                    <ExternalLink />
                  </Button>
                  <Button intent="outline" onPress={onReset} size="xs">
                    <RotateCcw />
                    New paper
                  </Button>
                </div>
                <object
                  aria-label={`Preview of ${file.name}`}
                  className="size-full min-h-0"
                  data={pdfUrl}
                  type="application/pdf"
                >
                  <div className="grid size-full place-items-center p-8 text-center text-sm text-muted-fg">
                    <div>
                      <p>Your browser cannot render this PDF inline.</p>
                      <Button
                        className="mt-3"
                        onPress={() => window.open(pdfUrl, '_blank')}
                        size="sm"
                      >
                        <ExternalLink />
                        Open PDF
                      </Button>
                    </div>
                  </div>
                </object>
              </div>
            ) : null}
          </SidebarContent>
        </Sidebar>

        <SidebarInset className="min-h-0 max-lg:w-full">
          <SidebarProvider
            className="min-h-0 flex-1 max-lg:flex-col"
            shortcut="j"
            style={{ '--sidebar-width': '22rem' } as CSSProperties}
          >
            <div className="min-h-[40rem] min-w-0 flex-1 lg:min-h-0">
              <AgentChat
                className="h-full min-h-0"
                paper={currentPaper}
                paperId={paperId}
              />
            </div>

            <Sidebar
              aria-label="Paper review"
              className="max-lg:h-auto max-lg:w-full lg:border-l lg:border-sidebar-border"
              collapsible="none"
              side="right"
            >
              <SidebarContent className="overflow-hidden p-2">
                <div className="grid min-h-0 flex-1 gap-2 lg:grid-rows-[auto_minmax(0,1fr)_minmax(0,1fr)]">
                  <PaperPipelineStatus paperId={paperId} />
                  <CitationAuditPanel
                    className="min-h-[20rem] lg:min-h-0"
                    error={citationAudit.error}
                    findings={citationAudit.findings}
                    percentage={citationAudit.percentage}
                    status={citationAudit.status}
                    onCandidateDecision={citationAudit.decideCandidate}
                    onFindingFeedback={citationAudit.reportFinding}
                    decisionPending={citationAudit.decisionPending}
                  />
                  <MatchedReferencesPanel
                    enrichment={enrichment}
                    references={currentPaper.references}
                  />
                </div>
              </SidebarContent>
            </Sidebar>
          </SidebarProvider>
        </SidebarInset>
      </SidebarProvider>
    </section>
  )
}
