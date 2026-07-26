import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FaTable, FaMapLocationDot, FaMagnifyingGlass } from 'react-icons/fa6'
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet'
import PageHeader from '../components/PageHeader'
import { ErrorCard, LoadingCard } from '../components/States'
import { api } from '../lib/api'
import { outletClassChip, outletClassColor } from '../lib/ui'
import type { OutletOut, RegionOut } from '../lib/types'

type View = 'table' | 'map'

function OutletTable({ outlets }: { outlets: OutletOut[] }) {
  if (outlets.length === 0)
    return <div className="bb-card text-sm text-muted">No outlets match your filters.</div>
  return (
    <div className="bb-card overflow-x-auto p-0">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
            <th className="px-4 py-3 font-semibold">Name</th>
            <th className="px-4 py-3 font-semibold">Area</th>
            <th className="px-4 py-3 font-semibold">Class</th>
            <th className="px-4 py-3 font-semibold">Trade type</th>
            <th className="px-4 py-3 font-semibold">Sales rep</th>
            <th className="px-4 py-3 font-semibold">Area manager</th>
            <th className="px-4 py-3 font-semibold">Distributor</th>
            <th className="px-4 py-3 font-semibold">Phone</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {outlets.map((o) => (
            <tr key={o.id} className="hover:bg-tint/60">
              <td className="px-4 py-3">
                <div className="font-semibold text-ink">{o.name}</div>
                <div className="text-xs text-muted">{o.code}</div>
              </td>
              <td className="px-4 py-3 text-muted">{o.area_name ?? '—'}</td>
              <td className="px-4 py-3">
                {o.outlet_class ? (
                  <span className={`bb-chip ${outletClassChip(o.outlet_class)}`}>
                    {o.outlet_class}
                  </span>
                ) : (
                  '—'
                )}
              </td>
              <td className="px-4 py-3 text-muted">{o.trade_type}</td>
              <td className="px-4 py-3 text-ink">{o.sales_rep ?? '—'}</td>
              <td className="px-4 py-3 text-muted">{o.area_manager ?? '—'}</td>
              <td className="px-4 py-3 text-muted">{o.distributor_name ?? '—'}</td>
              <td className="px-4 py-3 text-muted">{o.phone ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function OutletMap({ outlets }: { outlets: OutletOut[] }) {
  const geo = outlets.filter(
    (o): o is OutletOut & { lat: number; lon: number } =>
      typeof o.lat === 'number' && typeof o.lon === 'number',
  )
  return (
    <div className="bb-card overflow-hidden p-0">
      <MapContainer
        center={[11.0, 78.5]}
        zoom={6}
        scrollWheelZoom
        style={{ height: 560, width: '100%' }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {geo.map((o) => (
          <CircleMarker
            key={o.id}
            center={[o.lat, o.lon]}
            radius={7}
            pathOptions={{
              color: outletClassColor(o.outlet_class),
              fillColor: outletClassColor(o.outlet_class),
              fillOpacity: 0.75,
              weight: 1.5,
            }}
          >
            <Popup>
              <div className="text-sm">
                <div className="font-semibold">{o.name}</div>
                <div>Rep: {o.sales_rep ?? '—'}</div>
                <div>Class: {o.outlet_class ?? '—'}</div>
                <div>Area: {o.area_name ?? '—'}</div>
              </div>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  )
}

export default function Retailers() {
  const [view, setView] = useState<View>('table')
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [regionId, setRegionId] = useState<string>('')

  const { data: regions } = useQuery({
    queryKey: ['regions'],
    queryFn: () => api<RegionOut[]>('/api/regions'),
  })

  const path = useMemo(() => {
    const params = new URLSearchParams({ limit: '500' })
    if (q.trim()) params.set('q', q.trim())
    if (regionId) params.set('region_id', regionId)
    return `/api/outlets?${params.toString()}`
  }, [q, regionId])

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['outlets', q, regionId],
    queryFn: () => api<OutletOut[]>(path),
  })

  return (
    <>
      <PageHeader
        kicker="Retail mapping"
        title="Retailers & their sales team"
        subtitle="Each outlet with its sales rep, area manager and distributor — plus a map view."
        actions={
          <div className="inline-flex rounded-pill border border-line bg-white p-1 shadow-soft-sm">
            <button
              type="button"
              onClick={() => setView('table')}
              className={`inline-flex items-center gap-2 rounded-pill px-4 py-2 text-sm font-semibold transition-colors ${
                view === 'table' ? 'bg-ink text-white' : 'text-muted hover:text-ink'
              }`}
            >
              <FaTable className="h-3.5 w-3.5" /> Table
            </button>
            <button
              type="button"
              onClick={() => setView('map')}
              className={`inline-flex items-center gap-2 rounded-pill px-4 py-2 text-sm font-semibold transition-colors ${
                view === 'map' ? 'bg-ink text-white' : 'text-muted hover:text-ink'
              }`}
            >
              <FaMapLocationDot className="h-3.5 w-3.5" /> Map
            </button>
          </div>
        }
      />

      <form
        className="mb-6 flex flex-wrap items-center gap-3"
        onSubmit={(e) => {
          e.preventDefault()
          setQ(search)
        }}
      >
        <div className="relative flex-1 min-w-[220px]">
          <FaMagnifyingGlass className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search outlets by name, owner, code…"
            className="w-full rounded-pill border border-line bg-white py-2.5 pl-10 pr-4 text-sm text-ink shadow-soft-sm outline-none focus:border-violet"
          />
        </div>
        <select
          value={regionId}
          onChange={(e) => setRegionId(e.target.value)}
          className="rounded-pill border border-line bg-white px-4 py-2.5 text-sm text-ink shadow-soft-sm outline-none focus:border-violet"
        >
          <option value="">All regions</option>
          {regions?.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </select>
        <button type="submit" className="bb-pill py-2.5">
          Search
        </button>
      </form>

      {isLoading && <LoadingCard label="Loading outlets…" />}
      {isError && <ErrorCard error={error} />}

      {data && (
        <>
          <div className="mb-3 text-xs text-muted">
            {data.length} outlet{data.length === 1 ? '' : 's'}
            {view === 'map' &&
              ` · ${data.filter((o) => o.lat != null && o.lon != null).length} mapped`}
          </div>
          {view === 'table' ? <OutletTable outlets={data} /> : <OutletMap outlets={data} />}
        </>
      )}
    </>
  )
}
