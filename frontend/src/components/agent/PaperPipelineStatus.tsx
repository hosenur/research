import {
  CheckCircleIcon as Complete,
  ExclamationTriangleIcon as Warning,
  ArrowPathIcon as Processing,
} from '@heroicons/react/24/solid'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { usePaperJobs } from '@/hooks/use-paper-jobs'

interface PaperPipelineStatusProps {
  paperId: string
}

const labels: Record<string, string> = {
  index: 'Paper index',
  openalex: 'Reference enrichment',
  'citation-audit': 'Citation audit',
}

export function PaperPipelineStatus({ paperId }: PaperPipelineStatusProps) {
  const { data, error } = usePaperJobs(paperId)

  return (
    <Card className="shrink-0 bg-overlay shadow-overlay">
      <CardHeader title="Processing status" description="Background work continues while you review" />
      <CardContent className="border-t px-4 py-3">
        {error ? <p className="text-xs text-danger-subtle-fg">Status unavailable.</p> : (
          <ul className="space-y-2">
            {(data?.jobs ?? []).map((job) => (
              <li className="flex items-center justify-between gap-2 text-xs" key={job.jobId}>
                <span className="text-muted-fg">{labels[job.name] ?? job.name}</span>
                <Badge intent={job.status === 'failed' ? 'danger' : job.status === 'completed' ? 'success' : 'info'}>
                  {job.status === 'running' || job.status === 'queued' ? <Processing className="animate-spin" data-slot="icon" /> : null}
                  {job.status === 'completed' ? <Complete data-slot="icon" /> : null}
                  {job.status === 'failed' ? <Warning data-slot="icon" /> : null}
                  {job.status.replace('_', ' ')}
                </Badge>
              </li>
            ))}
            {!data?.jobs.length && !error ? <li className="text-xs text-muted-fg">No jobs have started.</li> : null}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
