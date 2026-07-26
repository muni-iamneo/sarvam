import { rupees } from '../lib/api'

/** A slim violet progress bar with achievement % and ₹ achieved / target. */
export default function AchievementBar({
  pct,
  achievedPaise,
  targetPaise,
  compact = false,
}: {
  pct: number
  achievedPaise: number
  targetPaise: number
  compact?: boolean
}) {
  const clamped = Math.max(0, Math.min(100, pct))
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <span className="font-sans text-sm font-semibold text-ink">{pct.toFixed(1)}%</span>
        {!compact && (
          <span className="text-xs text-muted">
            {rupees(achievedPaise)} / {rupees(targetPaise)}
          </span>
        )}
      </div>
      <div className="h-2 w-full overflow-hidden rounded-pill bg-line">
        <div
          className="h-full rounded-pill bg-violet transition-[width]"
          style={{ width: `${clamped}%` }}
        />
      </div>
      {compact && (
        <div className="mt-1 text-xs text-muted">
          {rupees(achievedPaise)} / {rupees(targetPaise)}
        </div>
      )}
    </div>
  )
}
