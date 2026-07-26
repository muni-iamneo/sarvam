// API response types for the BharatBeat dashboard.
// Base: http://localhost:8000 — see src/api/dashboard.py on the backend.

export interface OrderItem {
  sku_name: string
  qty: number
  unit_price_paise: number
  line_total_paise: number
}

export interface Order {
  id: number
  outlet_name: string
  total_paise: number
  status: string
  source: string
  delivery_date?: string | null
  created_at: string
  n_items: number
  items: OrderItem[]
}

// ---- Field Ops (rep-facing) ----
export interface RepRef {
  id?: number | null
  name?: string | null
  employee_code?: string | null
  designation?: string | null
  phone?: string | null
}

export interface Delivery {
  order_id: number
  outlet_id: number
  outlet_name: string
  outlet_code: string
  area_name?: string | null
  total_paise: number
  delivery_date?: string | null
  status: string
  created_at: string
  call_id?: number | null
  n_items: number
  items: OrderItem[]
}

export interface RepDeliveries {
  rep: RepRef
  n_orders: number
  total_paise: number
  orders: Delivery[]
}

export interface VisitAlert {
  outlet_id: number
  outlet_name: string
  outlet_code: string
  area_name?: string | null
  language?: string | null
  urgency: 'urgent' | 'watch'
  signals: string[]
  reason: string
  last_call_id?: number | null
  last_outcome?: string | null
  last_call_at?: string | null
  n_recent_calls: number
}

export interface RepVisitAlerts {
  rep: RepRef
  n_alerts: number
  n_urgent: number
  alerts: VisitAlert[]
}

export interface RegionAchievement {
  name: string
  target_paise: number
  achieved_paise: number
  achievement_pct: number
}

export interface Overview {
  company: string
  total_outlets: number
  active_outlets: number
  coverage_pct: number
  secondary_achievement_pct: number
  calls_today: number
  orders_total: number
  region_achievement: RegionAchievement[]
  recent_orders: Order[]
}

export interface RegionOut {
  id: number
  name: string
  code: string
  zone?: string | null
  regional_manager?: string | null
  n_areas: number
  n_outlets: number
  target_paise: number
  achieved_paise: number
  achievement_pct: number
}

export interface AreaOut {
  id: number
  region_id: number
  region_name: string
  name: string
  code: string
  area_manager?: string | null
  deputy_area_manager?: string | null
  n_outlets: number
  target_paise: number
  achieved_paise: number
  achievement_pct: number
}

export interface OutletOut {
  id: number
  code: string
  name: string
  phone?: string | null
  language?: string | null
  owner_name?: string | null
  outlet_class?: string | null
  trade_type: string
  category?: string | null
  lat?: number | null
  lon?: number | null
  best_call_time?: string | null
  last_order_at?: string | null
  status: string
  region_name?: string | null
  area_name?: string | null
  territory_name?: string | null
  beat_name?: string | null
  distributor_name?: string | null
  sales_rep?: string | null
  area_manager?: string | null
}

export interface RepOut {
  id: number
  name: string
  employee_code: string
  designation: string
  reporting_manager_id?: number | null
  reporting_manager?: string | null
  region_name?: string | null
  area_name?: string | null
  territory_name?: string | null
  phone?: string | null
}

export interface DistributorOut {
  id: number
  name: string
  code: string
  stockist_type: string
  territory_name?: string | null
  contact_person?: string | null
  phone?: string | null
  warehouse_lat?: number | null
  warehouse_lon?: number | null
  credit_limit_paise: number
  margin_pct: number
}

export interface BrandOut {
  id: number
  name: string
  code: string
  category?: string | null
  brand_manager?: string | null
  n_skus: number
}

export interface BrandManagerOut {
  id: number
  name: string
  employee_code: string
  designation: string
  n_brands: number
}

// ---- Voice agent / calls ----

export type CallOutcome =
  | 'initiated'
  | 'ordered'
  | 'declined'
  | 'no_answer'
  | 'failed'

export interface CallLog {
  id: number
  outlet_name: string
  outlet_code: string
  twilio_call_sid?: string | null
  started_at: string
  ended_at?: string | null
  outcome: CallOutcome
  language_detected?: string | null
  order_id?: number | null
  latency_p50_ms?: number | null
  cost_inr_paise: number
  summary?: string | null
}

export interface TranscriptTurn {
  role: 'user' | 'agent'
  text: string
  t_ms?: number // ms since call start — lets the UI show the gap between turns
}

export interface CallDetail extends CallLog {
  transcript: TranscriptTurn[]
  order: Order | null
  /** Backend proxy path for the Twilio recording (null until a call has a SID). */
  recording_url?: string | null
  recording_duration_s?: number | null
}

export interface StartCallResponse {
  call_id: number
  twilio_call_sid: string
  to: string
  live_ws: string
}

// ---- Call scheduling ----

export type ScheduleMode = 'now' | 'scheduled'
export type ScheduleStatus = 'pending' | 'running' | 'completed' | 'canceled' | 'failed'
export type ScheduleItemStatus = 'queued' | 'calling' | 'done' | 'failed' | 'skipped'

export interface ScheduleItem {
  id: number
  outlet_id: number
  outlet_name: string
  outlet_code: string
  to_number?: string | null
  position: number
  status: ScheduleItemStatus
  call_id?: number | null
  note?: string | null
  outcome?: string | null
  started_at?: string | null
  ended_at?: string | null
}

export interface Schedule {
  id: number
  name?: string | null
  mode: ScheduleMode
  scheduled_at?: string | null
  status: ScheduleStatus
  created_at: string
  n_items: number
  n_done: number
  active_call_id?: number | null
  items: ScheduleItem[]
}

/** A live order-summary snapshot carried by tool / order_placed events (rupees, not paise). */
export interface LiveOrder {
  order_id?: number
  total_rupees?: number
  delivery_date?: string | null
  status?: string
  items?: { sku_name: string; qty: number }[]
}

/** WebSocket event stream from `WS /calls/{id}/live` — discriminated by `type`. */
export type LiveEvent =
  | { type: 'call_started'; outlet: string }
  | { type: 'partial_transcript'; text: string }
  | { type: 'user_transcript'; text: string; t_ms?: number }
  | { type: 'agent_text'; text: string; t_ms?: number }
  | { type: 'tool'; name: string; result: Record<string, unknown> }
  | { type: 'order_placed'; order: LiveOrder }
  | { type: 'barge_in' }
  | { type: 'call_status'; status: string }
  | { type: 'call_end' }
  | {
      type: 'call_finalized'
      outcome: string
      order_id: number | null
      summary: string
      metrics: { p50_response_ms?: number }
    }
