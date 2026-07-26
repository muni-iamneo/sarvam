import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FaArrowsToDot, FaUpRightAndDownLeftFromCenter } from 'react-icons/fa6'
import { api } from '../lib/api'
import { ErrorCard, LoadingCard } from './States'
import OrgChart from './OrgChart'
import { buildTree, defaultCollapsed, desColor, desLabel, designationsIn } from '../lib/orgTree'
import type { RepOut } from '../lib/types'

function LegendDot({ d }: { d: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted">
      <span className="h-2.5 w-2.5 rounded-full" style={{ background: desColor(d) }} />
      {desLabel(d)}
    </span>
  )
}

export default function SalesHierarchy() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['reps'],
    queryFn: () => api<RepOut[]>('/api/reps'),
  })

  const root = useMemo(() => (data ? buildTree(data) : null), [data])
  const [collapsed, setCollapsed] = useState<Set<number> | null>(null)

  const effectiveCollapsed = useMemo(() => {
    if (collapsed) return collapsed
    return root ? defaultCollapsed(root) : new Set<number>()
  }, [collapsed, root])

  if (isLoading) return <LoadingCard label="Loading sales team…" />
  if (isError) return <ErrorCard error={error} />
  if (!root || root.children.length === 0)
    return <p className="text-sm text-muted">No reps seeded.</p>

  const toggle = (id: number) => {
    setCollapsed((prev) => {
      const base = prev ?? defaultCollapsed(root)
      const next = new Set(base)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
          {designationsIn(root).map((d) => (
            <LegendDot key={d} d={d} />
          ))}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setCollapsed(new Set())}
            className="inline-flex items-center gap-1.5 rounded-pill border border-line px-3 py-1.5 text-xs font-semibold text-violet transition-colors hover:bg-tint"
          >
            <FaUpRightAndDownLeftFromCenter className="h-3 w-3" /> Expand all
          </button>
          <button
            type="button"
            onClick={() => setCollapsed(defaultCollapsed(root))}
            className="inline-flex items-center gap-1.5 rounded-pill border border-line px-3 py-1.5 text-xs font-semibold text-violet transition-colors hover:bg-tint"
          >
            <FaArrowsToDot className="h-3 w-3" /> Collapse
          </button>
        </div>
      </div>

      <OrgChart root={root} collapsed={effectiveCollapsed} onToggle={toggle} />
    </div>
  )
}
