import useSWR from 'swr'

export interface PaperJob {
  name: string
  jobId: string
  status: 'not_started' | 'queued' | 'running' | 'completed' | 'failed'
  progress: Record<string, unknown>
  error?: string | null
}

interface PaperJobsResponse {
  paperId: string
  jobs: PaperJob[]
}

async function fetchJobs(url: string): Promise<PaperJobsResponse> {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`The API returned HTTP ${response.status}.`)
  return response.json() as Promise<PaperJobsResponse>
}

export function usePaperJobs(paperId: string) {
  return useSWR<PaperJobsResponse>(`/api/papers/${paperId}/jobs`, fetchJobs, {
    refreshInterval: 1_500,
    revalidateOnFocus: true,
  })
}
