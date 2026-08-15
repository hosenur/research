import type { CSSProperties } from 'react'
import {
  ArrowSquareOutIcon as ExternalLink,
  PlusIcon as NewPaper,
  SpinnerGapIcon as Processing,
  WarningIcon as Warning,
} from '@phosphor-icons/react'
import { AgentChat } from '@/components/agent/AgentChat'
import { PaperPipelineStatus } from '@/components/agent/PaperPipelineStatus'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import {
  Sidebar,
  SidebarContent,
  SidebarInset,
  SidebarProvider,
} from '@/components/ui/sidebar'
import type { PaperLifecycleJson } from '@/lib/paper'

interface PaperPendingWorkspaceProps {
  lifecycle: PaperLifecycleJson
  onRefresh: () => void
  onReset: () => void
  pdfUrl: string
}

export function PaperPendingWorkspace({
  lifecycle,
  onRefresh,
  onReset,
  pdfUrl,
}: PaperPendingWorkspaceProps) {
  const failed = lifecycle.status === 'failed'
  const quickReadReady = lifecycle.retrievalMode === 'provisional'

  return (
    <section aria-label="Research paper workspace" className="min-h-dvh w-full bg-bg">
      <SidebarProvider
        className="min-h-dvh max-lg:flex-col lg:h-dvh lg:overflow-hidden"
        style={{ '--sidebar-width': 'clamp(18rem,58vw,64rem)' } as CSSProperties}
      >
        <Sidebar
          aria-label="PDF preview"
          className="max-lg:h-[40rem] max-lg:w-full lg:border-r lg:border-sidebar-border"
          collapsible="none"
          side="left"
        >
          <SidebarContent className="overflow-hidden p-2">
            <div className="relative min-h-0 flex-1 overflow-hidden rounded-lg border border-sidebar-border bg-muted">
              <div className="absolute right-2 top-2 z-10 flex items-center gap-1.5 rounded-lg border border-border bg-overlay/95 p-1 shadow-sm backdrop-blur-sm">
                <Button
                  aria-label="Open PDF in a new tab"
                  intent="plain"
                  onPress={() => window.open(pdfUrl, '_blank', 'noopener,noreferrer')}
                  size="sq-xs"
                >
                  <ExternalLink />
                </Button>
                <Button intent="outline" onPress={onReset} size="xs">
                  <NewPaper />
                  New paper
                </Button>
              </div>
              <object
                aria-label={`Preview of ${lifecycle.filename}`}
                className="size-full min-h-0"
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
          </SidebarContent>
        </Sidebar>

        <SidebarInset className="min-h-0 max-lg:w-full">
          <div className="flex min-h-full flex-col gap-3 p-4 sm:p-6">
            <Card className="bg-overlay shadow-overlay">
              <CardHeader
                title={failed ? 'Paper parsing needs attention' : 'Building your review workspace'}
                description={
                  failed
                    ? 'The original PDF is safe. Background retries may still recover this paper.'
                    : quickReadReady
                      ? 'Ask broad questions now while GROBID extracts citation-safe structure.'
                      : 'Keep reading the PDF while fast text extraction and GROBID run together.'
                }
              />
              <CardContent className="border-t px-4 py-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <Badge intent={failed ? 'danger' : 'info'}>
                    {failed ? (
                      <Warning data-slot="icon" />
                    ) : (
                      <Processing className="animate-spin" data-slot="icon" />
                    )}
                    {failed ? 'Parse failed' : 'Authoritative parse running'}
                  </Badge>
                  {quickReadReady ? (
                    <Badge intent="warning">Quick read · provisional</Badge>
                  ) : null}
                  {failed ? (
                    <Button intent="outline" onPress={onRefresh} size="sm">
                      <Processing />
                      Check again
                    </Button>
                  ) : null}
                </div>
                {lifecycle.error ? (
                  <p className="mt-3 text-sm/6 text-danger-subtle-fg" role="alert">
                    {lifecycle.error}
                  </p>
                ) : (
                  <p className="mt-3 text-sm/6 text-muted-fg">
                    {quickReadReady
                      ? 'Broad paper chat is ready. Citation review and editing remain locked until the authoritative parse arrives.'
                      : 'Quick read will unlock broad chat first; citation-sensitive actions unlock with the authoritative paper model.'}
                  </p>
                )}
              </CardContent>
            </Card>
            <PaperPipelineStatus paperId={lifecycle.id} />
            {quickReadReady ? (
              <Card className="flex min-h-[32rem] flex-1 flex-col overflow-hidden bg-overlay shadow-overlay">
                <CardHeader
                  title="Quick read"
                  description="Answers use rough PDF text and automatically switch to authoritative context when parsing finishes."
                />
                <CardContent className="min-h-0 flex-1 border-t p-0">
                  <AgentChat
                    className="h-full min-h-0"
                    paper={null}
                    paperId={lifecycle.id}
                  />
                </CardContent>
              </Card>
            ) : null}
          </div>
        </SidebarInset>
      </SidebarProvider>
    </section>
  )
}
