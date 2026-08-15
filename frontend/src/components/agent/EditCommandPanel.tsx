import { useEffect, useMemo, useState } from 'react'
import { CheckCircleIcon, MagicWandIcon } from '@phosphor-icons/react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Checkbox, CheckboxField } from '@/components/ui/checkbox'
import type { ManuscriptEditFlow } from '@/hooks/use-manuscript-edits'

export function EditProposalThread({
  edits,
  onDecisionComplete,
}: {
  edits: ManuscriptEditFlow
  onDecisionComplete?: () => void
}) {
  const [selected, setSelected] = useState<string[]>([])
  const validOperations = useMemo(
    () =>
      edits.proposal?.operations.filter(
        (operation) => operation.validationStatus === 'valid',
      ) ?? [],
    [edits.proposal],
  )
  useEffect(() => {
    setSelected(validOperations.map((operation) => operation.id))
  }, [validOperations])

  async function discardProposal() {
    const discarded = await edits.discard()
    if (discarded) onDecisionComplete?.()
  }

  async function approveProposal() {
    const approved = await edits.approve(selected)
    if (approved) onDecisionComplete?.()
  }

  return (
    <div className="space-y-3">
      {edits.error ? (
        <div
          className="rounded-lg border border-danger/30 bg-danger-subtle px-3 py-3 text-sm/6 text-danger-subtle-fg"
          role="alert"
        >
          {edits.error instanceof Error
            ? edits.error.message
            : 'The edit could not be prepared.'}
        </div>
      ) : null}

      {edits.proposal ? (
        <Card className="bg-overlay shadow-overlay">
          <CardHeader
            title={edits.proposal.summary}
            description={`Proposed edit · ${edits.proposal.operations.length} operations`}
          >
            <Badge
              intent={edits.proposal.status === 'approved' ? 'success' : 'warning'}
            >
              {edits.proposal.status === 'approved' ? (
                <CheckCircleIcon data-slot="icon" />
              ) : (
                <MagicWandIcon data-slot="icon" />
              )}
              {edits.proposal.status}
            </Badge>
          </CardHeader>
          <CardContent className="border-t px-4 py-4">
            {edits.proposal.warnings.length ? (
              <ul className="mb-3 list-disc space-y-1 pl-4 text-xs/5 text-warning-subtle-fg">
                {edits.proposal.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            ) : null}
            <ol className="space-y-3">
              {edits.proposal.operations.map((operation) => (
                <li className="rounded-lg border border-border p-3" key={operation.id}>
                  {operation.validationStatus === 'valid' &&
                  edits.proposal?.status === 'planned' ? (
                    <CheckboxField
                      isSelected={selected.includes(operation.id)}
                      onChange={(isSelected: boolean) =>
                        setSelected((current) =>
                          isSelected
                            ? [...current, operation.id]
                            : current.filter((id) => id !== operation.id),
                        )
                      }
                    >
                      <Checkbox>
                        {operation.rationale || `Edit ${operation.position + 1}`}
                      </Checkbox>
                    </CheckboxField>
                  ) : (
                    <p className="text-sm font-medium">
                      {operation.rationale || `Edit ${operation.position + 1}`}
                    </p>
                  )}
                  <div className="mt-3 grid gap-2 text-xs/5">
                    {operation.bibliographyChange ? (
                      <p className="font-medium text-muted-fg">Manuscript</p>
                    ) : null}
                    <div className="rounded-md border border-danger/20 bg-danger-subtle p-2 text-danger-subtle-fg">
                      <span className="mr-2 font-mono">−</span>
                      {operation.beforeText}
                    </div>
                    <div className="rounded-md border border-success/20 bg-success-subtle p-2 text-success-subtle-fg">
                      <span className="mr-2 font-mono">+</span>
                      {operation.afterText}
                    </div>
                  </div>
                  {operation.bibliographyChange ? (
                    <BibliographyPreview change={operation.bibliographyChange} />
                  ) : null}
                  {operation.validationError ? (
                    <p className="mt-2 text-xs text-danger-subtle-fg">
                      {operation.validationError}
                    </p>
                  ) : null}
                </li>
              ))}
            </ol>
            {edits.proposal.status === 'planned' ? (
              <div className="mt-4 flex justify-end gap-2 border-t border-border pt-4">
                <Button
                  intent="outline"
                  isDisabled={edits.isApproving || edits.isDiscarding}
                  onPress={() => void discardProposal()}
                  size="sm"
                >
                  {edits.isDiscarding ? 'Discarding…' : 'Discard'}
                </Button>
                <Button
                  isDisabled={!selected.length || edits.isApproving || edits.isDiscarding}
                  onPress={() => void approveProposal()}
                  size="sm"
                >
                  <CheckCircleIcon />
                  {edits.isApproving ? 'Applying…' : `Approve ${selected.length}`}
                </Button>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

    </div>
  )
}

function BibliographyPreview({
  change,
}: {
  change: NonNullable<
    NonNullable<ManuscriptEditFlow['proposal']>['operations'][number]['bibliographyChange']
  >
}) {
  const marker = change.citationMarker ? `${change.citationMarker} ` : ''

  return (
    <section className="mt-4 border-t border-border pt-3" aria-label="Bibliography change">
      <p className="text-xs font-medium text-muted-fg">Bibliography</p>
      {change.action === 'add' ? (
        <>
          <p className="mt-1 text-xs/5 text-muted-fg">
            A new bibliography entry will be added.
          </p>
          <div className="mt-2 rounded-md border border-success/20 bg-success-subtle p-2 text-xs/5 text-success-subtle-fg">
            <span className="mr-2 font-mono">+</span>
            {marker}{change.afterText}
          </div>
        </>
      ) : null}
      {change.action === 'reuse' ? (
        <>
          <p className="mt-1 text-xs/5 text-muted-fg">
            This source already exists in the bibliography, so no duplicate entry will be added.
          </p>
          <div className="mt-2 rounded-md border border-border bg-muted/40 p-2 text-xs/5 text-fg">
            <span className="mr-2 font-mono">=</span>
            {marker}{change.afterText}
          </div>
        </>
      ) : null}
      {change.action === 'remove' ? (
        <>
          <p className="mt-1 text-xs/5 text-muted-fg">
            This source is not cited elsewhere, so its bibliography entry will also be removed.
          </p>
          <div className="mt-2 rounded-md border border-danger/20 bg-danger-subtle p-2 text-xs/5 text-danger-subtle-fg">
            <span className="mr-2 font-mono">−</span>
            {marker}{change.beforeText}
          </div>
        </>
      ) : null}
      {change.action === 'retain' ? (
        <>
          <p className="mt-1 text-xs/5 text-muted-fg">
            This source is cited elsewhere, so its bibliography entry will be kept.
          </p>
          <div className="mt-2 rounded-md border border-border bg-muted/40 p-2 text-xs/5 text-fg">
            <span className="mr-2 font-mono">=</span>
            {marker}{change.afterText}
          </div>
        </>
      ) : null}
    </section>
  )
}
