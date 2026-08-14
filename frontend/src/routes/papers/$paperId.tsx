import { createFileRoute } from '@tanstack/react-router'
import { ExclamationTriangleIcon as Warning } from '@heroicons/react/24/solid'
import { PaperPendingWorkspace } from '@/components/agent/PaperPendingWorkspace'
import { PaperWorkspace } from '@/components/agent/PaperWorkspace'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { usePaperLifecycle } from '@/hooks/use-paper'

function PersistedPaperPage() {
  const { paperId } = Route.useParams()
  const navigate = Route.useNavigate()
  const lifecycle = usePaperLifecycle(paperId)
  const pdfUrl = `/api/papers/${paperId}/source`
  const reset = () => navigate({ to: '/' })

  if (lifecycle.error && !lifecycle.data) {
    return (
      <div className="grid min-h-dvh place-items-center p-4">
        <Card className="w-full max-w-lg bg-overlay shadow-overlay">
          <CardHeader
            title="Could not load this paper"
            description={
              lifecycle.error instanceof Error
                ? lifecycle.error.message
                : 'The paper workspace is unavailable.'
            }
          />
          <CardContent className="flex gap-2 border-t px-4 py-4">
            <Button intent="outline" onPress={() => void lifecycle.mutate()}>
              <Warning />
              Try again
            </Button>
            <Button onPress={reset}>Upload another paper</Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (!lifecycle.data) {
    return (
      <div className="grid min-h-dvh place-items-center p-4 text-sm text-muted-fg" role="status">
        Restoring paper workspace…
      </div>
    )
  }

  if (lifecycle.data.status !== 'ready' || !lifecycle.data.paper) {
    return (
      <PaperPendingWorkspace
        lifecycle={lifecycle.data}
        onRefresh={() => void lifecycle.mutate()}
        onReset={reset}
        pdfUrl={pdfUrl}
      />
    )
  }

  return (
    <PaperWorkspace
      filename={lifecycle.data.filename}
      onReset={reset}
      paper={lifecycle.data.paper}
      paperId={paperId}
      paperRevision={lifecycle.data.revision}
      pdfUrl={pdfUrl}
    />
  )
}

export const Route = createFileRoute('/papers/$paperId')({
  component: PersistedPaperPage,
})
