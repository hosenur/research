import { useState } from 'react'
import { ClipboardTextIcon } from '@phosphor-icons/react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Checkbox, CheckboxField } from '@/components/ui/checkbox'
import { useSectionReview } from '@/hooks/use-section-review'
import type { PaperSectionJson } from '@/lib/paper'

export function SectionReviewPanel({ paperId, sections }: { paperId: string; sections: PaperSectionJson[] }) {
  const [selected, setSelected] = useState<string[]>([])
  const [started, setStarted] = useState(false)
  const review = useSectionReview(paperId)
  if (started) return null
  return (
    <Card className="mb-2 shrink-0 bg-overlay shadow-overlay">
      <CardHeader
        title="Choose sections to review"
        description="This paper exceeds 80 pages. Select up to five sections to bound latency and cost."
      />
      <CardContent className="border-t px-4 py-3">
        <div className="max-h-44 space-y-2 overflow-y-auto">
          {sections.map((section) => (
            <CheckboxField
              isSelected={selected.includes(section.id)}
              key={section.id}
              onChange={(isSelected) => setSelected((current) => {
                if (isSelected && current.length >= 5) return current
                return isSelected ? [...current, section.id] : current.filter((id) => id !== section.id)
              })}
            >
              <Checkbox>{section.number ? `${section.number} ` : ''}{section.title}</Checkbox>
            </CheckboxField>
          ))}
        </div>
        <div className="mt-3 flex items-center justify-between gap-2">
          <span className="text-xs text-muted-fg">{selected.length}/5 selected</span>
          <Button
            isDisabled={!selected.length || review.isMutating}
            onPress={() => void review.start(selected).then(() => setStarted(true))}
            size="sm"
          >
            <ClipboardTextIcon />
            {review.isMutating ? 'Starting…' : 'Review sections'}
          </Button>
        </div>
        {review.error ? (
          <p className="mt-2 text-xs text-danger-subtle-fg">
            {review.error instanceof Error ? review.error.message : 'Section review could not start.'}
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}
