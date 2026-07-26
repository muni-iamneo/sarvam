import { useQuery } from '@tanstack/react-query'
import { FaSitemap, FaWarehouse, FaTags } from 'react-icons/fa6'
import PageHeader from '../components/PageHeader'
import SalesHierarchy from '../components/SalesHierarchy'
import { ErrorCard, LoadingCard } from '../components/States'
import { api } from '../lib/api'
import type { BrandManagerOut, BrandOut, DistributorOut } from '../lib/types'

function SectionHeader({
  icon: Icon,
  grad,
  kicker,
  title,
}: {
  icon: React.ComponentType<{ className?: string }>
  grad: string
  kicker: string
  title: string
}) {
  return (
    <div className="bb-feature mb-5">
      <div className={`bb-tile ${grad}`}>
        <Icon className="h-[44%] w-[44%]" />
      </div>
      <div>
        <div className="bb-kicker">{kicker}</div>
        <h3 className="bb-h3">{title}</h3>
      </div>
    </div>
  )
}

function Stockists() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['distributors'],
    queryFn: () => api<DistributorOut[]>('/api/distributors'),
  })

  if (isLoading) return <LoadingCard label="Loading stockists…" />
  if (isError) return <ErrorCard error={error} />
  if (!data || data.length === 0)
    return <p className="text-sm text-muted">No distributors seeded.</p>

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-muted">
            <th className="py-2 pr-4 font-semibold">Name</th>
            <th className="py-2 pr-4 font-semibold">Type</th>
            <th className="py-2 pr-4 font-semibold">Territory</th>
            <th className="py-2 pr-4 font-semibold">Contact</th>
            <th className="py-2 pr-4 font-semibold">Margin</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {data.map((d) => (
            <tr key={d.id}>
              <td className="py-3 pr-4">
                <div className="font-semibold text-ink">{d.name}</div>
                <div className="text-xs text-muted">{d.code}</div>
              </td>
              <td className="py-3 pr-4">
                <span className="bb-chip bg-tint text-violet">{d.stockist_type}</span>
              </td>
              <td className="py-3 pr-4 text-muted">{d.territory_name ?? '—'}</td>
              <td className="py-3 pr-4 text-muted">
                {d.contact_person ?? '—'}
                {d.phone ? ` · ${d.phone}` : ''}
              </td>
              <td className="py-3 pr-4 font-semibold text-ink">{d.margin_pct.toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function BrandManagers() {
  const managers = useQuery({
    queryKey: ['brand-managers'],
    queryFn: () => api<BrandManagerOut[]>('/api/brand-managers'),
  })
  const brands = useQuery({
    queryKey: ['brands'],
    queryFn: () => api<BrandOut[]>('/api/brands'),
  })

  if (managers.isLoading || brands.isLoading)
    return <LoadingCard label="Loading brand managers…" />
  if (managers.isError) return <ErrorCard error={managers.error} />
  if (brands.isError) return <ErrorCard error={brands.error} />

  const mgrs = managers.data ?? []
  const allBrands = brands.data ?? []
  if (mgrs.length === 0) return <p className="text-sm text-muted">No brand managers seeded.</p>

  const brandsByManager = new Map<string, BrandOut[]>()
  const unassigned: BrandOut[] = []
  for (const b of allBrands) {
    if (b.brand_manager) {
      const list = brandsByManager.get(b.brand_manager) ?? []
      list.push(b)
      brandsByManager.set(b.brand_manager, list)
    } else {
      unassigned.push(b)
    }
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      {mgrs.map((mgr) => {
        const owned = brandsByManager.get(mgr.name) ?? []
        return (
          <div key={mgr.id} className="rounded-tile border border-line bg-tint/50 p-4">
            <div className="font-semibold text-ink">{mgr.name}</div>
            <div className="text-xs text-muted">
              {mgr.designation} · {mgr.employee_code} · {mgr.n_brands}{' '}
              {mgr.n_brands === 1 ? 'brand' : 'brands'}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {owned.length === 0 ? (
                <span className="text-xs text-muted">No brands linked.</span>
              ) : (
                owned.map((b) => (
                  <span
                    key={b.id}
                    className="bb-chip bg-brand-colgate/10 text-brand-colgate"
                    title={b.category ?? undefined}
                  >
                    {b.name} · {b.n_skus} SKU{b.n_skus === 1 ? '' : 's'}
                  </span>
                ))
              )}
            </div>
          </div>
        )
      })}
      {unassigned.length > 0 && (
        <div className="rounded-tile border border-line bg-tint/50 p-4 md:col-span-2">
          <div className="font-semibold text-ink">Unassigned brands</div>
          <div className="mt-3 flex flex-wrap gap-2">
            {unassigned.map((b) => (
              <span key={b.id} className="bb-chip bg-brand-colgate/10 text-brand-colgate">
                {b.name} · {b.n_skus} SKU{b.n_skus === 1 ? '' : 's'}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function Org() {
  return (
    <>
      <PageHeader
        kicker="Channel & org"
        title="Our stockists, sales hierarchy & brand managers"
        subtitle="The current stockist/distributor network, the field org chart (RSM → ASM → TSO → DSR with deputies), and brand managers by brand."
      />

      <div className="space-y-6">
        <div className="bb-card">
          <SectionHeader
            icon={FaWarehouse}
            grad="bg-grad-periwinkle"
            kicker="Channel"
            title="Stockists & distributors"
          />
          <Stockists />
        </div>

        <div className="bb-card">
          <SectionHeader
            icon={FaSitemap}
            grad="bg-grad-violet"
            kicker="Field force"
            title="Sales hierarchy"
          />
          <SalesHierarchy />
        </div>

        <div className="bb-card">
          <SectionHeader
            icon={FaTags}
            grad="bg-grad-indigo"
            kicker="Brands"
            title="Brand managers & portfolios"
          />
          <BrandManagers />
        </div>
      </div>
    </>
  )
}
