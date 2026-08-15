import useSWR from 'swr'
import useSWRMutation from 'swr/mutation'

export interface PaperJob {
  name: string
  jobId: string
  status: 'not_started' | 'queued' | 'running' | 'completed' | 'failed' | 'skipped'
  progress: Record<string, unknown>
  error?: string | null
  durationMs?: number | null
}

interface PaperJobsResponse {
  paperId: string
  stages: Array<{
    name: string
    status: PaperJob['status']
    attempt: number
    revision: number
    progress: Record<string, unknown>
    error?: string | null
    durationMs?: number | null
  }>
}

async function fetchJobs(url: string): Promise<PaperJobsResponse> {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`The API returned HTTP ${response.status}.`)
  return response.json() as Promise<PaperJobsResponse>
}

export function usePaperJobs(paperId: string) {
  const request = useSWR<PaperJobsResponse>(`/api/papers/${paperId}/pipeline`, fetchJobs, {
    refreshInterval: 1_500,
    revalidateOnFocus: true,
  })
  const retry = useSWRMutation(
    `/api/papers/${paperId}/pipeline`,
    async (url: string, { arg }: { arg: { stage: string } }) => {
      const response = await fetch(`${url}/${arg.stage}/retry`, { method: 'POST' })
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null
        throw new Error(payload?.detail ?? `The API returned HTTP ${response.status}.`)
      }
      return response.json()
    },
  )
  return {
    ...request,
    retryStage: async (stage: string) => {
      await retry.trigger({ stage })
      await request.mutate()
    },
    retrying: retry.isMutating,
    data: request.data
      ? {
          paperId: request.data.paperId,
          jobs: request.data.stages.map((stage) => ({
            ...stage,
            jobId: `${paperId}:${stage.name}`,
            status: stage.status,
          })),
        }
      : undefined,
  }
}
