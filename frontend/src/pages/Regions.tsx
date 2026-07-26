import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FaChevronRight, FaUserTie, FaLayerGroup, FaStore } from 'react-icons/fa6'
import PageHeader from '../components/PageHeader'
import AchievementBar from '../components/AchievementBar'
import { ErrorCard, LoadingCard } from '../components/States'
import { api } from '../lib/api'
import type { AreaOut, RegionOut } from '../lib/types'

function AreaTable({ regionId }: { regionId: number }) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['areas', regionId],
    queryFn: () => api<AreaOut[]>(`/api/areas?region_id=${regionId}`),
  })

  if (isLoading) return <LoadingCard label="Loading areas…" />
  if (isError) return <ErrorCard error={error} />
  if (!data || data.length === 0)
    return <p className="text-sm text-muted">No areas in this region.</p>

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-muted">
            <th className="py-2 pr-4 font-semibold">Area</th>
            <th className="py-2 pr-4 font-semibold">Area manager</th>
            <th className="py-2 pr-4 font-semibold">Deputy</th>
            <th className="py-2 pr-4 font-semibold">Outlets</th>
            <th className="min-w-[200px] py-2 font-semibold">Achievement</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {data.map((a) => (
            <tr key={a.id} className="align-top">
              <td className="py-3 pr-4">
                <div className="font-semibold text-ink">{a.name}</div>
                <div className="text-xs text-muted">{a.code}</div>
              </td>
              <td className="py-3 pr-4 text-ink">{a.area_manager ?? '—'}</td>
              <td className="py-3 pr-4 text-muted">{a.deputy_area_manager ?? '—'}</td>
              <td className="py-3 pr-4 text-ink">{a.n_outlets}</td>
              <td className="py-3">
                <AchievementBar
                  pct={a.achievement_pct}
                  achievedPaise={a.achieved_paise}
                  targetPaise={a.target_paise}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RegionCard({
  region,
  selected,
  onToggle,
}: {
  region: RegionOut
  selected: boolean
  onToggle: () => void
}) {
  return (
    <div className="bb-card">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-start justify-between gap-3 text-left"
      >
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="bb-h3">{region.name}</h3>
            {region.zone && <span className="bb-chip bg-tint text-violet">{region.zone}</span>}
          </div>
          {region.regional_manager && (
            <div className="mt-1 flex items-center gap-1.5 text-xs text-muted">
              <FaUserTie className="h-3 w-3" /> {region.regional_manager}
            </div>
          )}
        </div>
        <FaChevronRight
          className={`mt-1 h-4 w-4 shrink-0 text-violet transition-transform ${
            selected ? 'rotate-90' : ''
          }`}
        />
      </button>

      <div className="mt-4 flex gap-4 text-sm text-muted">
        <span className="flex items-center gap-1.5">
          <FaLayerGroup className="h-3.5 w-3.5 text-violet" /> {region.n_areas} areas
        </span>
        <span className="flex items-center gap-1.5">
          <FaStore className="h-3.5 w-3.5 text-violet" /> {region.n_outlets} outlets
        </span>
      </div>

      <div className="mt-4">
        <AchievementBar
          pct={region.achievement_pct}
          achievedPaise={region.achieved_paise}
          targetPaise={region.target_paise}
        />
      </div>

      {selected && (
        <div className="mt-5 border-t border-line pt-5">
          <div className="bb-kicker mb-3">Areas in {region.name}</div>
          <AreaTable regionId={region.id} />
        </div>
      )}
    </div>
  )
}

export default function Regions() {
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['regions'],
    queryFn: () => api<RegionOut[]>('/api/regions'),
  })

  return (
    <>
      <PageHeader
        kicker="Why now"
        title="Regions, areas & targets vs. achieved"
        subtitle="Drill Region → Area with primary/secondary targets vs. actuals at each level."
      />

      {isLoading && <LoadingCard label="Loading regions…" />}
      {isError && <ErrorCard error={error} />}

      {data && data.length === 0 && (
        <div className="bb-card text-sm text-muted">No regions seeded.</div>
      )}

      {data && data.length > 0 && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {data.map((r) => (
            <div key={r.id} className={selectedId === r.id ? 'lg:col-span-2' : ''}>
              <RegionCard
                region={r}
                selected={selectedId === r.id}
                onToggle={() => setSelectedId((cur) => (cur === r.id ? null : r.id))}
              />
            </div>
          ))}
        </div>
      )}
    </>
  )
}
