import { useCallback } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import {
  CloudArrowUpIcon as UploadCloud,
  FileTextIcon as FileText,
  XIcon as X,
} from '@phosphor-icons/react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { DropZone } from '@/components/ui/drop-zone'
import { FileTrigger } from '@/components/ui/file-trigger'
import { PaperProcessingSteps } from '@/components/ui/PaperProcessingSteps'
import { usePaperUploadFlow } from '@/hooks/use-paper'
import type { PaperLifecycleJson } from '@/lib/paper'

function PaperPage() {
  const navigate = Route.useNavigate()
  const onUploaded = useCallback(
    (lifecycle: PaperLifecycleJson) => {
      void navigate({
        to: '/papers/$paperId',
        params: { paperId: lifecycle.id },
      })
    },
    [navigate],
  )
  const upload = usePaperUploadFlow(onUploaded)

  if (upload.state.kind === 'uploading') {
    return (
      <main
        aria-label="Uploading research paper"
        className="grid min-h-dvh place-items-center bg-bg p-4 sm:p-8"
      >
        <Card className="w-full max-w-xl bg-overlay shadow-overlay">
          <CardHeader
            title={upload.state.file.name}
            description="Uploading the original PDF securely. Processing begins automatically."
          >
            <span className="grid size-10 place-items-center rounded-lg bg-primary-subtle text-primary-subtle-fg">
              <FileText aria-hidden="true" className="size-5" />
            </span>
          </CardHeader>
          <CardContent className="border-t px-5 py-5">
            <PaperProcessingSteps uploadProgress={upload.state.uploadProgress} />
            <div className="mt-5 flex justify-end border-t border-border pt-4">
              <Button intent="outline" onPress={upload.reset} size="sm">
                <X />
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      </main>
    )
  }

  return (
    <div className="grid min-h-dvh place-items-center p-4 sm:p-8">
      <DropZone
        aria-label="Upload a research paper"
        className="min-h-[min(38rem,calc(100dvh-4rem))] w-full max-w-5xl max-h-none border-border bg-overlay p-8 shadow-overlay transition-[border-color,background-color,box-shadow] duration-150 data-[drop-target]:border-primary data-[drop-target]:bg-primary-subtle/40 sm:p-12"
        getDropOperation={(types) =>
          types.has('application/pdf') || types.has('Files') ? 'copy' : 'cancel'
        }
        onDrop={(event) => {
          const droppedFile = event.items.find((item) => item.kind === 'file')
          if (droppedFile?.kind === 'file') {
            void droppedFile.getFile().then(upload.selectFile)
          }
        }}
      >
        <div className="flex max-w-lg flex-col items-center text-center">
          <span className="grid size-16 place-items-center rounded-2xl bg-primary-subtle text-primary-subtle-fg transition-transform duration-150 group-data-[drop-target]/drop-zone:scale-[0.97]">
            <UploadCloud aria-hidden="true" className="size-7" />
          </span>
          <h1 className="mt-6 font-display text-3xl font-semibold tracking-[-0.035em] text-fg sm:text-4xl">
            Drop your research paper here
          </h1>
          <p className="mt-3 text-sm/6 text-muted-fg">
            Upload one PDF up to 50 MB. Parsing starts automatically.
          </p>
          <p className="mt-2 text-xs/5 text-warning-subtle-fg">
            Assessment environment: do not upload confidential or unpublished manuscripts.
          </p>
          <FileTrigger
            acceptedFileTypes={['application/pdf', '.pdf']}
            className="mt-7"
            onSelect={(files) => upload.selectFile(files?.item(0))}
            size="lg"
          >
            Choose PDF
          </FileTrigger>
          {upload.state.kind === 'error' ? (
            <p className="mt-5 text-sm font-medium text-danger-subtle-fg" role="alert">
              {upload.state.message}
            </p>
          ) : null}
        </div>
      </DropZone>
    </div>
  )
}

export const Route = createFileRoute('/')({ component: PaperPage })
