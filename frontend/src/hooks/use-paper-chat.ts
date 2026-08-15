import { useEffect, useMemo, useState } from 'react'
import type { UIMessage } from '@tanstack/ai'
import { fetchServerSentEvents, useChat } from '@tanstack/ai-react'
import useSWR from 'swr'
import type { PaperAgentSelectionContext } from '@/lib/manuscript-focus'

const INITIAL_MESSAGE: UIMessage = {
  id: 'paper-agent-intro',
  role: 'assistant',
  parts: [
    {
      type: 'text',
      content:
        'I can inspect this paper, answer questions, and prepare safe edits. Any change appears as a diff for your approval before it is applied.',
    },
  ],
}

const PROVISIONAL_INITIAL_MESSAGE: UIMessage = {
  id: 'paper-agent-index-ready',
  role: 'assistant',
  parts: [
    {
      type: 'text',
      content:
        'Chat is ready from the fast vector index. Ask broad questions about the paper now; exact citations, review, and editing will unlock as background processing finishes.',
    },
  ],
}

async function paperAgentFetch(input: RequestInfo | URL, init?: RequestInit) {
  const response = await fetch(input, init)
  if (response.ok) return response

  let message = `The paper agent returned HTTP ${response.status}.`
  try {
    const payload = (await response.clone().json()) as { detail?: unknown }
    if (typeof payload.detail === 'string') message = payload.detail
  } catch {
    // Keep the status-based message when the server did not return JSON.
  }
  throw new Error(message)
}

interface ChatHistoryResponse {
  messages: Array<{
    id: string
    role: 'user' | 'assistant' | 'system' | 'tool' | 'reasoning'
    content: unknown
  }>
}

async function fetchChatHistory(url: string): Promise<ChatHistoryResponse> {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`Unable to restore chat history (HTTP ${response.status}).`)
  return response.json() as Promise<ChatHistoryResponse>
}

export function usePaperChat(
  paper: unknown,
  paperId: string,
  selectionContext?: PaperAgentSelectionContext | null,
) {
  const [threadId] = useState(
    () => {
      const key = `paper-chat-thread:${paperId}`
      const existing = typeof window !== 'undefined' ? window.localStorage.getItem(key) : null
      const next = existing ?? `paper-${globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)}`
      if (typeof window !== 'undefined') window.localStorage.setItem(key, next)
      return next
    },
  )
  const history = useSWR<ChatHistoryResponse>(
    `/api/chat/${threadId}${paperId ? `?paper_id=${encodeURIComponent(paperId)}` : ''}`,
    fetchChatHistory,
  )
  const connection = useMemo(
    () =>
      fetchServerSentEvents(`/api/chat?paper_id=${encodeURIComponent(paperId)}`, {
        fetchClient: paperAgentFetch,
      }),
    [paperId],
  )
  const forwardedProps = useMemo(
    () => ({ paper, paperId, selectionContext }),
    [paper, paperId, selectionContext],
  )

  const chat = useChat({
    connection,
    forwardedProps,
    initialMessages: [paper == null ? PROVISIONAL_INITIAL_MESSAGE : INITIAL_MESSAGE],
    threadId,
  })

  useEffect(() => {
    if (!history.data?.messages.length) return
    const restored = history.data.messages.map((message) => ({
      id: message.id,
      role: message.role,
      parts: [{ type: 'text' as const, content: typeof message.content === 'string' ? message.content : JSON.stringify(message.content) }],
    })) as UIMessage[]
    chat.setMessages(restored)
  }, [chat.setMessages, history.data])

  return chat
}
