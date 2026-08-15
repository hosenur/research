import type { CSSProperties } from 'react'
import {
  ArrowClockwiseIcon as Refresh,
  BooksIcon,
  ChatCenteredTextIcon,
  ClipboardTextIcon,
  PlusIcon as NewPaper,
  WarningIcon as Warning,
} from '@phosphor-icons/react'
import { AgentChat } from '@/components/agent/AgentChat'
import { Button } from '@/components/ui/button'
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
            <p className="min-w-0 truncate text-sm font-medium text-fg">
              {lifecycle.filename}
            </p>
            <Button intent="outline" onPress={onReset} size="sm">
              <NewPaper />
              New paper
            </Button>
          </header>

          <div className="flex min-h-0 flex-1 items-center justify-center bg-bg">
            {failed ? (
              <div className="flex max-w-sm flex-col items-center gap-3 px-6 text-center">
                <Warning className="size-6 text-danger-subtle-fg" />
                <p className="text-sm font-medium text-fg">
                  Paper preview could not be prepared.
                </p>
                {lifecycle.error ? (
                  <p className="text-sm/6 text-muted-fg" role="alert">
                    {lifecycle.error}
                  </p>
                ) : null}
                <Button intent="outline" onPress={onRefresh} size="sm">
                  <Refresh />
                  Try again
                </Button>
              </div>
            ) : (
              <UiProvider>
                <LoadingState label="Preparing paper" variant="Drive" />
              </UiProvider>
            )}
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
                    className="flex h-full min-h-80 flex-col items-center justify-center gap-3 px-6 text-center"
                    role="status"
                  >
                    {chatIndexFailed ? (
                      <Warning className="size-6 text-danger-subtle-fg" />
                    ) : null}
                    <p className="text-sm text-muted-fg">
                      {chatIndexFailed ? 'Chat indexing failed.' : 'Preparing chat…'}
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
