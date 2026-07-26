export const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'
export const WS_BASE = import.meta.env.VITE_WS_BASE ?? 'ws://localhost:8000'

/** Absolute URL for a backend media/asset path (e.g. a recording proxy). */
export function mediaUrl(path: string): string {
  return `${API_BASE}${path}`
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText} — ${path}${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as T
}

/** Format integer paise as ₹ rupees. */
export function rupees(paise: number): string {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format((paise ?? 0) / 100)
}
