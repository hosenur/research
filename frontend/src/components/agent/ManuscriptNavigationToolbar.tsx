import { useEffect, useState } from 'react'
import {
  ArrowSquareOutIcon,
  CaretDownIcon,
  CaretUpIcon,
} from '@phosphor-icons/react'
import { Button } from '@/components/ui/button'
import { Link } from '@/components/ui/link'
import {
  Toolbar,
  ToolbarGroup,
  ToolbarSeparator,
} from '@/components/ui/toolbar'
import type { ManuscriptSelection } from '@/lib/manuscript-focus'

interface ManuscriptNavigationToolbarProps {
  activeSelection?: ManuscriptSelection | null
  categoryKey: string
  label: string
  onBrowse?: (selection: ManuscriptSelection) => void
  onSelect: (selection: ManuscriptSelection) => void
  targets: ManuscriptSelection[]
}

export function ManuscriptNavigationToolbar({
  activeSelection,
  categoryKey,
  label,
  onBrowse,
  onSelect,
  targets,
}: ManuscriptNavigationToolbarProps) {
  const [activeIndex, setActiveIndex] = useState(-1)

  useEffect(
    () => setActiveIndex(targets.length ? 0 : -1),
    [categoryKey],
  )
  useEffect(() => {
    setActiveIndex((current) => {
      if (!targets.length) return -1
      if (current < 0) return 0
      return current < targets.length ? current : targets.length - 1
    })
  }, [targets.length])
  useEffect(() => {
    if (!activeSelection) return
    const selectedIndex = targets.findIndex(
      (target) =>
        target.paragraphId === activeSelection.paragraphId &&
        target.startOffset === activeSelection.startOffset &&
        target.endOffset === activeSelection.endOffset &&
        target.text === activeSelection.text,
    )
    if (selectedIndex >= 0) setActiveIndex(selectedIndex)
  }, [activeSelection, targets])

  function navigate(direction: -1 | 1) {
    if (!targets.length) return
    const nextIndex =
      activeIndex < 0
        ? direction === 1
          ? 0
          : targets.length - 1
        : (activeIndex + direction + targets.length) % targets.length
    setActiveIndex(nextIndex)
    onSelect(targets[nextIndex])
  }

  const position =
    activeIndex >= 0 ? `${activeIndex + 1} / ${targets.length}` : `${targets.length}`
  const activeSource = activeIndex >= 0 ? targets[activeIndex]?.source : undefined
  const activeTarget = activeIndex >= 0 ? targets[activeIndex] : undefined

  useEffect(() => {
    if (activeTarget) onBrowse?.(activeTarget)
  }, [activeTarget, onBrowse])

  return (
    <div className="sticky top-0 z-20 border-b border-border bg-overlay/95 px-3 py-2 backdrop-blur-sm">
      <Toolbar
        aria-label={`${label} manuscript navigation`}
        className="flex w-full rounded-none bg-transparent p-0 inset-ring-0"
      >
        <p className="shrink-0 text-sm font-medium text-fg">{label}</p>
        {activeSource ? (
          <>
            <ToolbarSeparator />
            {activeSource.url ? (
              <Link
                className="flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden text-xs"
                href={activeSource.url}
                rel="noreferrer"
                target="_blank"
              >
                <span className="min-w-0 truncate">{activeSource.title}</span>
                <span className="hidden min-w-0 truncate font-normal text-muted-fg md:inline">
                  {activeSource.url}
                </span>
                <ArrowSquareOutIcon className="shrink-0" data-slot="icon" />
              </Link>
            ) : (
              <span className="min-w-0 flex-1 truncate text-xs text-muted-fg">
                {activeSource.title}
              </span>
            )}
          </>
        ) : null}
        <span aria-live="polite" className="ml-auto text-xs tabular-nums text-muted-fg">
          {position}
        </span>
        <ToolbarSeparator />
        <ToolbarGroup aria-label={`${label} navigation controls`}>
          <Button
            aria-label={`Previous ${label.toLowerCase()} reference`}
            intent="plain"
            isDisabled={!targets.length}
            onPress={() => navigate(-1)}
            size="sq-xs"
          >
            <CaretUpIcon />
          </Button>
          <Button
            aria-label={`Next ${label.toLowerCase()} reference`}
            intent="plain"
            isDisabled={!targets.length}
            onPress={() => navigate(1)}
            size="sq-xs"
          >
            <CaretDownIcon />
          </Button>
        </ToolbarGroup>
      </Toolbar>
    </div>
  )
}
