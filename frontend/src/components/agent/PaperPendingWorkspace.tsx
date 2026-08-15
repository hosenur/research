import type { CSSProperties } from 'react'
import {
  BooksIcon,
  ChatCenteredTextIcon,
  ClipboardTextIcon,
  PlusIcon as NewPaper,
  SpinnerGapIcon as Processing,
  WarningIcon as Warning,
} from '@phosphor-icons/react'
import { AgentChat } from '@/components/agent/AgentChat'
import { PaperPipelineStatus } from '@/components/agent/PaperPipelineStatus'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import LoadingState from '@/components/ui/LoadingState'
import {
  Sidebar,
  SidebarContent,
  SidebarInset,
  SidebarProvider,
} from '@/components/ui/sidebar'
import { Tab, TabList, TabPanel, Tabs } from '@/components/ui/tabs'
import { UiProvider } from '@/components/ui/UiProvider'
import { usePaperJobs } from '@/hooks/use-paper-jobs'
import type { PaperLifecycleJson } from '@/lib/paper'

interface PaperPendingWorkspaceProps {
  lifecycle: PaperLifecycleJson
  onRefresh: () => void
  onReset: () => void
}

export function PaperPendingWorkspace({
  lifecycle,
  onRefresh,
  onReset,
}: PaperPendingWorkspaceProps) {
  const { data: pipeline } = usePaperJobs(lifecycle.id)
  const parseStatus = pipeline?.jobs.find(
    (job) => job.name === 'authoritative-parse',
  )?.status
  const quickIndexStatus = pipeline?.jobs.find(
    (job) => job.name === 'quick-index',
  )?.status
  const chatReady =
    lifecycle.retrievalMode !== 'unavailable' || quickIndexStatus === 'completed'
  const chatIndexFailed = quickIndexStatus === 'failed'
  const lifecycleFailed = lifecycle.status === 'failed'
  const recovering =
    lifecycleFailed &&
    (!pipeline || ['queued', 'running', 'completed'].includes(parseStatus ?? ''))
  const failed = lifecycleFailed && !recovering

  return (
    <section
      aria-label="Research paper workspace"
      className="workspace-enter min-h-dvh w-full bg-bg"
    >
      <SidebarProvider
        className="min-h-dvh lg:h-dvh lg:overflow-hidden"
        style={{ '--sidebar-width': 'clamp(21rem,30vw,29rem)' } as CSSProperties}
      >
        <SidebarInset className="min-h-0 min-w-0">
          <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-border bg-overlay px-3 sm:px-4">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-fg">
                {lifecycle.filename}
              </p>
              <p className="text-xs text-muted-fg">
                {chatReady
                  ? 'Chat ready · paper analysis continues'
                  : chatIndexFailed
                    ? 'Chat index delayed · structured parsing continues'
                    : 'Chunking and vectorizing for chat'}
              </p>
            </div>
            <Button intent="outline" onPress={onReset} size="sm">
              <NewPaper />
              New paper
            </Button>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto bg-bg p-4 sm:p-6">
            <div className="mx-auto w-full max-w-2xl space-y-3">
              <Card className="bg-overlay shadow-overlay">
                <CardHeader
                  title={
                    failed
                      ? 'Authoritative processing needs attention'
                      : recovering
                        ? 'Confirming paper processing'
                        : chatReady
                          ? 'Chat is ready'
                          : 'Preparing chat first'
                  }
                  description={
                    failed
                      ? chatReady
                        ? 'Indexed chat remains available while you review or retry the failed stage.'
                        : 'Review or retry the failed stage while the workspace checks for an available index.'
                      : recovering
                        ? chatReady
                          ? 'A background retry is running. Indexed chat remains available.'
                          : 'A background retry is running. Chat will unlock when an index becomes available.'
                        : chatReady
                          ? 'Ask about the paper now. Citation-safe structure and review results will unlock here as background work finishes.'
                          : 'Extracting text, creating chunks, and generating embeddings before enabling grounded chat.'
                  }
                />
                <CardContent className="border-t px-4 py-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <Badge intent={failed || chatIndexFailed ? 'danger' : 'info'}>
                      {failed || chatIndexFailed ? (
                        <Warning data-slot="icon" />
                      ) : chatReady ? null : (
                        <Processing className="animate-spin" data-slot="icon" />
                      )}
                      {failed
                        ? 'Some analysis is unavailable'
                        : chatIndexFailed
                          ? 'Chat indexing needs attention'
                          : chatReady
                            ? 'Provisional vector index ready'
                            : 'Building vector index'}
                    </Badge>
                    {failed || chatIndexFailed ? (
                      <Button intent="outline" onPress={onRefresh} size="sm">
                        <Processing />
                        Refresh status
                      </Button>
                    ) : null}
                  </div>
                  {lifecycle.error ? (
                    <p className="mt-3 text-sm/6 text-danger-subtle-fg" role="alert">
                      {lifecycle.error}
                    </p>
                  ) : (
                    <p className="mt-3 text-sm/6 text-muted-fg">
                      Background parsing, reference resolution, citation review, and the
                      authoritative index continue without leaving this workspace.
                    </p>
                  )}
                </CardContent>
              </Card>
              <PaperPipelineStatus paperId={lifecycle.id} />
            </div>
          </div>
        </SidebarInset>

        <Sidebar
          aria-label="Paper context"
          className="max-lg:w-full lg:border-l lg:border-sidebar-border"
          collapsible="none"
          side="right"
        >
          <SidebarContent className="overflow-hidden p-2">
            <Tabs className="min-h-0 flex-1 gap-2 self-stretch" selectedKey="agent">
              <TabList aria-label="Paper tools" className="shrink-0 px-2">
                <Tab id="agent">
                  <ChatCenteredTextIcon />Agent
                </Tab>
                <Tab id="review" isDisabled>
                  <ClipboardTextIcon />Review
                </Tab>
                <Tab id="references" isDisabled>
                  <BooksIcon />References
                </Tab>
              </TabList>
              <TabPanel className="min-h-0 overflow-hidden" id="agent">
                {chatReady ? (
                  <AgentChat
                    className="h-full min-h-0"
                    paper={null}
                    paperId={lifecycle.id}
                  />
                ) : (
                  <div
                    className="flex h-full min-h-80 flex-col items-center justify-center gap-4 px-6 text-center"
                    role="status"
                  >
                    {chatIndexFailed ? (
                      <Warning className="size-6 text-danger-subtle-fg" />
                    ) : (
                      <UiProvider>
                        <LoadingState
                          label="Chunking and vectorizing PDF"
                          variant="Drive"
                        />
                      </UiProvider>
                    )}
                    <p className="max-w-xs text-sm/6 text-muted-fg">
                      {chatIndexFailed
                        ? 'The fast chat index could not finish. Structured parsing is still running and may unlock the authoritative workspace.'
                        : 'Grounded chat opens here automatically as soon as the first vector index is ready.'}
                    </p>
                  </div>
                )}
              </TabPanel>
            </Tabs>
          </SidebarContent>
        </Sidebar>
      </SidebarProvider>
    </section>
  )
}
