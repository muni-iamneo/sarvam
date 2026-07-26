import { useQuery } from '@tanstack/react-query'
import {
  FaTruckFast,
  FaTriangleExclamation,
  FaBoxesStacked,
  FaLocationDot,
  FaUserTie,
} from 'react-icons/fa6'
import PageHeader from '../components/PageHeader'
import { ErrorCard, LoadingCard, EmptyCard } from '../components/States'
import { api, rupees } from '../lib/api'
import type { Delivery, RepDeliveries, RepVisitAlerts, VisitAlert } from '../lib/types'

const SIGNAL_LABEL: Record<string, string> = {
  declined: 'Declined renewal',
  unreachable: 'Unreachable',
  visit_requested: 'Visit requested',
  complaint: 'Complaint',
  competitor: 'Competitor risk',
  overstock: 'Overstocked',
}

function fmtDate(d?: string | null): string {
  if (!d) return '—'
  const dt = new Date(d)
  if (Number.isNaN(dt.getTime())) return d
  return dt.toLocaleDateString('en-IN', { weekday: 'short', month: 'short', day: 'numeric' })
}

function isTomorrow(d?: string | null): boolean {
  if (!d) return false
  const t = new Date()
  t.setDate(t.getDate() + 1)
  return d.slice(0, 10) === t.toISOString().slice(0, 10)
}

function RepBadge({ rep }: { rep: RepDeliveries['rep'] }) {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-9 w-9 items-center justify-center rounded-full bg-tint text-violet">
        <FaUserTie className="h-4 w-4" />
      </div>
      <div>
        <div className="font-semibold leading-tight text-ink">{rep.name ?? 'Unassigned'}</div>
        <div className="text-[11px] text-muted">
          {[rep.designation, rep.employee_code, rep.phone].filter(Boolean).join(' · ') || 'No rep on this beat'}
        </div>
      </div>
    </div>
  )
}

function DeliveryRow({ d }: { d: Delivery }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 rounded-tile border border-line bg-white px-4 py-3">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-ink">{d.outlet_name}</span>
          <span className="text-[11px] text-muted">{d.outlet_code}</span>
          {d.area_name && (
            <span className="inline-flex items-center gap-1 text-[11px] text-muted">
              <FaLocationDot className="h-2.5 w-2.5" /> {d.area_name}
            </span>
          )}
        </div>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {d.items.map((it, i) => (
            <span key={i} className="inline-flex items-center gap-1 rounded-chip bg-tint px-2 py-0.5 text-[11px] text-ink">
              <FaBoxesStacked className="h-2.5 w-2.5 text-violet" />
              {it.qty}× {it.sku_name}
            </span>
          ))}
          {d.items.length === 0 && <span className="text-[11px] text-muted">order #{d.order_id}</span>}
        </div>
      </div>
      <div className="text-right">
        <div className="font-display text-lg font-bold text-ink">{rupees(d.total_paise)}</div>
        <span
          className={`mt-0.5 inline-block rounded-chip px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
            isTomorrow(d.delivery_date) ? 'bg-violet text-white' : 'bg-tint text-violet'
          }`}
        >
          Deliver {isTomorrow(d.delivery_date) ? 'tomorrow' : fmtDate(d.delivery_date)}
        </span>
      </div>
    </div>
  )
}

function AlertRow({ a }: { a: VisitAlert }) {
  const urgent = a.urgency === 'urgent'
  return (
    <div
      className={`rounded-tile border bg-white px-4 py-3 ${urgent ? 'border-red-300' : 'border-line'}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span
            className={`rounded-chip px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
              urgent ? 'bg-red-500 text-white' : 'bg-amber-400 text-amber-950'
            }`}
          >
            {urgent ? '🔴 Urgent' : '🟡 Watch'}
          </span>
          <span className="font-semibold text-ink">{a.outlet_name}</span>
          <span className="text-[11px] text-muted">{a.outlet_code}</span>
          {a.area_name && <span className="text-[11px] text-muted">· {a.area_name}</span>}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {a.signals.map((s) => (
            <span key={s} className="rounded-chip bg-tint px-2 py-0.5 text-[10px] font-semibold text-violet">
              {SIGNAL_LABEL[s] ?? s}
            </span>
          ))}
        </div>
      </div>
      <p className="mt-2 whitespace-pre-line text-sm leading-snug text-ink/80">{a.reason}</p>
      <div className="mt-1.5 text-[11px] text-muted">
        {a.n_recent_calls} recent call{a.n_recent_calls === 1 ? '' : 's'} · last outcome{' '}
        <span className="font-medium text-ink/70">{a.last_outcome ?? '—'}</span> · {fmtDate(a.last_call_at)}
      </div>
    </div>
  )
}

function DeliveriesSection() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['deliveries'],
    queryFn: () => api<RepDeliveries[]>('/api/deliveries'),
    refetchInterval: 8000,
  })
  if (isLoading) return <LoadingCard label="Loading deliveries…" />
  if (isError) return <ErrorCard error={error} />
  if (!data || data.length === 0)
    return <EmptyCard label="No confirmed orders to deliver yet. Orders placed on calls appear here." />

  const totalOrders = data.reduce((n, g) => n + g.n_orders, 0)
  const totalValue = data.reduce((n, g) => n + g.total_paise, 0)
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">
        <span className="font-semibold text-ink">{totalOrders}</span> order{totalOrders === 1 ? '' : 's'} ·{' '}
        <span className="font-semibold text-ink">{rupees(totalValue)}</span> across{' '}
        {data.length} rep{data.length === 1 ? '' : 's'} — deliver next day.
      </p>
      {data.map((g, i) => (
        <div key={g.rep.id ?? `x${i}`} className="bb-card">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <RepBadge rep={g.rep} />
            <div className="text-right text-xs text-muted">
              {g.n_orders} order{g.n_orders === 1 ? '' : 's'} ·{' '}
              <span className="font-semibold text-ink">{rupees(g.total_paise)}</span>
            </div>
          </div>
          <div className="space-y-2">
            {g.orders.map((d) => (
              <DeliveryRow key={d.order_id} d={d} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function AlertsSection() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['visit-alerts'],
    queryFn: () => api<RepVisitAlerts[]>('/api/visit-alerts'),
    refetchInterval: 8000,
  })
  if (isLoading) return <LoadingCard label="Analysing recent calls…" />
  if (isError) return <ErrorCard error={error} />
  if (!data || data.length === 0)
    return <EmptyCard label="No at-risk outlets from recent calls. Everyone looks healthy." />

  const totalAlerts = data.reduce((n, g) => n + g.n_alerts, 0)
  const totalUrgent = data.reduce((n, g) => n + g.n_urgent, 0)
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">
        <span className="font-semibold text-ink">{totalAlerts}</span> outlet{totalAlerts === 1 ? '' : 's'} need a visit
        {totalUrgent > 0 && (
          <>
            {' '}
            (<span className="font-semibold text-red-600">{totalUrgent} urgent</span>)
          </>
        )}{' '}
        — flagged from recent agent calls.
      </p>
      {data.map((g, i) => (
        <div key={g.rep.id ?? `x${i}`} className="bb-card">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <RepBadge rep={g.rep} />
            <div className="text-right text-xs text-muted">
              {g.n_alerts} to visit
              {g.n_urgent > 0 && <span className="ml-1 font-semibold text-red-600">· {g.n_urgent} urgent</span>}
            </div>
          </div>
          <div className="space-y-2">
            {g.alerts.map((a) => (
              <AlertRow key={a.outlet_id} a={a} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function FieldOps() {
  return (
    <div>
      <PageHeader
        kicker="Field operations"
        title="Deliveries & visit alerts"
        subtitle="What each sales rep needs to act on — orders taken by the voice agent to deliver next day, and at-risk outlets flagged from recent calls."
      />

      <section className="mb-8">
        <h3 className="mb-3 flex items-center gap-2 font-display text-base font-bold text-ink">
          <FaTruckFast className="h-4 w-4 text-violet" /> Deliveries to run
        </h3>
        <DeliveriesSection />
      </section>

      <section>
        <h3 className="mb-3 flex items-center gap-2 font-display text-base font-bold text-ink">
          <FaTriangleExclamation className="h-4 w-4 text-violet" /> Visit alerts · at-risk stores
        </h3>
        <AlertsSection />
      </section>
    </div>
  )
}
