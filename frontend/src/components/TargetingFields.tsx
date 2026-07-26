import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FaMagnifyingGlass, FaXmark } from 'react-icons/fa6'
import { getLanguages, searchProducts } from '../lib/api'
import type { Product } from '../lib/types'

/** Operator-chosen call targeting: required starting language + optional product push. */
export interface TargetingValue {
  language: string
  pushProduct: Product | null
  pushDiscount: string // percent, kept as the raw input string
}

export const EMPTY_TARGETING: TargetingValue = { language: '', pushProduct: null, pushDiscount: '' }

/** True when the targeting is submittable: a language is chosen and, if a product
 * is pushed, the discount is a percent in (0, 100]. */
export function targetingValid(v: TargetingValue): boolean {
  if (!v.language) return false
  if (v.pushProduct) {
    const n = Number(v.pushDiscount)
    if (!Number.isFinite(n) || n <= 0 || n > 100) return false
  }
  return true
}

/** The request-body slice these fields contribute (spread into POST /calls or /api/schedules). */
export function targetingBody(v: TargetingValue): {
  language: string
  push_sku_id?: number
  push_discount_pct?: number
} {
  const body: { language: string; push_sku_id?: number; push_discount_pct?: number } = {
    language: v.language,
  }
  if (v.pushProduct) {
    body.push_sku_id = v.pushProduct.sku_id
    body.push_discount_pct = Number(v.pushDiscount)
  }
  return body
}

export function TargetingFields({
  value,
  onChange,
}: {
  value: TargetingValue
  onChange: (v: TargetingValue) => void
}) {
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')

  const { data: languages } = useQuery({ queryKey: ['languages'], queryFn: getLanguages })
  const { data: products } = useQuery({
    queryKey: ['products', q],
    queryFn: () => searchProducts(q),
    enabled: q.length > 0 && value.pushProduct == null,
  })

  return (
    <div className="space-y-3">
      {/* language (required) */}
      <div>
        <label className="mb-1.5 block text-xs font-semibold text-muted">Conversation language *</label>
        <select
          value={value.language}
          onChange={(e) => onChange({ ...value, language: e.target.value })}
          className="w-full rounded-pill border border-line bg-white px-4 py-2.5 text-sm text-ink shadow-soft-sm outline-none focus:border-violet"
        >
          <option value="" disabled>
            Select language…
          </option>
          {languages?.map((l) => (
            <option key={l.code} value={l.code}>
              {l.label}
            </option>
          ))}
        </select>
      </div>

      {/* product to push (optional) */}
      <div>
        <label className="mb-1.5 block text-xs font-semibold text-muted">
          Push a product with extra discount (optional)
        </label>
        {value.pushProduct ? (
          <div className="flex items-center gap-2">
            <span className="inline-flex min-w-0 items-center gap-1.5 rounded-pill bg-tint px-3 py-1.5 text-sm font-semibold text-violet">
              <span className="truncate">{value.pushProduct.name}</span>
              <button
                type="button"
                aria-label="Clear pushed product"
                onClick={() => onChange({ ...value, pushProduct: null, pushDiscount: '' })}
                className="shrink-0"
              >
                <FaXmark className="h-3 w-3" />
              </button>
            </span>
            <input
              type="number"
              min={1}
              max={100}
              value={value.pushDiscount}
              onChange={(e) => onChange({ ...value, pushDiscount: e.target.value })}
              placeholder="Extra % off"
              className="w-32 rounded-pill border border-line bg-white px-4 py-2.5 text-sm text-ink shadow-soft-sm outline-none focus:border-violet"
            />
          </div>
        ) : (
          <>
            <form
              className="relative"
              onSubmit={(e) => {
                e.preventDefault()
                setQ(search)
              }}
            >
              <FaMagnifyingGlass className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search products to push…"
                className="w-full rounded-pill border border-line bg-white py-2.5 pl-10 pr-4 text-sm text-ink shadow-soft-sm outline-none focus:border-violet"
              />
            </form>
            {q.length > 0 && products && products.length > 0 && (
              <div className="mt-1.5 max-h-40 space-y-1 overflow-y-auto pr-1">
                {products.map((p) => (
                  <button
                    key={p.sku_id}
                    type="button"
                    onClick={() => onChange({ ...value, pushProduct: p })}
                    className="flex w-full items-center justify-between gap-3 rounded-tile border border-line bg-white p-2.5 text-left text-sm transition-colors hover:bg-tint/60"
                  >
                    <span className="min-w-0 truncate text-ink">{p.name}</span>
                    <span className="shrink-0 text-xs text-muted">
                      ₹{p.unit_price_rupees}/{p.unit_label}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
