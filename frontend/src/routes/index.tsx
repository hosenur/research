import { useCallback } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import {
  ArrowTopRightOnSquareIcon as ExternalLink,
  CloudArrowUpIcon as UploadCloud,
  DocumentTextIcon as FileText,
  XMarkIcon as X,
} from '@heroicons/react/24/solid'
import { Button } from '@/components/ui/button'
import { DropZone } from '@/components/ui/drop-zone'
import { FileTrigger } from '@/components/ui/file-trigger'
import { PaperProcessingSteps } from '@/components/ui/PaperProcessingSteps'
import { useObjectUrl, usePaperUploadFlow } from '@/hooks/use-paper'
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
  const previewUrl = useObjectUrl(
    upload.state.kind === 'uploading' ? upload.state.file : null,
  )

  if (upload.state.kind === 'uploading') {
    return (
      <section
        aria-label="Uploading research paper"
        className="grid min-h-dvh gap-4 bg-bg p-3 lg:grid-cols-[minmax(0,1fr)_24rem] lg:p-4"
      >
        <div className="relative min-h-[60dvh] overflow-hidden rounded-xl border border-border bg-muted shadow-overlay lg:min-h-0">
          <div className="absolute right-2 top-2 z-10 flex gap-1.5 rounded-lg border border-border bg-overlay/95 p-1 shadow-sm backdrop-blur-sm">
            <Button
              aria-label="Open PDF in a new tab"
              intent="plain"
              isDisabled={!previewUrl}
              onPress={() => window.open(previewUrl, '_blank', 'noopener,noreferrer')}
              size="sq-xs"
            >
              <ExternalLink />
            </Button>
            <Button intent="outline" onPress={upload.reset} size="xs">
              <X />
              Cancel
            </Button>
          </div>
          {previewUrl ? (
            <object
              aria-label={`Preview of ${upload.state.file.name}`}
              className="size-full"
              data={previewUrl}
              type="application/pdf"
            >
              <div className="grid size-full place-items-center p-8 text-center text-sm text-muted-fg">
                <Button onPress={() => window.open(previewUrl, '_blank')} size="sm">
                  <ExternalLink />
                  Open PDF
                </Button>
              </div>
            </object>
          ) : null}
        </div>
        <aside className="self-center rounded-xl border border-border bg-overlay p-5 shadow-overlay lg:self-stretch">
          <span className="grid size-11 place-items-center rounded-xl bg-primary-subtle text-primary-subtle-fg">
            <FileText aria-hidden="true" className="size-5" />
          </span>
          <h1 className="mt-4 truncate font-display text-xl font-semibold text-fg">
            {upload.state.file.name}
          </h1>
          <p className="mt-2 text-sm/6 text-muted-fg">
            You can read the PDF now. We will open a permanent workspace as soon as the upload finishes.
          </p>
          <PaperProcessingSteps uploadProgress={upload.state.uploadProgress} />
        </aside>
      </section>
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
