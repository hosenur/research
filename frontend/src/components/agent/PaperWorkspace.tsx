import { useEffect, useRef, useState, type CSSProperties } from 'react'
import {
  ArrowCounterClockwiseIcon as RotateCcw,
  ArrowSquareOutIcon as ExternalLink,
  BooksIcon,
  ChatCenteredTextIcon,
  ClipboardTextIcon,
  FilePdfIcon,
  ExportIcon,
  RowsIcon,
} from '@phosphor-icons/react'
import { AgentChat } from '@/components/agent/AgentChat'
import { ExportPanel } from '@/components/agent/ExportPanel'
import { MatchedReferencesPanel } from '@/components/agent/MatchedReferencesPanel'
import {
  PaperManuscript,
  type ManuscriptFocus,
} from '@/components/agent/PaperManuscript'
import { ReviewInbox } from '@/components/agent/ReviewInbox'
import { SectionReviewPanel } from '@/components/agent/SectionReviewPanel'
import { Badge } from '@/components/ui/badge'
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
import type { PaperJson } from '@/lib/paper'

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
  const [manuscriptFocus, setManuscriptFocus] = useState<ManuscriptFocus | null>(null)
  const focusTimer = useRef<number | null>(null)
  const { enrichment, paper: currentPaper } = useOpenAlexEnrichment({
    initialRevision: documentRevision,
    paper,
    paperId,
  })
  const citationAudit = useCitationAudit(paperId)
  const claimCitationReview = useClaimCitationReview(paperId)
  const manuscriptEdits = useManuscriptEdits(paperId)

  useEffect(
    () => () => {
      if (focusTimer.current != null) window.clearTimeout(focusTimer.current)
    },
    [],
  )

  function focusManuscriptNode(
    paragraphId: string,
    startOffset?: number,
    endOffset?: number,
    text?: string,
  ) {
    setManuscriptFocus({ paragraphId, startOffset, endOffset, text, token: Date.now() })
    const node = document.getElementById(`node-${paragraphId}`)
    node?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    if (focusTimer.current != null) window.clearTimeout(focusTimer.current)
    focusTimer.current = window.setTimeout(() => setManuscriptFocus(null), 4_100)
  }

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
              <Badge intent="success">Review ready</Badge>
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
            <Tabs className="min-h-0 flex-1 gap-2 self-stretch" defaultSelectedKey="review">
              <TabList aria-label="Paper tools" className="shrink-0 px-2">
                <Tab id="review"><ClipboardTextIcon />Review</Tab>
                <Tab id="agent"><ChatCenteredTextIcon />Agent</Tab>
                <Tab id="references"><BooksIcon />References</Tab>
                <Tab id="export"><ExportIcon />Export</Tab>
              </TabList>
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
                    onFindingSelect={focusManuscriptNode}
                    paper={currentPaper}
                  />
                </div>
                </div>
              </TabPanel>
              <TabPanel className="min-h-0 overflow-hidden" id="agent">
                <AgentChat
                  className="h-full min-h-0"
                  edits={manuscriptEdits}
                  paper={currentPaper}
                  paperId={paperId}
                  revision={paperRevision}
                />
              </TabPanel>
              <TabPanel className="min-h-0 overflow-hidden" id="references">
                <MatchedReferencesPanel
                  enrichment={enrichment}
                  references={currentPaper.references}
                />
              </TabPanel>
              <TabPanel className="min-h-0 overflow-hidden" id="export">
                <ExportPanel paperId={paperId} revision={paperRevision} />
              </TabPanel>
            </Tabs>
          </SidebarContent>
        </Sidebar>
      </SidebarProvider>
    </section>
  )
}
