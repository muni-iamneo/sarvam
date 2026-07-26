import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  FaXmark,
  FaMagnifyingGlass,
  FaCalendarPlus,
  FaBolt,
  FaClock,
  FaCheck,
  FaCircleXmark,
  FaBan,
} from 'react-icons/fa6'
import { api } from '../lib/api'
import { EmptyCard, ErrorCard, LoadingCard } from './States'
import type { OutletOut, Schedule, ScheduleItem } from '../lib/types'
import {
  EMPTY_TARGETING,
  TargetingFields,
  targetingBody,
  targetingValid,
  type TargetingValue,
} from './TargetingFields'

// ---- chips ----

function scheduleChip(status: string): string {
  switch (status) {
    case 'running':
      return 'bg-violet text-white'
    case 'completed':
      return 'bg-tint text-violet'
    case 'canceled':
      return 'bg-line text-muted'
    case 'failed':
      return 'bg-brand-colgate/10 text-brand-colgate'
    default:
      return 'bg-line text-ink' // pending
  }
}

function ItemStatusIcon({ status }: { status: ScheduleItem['status'] }) {
  switch (status) {
    case 'calling':
      return <span className="h-2 w-2 animate-pulse rounded-full bg-violet" />
    case 'done':
      return <FaCheck className="h-3 w-3 text-violet" />
    case 'failed':
      return <FaCircleXmark className="h-3 w-3 text-brand-colgate" />
    case 'skipped':
      return <FaBan className="h-3 w-3 text-muted" />
    default:
      return <FaClock className="h-3 w-3 text-muted" /> // queued
  }
}

// ---- builder modal ----

function nowLocalValue(): string {
  // datetime-local wants "YYYY-MM-DDThh:mm" in local time.
  const d = new Date(Date.now() + 5 * 60 * 1000) // default +5 min
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function ScheduleBuilder({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: (s: Schedule) => void
}) {
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [picked, setPicked] = useState<Map<number, OutletOut>>(new Map())
  const [mode, setMode] = useState<'now' | 'scheduled'>('now')
  const [when, setWhen] = useState(nowLocalValue())
  const [name, setName] = useState('')
  const [targeting, setTargeting] = useState<TargetingValue>(EMPTY_TARGETING)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { data, isLoading, isError, error: qErr } = useQuery({
    queryKey: ['agent-outlets', q],
    queryFn: () => api<OutletOut[]>(`/api/outlets?q=${encodeURIComponent(q)}&limit=25`),
  })

  const chosen = useMemo(() => [...picked.values()], [picked])

  function toggle(o: OutletOut) {
    setPicked((prev) => {
      const next = new Map(prev)
      if (next.has(o.id)) next.delete(o.id)
      else next.set(o.id, o)
      return next
    })
  }

  async function submit() {
    if (chosen.length === 0 || !targetingValid(targeting)) return
    setBusy(true)
    setError(null)
    try {
      const body = {
        name: name.trim() || null,
        mode,
        scheduled_at: mode === 'scheduled' ? when : null,
        items: chosen.map((o) => ({ outlet_id: o.id })),
        ...targetingBody(targeting),
      }
      const created = await api<Schedule>('/api/schedules', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      onCreated(created)
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-ink/30 p-4 pt-16"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl rounded-card border border-line bg-white p-6 shadow-soft"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <div className="bb-kicker">Batch calls</div>
            <h3 className="bb-h3">Schedule a call campaign</h3>
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

        {/* selected chips */}
        {chosen.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-2">
            {chosen.map((o) => (
              <button
                key={o.id}
                type="button"
                onClick={() => toggle(o)}
                className="inline-flex items-center gap-1.5 rounded-pill bg-violet px-3 py-1 text-xs font-semibold text-white"
              >
                {o.name}
                <FaXmark className="h-3 w-3" />
              </button>
            ))}
          </div>
        )}

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
            placeholder="Search outlets to add…"
            className="w-full rounded-pill border border-line bg-white py-2.5 pl-10 pr-4 text-sm text-ink shadow-soft-sm outline-none focus:border-violet"
          />
        </form>

        <div className="max-h-48 space-y-1.5 overflow-y-auto pr-1">
          {isLoading && <LoadingCard label="Loading outlets…" />}
          {isError && <ErrorCard error={qErr} />}
          {data && data.length === 0 && <EmptyCard label="No outlets match." />}
          {data?.map((o) => {
            const active = picked.has(o.id)
            return (
              <button
                key={o.id}
                type="button"
                onClick={() => toggle(o)}
                className={`flex w-full items-center justify-between gap-3 rounded-tile border p-3 text-left transition-colors ${
                  active ? 'border-violet bg-tint' : 'border-line bg-white hover:bg-tint/60'
                }`}
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-ink">{o.name}</div>
                  <div className="truncate text-xs text-muted">
                    {[o.code, o.area_name].filter(Boolean).join(' · ')}
                  </div>
                </div>
                <span
                  className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-chip border ${
                    active ? 'border-violet bg-violet text-white' : 'border-line text-transparent'
                  }`}
                >
                  <FaCheck className="h-2.5 w-2.5" />
                </span>
              </button>
            )
          })}
        </div>

        {/* when */}
        <div className="mt-4 border-t border-line pt-4">
          <div className="mb-3 flex gap-2">
            <button
              type="button"
              onClick={() => setMode('now')}
              className={`inline-flex flex-1 items-center justify-center gap-2 rounded-pill border px-3 py-2 text-sm font-semibold transition-colors ${
                mode === 'now' ? 'border-violet bg-tint text-violet' : 'border-line text-muted'
              }`}
            >
              <FaBolt className="h-3.5 w-3.5" /> Call now
            </button>
            <button
              type="button"
              onClick={() => setMode('scheduled')}
              className={`inline-flex flex-1 items-center justify-center gap-2 rounded-pill border px-3 py-2 text-sm font-semibold transition-colors ${
                mode === 'scheduled' ? 'border-violet bg-tint text-violet' : 'border-line text-muted'
              }`}
            >
              <FaClock className="h-3.5 w-3.5" /> Schedule
            </button>
          </div>

          {mode === 'scheduled' && (
            <input
              type="datetime-local"
              value={when}
              onChange={(e) => setWhen(e.target.value)}
              className="mb-3 w-full rounded-pill border border-line bg-white px-4 py-2.5 text-sm text-ink shadow-soft-sm outline-none focus:border-violet"
            />
          )}

          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Campaign name (optional)"
            className="mb-1 w-full rounded-pill border border-line bg-white px-4 py-2.5 text-sm text-ink shadow-soft-sm outline-none focus:border-violet"
          />
          <p className="mb-3 px-1 text-xs text-muted">
            Calls run one at a time, in order{mode === 'now' ? ', starting now.' : ', from the scheduled time.'}
          </p>

          <div className="mb-3">
            <TargetingFields value={targeting} onChange={setTargeting} />
          </div>

          {error && (
            <div className="mb-3 rounded-tile border border-brand-colgate/20 bg-brand-colgate/5 p-3 text-xs text-brand-colgate">
              {error}
            </div>
          )}

          <div className="flex items-center justify-between gap-3">
            <span className="text-xs text-muted">{chosen.length} selected</span>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={onClose}
                className="rounded-pill px-4 py-2.5 text-sm font-semibold text-muted transition-colors hover:text-ink"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={chosen.length === 0 || !targetingValid(targeting) || busy}
                onClick={submit}
                className="bb-pill py-2.5 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <FaCalendarPlus className="h-4 w-4" />
                {busy ? 'Scheduling…' : mode === 'now' ? 'Start campaign' : 'Schedule campaign'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ---- schedule detail (items) ----

function ScheduleDetail({
  scheduleId,
  onOpenCall,
}: {
  scheduleId: number
  onOpenCall: (callId: number, live: boolean) => void
}) {
  const qc = useQueryClient()
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['schedule', scheduleId],
    queryFn: () => api<Schedule>(`/api/schedules/${scheduleId}`),
    refetchInterval: 3000,
  })

  // Auto-follow the live call: whenever the active call changes, stream it.
  const activeCallId = data?.active_call_id ?? null
  useEffect(() => {
    if (activeCallId != null) onOpenCall(activeCallId, true)
  }, [activeCallId, onOpenCall])

  async function cancel() {
    await api(`/api/schedules/${scheduleId}/cancel`, { method: 'POST' })
    qc.invalidateQueries({ queryKey: ['schedule', scheduleId] })
    qc.invalidateQueries({ queryKey: ['schedules'] })
  }

  if (isLoading) return <LoadingCard label="Loading schedule…" />
  if (isError) return <ErrorCard error={error} />
  if (!data) return null

  const cancelable = data.status === 'pending' || data.status === 'running'

  return (
    <div className="mt-3 border-t border-line pt-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-xs text-muted">
          {data.n_done}/{data.n_items} done
          {data.mode === 'scheduled' && data.scheduled_at
            ? ` · for ${new Date(data.scheduled_at).toLocaleString('en-IN')}`
            : ''}
        </span>
        {cancelable && (
          <button
            type="button"
            onClick={cancel}
            className="rounded-pill border border-line px-2.5 py-1 text-[11px] font-semibold text-brand-colgate transition-colors hover:bg-brand-colgate/5"
          >
            Cancel remaining
          </button>
        )}
      </div>
      <ul className="space-y-1.5">
        {data.items.map((it) => {
          const clickable = it.call_id != null
          return (
            <li key={it.id}>
              <button
                type="button"
                disabled={!clickable}
                onClick={() => it.call_id != null && onOpenCall(it.call_id, it.status === 'calling')}
                className={`flex w-full items-center justify-between gap-2 rounded-chip px-2.5 py-2 text-left text-sm transition-colors ${
                  clickable ? 'hover:bg-tint' : 'cursor-default'
                } ${it.status === 'calling' ? 'bg-tint' : ''}`}
              >
                <span className="flex min-w-0 items-center gap-2">
                  <ItemStatusIcon status={it.status} />
                  <span className="truncate text-ink">{it.outlet_name}</span>
                </span>
                <span className="shrink-0 text-xs text-muted">
                  {it.outcome ?? it.note ?? it.status}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

// ---- schedules list panel ----

export function SchedulesPanel({
  onOpenCall,
}: {
  onOpenCall: (callId: number, live: boolean) => void
}) {
  const [openId, setOpenId] = useState<number | null>(null)
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['schedules'],
    queryFn: () => api<Schedule[]>('/api/schedules?limit=50'),
    refetchInterval: 4000,
  })

  // Auto-open the most recent running schedule so its live call is visible.
  useEffect(() => {
    if (openId != null || !data) return
    const running = data.find((s) => s.status === 'running')
    if (running) setOpenId(running.id)
  }, [data, openId])

  return (
    <div className="bb-card">
      <div className="bb-kicker mb-3">Scheduled campaigns</div>
      {isLoading && <LoadingCard label="Loading schedules…" />}
      {isError && <ErrorCard error={error} />}
      {data && data.length === 0 && <EmptyCard label="No campaigns yet — schedule one." />}
      {data && data.length > 0 && (
        <div className="max-h-[560px] space-y-2 overflow-y-auto pr-1">
          {data.map((s) => {
            const open = openId === s.id
            return (
              <div
                key={s.id}
                className={`rounded-tile border p-3 transition-colors ${
                  open ? 'border-violet bg-tint/40' : 'border-line bg-white'
                }`}
              >
                <button
                  type="button"
                  onClick={() => setOpenId(open ? null : s.id)}
                  className="flex w-full items-start justify-between gap-3 text-left"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-ink">
                      {s.name || `Campaign #${s.id}`}
                    </div>
                    <div className="mt-0.5 flex items-center gap-1.5 text-xs text-muted">
                      {s.mode === 'scheduled' ? (
                        <FaClock className="h-3 w-3" />
                      ) : (
                        <FaBolt className="h-3 w-3" />
                      )}
                      {s.n_items} outlet{s.n_items === 1 ? '' : 's'} · {s.n_done}/{s.n_items}
                    </div>
                  </div>
                  <span className={`bb-chip ${scheduleChip(s.status)} inline-flex items-center gap-1.5`}>
                    {s.status === 'running' && (
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
                    )}
                    {s.status}
                  </span>
                </button>
                {open && <ScheduleDetail scheduleId={s.id} onOpenCall={onOpenCall} />}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
