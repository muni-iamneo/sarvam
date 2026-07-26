import { useEffect, useRef, useState } from 'react'
import { WS_BASE } from '../lib/api'
import type { LiveEvent, LiveOrder, TranscriptTurn } from '../lib/types'

export interface CallFinalized {
  outcome: string
  order_id: number | null
  summary: string
  p50_response_ms?: number
}

export interface CallLiveState {
  /** WebSocket connection state. */
  connected: boolean
  /** Outlet name from the call_started event, if seen. */
  outlet: string | null
  /** Ordered user/agent turns as they arrive. */
  transcript: TranscriptTurn[]
  /** Latest interim user speech (cleared once a final turn lands). */
  partial: string | null
  /** Latest live order snapshot from tool / order_placed events (rupees). */
  liveOrder: LiveOrder | null
  /** Latest coarse call status. */
  status: string | null
  /** True briefly when the user interrupts the agent. */
  bargeIn: boolean
  /** Set once the server finalizes the call. */
  finalized: CallFinalized | null
}

const EMPTY: CallLiveState = {
  connected: false,
  outlet: null,
  transcript: [],
  partial: null,
  liveOrder: null,
  status: null,
  bargeIn: false,
  finalized: null,
}

/**
 * Opens a WebSocket to `WS_BASE/calls/{callId}/live`, accumulates the replayed +
 * streamed events into state, and tears down on unmount / callId change.
 * Pass `null` to keep the socket closed.
 */
export function useCallLive(callId: number | null): CallLiveState {
  const [state, setState] = useState<CallLiveState>(EMPTY)
  const bargeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (callId == null) {
      setState(EMPTY)
      return
    }

    // Reset for the new call before replay begins.
    setState({ ...EMPTY })

    let closed = false
    const ws = new WebSocket(`${WS_BASE}/calls/${callId}/live`)

    ws.onopen = () => {
      if (!closed) setState((s) => ({ ...s, connected: true }))
    }

    ws.onmessage = (ev) => {
      let event: LiveEvent
      try {
        event = JSON.parse(ev.data as string) as LiveEvent
      } catch {
        return
      }
      setState((s) => reduce(s, event))

      if (event.type === 'barge_in') {
        if (bargeTimer.current) clearTimeout(bargeTimer.current)
        bargeTimer.current = setTimeout(() => {
          setState((s) => ({ ...s, bargeIn: false }))
        }, 1200)
      }
    }

    ws.onclose = () => {
      if (!closed) setState((s) => ({ ...s, connected: false }))
    }
    ws.onerror = () => {
      if (!closed) setState((s) => ({ ...s, connected: false }))
    }

    return () => {
      closed = true
      if (bargeTimer.current) clearTimeout(bargeTimer.current)
      // 1 === OPEN, 0 === CONNECTING
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close()
      }
    }
  }, [callId])

  return state
}

function toLiveOrder(result: Record<string, unknown>): LiveOrder {
  const rawItems = Array.isArray(result.items) ? (result.items as unknown[]) : undefined
  const items = rawItems?.map((it) => {
    const rec = (it ?? {}) as Record<string, unknown>
    return {
      sku_name: String(rec.sku_name ?? rec.name ?? ''),
      qty: Number(rec.qty ?? 0),
    }
  })
  return {
    order_id: typeof result.order_id === 'number' ? result.order_id : undefined,
    total_rupees: typeof result.total_rupees === 'number' ? result.total_rupees : undefined,
    delivery_date: typeof result.delivery_date === 'string' ? result.delivery_date : undefined,
    status: typeof result.status === 'string' ? result.status : undefined,
    items,
  }
}

function reduce(s: CallLiveState, ev: LiveEvent): CallLiveState {
  switch (ev.type) {
    case 'call_started':
      return { ...s, outlet: ev.outlet, status: 'in progress' }
    case 'partial_transcript':
      return { ...s, partial: ev.text }
    case 'user_transcript':
      return {
        ...s,
        transcript: [...s.transcript, { role: 'user', text: ev.text, t_ms: ev.t_ms }],
        partial: null,
      }
    case 'agent_text':
      return {
        ...s,
        transcript: [...s.transcript, { role: 'agent', text: ev.text, t_ms: ev.t_ms }],
      }
    case 'tool':
      if (ev.name === 'get_order_summary' || ev.name === 'place_order') {
        return { ...s, liveOrder: { ...s.liveOrder, ...toLiveOrder(ev.result) } }
      }
      return s
    case 'order_placed':
      return { ...s, liveOrder: { ...s.liveOrder, ...ev.order }, status: 'order placed' }
    case 'barge_in':
      return { ...s, bargeIn: true }
    case 'call_status':
      return { ...s, status: ev.status }
    case 'call_end':
      return { ...s, status: 'ended', partial: null }
    case 'call_finalized':
      return {
        ...s,
        partial: null,
        status: ev.outcome,
        finalized: {
          outcome: ev.outcome,
          order_id: ev.order_id,
          summary: ev.summary,
          p50_response_ms: ev.metrics?.p50_response_ms,
        },
      }
    default:
      return s
  }
}
