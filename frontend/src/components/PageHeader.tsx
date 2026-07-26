import type { ReactNode } from 'react'

export default function PageHeader({
  kicker,
  title,
  subtitle,
  actions,
}: {
  kicker: string
  title: string
  subtitle?: string
  actions?: ReactNode
}) {
  return (
    <header className="mb-6 flex items-start justify-between gap-4">
      <div>
        <div className="bb-kicker mb-2">{kicker}</div>
        <h2 className="bb-h2">{title}</h2>
        {subtitle && <p className="mt-1 max-w-2xl text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="shrink-0">{actions}</div>}
    </header>
  )
}
