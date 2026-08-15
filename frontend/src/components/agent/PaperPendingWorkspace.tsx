import {
  PlusIcon as NewPaper,
  SpinnerGapIcon as Processing,
  WarningIcon as Warning,
} from '@phosphor-icons/react'
import { PaperPipelineStatus } from '@/components/agent/PaperPipelineStatus'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
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
  const lifecycleFailed = lifecycle.status === 'failed'
  const recovering =
    lifecycleFailed &&
    (!pipeline || ['queued', 'running', 'completed'].includes(parseStatus ?? ''))
  const failed = lifecycleFailed && !recovering

  return (
    <main
      aria-label="Preparing research paper workspace"
      className="grid min-h-dvh place-items-center bg-bg p-4 sm:p-8"
    >
      <div className="w-full max-w-2xl space-y-3">
        <Card className="bg-overlay shadow-overlay">
          <CardHeader
            title={
              failed
                ? 'Paper processing was interrupted'
                : recovering
                  ? 'Confirming paper processing'
                  : 'Preparing your paper dashboard'
            }
            description={
              failed
                ? 'The original PDF is safe. Refresh the status or retry the failed stage below.'
                : recovering
                  ? 'A background retry is running. The dashboard will open automatically when it finishes.'
                  : `Extracting the manuscript structure from ${lifecycle.filename}. The dashboard will open automatically.`
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
                {failed
                  ? 'Processing interrupted'
                  : recovering
                    ? 'Checking background retry'
                    : 'Building structured manuscript'}
              </Badge>
              <div className="flex gap-2">
                {failed ? (
                  <Button intent="outline" onPress={onRefresh} size="sm">
                    <Processing />
                    Refresh status
                  </Button>
                ) : null}
                <Button intent="outline" onPress={onReset} size="sm">
                  <NewPaper />
                  New paper
                </Button>
              </div>
            </div>
            {failed && lifecycle.error ? (
              <p className="mt-3 text-sm/6 text-danger-subtle-fg" role="alert">
                {lifecycle.error}
              </p>
            ) : (
              <p className="mt-3 text-sm/6 text-muted-fg">
                {recovering
                  ? 'No upload action is needed while the latest attempt completes.'
                  : 'Sections, sentences, citations, and references are being prepared for review.'}
              </p>
            )}
          </CardContent>
        </Card>
        <PaperPipelineStatus paperId={lifecycle.id} />
      </div>
    </main>
  )
}
