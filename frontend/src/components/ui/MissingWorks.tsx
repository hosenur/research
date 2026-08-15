import { ArrowUpRightIcon as ArrowUpRight } from '@phosphor-icons/react'

export interface MissingWorkJson {
  sectionId: string
  sectionTitle: string
  claim: string
  reason: string
  work: {
    id: string
    title?: string | null
    year?: number | null
    citedByCount?: number | null
    landingPageUrl?: string | null
    abstract?: string | null
  }
}

export interface MissingWorkReportJson {
  queries: { sectionTitle: string; text: string; status: string; error?: string | null }[]
  findings: MissingWorkJson[]
  warnings: string[]
}

export function MissingWorks({ report }: { report: MissingWorkReportJson }) {
  return (
    <div className="openalex-panel border-t border-ink/10 bg-white/70">
      <div className="flex items-center justify-between gap-3 px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-[0.1em] text-ink/45">
          Missing work
        </p>
        <p className="text-xs tabular-nums text-ink/40">
          {report.findings.length} candidate{report.findings.length === 1 ? '' : 's'}
        </p>
      </div>

      {report.warnings.length ? (
        <p className="px-4 pb-2 text-xs leading-5 text-ink/45">{report.warnings.at(-1)}</p>
      ) : null}

      <div className="max-h-[28rem] overflow-auto [scrollbar-color:rgba(41,39,32,0.2)_transparent]">
        {report.findings.length ? (
          report.findings.map((finding, index) => {
            const href = finding.work.landingPageUrl || finding.work.id
            return (
              <article
                key={`${finding.work.id}-${index}`}
                className="openalex-row border-t border-ink/8 px-4 py-3.5"
                style={{ animationDelay: `${Math.min(index, 8) * 35}ms` }}
              >
                <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-ink/35">
                  {finding.sectionTitle}
                </p>
                <p className="mt-1 text-sm font-semibold leading-5 text-ink">
                  {finding.work.title || finding.work.id}
                </p>
                <p className="mt-1 text-xs text-ink/45">
                  {[finding.work.year, finding.reason].filter(Boolean).join(' · ')}
                </p>
                <p className="mt-2 text-[13px] leading-5 text-ink/55">“{finding.claim}”</p>
                {href ? (
                  <a
                    href={href}
                    target="_blank"
                    rel="noreferrer"
                    className="pressable mt-2 inline-flex items-center gap-1 text-xs font-medium text-sage outline-none hover:text-sage/80 focus-visible:ring-2 focus-visible:ring-sage/30"
                  >
                    Open in OpenAlex
                    <ArrowUpRight aria-hidden="true" className="size-3.5" />
                  </a>
                ) : null}
              </article>
            )
          })
        ) : (
          <p className="px-4 py-6 text-sm text-ink/45">
            No uncited related work turned up. Empty or failed searches stay visible in the
            report instead of inventing papers.
          </p>
        )}
      </div>
    </div>
  )
}
