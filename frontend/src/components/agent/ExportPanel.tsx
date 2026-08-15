import { useState } from 'react'
import {
  CheckCircleIcon,
  DownloadSimpleIcon,
  ExportIcon,
  FilePdfIcon,
  FileZipIcon,
  SpinnerGapIcon,
} from '@phosphor-icons/react'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Description, Label } from '@/components/ui/field'
import {
  Popover,
  PopoverBody,
  PopoverContent,
  PopoverFooter,
  PopoverHeader,
} from '@/components/ui/popover'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectLabel,
  SelectTrigger,
} from '@/components/ui/select'
import {
  usePaperExport,
  type PaperExportFormat,
} from '@/hooks/use-paper-export'

export function ExportControl({ paperId, revision }: { paperId: string; revision: number }) {
  const [format, setFormat] = useState<PaperExportFormat>('pdf')
  const exportFlow = usePaperExport(paperId, revision)
  const current = exportFlow.export

  return (
    <Popover>
      <Button intent="outline" size="sm">
        <ExportIcon />
        Export
      </Button>
      <PopoverContent className="w-80" placement="bottom end">
        <Dialog>
          <PopoverHeader
            title="Export manuscript"
            description={`Choose a format and download revision ${revision}.`}
          />
          <PopoverBody className="space-y-4">
            <Select
              isDisabled={exportFlow.isDownloading || exportFlow.isLoadingStyle}
              onChange={(key) => {
                if (key != null) void exportFlow.confirmStyle(String(key))
              }}
              placeholder="Choose a citation style"
              value={exportFlow.style?.styleId ?? null}
            >
              <Label>Citation style</Label>
              <SelectTrigger />
              <SelectContent items={exportFlow.style?.candidates ?? []}>
                {(candidate) => (
                  <SelectItem id={candidate.id} textValue={candidate.label}>
                    {candidate.label}
                  </SelectItem>
                )}
              </SelectContent>
              <Description>
                Detected family: {exportFlow.style?.detectedFamily ?? 'unknown'}
              </Description>
            </Select>

            <Select
              isDisabled={exportFlow.isDownloading}
              onChange={(key) => {
                if (key === 'pdf' || key === 'latex') setFormat(key)
              }}
              value={format}
            >
              <Label>Format</Label>
              <SelectTrigger />
              <SelectContent>
                <SelectItem id="pdf" textValue="PDF">
                  <FilePdfIcon />
                  <SelectLabel>PDF</SelectLabel>
                </SelectItem>
                <SelectItem id="latex" textValue="LaTeX project">
                  <FileZipIcon />
                  <SelectLabel>LaTeX project</SelectLabel>
                </SelectItem>
              </SelectContent>
              <Description>
                Figures, tables, display equations, footnotes, captions, and page layout are not
                represented as first-class manuscript nodes and may be omitted or flattened.
                Compare the export with the original PDF.
              </Description>
            </Select>

            {!exportFlow.style?.confirmed && !exportFlow.isLoadingStyle ? (
              <p className="text-xs/5 text-warning-subtle-fg">
                Choose a citation style before downloading.
              </p>
            ) : null}
            {current?.status === 'failed' ? (
              <p className="text-sm/6 text-danger-subtle-fg" role="alert">
                {current.error ?? 'Export failed.'}
              </p>
            ) : null}
            {exportFlow.error ? (
              <p className="text-sm/6 text-danger-subtle-fg" role="alert">
                {exportFlow.error instanceof Error
                  ? exportFlow.error.message
                  : 'Export is unavailable.'}
              </p>
            ) : null}
            {exportFlow.downloadedAt ? (
              <p className="flex items-center gap-2 text-xs/5 text-success-subtle-fg" role="status">
                <CheckCircleIcon /> Download started.
              </p>
            ) : null}
            {current?.status === 'completed' && current.warnings.length ? (
              <ul className="list-disc space-y-1 pl-4 text-xs/5 text-warning-subtle-fg">
                {current.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            ) : null}
          </PopoverBody>
          <PopoverFooter>
            <Button
              isDisabled={
                !exportFlow.style?.confirmed ||
                exportFlow.isDownloading ||
                exportFlow.isSavingStyle
              }
              onPress={() => void exportFlow.downloadExport(format)}
              size="sm"
            >
              {exportFlow.isDownloading ? (
                <SpinnerGapIcon className="animate-spin" />
              ) : (
                <DownloadSimpleIcon />
              )}
              {exportFlow.isDownloading ? 'Preparing download…' : 'Download'}
            </Button>
          </PopoverFooter>
        </Dialog>
      </PopoverContent>
    </Popover>
  )
}
