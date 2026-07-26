import { useCallback, useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  FaPhoneVolume,
  FaMagnifyingGlass,
  FaXmark,
  FaTriangleExclamation,
  FaBoltLightning,
  FaCalendarPlus,
} from 'react-icons/fa6'
import PageHeader from '../components/PageHeader'
import CallDetail from '../components/CallDetail'
import { ScheduleBuilder, SchedulesPanel } from '../components/Schedules'
import { EmptyCard, ErrorCard, LoadingCard } from '../components/States'
import { api, rupees } from '../lib/api'
import { statusChip } from '../lib/ui'
import type { CallLog, OutletOut, StartCallResponse } from '../lib/types'

// ---- Outlet picker modal ----

function OutletPicker({
  onClose,
  onStarted,
  onBanner,
}: {
  onClose: () => void
  onStarted: (callId: number) => void
  onBanner: (msg: string | null) => void
}) {
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [to, setTo] = useState('')
  const [picked, setPicked] = useState<OutletOut | null>(null)
  const [starting, setStarting] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['agent-outlets', q],
    queryFn: () => api<OutletOut[]>(`/api/outlets?q=${encodeURIComponent(q)}&limit=25`),
  })

  async function start() {
    if (!picked) return
    setStarting(true)
    setLocalError(null)
    onBanner(null)
    try {
      const body: { outlet_id: number; to?: string } = { outlet_id: picked.id }
      if (to.trim()) body.to = to.trim()
      const res = await api<StartCallResponse>('/calls', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      onStarted(res.call_id)
      onClose()
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      // 503: Twilio/PUBLIC_URL not configured. 502: Twilio call failed.
      if (msg.includes('503')) {
        onBanner('Live calling needs TWILIO_* + PUBLIC_URL in backend/.env — History and Detail still work.')
        onClose()
      } else if (msg.includes('502')) {
        onBanner('Twilio failed to place the call (502). Check the backend logs and try again.')
        onClose()
      } else {
        setLocalError(msg)
      }
    } finally {
      setStarting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-ink/30 p-4 pt-24"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-card border border-line bg-white p-6 shadow-soft"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <div className="bb-kicker">New call</div>
            <h3 className="bb-h3">Pick an outlet</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-pill p-2 text-muted transition-colors hover:bg-tint hover:text-ink"
            aria-label="Close"
          >
            <FaXmark className="h-4 w-4" />
          </button>
        </div>

        <form
          className="relative mb-3"
          onSubmit={(e) => {
            e.preventDefault()
            setQ(search)
          }}
        >
          <FaMagnifyingGlass className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <input
            autoFocus
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search outlets by name, code, area…"
            className="w-full rounded-pill border border-line bg-white py-2.5 pl-10 pr-4 text-sm text-ink shadow-soft-sm outline-none focus:border-violet"
          />
        </form>

        <div className="max-h-64 space-y-1.5 overflow-y-auto pr-1">
          {isLoading && <LoadingCard label="Loading outlets…" />}
          {isError && <ErrorCard error={error} />}
          {data && data.length === 0 && <EmptyCard label="No outlets match." />}
          {data?.map((o) => {
            const active = picked?.id === o.id
            return (
              <button
                key={o.id}
                type="button"
                onClick={() => setPicked(o)}
                className={`flex w-full items-center justify-between gap-3 rounded-tile border p-3 text-left transition-colors ${
                  active
                    ? 'border-violet bg-tint'
                    : 'border-line bg-white hover:bg-tint/60'
                }`}
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-ink">{o.name}</div>
                  <div className="truncate text-xs text-muted">
                    {[o.code, o.area_name, o.sales_rep].filter(Boolean).join(' · ')}
                  </div>
                </div>
                <div className="shrink-0 text-right text-xs text-muted">
                  {o.language && <div>{o.language}</div>}
                  {o.phone && <div>{o.phone}</div>}
                </div>
              </button>
            )
          })}
        </div>

        <div className="mt-4 border-t border-line pt-4">
          <label className="mb-1.5 block text-xs font-semibold text-muted">
            Override “to” number (optional)
          </label>
          <input
            value={to}
            onChange={(e) => setTo(e.target.value)}
            placeholder={picked?.phone ?? '+91…'}
            className="mb-3 w-full rounded-pill border border-line bg-white px-4 py-2.5 text-sm text-ink shadow-soft-sm outline-none focus:border-violet"
          />
          {localError && (
            <div className="mb-3 flex items-start gap-2 rounded-tile border border-brand-colgate/20 bg-brand-colgate/5 p-3 text-xs text-brand-colgate">
              <FaTriangleExclamation className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span className="break-words">{localError}</span>
            </div>
          )}
          <div className="flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-pill px-4 py-2.5 text-sm font-semibold text-muted transition-colors hover:text-ink"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={!picked || starting}
              onClick={start}
              className="bb-pill py-2.5 disabled:cursor-not-allowed"
            >
              <FaPhoneVolume className="h-4 w-4" />
              {starting ? 'Starting…' : picked ? `Call ${picked.name}` : 'Start a call'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ---- Call history list ----

function outcomeColor(outcome: string): string {
  const o = outcome.toLowerCase()
  if (o === 'ordered') return 'bg-violet text-white'
  if (o === 'initiated') return 'bg-tint text-violet'
  if (o === 'declined' || o === 'no_answer') return 'bg-line text-ink'
  if (o === 'failed') return 'bg-brand-colgate/10 text-brand-colgate'
  return statusChip(outcome)
}

function HistoryRow({
  call,
  selected,
  active,
  onClick,
}: {
  call: CallLog
  selected: boolean
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full flex-col gap-2 rounded-tile border p-3 text-left transition-colors ${
        selected ? 'border-violet bg-tint' : 'border-line bg-white hover:bg-tint/60'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-ink">{call.outlet_name}</div>
          <div className="truncate text-xs text-muted">{call.outlet_code}</div>
        </div>
        <span className={`bb-chip ${outcomeColor(call.outcome)} inline-flex items-center gap-1.5`}>
          {active && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />}
          {call.outcome}
        </span>
      </div>
      <div className="flex items-center justify-between gap-3 text-xs text-muted">
        <span>{new Date(call.started_at).toLocaleTimeString('en-IN')}</span>
        <div className="flex items-center gap-3">
          {call.latency_p50_ms != null && (
            <span className="inline-flex items-center gap-1">
              <FaBoltLightning className="h-3 w-3 text-violet" />
              {call.latency_p50_ms} ms
            </span>
          )}
          {call.order_id != null && (
            <span className="font-semibold text-violet">{rupees(call.cost_inr_paise)}</span>
          )}
        </div>
      </div>
    </button>
  )
}

function CallHistory({
  selectedId,
  activeId,
  onSelect,
}: {
  selectedId: number | null
  activeId: number | null
  onSelect: (id: number) => void
}) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['calls'],
    queryFn: () => api<CallLog[]>('/api/calls?limit=50'),
    refetchInterval: 4000,
  })

  return (
    <div className="bb-card">
      <div className="bb-kicker mb-3">Call history</div>
      {isLoading && <LoadingCard label="Loading calls…" />}
      {isError && <ErrorCard error={error} />}
      {data && data.length === 0 && <EmptyCard label="No calls yet — start one." />}
      {data && data.length > 0 && (
        <div className="max-h-[560px] space-y-2 overflow-y-auto pr-1">
          {data.map((c) => (
            <HistoryRow
              key={c.id}
              call={c}
              selected={selectedId === c.id}
              active={activeId === c.id}
              onClick={() => onSelect(c.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ---- Page ----

type Tab = 'history' | 'schedules'

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-pill px-4 py-1.5 text-sm font-semibold transition-colors ${
        active ? 'bg-violet text-white' : 'text-muted hover:text-ink'
      }`}
    >
      {children}
    </button>
  )
}

export default function Agent() {
  const qc = useQueryClient()
  const [pickerOpen, setPickerOpen] = useState(false)
  const [scheduleOpen, setScheduleOpen] = useState(false)
  const [tab, setTab] = useState<Tab>('history')
  const [banner, setBanner] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [activeId, setActiveId] = useState<number | null>(null)

  const isActive = useMemo(
    () => selectedId != null && selectedId === activeId,
    [selectedId, activeId],
  )

  // Refresh history when the active call is set/cleared.
  useEffect(() => {
    qc.invalidateQueries({ queryKey: ['calls'] })
  }, [activeId, qc])

  function handleStarted(callId: number) {
    setActiveId(callId)
    setSelectedId(callId)
  }

  function handleFinalized() {
    // The active call has wrapped up — drop the live flag so the detail view
    // falls back to the saved record and history reflects the outcome.
    setActiveId(null)
    qc.invalidateQueries({ queryKey: ['calls'] })
    if (selectedId != null) qc.invalidateQueries({ queryKey: ['call', selectedId] })
  }

  // Bridge a schedule item to the unified CallDetail view (live or saved).
  const openCall = useCallback((callId: number, live: boolean) => {
    setSelectedId(callId)
    setActiveId(live ? callId : null)
  }, [])

  return (
    <>
      <PageHeader
        kicker="Live demo"
        title="Voice agent"
        subtitle="Trigger a renewal call or schedule a batch, watch it live, and review the transcript, order and post-call summary."
        actions={
          <div className="flex items-center gap-2">
            <button className="bb-pill" onClick={() => setPickerOpen(true)}>
              <FaPhoneVolume className="h-4 w-4" /> Start a call
            </button>
            <button
              className="inline-flex items-center gap-2 rounded-pill border border-line bg-white px-4 py-2.5 text-sm font-semibold text-violet transition-colors hover:bg-tint"
              onClick={() => setScheduleOpen(true)}
            >
              <FaCalendarPlus className="h-4 w-4" /> Schedule calls
            </button>
          </div>
        }
      />

      {banner && (
        <div className="mb-6 flex items-start justify-between gap-3 rounded-card border border-violet/20 bg-tint p-4">
          <div className="flex items-start gap-3">
            <FaTriangleExclamation className="mt-0.5 h-4 w-4 shrink-0 text-violet" />
            <p className="text-sm text-ink">{banner}</p>
          </div>
          <button
            type="button"
            onClick={() => setBanner(null)}
            className="shrink-0 rounded-pill p-1 text-muted transition-colors hover:text-ink"
            aria-label="Dismiss"
          >
            <FaXmark className="h-4 w-4" />
          </button>
        </div>
      )}

      <div className="mb-4 inline-flex rounded-pill border border-line bg-white p-1">
        <TabButton active={tab === 'history'} onClick={() => setTab('history')}>
          Call history
        </TabButton>
        <TabButton active={tab === 'schedules'} onClick={() => setTab('schedules')}>
          Schedules
        </TabButton>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(280px,360px)_1fr]">
        {tab === 'history' ? (
          <CallHistory selectedId={selectedId} activeId={activeId} onSelect={setSelectedId} />
        ) : (
          <SchedulesPanel onOpenCall={openCall} />
        )}
        <CallDetail callId={selectedId} isActive={isActive} onFinalized={handleFinalized} />
      </div>

      {pickerOpen && (
        <OutletPicker
          onClose={() => setPickerOpen(false)}
          onStarted={handleStarted}
          onBanner={setBanner}
        />
      )}

      {scheduleOpen && (
        <ScheduleBuilder
          onClose={() => setScheduleOpen(false)}
          onCreated={() => {
            setTab('schedules')
            qc.invalidateQueries({ queryKey: ['schedules'] })
          }}
        />
      )}
    </>
  )
}
