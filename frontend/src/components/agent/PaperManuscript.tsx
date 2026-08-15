import { CheckCircleIcon, WarningIcon } from '@phosphor-icons/react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import type { ManuscriptSelection } from '@/lib/manuscript-focus'
import type {
  PaperJson,
  PaperParagraphJson,
} from '@/lib/paper'

export interface ManuscriptFocus extends ManuscriptSelection {
  highlighted: boolean
  token: number
}

function FocusHighlight({
  children,
  className,
  focus,
  ...props
}: React.ComponentProps<'mark'> & { focus: ManuscriptFocus }) {
  return focus.highlighted ? (
    <mark {...props} className={className}>
      {children}
    </mark>
  ) : (
    <span {...props}>{children}</span>
  )
}

function authorName(author: NonNullable<PaperJson['authors']>[number]) {
  return author.literal || [author.given, author.family].filter(Boolean).join(' ')
}

function Paragraph({
  focus,
  paragraph,
}: {
  focus?: ManuscriptFocus | null
  paragraph: PaperParagraphJson
}) {
  const focused = focus?.paragraphId === paragraph.id ? focus : null
  const plainText = paragraph.nodes
    .map((node) => (node.type === 'text' ? node.text : node.rawText))
    .join('')
  const textStart = focused?.text ? plainText.indexOf(focused.text) : -1
  const focusStart =
    focused?.startOffset != null && focused.startOffset >= 0
      ? focused.startOffset
      : textStart
  const focusEnd =
    focused?.endOffset != null && focused.endOffset > focusStart
      ? focused.endOffset
      : textStart >= 0 && focused?.text
        ? textStart + focused.text.length
        : -1
  let cursor = 0

  return (
    <p
      className="scroll-mt-20 text-[0.98rem]/7 text-fg"
      data-node-id={paragraph.id}
      id={`node-${paragraph.id}`}
    >
      {paragraph.nodes.map((node, index) => {
        const value = node.type === 'text' ? node.text : node.rawText
        const nodeStart = cursor
        const nodeEnd = nodeStart + value.length
        cursor = nodeEnd
        const overlaps = focusStart >= 0 && focusEnd > nodeStart && focusStart < nodeEnd
        if (node.type === 'text') {
          const localStart = Math.max(0, focusStart - nodeStart)
          const localEnd = Math.min(node.text.length, focusEnd - nodeStart)
          return (
            <span key={`${paragraph.id}:text:${index}`}>
              {overlaps ? (
                <>
                  {node.text.slice(0, localStart)}
                  <FocusHighlight
                    className="review-text-highlight rounded-sm px-0.5 text-inherit"
                    focus={focus!}
                    key={`${focus?.token}:${nodeStart}`}
                  >
                    {node.text.slice(localStart, localEnd)}
                  </FocusHighlight>
                  {node.text.slice(localEnd)}
                </>
              ) : (
                node.text
              )}
            </span>
          )
        }
        if (overlaps && focus) {
          return (
            <FocusHighlight
              className="review-text-highlight mx-0.5 rounded px-1 py-0.5 font-medium text-inherit"
              data-citation-id={node.id ?? undefined}
              focus={focus}
              key={node.id ?? `${paragraph.id}:citation:${index}`}
            >
              {node.rawText}
            </FocusHighlight>
          )
        }
        return (
          <span
            className={
              node.resolution.status === 'resolved'
                ? 'mx-0.5 rounded bg-primary-subtle px-1 py-0.5 font-medium text-primary-subtle-fg'
                : 'mx-0.5 rounded bg-warning-subtle px-1 py-0.5 font-medium text-warning-subtle-fg'
            }
            data-citation-id={node.id ?? undefined}
            key={node.id ?? `${paragraph.id}:citation:${index}`}
          >
            {node.rawText}
          </span>
        )
      })}
    </p>
  )
}

export function PaperManuscript({
  focus,
  paper,
}: {
  focus?: ManuscriptFocus | null
  paper: PaperJson
}) {
  const quality = paper.extraction?.quality
  const authorLine = (paper.authors ?? []).map(authorName).filter(Boolean).join(', ')
  const unresolved = paper.unresolvedReferenceIds?.length ?? 0

  return (
    <article className="mx-auto w-full max-w-4xl px-5 py-8 sm:px-9 sm:py-12">
      <header className="mb-9 border-b border-border pb-7">
        <Card className="mb-5 bg-muted/40 shadow-none">
          <CardContent className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2">
            <div className="flex flex-wrap gap-1.5">
              {quality ? (
                <Badge intent={quality.status === 'usable' ? 'success' : 'warning'}>
                  {quality.status === 'usable' ? (
                    <CheckCircleIcon data-slot="icon" />
                  ) : (
                    <WarningIcon data-slot="icon" />
                  )}
                  {quality.status === 'usable' ? 'Usable extraction' : 'Extraction warnings'}
                </Badge>
              ) : null}
              <Badge intent={unresolved ? 'warning' : 'secondary'}>
                {unresolved ? `${unresolved} unresolved citations` : 'Citations resolved'}
              </Badge>
              {paper.citationStyleDetection ? (
                <Badge intent="secondary">
                  {paper.citationStyleDetection.family} style ·{' '}
                  {paper.citationStyleDetection.confidence}
                </Badge>
              ) : null}
            </div>
            {quality ? (
              <dl className="ml-auto flex flex-wrap items-center divide-x divide-border text-xs">
                <div className="flex items-baseline gap-1 px-2 first:pl-0">
                  <dt className="text-muted-fg">Sections</dt>
                  <dd className="font-semibold">{quality.sectionCount}</dd>
                </div>
                <div className="flex items-baseline gap-1 px-2">
                  <dt className="text-muted-fg">Sentences</dt>
                  <dd className="font-semibold">{quality.sentenceCount}</dd>
                </div>
                <div className="flex items-baseline gap-1 px-2">
                  <dt className="text-muted-fg">Citations</dt>
                  <dd className="font-semibold">{quality.citationCount}</dd>
                </div>
                <div className="flex items-baseline gap-1 px-2 last:pr-0">
                  <dt className="text-muted-fg">Resolved</dt>
                  <dd className="font-semibold">
                    {Math.round(quality.resolvedTargetRatio * 100)}%
                  </dd>
                </div>
              </dl>
            ) : null}
          </CardContent>
        </Card>
        <h1 className="text-balance text-3xl font-semibold tracking-tight text-fg sm:text-4xl">
          {paper.title}
        </h1>
        {authorLine ? <p className="mt-3 text-sm/6 text-muted-fg">{authorLine}</p> : null}
      </header>

      {paper.abstract ? (
        <section className="mb-9" id="paper-abstract">
          <h2 className="mb-3 text-lg font-semibold tracking-tight">Abstract</h2>
          <p className="text-[0.98rem]/7 text-fg">{paper.abstract}</p>
        </section>
      ) : null}

      <div className="space-y-9">
        {paper.sections.map((section) => (
          <section className="scroll-mt-20" data-section-id={section.id} id={`section-${section.id}`} key={section.id}>
            <h2 className="mb-4 text-xl font-semibold tracking-tight text-fg">
              {section.number ? <span className="mr-2 text-muted-fg">{section.number}</span> : null}
              {section.title}
            </h2>
            <div className="space-y-4">
              {section.paragraphs.map((paragraph) => (
                <Paragraph focus={focus} key={paragraph.id} paragraph={paragraph} />
              ))}
            </div>
          </section>
        ))}
      </div>

      <section className="mt-12 border-t border-border pt-8" id="paper-references">
        <h2 className="mb-5 text-xl font-semibold tracking-tight">References</h2>
        <ol className="space-y-3 text-sm/6 text-muted-fg">
          {paper.references.map((reference) => (
            <li className="scroll-mt-20" id={`reference-${reference.id}`} key={reference.id}>
              <span className="mr-2 font-mono text-xs text-fg">{reference.id}</span>
              {reference.rawText ?? reference.csl?.title ?? 'Unparsed reference'}
            </li>
          ))}
        </ol>
      </section>
    </article>
  )
}
