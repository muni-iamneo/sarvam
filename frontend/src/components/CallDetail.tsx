import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  FaMicrophoneLines,
  FaBoltLightning,
  FaClockRotateLeft,
  FaBasketShopping,
  FaWaveSquare,
  FaHeadphones,
} from 'react-icons/fa6'
import { api, mediaUrl, rupees } from '../lib/api'
import { statusChip } from '../lib/ui'
import { useCallLive } from '../hooks/useCallLive'
import type { CallDetail as CallDetailData, LiveOrder, Order, TranscriptTurn } from '../lib/types'
import { EmptyCard, ErrorCard, LoadingCard } from './States'

function StatusPill({ label, live }: { label: string; live?: boolean }) {
  return (
    <span
      className={`bb-chip ${statusChip(label)} inline-flex items-center gap-1.5`}
      title={live ? 'Live call' : undefined}
    >
      {live && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />}
      {label}
    </span>
  )
}

function fmtElapsed(ms?: number): string | null {
  if (ms == null) return null
  const s = Math.floor(ms / 1000)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

function gapBetween(prev: TranscriptTurn | undefined, cur: TranscriptTurn): number | undefined {
  if (!prev || prev.t_ms == null || cur.t_ms == null) return undefined
  const g = cur.t_ms - prev.t_ms
  return g >= 0 ? g : undefined
}

function Bubble({ turn, gapMs }: { turn: TranscriptTurn; gapMs?: number }) {
  const isUser = turn.role === 'user'
  const elapsed = fmtElapsed(turn.t_ms)
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] rounded-tile px-4 py-2.5 text-sm ${
          isUser
            ? 'bg-violet text-white'
            : 'border border-line bg-tint text-ink'
        }`}
      >
        <div
          className={`mb-0.5 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wide ${
            isUser ? 'text-on-dark-accent' : 'text-violet'
          }`}
        >
          <span>{isUser ? 'Retailer' : 'Agent'}</span>
          {elapsed && <span className="font-normal tabular-nums opacity-70">{elapsed}</span>}
          {gapMs != null && (
            <span
              className={`rounded px-1 py-px font-normal tabular-nums ${
                isUser ? 'bg-white/15 text-white/85' : 'bg-violet/10 text-violet/80'
              }`}
              title="gap since previous turn (round-trip latency)"
            >
              +{(gapMs / 1000).toFixed(1)}s
            </span>
          )}
        </div>
        {turn.text}
      </div>
    </div>
  )
}

function ListeningLine({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="flex max-w-[80%] items-center gap-2 rounded-tile border border-dashed border-violet/40 bg-tint px-4 py-2.5 text-sm text-muted">
        <span className="flex gap-1">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-violet [animation-delay:0ms]" />
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-violet [animation-delay:150ms]" />
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-violet [animation-delay:300ms]" />
        </span>
        <span className="italic">{text || 'listening…'}</span>
      </div>
    </div>
  )
}

function TranscriptScroller({
  turns,
  partial,
  bargeIn,
}: {
  turns: TranscriptTurn[]
  partial?: string | null
  bargeIn?: boolean
}) {
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [turns.length, partial])

  if (turns.length === 0 && !partial)
    return <p className="text-sm text-muted">No transcript yet.</p>

  return (
    <div className="max-h-[420px] space-y-3 overflow-y-auto pr-1">
      {turns.map((t, i) => (
        <Bubble key={i} turn={t} gapMs={gapBetween(turns[i - 1], t)} />
      ))}
      {bargeIn && (
        <div className="text-center text-[11px] font-semibold uppercase tracking-wide text-violet/70">
          — interrupted —
        </div>
      )}
      {partial != null && <ListeningLine text={partial} />}
      <div ref={endRef} />
    </div>
  )
}

/** Live "order forming" card driven by streaming rupee-denominated events. */
function LiveOrderCard({ order }: { order: LiveOrder }) {
  return (
    <div className="rounded-tile border border-line bg-tint/60 p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="bb-kicker flex items-center gap-2">
          <FaBasketShopping className="h-3.5 w-3.5" />
          {order.order_id ? 'Order placed' : 'Order forming'}
        </div>
        {order.total_rupees != null && (
          <span className="font-sans text-lg font-semibold text-violet">
            ₹{order.total_rupees.toLocaleString('en-IN')}
          </span>
        )}
      </div>
      {order.items && order.items.length > 0 ? (
        <ul className="space-y-1.5 text-sm">
          {order.items.map((it, i) => (
            <li key={i} className="flex items-center justify-between gap-3">
              <span className="min-w-0 truncate text-ink">{it.sku_name}</span>
              <span className="shrink-0 text-muted">× {it.qty}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted">Building the basket…</p>
      )}
      {(order.status || order.delivery_date) && (
        <div className="mt-3 flex items-center gap-2 border-t border-line pt-3 text-xs text-muted">
          {order.status && <span className={`bb-chip ${statusChip(order.status)}`}>{order.status}</span>}
          {order.delivery_date && <span>Delivery {order.delivery_date}</span>}
        </div>
      )}
    </div>
  )
}

/** Saved order card (paise-denominated) for a finalized call. */
function SavedOrderCard({ order }: { order: Order }) {
  return (
    <div className="rounded-tile border border-line bg-tint/60 p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="bb-kicker flex items-center gap-2">
          <FaBasketShopping className="h-3.5 w-3.5" />
          Order · {order.source}
        </div>
        <span className="font-sans text-lg font-semibold text-violet">
          {rupees(order.total_paise)}
        </span>
      </div>
      <ul className="space-y-1.5 text-sm">
        {order.items.map((it, i) => (
          <li key={i} className="flex items-center justify-between gap-3">
            <span className="min-w-0 truncate text-ink">
              {it.sku_name} <span className="text-muted">× {it.qty}</span>
            </span>
            <span className="shrink-0 text-muted">{rupees(it.line_total_paise)}</span>
          </li>
        ))}
      </ul>
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-line pt-3 text-xs text-muted">
        <span className={`bb-chip ${statusChip(order.status)}`}>{order.status}</span>
        {order.delivery_date && <span>Delivery {order.delivery_date}</span>}
        <span>
          {order.n_items} item{order.n_items === 1 ? '' : 's'}
        </span>
      </div>
    </div>
  )
}

function Metric({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string
}) {
  return (
    <div className="flex items-center gap-2 rounded-chip bg-tint px-3 py-2">
      <Icon className="h-3.5 w-3.5 text-violet" />
      <div>
        <div className="text-[10px] font-semibold uppercase tracking-wide text-muted">{label}</div>
        <div className="text-sm font-semibold text-ink">{value}</div>
      </div>
    </div>
  )
}

function fmtDuration(s: number): string {
  const sec = Math.max(0, Math.round(s))
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`
}

/**
 * Twilio call recording, streamed through the backend proxy. The recording is
 * ready a few seconds after hangup, so we auto-retry a handful of times before
 * offering a manual retry.
 */
function RecordingPlayer({ src, durationS }: { src: string; durationS?: number | null }) {
  const [attempt, setAttempt] = useState(0)
  const [failed, setFailed] = useState(false)
  const url = `${src}${src.includes('?') ? '&' : '?'}t=${attempt}`

  useEffect(() => {
    if (!failed || attempt >= 4) return
    const t = setTimeout(() => {
      setFailed(false)
      setAttempt((a) => a + 1)
    }, 5000)
    return () => clearTimeout(t)
  }, [failed, attempt])

  return (
    <div className="rounded-tile border border-line bg-white p-4">
      <div className="bb-kicker mb-2 flex items-center gap-2">
        <FaHeadphones className="h-3.5 w-3.5" /> Call recording
        {durationS ? (
          <span className="font-normal normal-case tracking-normal text-muted">
            · {fmtDuration(durationS)}
          </span>
        ) : null}
      </div>
      {failed ? (
        <div className="flex items-center gap-3 text-sm text-muted">
          <span>Recording is still processing…</span>
          <button
            type="button"
            className="bb-chip bg-tint text-violet"
            onClick={() => {
              setFailed(false)
              setAttempt((a) => a + 1)
            }}
          >
            Retry
          </button>
        </div>
      ) : (
        <audio
          key={attempt}
          controls
          preload="none"
          className="w-full"
          src={url}
          onError={() => setFailed(true)}
        />
      )}
    </div>
  )
}

/** Saved / finalized record fetched from GET /api/calls/{id}. */
function SavedDetail({ callId }: { callId: number }) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['call', callId],
    queryFn: () => api<CallDetailData>(`/api/calls/${callId}`),
  })

  if (isLoading) return <LoadingCard label="Loading call…" />
  if (isError) return <ErrorCard error={error} />
  if (!data) return <EmptyCard label="Call not found." />

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="bb-kicker">{data.outlet_code}</div>
          <h3 className="bb-h3 truncate">{data.outlet_name}</h3>
          <div className="mt-1 text-xs text-muted">
            {new Date(data.started_at).toLocaleString('en-IN')}
            {data.language_detected ? ` · ${data.language_detected}` : ''}
          </div>
        </div>
        <StatusPill label={data.outcome} />
      </div>

      {data.summary && (
        <div className="rounded-tile border border-line bg-white p-4">
          <div className="bb-kicker mb-1">Post-call summary</div>
          <p className="text-sm text-ink">{data.summary}</p>
        </div>
      )}

      {data.recording_url && (
        <RecordingPlayer src={mediaUrl(data.recording_url)} durationS={data.recording_duration_s} />
      )}

      <div className="flex flex-wrap gap-2">
        {data.latency_p50_ms != null && (
          <Metric icon={FaBoltLightning} label="p50 latency" value={`${data.latency_p50_ms} ms`} />
        )}
        <Metric icon={FaClockRotateLeft} label="Cost" value={rupees(data.cost_inr_paise)} />
        {data.ended_at && (
          <Metric
            icon={FaClockRotateLeft}
            label="Duration"
            value={durationLabel(data.started_at, data.ended_at)}
          />
        )}
      </div>

      {data.order && <SavedOrderCard order={data.order} />}

      <div>
        <div className="bb-kicker mb-3 flex items-center gap-2">
          <FaMicrophoneLines className="h-3.5 w-3.5" /> Transcript
        </div>
        <TranscriptScroller turns={data.transcript} />
      </div>
    </div>
  )
}

/** Live record streamed from the WebSocket while the call is in progress. */
function LiveDetail({ callId, onFinalized }: { callId: number; onFinalized: () => void }) {
  const live = useCallLive(callId)

  useEffect(() => {
    if (live.finalized) onFinalized()
  }, [live.finalized, onFinalized])

  const statusLabel = live.status ?? (live.connected ? 'connecting…' : 'offline')

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="bb-kicker">Live</div>
          <h3 className="bb-h3 truncate">{live.outlet ?? `Call #${callId}`}</h3>
          <div className="mt-1 text-xs text-muted">
            {live.connected ? 'Streaming over WebSocket' : 'Connecting…'}
          </div>
        </div>
        <StatusPill label={statusLabel} live />
      </div>

      {live.liveOrder && <LiveOrderCard order={live.liveOrder} />}

      <div>
        <div className="bb-kicker mb-3 flex items-center gap-2">
          <FaWaveSquare className="h-3.5 w-3.5" /> Live transcript
        </div>
        <TranscriptScroller turns={live.transcript} partial={live.partial} bargeIn={live.bargeIn} />
      </div>
    </div>
  )
}

function durationLabel(start: string, end: string): string {
  const ms = new Date(end).getTime() - new Date(start).getTime()
  if (!Number.isFinite(ms) || ms < 0) return '—'
  const s = Math.round(ms / 1000)
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
}

/**
 * Unified call detail. When `callId` matches the active (in-progress) call it
 * streams live; otherwise (or once finalized) it renders the saved record.
 * `onFinalized` lets the parent clear the active-call flag so the view swaps to
 * the saved record and history refreshes.
 */
export default function CallDetail({
  callId,
  isActive,
  onFinalized,
}: {
  callId: number | null
  isActive: boolean
  onFinalized: () => void
}) {
  if (callId == null) {
    return (
      <div className="bb-card">
        <div className="bb-feature">
          <div className="bb-tile bg-grad-violet">
            <FaMicrophoneLines className="h-[44%] w-[44%]" />
          </div>
          <div className="min-w-0">
            <div className="bb-kicker">Call detail</div>
            <p className="mt-1 text-sm text-muted">
              Start a call or pick one from the history to see its transcript, order and summary.
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="bb-card">
      {isActive ? (
        <LiveDetail callId={callId} onFinalized={onFinalized} />
      ) : (
        <SavedDetail callId={callId} />
      )}
    </div>
  )
}
