import { FaTriangleExclamation } from 'react-icons/fa6'

export function LoadingCard({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="bb-card flex items-center gap-3 text-sm text-muted">
      <span className="h-3 w-3 animate-pulse rounded-full bg-chart-muted" />
      {label}
    </div>
  )
}

export function ErrorCard({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : String(error)
  return (
    <div className="bb-card">
      <div className="bb-feature">
        <div className="bb-tile bg-grad-violet">
          <FaTriangleExclamation className="h-[44%] w-[44%]" />
        </div>
        <div className="min-w-0">
          <div className="bb-kicker">Couldn’t load data</div>
          <p className="mt-1 break-words text-sm text-muted">{msg}</p>
          <p className="mt-1 text-xs text-muted">
            Is the backend running at http://localhost:8000?
          </p>
        </div>
      </div>
    </div>
  )
}

export function EmptyCard({ label = 'Nothing to show yet.' }: { label?: string }) {
  return (
    <div className="bb-card text-sm text-muted">{label}</div>
  )
}
