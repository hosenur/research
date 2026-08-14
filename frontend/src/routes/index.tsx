import { useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import {
  CloudArrowUpIcon as UploadCloud,
  DocumentTextIcon as FileText,
  XMarkIcon as X,
} from '@heroicons/react/24/solid'
import { PaperWorkspace } from '@/components/agent/PaperWorkspace'
import { Button } from '@/components/ui/button'
import { DropZone } from '@/components/ui/drop-zone'
import { FileTrigger } from '@/components/ui/file-trigger'
import LoadingState from '@/components/ui/LoadingState'
import { UiProvider } from '@/components/ui/UiProvider'
import { useParsePaper } from '@/hooks/use-paper'
import type { PaperDocumentJson } from '@/lib/paper'

const MAX_PDF_BYTES = 50 * 1024 * 1024

type PageState =
  | { kind: 'upload' }
  | { kind: 'parsing'; file: File; uploadProgress: number }
  | { kind: 'workspace'; file: File; document: PaperDocumentJson }
  | { kind: 'error'; message: string }

function fileError(file: File) {
  if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
    return 'Choose a PDF research paper.'
  }
  if (file.size > MAX_PDF_BYTES) return 'PDF files must be 50 MB or smaller.'
  return null
}

function PaperPage() {
  const [state, setState] = useState<PageState>({ kind: 'upload' })
  const paperMutation = useParsePaper()

  function reset() {
    paperMutation.abort()
    setState({ kind: 'upload' })
  }

  function selectFile(file?: File | null) {
    if (!file) return
    const validationError = fileError(file)
    if (validationError) {
      setState({ kind: 'error', message: validationError })
      return
    }
    parsePaper(file)
  }

  function parsePaper(file: File) {
    setState({ kind: 'parsing', file, uploadProgress: 0 })
    void paperMutation
      .parse(file, (uploadProgress) => setState({ kind: 'parsing', file, uploadProgress }))
      .then((document) => setState({ kind: 'workspace', file, document }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setState({
          kind: 'error',
          message: error instanceof Error ? error.message : 'Could not process this paper.',
        })
      })
  }

  if (state.kind === 'workspace') {
    return (
      <PaperWorkspace
        file={state.file}
        onReset={reset}
        paper={state.document.paper}
        paperId={state.document.id}
        paperRevision={state.document.revision}
      />
    )
  }

  const isParsing = state.kind === 'parsing'

  return (
    <div className="grid min-h-dvh place-items-center p-4 sm:p-8">
      <DropZone
        aria-label="Upload a research paper"
        className="min-h-[min(38rem,calc(100dvh-4rem))] w-full max-w-5xl max-h-none border-border bg-overlay p-8 shadow-overlay transition-[border-color,background-color,box-shadow] duration-150 data-[drop-target]:border-primary data-[drop-target]:bg-primary-subtle/40 sm:p-12"
        getDropOperation={(types) =>
          types.has('application/pdf') || types.has('Files') ? 'copy' : 'cancel'
        }
        isDisabled={isParsing}
        onDrop={(event) => {
          const droppedFile = event.items.find((item) => item.kind === 'file')
          if (droppedFile?.kind === 'file') {
            void droppedFile.getFile().then(selectFile)
          }
        }}
      >
        {state.kind === 'parsing' ? (
          <div className="flex max-w-md flex-col items-center text-center">
            <span className="grid size-14 place-items-center rounded-xl bg-primary-subtle text-primary-subtle-fg">
              <FileText aria-hidden="true" className="size-6" />
            </span>
            <p className="mt-5 max-w-full truncate font-display text-xl font-semibold text-fg">
              {state.file.name}
            </p>
            <p className="mt-2 text-sm text-muted-fg">
              {state.uploadProgress < 100
                ? `Uploading ${state.uploadProgress}%`
                : 'Extracting the paper and citations'}
            </p>
            <div className="mt-6">
              <UiProvider>
                <LoadingState
                  label={state.uploadProgress < 100 ? 'Uploading paper' : 'Structuring paper'}
                  variant="Drive"
                />
              </UiProvider>
            </div>
            <Button className="mt-8" intent="plain" onPress={reset} size="sm">
              <X />
              Cancel
            </Button>
          </div>
        ) : (
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
              onSelect={(files) => selectFile(files?.item(0))}
              size="lg"
            >
              Choose PDF
            </FileTrigger>
            {state.kind === 'error' ? (
              <p className="mt-5 text-sm font-medium text-danger-subtle-fg" role="alert">
                {state.message}
              </p>
            ) : null}
          </div>
        )}
      </DropZone>
    </div>
  )
}

export const Route = createFileRoute('/')({ component: PaperPage })
