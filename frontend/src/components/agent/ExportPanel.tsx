import {
  CheckCircleIcon,
  DownloadSimpleIcon,
  FilePdfIcon,
  FileZipIcon,
  SpinnerGapIcon,
  WarningIcon,
} from '@phosphor-icons/react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { usePaperExport } from '@/hooks/use-paper-export'

export function ExportPanel({ paperId, revision }: { paperId: string; revision: number }) {
  const exportFlow = usePaperExport(paperId, revision)
  const current = exportFlow.export
  return (
    <div className="h-full min-h-0 overflow-y-auto p-1">
      <Card className="bg-overlay shadow-overlay">
        <CardHeader
          title="Citation style"
          description="Citations and bibliography are rendered from canonical CSL-JSON through citeproc."
        >
          {exportFlow.style?.confirmed ? (
            <Badge intent="success"><CheckCircleIcon data-slot="icon" />Confirmed</Badge>
          ) : (
            <Badge intent="warning"><WarningIcon data-slot="icon" />Confirmation required</Badge>
          )}
        </CardHeader>
        <CardContent className="border-t px-4 py-4">
          <p className="mb-3 text-xs text-muted-fg">
            Detected family: {exportFlow.style?.detectedFamily ?? 'unknown'}. Confirm before the first citation-changing export.
          </p>
          <div className="flex flex-wrap gap-2">
            {(exportFlow.style?.candidates ?? []).map((candidate) => (
              <Button
                intent={exportFlow.style?.styleId === candidate.id ? 'primary' : 'outline'}
                isDisabled={exportFlow.isSavingStyle}
                key={candidate.id}
                onPress={() => void exportFlow.confirmStyle(candidate.id)}
                size="sm"
              >
                {candidate.label}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card className="mt-3 bg-overlay shadow-overlay">
        <CardHeader
          title={`Export revision ${revision}`}
          description="Produces an editable LaTeX project and its compiled PDF."
        />
        <CardContent className="border-t px-4 py-4">
          <Button
            isDisabled={!exportFlow.style?.confirmed || exportFlow.isCreating || current?.status === 'queued' || current?.status === 'running'}
            onPress={() => void exportFlow.createExport()}
            size="sm"
          >
            {current?.status === 'queued' || current?.status === 'running' ? <SpinnerGapIcon className="animate-spin" /> : <FileZipIcon />}
            {current?.status === 'queued' || current?.status === 'running' ? 'Building export…' : 'Build export'}
          </Button>
          {current?.status === 'failed' ? (
            <p className="mt-3 text-sm text-danger-subtle-fg">{current.error ?? 'Export failed.'}</p>
          ) : null}
          {current?.status === 'completed' ? (
            <div className="mt-4">
              <Badge intent="success"><CheckCircleIcon data-slot="icon" />Export ready</Badge>
              <div className="mt-3 flex flex-wrap gap-2">
                {current.latexUrl ? (
                  <Button onPress={() => window.open(`/api${current.latexUrl}`, '_blank')} size="sm">
                    <FileZipIcon />LaTeX project<DownloadSimpleIcon />
                  </Button>
                ) : null}
                {current.pdfUrl ? (
                  <Button intent="outline" onPress={() => window.open(`/api${current.pdfUrl}`, '_blank')} size="sm">
                    <FilePdfIcon />Compiled PDF<DownloadSimpleIcon />
                  </Button>
                ) : null}
              </div>
              {current.warnings.length ? (
                <ul className="mt-4 list-disc space-y-1 pl-4 text-xs/5 text-warning-subtle-fg">
                  {current.warnings.map((warning) => <li key={warning}>{warning}</li>)}
                </ul>
              ) : null}
            </div>
          ) : null}
          {exportFlow.error ? (
            <p className="mt-3 text-sm text-danger-subtle-fg">
              {exportFlow.error instanceof Error ? exportFlow.error.message : 'Export is unavailable.'}
            </p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
