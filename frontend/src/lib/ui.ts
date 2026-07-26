// Shared className helpers for chips used across screens.

/** Colored .bb-chip classes for an outlet class (A/B/C/D). */
export function outletClassChip(cls?: string | null): string {
  switch ((cls ?? '').toUpperCase()) {
    case 'A':
      return 'bg-violet text-white'
    case 'B':
      return 'bg-tint text-violet'
    case 'C':
      return 'bg-line text-ink'
    case 'D':
      return 'bg-muted/15 text-muted'
    default:
      return 'bg-line text-muted'
  }
}

/** Leaflet marker fill colour for an outlet class. */
export function outletClassColor(cls?: string | null): string {
  switch ((cls ?? '').toUpperCase()) {
    case 'A':
      return '#6D4AE0'
    case 'B':
      return '#8B6FE8'
    case 'C':
      return '#CDBFF2'
    case 'D':
      return '#B8B2C9'
    default:
      return '#CDBFF2'
  }
}

/** Colored .bb-chip classes for an order/outlet status. */
export function statusChip(status?: string | null): string {
  const s = (status ?? '').toLowerCase()
  if (['delivered', 'confirmed', 'completed', 'active'].includes(s))
    return 'bg-violet text-white'
  if (['pending', 'placed', 'processing', 'draft'].includes(s))
    return 'bg-tint text-violet'
  if (['cancelled', 'canceled', 'failed', 'inactive'].includes(s))
    return 'bg-brand-colgate/10 text-brand-colgate'
  return 'bg-line text-ink'
}
