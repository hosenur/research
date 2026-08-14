import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import type { UIMessage } from '@tanstack/ai'
import {
  ArrowPathIcon as Retry,
  ArrowUpIcon as ArrowUp,
  MagnifyingGlassIcon as Search,
  StopIcon as Stop,
} from '@heroicons/react/24/solid'
import { Button } from '@/components/ui/button'
import LoadingState from '@/components/ui/LoadingState'
import { Textarea } from '@/components/ui/textarea'
import { UiProvider } from '@/components/ui/UiProvider'
import { usePaperChat } from '@/hooks/use-paper-chat'
import { twMerge } from 'tailwind-merge'
import { ChatMarkdown } from './ChatMarkdown'

const SUGGESTIONS = [
  'Check the claims in the introduction',
  'Explain citation [12]',
  'Summarize the methods and findings',
]

function messageText(message: UIMessage) {
  return message.parts
    .filter((part) => part.type === 'text')
    .map((part) => part.content)
    .join('')
}

export function AgentChat({
  className,
  paper,
  paperId,
}: {
  className?: string
  paper: unknown
  paperId?: string
}) {
  const [draft, setDraft] = useState('')
  const { error, isLoading, messages, reload, sendMessage, stop } = usePaperChat(paper, paperId)
  const threadRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    threadRef.current?.scrollTo({
      top: threadRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [messages, isLoading, error])

  function submit(text = draft) {
    const prompt = text.trim()
    if (!prompt || isLoading) return
    setDraft('')
    void sendMessage(prompt)
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    submit()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <section
      aria-label="Paper agent"
      className={twMerge(
        'flex h-[42rem] min-h-0 flex-col overflow-hidden bg-bg text-fg',
        className,
      )}
    >
      <div className="flex min-h-0 flex-1 flex-col">
        <div
          aria-live="polite"
          className="no-bar min-h-0 flex-1 overflow-y-auto px-4 py-5"
          ref={threadRef}
        >
          <div className="flex min-h-full flex-col justify-end gap-5">
            {messages.map((message, index) => (
              <div
                className={message.role === 'user' ? 'flex justify-end' : 'flex justify-start'}
                key={message.id}
              >
                <div
                  className={
                    message.role === 'user'
                      ? 'max-w-[85%] whitespace-pre-wrap rounded-[10px] bg-secondary px-3.5 py-2.5 text-sm/6 text-fg shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--fg)_3%,transparent)]'
                      : 'max-w-[92%] min-w-0 text-fg'
                  }
                >
                  {message.role === 'user' ? (
                    messageText(message)
                  ) : (
                    <ChatMarkdown streaming={isLoading && index === messages.length - 1}>
                      {messageText(message)}
                    </ChatMarkdown>
                  )}
                </div>
              </div>
            ))}

            {isLoading ? (
              <UiProvider>
                <LoadingState label="Reading the paper" variant="Drive" />
              </UiProvider>
            ) : null}

            {error ? (
              <div className="rounded-[10px] border border-danger/30 bg-danger-subtle px-3.5 py-3 text-sm/6 text-danger-subtle-fg">
                <p>{error.message}</p>
                <Button className="mt-2" intent="outline" onPress={() => void reload()} size="xs">
                  <Retry />
                  Try again
                </Button>
              </div>
            ) : null}
          </div>
        </div>

        <div className="border-t border-border bg-bg/80 px-3 py-3">
          {messages.length === 1 ? (
            <div className="no-bar mb-2 flex gap-2 overflow-x-auto pb-1">
              {SUGGESTIONS.map((suggestion) => (
                <Button
                  className="shrink-0"
                  intent="outline"
                  key={suggestion}
                  onPress={() => submit(suggestion)}
                  size="xs"
                >
                  <Search />
                  {suggestion}
                </Button>
              ))}
            </div>
          ) : null}

          <form
            className="overflow-hidden rounded-[10px] border border-border bg-overlay shadow-sm transition-[border-color,box-shadow] duration-150 focus-within:border-input focus-within:shadow-md"
            onSubmit={handleSubmit}
          >
            <Textarea
              aria-label="Ask the paper agent"
              className="max-h-40 min-h-20 rounded-none border-0 bg-transparent px-3.5 pt-3 shadow-none focus:border-0 focus:ring-0 enabled:hover:border-0"
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about a claim, citation, or section…"
              rows={2}
              value={draft}
            />
            <div className="flex items-center justify-between px-3 pb-3">
              <span className="text-xs text-muted-fg">Enter to send · Shift+Enter for a new line</span>
              <Button
                aria-label={isLoading ? 'Stop response' : 'Send message'}
                isDisabled={!isLoading && !draft.trim()}
                onPress={isLoading ? stop : undefined}
                size="sq-sm"
                type={isLoading ? 'button' : 'submit'}
              >
                {isLoading ? <Stop /> : <ArrowUp />}
              </Button>
            </div>
          </form>
        </div>
      </div>
    </section>
  )
}
