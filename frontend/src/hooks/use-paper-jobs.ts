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
  supportsStageRetry: boolean
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

interface PaperPipelineResponse extends Omit<PaperJobsResponse, 'supportsStageRetry'> {}

interface LegacyPaperJobsResponse {
  paperId: string
  jobs: Array<{
    name: string
    status: Exclude<PaperJob['status'], 'skipped'>
    progress: Record<string, unknown>
    error?: string | null
  }>
}

const legacyStageNames: Record<string, string> = {
  'quick-read': 'quick-extraction',
  parse: 'authoritative-parse',
  index: 'authoritative-index',
  'reference-evidence': 'reference-resolution',
  'citation-audit': 'missing-citation-review',
}

class PaperJobsRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

async function responseError(response: Response) {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null
  return new PaperJobsRequestError(
    payload?.detail ?? `The API returned HTTP ${response.status}.`,
    response.status,
  )
}

async function fetchJobs(url: string): Promise<PaperJobsResponse> {
  const response = await fetch(url)
  if (response.ok) {
    const pipeline = (await response.json()) as PaperPipelineResponse
    return { ...pipeline, supportsStageRetry: true }
  }

  if (response.status === 404) {
    const legacyResponse = await fetch(url.replace(/\/pipeline$/, '/jobs'))
    if (legacyResponse.ok) {
      const legacy = (await legacyResponse.json()) as LegacyPaperJobsResponse
      return {
        paperId: legacy.paperId,
        supportsStageRetry: false,
        stages: legacy.jobs.map((job) => ({
          name: legacyStageNames[job.name] ?? job.name,
          status: job.status,
          attempt: 0,
          revision: 1,
          progress: job.progress,
          error: job.error,
        })),
      }
    }
    throw await responseError(legacyResponse)
  }

  throw await responseError(response)
}

export function usePaperJobs(paperId: string) {
  const request = useSWR<PaperJobsResponse, PaperJobsRequestError>(`/api/papers/${paperId}/pipeline`, fetchJobs, {
    errorRetryInterval: 1_500,
    keepPreviousData: true,
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
          supportsStageRetry: request.data.supportsStageRetry,
          jobs: request.data.stages.map((stage) => ({
            ...stage,
            jobId: `${paperId}:${stage.name}`,
            status: stage.status,
          })),
        }
      : undefined,
  }
}
