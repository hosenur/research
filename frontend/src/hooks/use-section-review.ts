import useSWRMutation from 'swr/mutation'
import { useSWRConfig } from 'swr'

async function startReview(
  url: string,
  { arg }: { arg: { sectionIds: string[] } },
) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(arg),
  })
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(payload?.detail ?? `The API returned HTTP ${response.status}.`)
  }
  return response.json()
}

export function useSectionReview(paperId: string) {
  const { mutate } = useSWRConfig()
  const mutation = useSWRMutation(`/api/papers/${paperId}/section-review`, startReview)
  return {
    ...mutation,
    start: async (sectionIds: string[]) => {
      const result = await mutation.trigger({ sectionIds })
      await Promise.all([
        mutate(`/api/papers/${paperId}/pipeline`),
        mutate(`/api/papers/${paperId}/claim-citation-review`),
      ])
      return result
    },
  }
}
