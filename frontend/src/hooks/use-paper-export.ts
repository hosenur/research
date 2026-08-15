import { useEffect, useState } from 'react'
import useSWR from 'swr'
import useSWRMutation from 'swr/mutation'

export type PaperExportFormat = 'latex' | 'pdf'

interface CitationStyleStatus {
  paperId: string
  styleId?: string | null
  confirmed: boolean
  detectedFamily?: string | null
  candidates: Array<{ id: string; label: string }>
}

export interface PaperExportStatus {
  id: string
  paperId: string
  revision: number
  styleId: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  warnings: string[]
  error?: string | null
  latexUrl?: string | null
  pdfUrl?: string | null
}

async function jsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(payload?.detail ?? `The API returned HTTP ${response.status}.`)
  }
  return response.json() as Promise<T>
}

async function fetchJson<T>(url: string): Promise<T> {
  return jsonResponse<T>(await fetch(url))
}

async function confirmStyle(url: string, { arg }: { arg: { styleId: string } }) {
  return jsonResponse<CitationStyleStatus>(
    await fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(arg),
    }),
  )
}

async function createExport(url: string, { arg }: { arg: { revision: number } }) {
  return jsonResponse<PaperExportStatus>(
    await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(arg),
    }),
  )
}

export function usePaperExport(paperId: string, revision: number) {
  const [exportId, setExportId] = useState<string | null>(null)
  const [pendingDownload, setPendingDownload] = useState<{
    exportId: string
    format: PaperExportFormat
  } | null>(null)
  const [downloadError, setDownloadError] = useState<Error | null>(null)
  const [downloadedAt, setDownloadedAt] = useState<number | null>(null)
  const styleUrl = `/api/papers/${paperId}/citation-style`
  const style = useSWR<CitationStyleStatus>(styleUrl, fetchJson)
  const confirm = useSWRMutation(styleUrl, confirmStyle)
  const create = useSWRMutation(`/api/papers/${paperId}/exports`, createExport)
  const status = useSWR<PaperExportStatus>(
    exportId ? `/api/papers/${paperId}/exports/${exportId}` : null,
    fetchJson,
    {
      refreshInterval: (latest) =>
        latest?.status === 'completed' || latest?.status === 'failed' ? 0 : 1_500,
    },
  )

  useEffect(() => {
    const current = status.data
    if (!pendingDownload || current?.id !== pendingDownload.exportId) return
    if (current.status === 'failed') {
      setPendingDownload(null)
      return
    }
    if (current.status !== 'completed') return

    const downloadUrl =
      pendingDownload.format === 'latex' ? current.latexUrl : current.pdfUrl
    if (!downloadUrl) {
      setDownloadError(new Error('The requested export file was not generated.'))
      setPendingDownload(null)
      return
    }

    window.location.assign(`/api${downloadUrl}`)
    setDownloadedAt(Date.now())
    setPendingDownload(null)
  }, [pendingDownload, status.data])

  return {
    confirmStyle: async (styleId: string) => {
      const next = await confirm.trigger({ styleId })
      await style.mutate(next, { revalidate: false })
    },
    downloadExport: async (format: PaperExportFormat) => {
      setDownloadError(null)
      setDownloadedAt(null)
      const next = await create.trigger({ revision })
      setExportId(next.id)
      setPendingDownload({ exportId: next.id, format })
    },
    downloadedAt,
    error: downloadError ?? style.error ?? confirm.error ?? create.error ?? status.error,
    export: status.data,
    isDownloading: create.isMutating || pendingDownload !== null,
    isLoadingStyle: style.isLoading,
    isSavingStyle: confirm.isMutating,
    style: style.data,
  }
}
