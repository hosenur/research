import {
  ArrowClockwiseIcon,
  CheckCircleIcon as Complete,
  SpinnerGapIcon as Processing,
  WarningIcon as Warning,
} from '@phosphor-icons/react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { usePaperJobs } from '@/hooks/use-paper-jobs'

interface PaperPipelineStatusProps {
  paperId: string
}

const labels: Record<string, string> = {
  upload: 'Upload secured',
  'quick-extraction': 'Quick text extraction',
  'quick-index': 'Quick read index',
  'authoritative-parse': 'Paper structure',
  'authoritative-index': 'Authoritative index',
  'reference-resolution': 'Reference enrichment',
  'missing-citation-review': 'Missing-work review',
  'existing-citation-review': 'Claim/citation review',
  export: 'Export',
}

export function PaperPipelineStatus({ paperId }: PaperPipelineStatusProps) {
  const { data, error, isLoading, retryStage, retrying } = usePaperJobs(paperId)

  return (
    <Card className="shrink-0 bg-overlay shadow-overlay">
      <CardHeader title="Processing status" description="Live progress for this paper" />
      <CardContent className="border-t px-4 py-3">
        {!data && (isLoading || error) ? (
          <p className="flex items-center gap-2 text-xs text-muted-fg" role="status">
            <Processing className="animate-spin" />
            {error ? 'Reconnecting to processing status…' : 'Loading processing status…'}
          </p>
        ) : (
          <ul className="space-y-2">
            {(data?.jobs ?? []).map((job) => (
              <li className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 text-xs" key={job.jobId}>
                <span className="text-muted-fg">
                  {labels[job.name] ?? job.name}
                  {job.durationMs != null ? ` · ${(job.durationMs / 1000).toFixed(1)}s` : ''}
                </span>
                <div className="flex items-center gap-1">
                <Badge intent={job.status === 'failed' ? 'danger' : job.status === 'completed' ? 'success' : job.status === 'skipped' ? 'warning' : 'info'}>
                  {job.status === 'running' || job.status === 'queued' ? <Processing className="animate-spin" data-slot="icon" /> : null}
                  {job.status === 'completed' ? <Complete data-slot="icon" /> : null}
                  {job.status === 'failed' ? <Warning data-slot="icon" /> : null}
                  {job.status.replace('_', ' ')}
                </Badge>
                {job.status === 'failed' && data?.supportsStageRetry ? (
                  <Button aria-label={`Retry ${labels[job.name] ?? job.name}`} intent="plain" isDisabled={retrying} onPress={() => void retryStage(job.name)} size="sq-xs">
                    <ArrowClockwiseIcon />
                  </Button>
                ) : null}
                </div>
                {typeof job.progress.reason === 'string' ? (
                  <p className="col-span-2 text-[11px]/4 text-warning-subtle-fg">{job.progress.reason}</p>
                ) : null}
              </li>
            ))}
            {!data?.jobs.length && !error ? <li className="text-xs text-muted-fg">No jobs have started.</li> : null}
            {error && data ? (
              <li className="flex items-center gap-2 text-xs text-muted-fg" role="status">
                <Processing className="animate-spin" />
                Refreshing the latest processing status…
              </li>
            ) : null}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
