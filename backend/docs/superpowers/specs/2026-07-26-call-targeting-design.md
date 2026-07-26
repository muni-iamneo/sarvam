# Per-Call Targeting: Starting Language + Product Push with Extra Discount

**Date:** 2026-07-26
**Status:** Implemented (branch `feat/call-targeting`)
**Scope:** BharatBeat voice agent — add operator-chosen *starting language* and an optional *pushed product with a real extra discount* to both the "start a call" and "schedule calls" flows.

---

## 1. Goal & requirements

When an operator starts or schedules a call from the console, they can:

1. **Choose the starting language** (from the Sarvam-supported set) the agent opens the conversation in. **Required.**
2. **Optionally push one product** with a **real extra discount** — the agent proactively promotes it, and the discount actually applies to the order total.

Available in **both** flows:
- **Start a call** (immediate, single outlet) — `Agent.tsx` → `POST /calls`.
- **Schedule calls** (batch campaign) — `Schedules.tsx` → `POST /api/schedules`. The language + pushed product are **one setting for the whole batch**.

### Hard constraint — do not touch the mid-call language-switch pipeline
The chosen language only **seeds the first turn**. STT stays on auto-detect (`sarvam_stt_language="unknown"`), and `CallHandler._on_transcript` continues to overwrite `self.language` from each detected transcript. If the caller switches language mid-call, the existing pipeline handles it unchanged.

### Decisions locked during brainstorming
| Decision | Choice |
|---|---|
| Discount effect | **Real** — changes actual order totals (not verbal-only) |
| Discount input | **Custom %** entered per call |
| Batch scope | **One** language + one pushed product/discount for the whole campaign |
| Language selection | **Required** |
| Discount combination | **Better-of** the pushed % vs. the SKU's existing best scheme (never stacked, never worse than normal) |
| Push behavior | Agent **offers** the product and adds it on a clear "yes" (does not force it into the cart) |

---

## 2. Architecture / approach

**Carry the targeting on the DB rows, not through Twilio.**

`media_stream.run_media_stream` already loads the `CallLog` row on the Twilio `start` event. Persisting the targeting on `CallLog` means the live call reads it with **zero TwiML changes**, works identically for immediate and scheduled calls, and every call is auditable.

Data flow:

```
UI (Agent.tsx / Schedules.tsx)
  → POST /calls              → initiate_call(...) ─┐
  → POST /api/schedules      → CallSchedule row    │  writes
                               → scheduler          │  initial_language,
                               → initiate_call(...) ─┤  push_sku_id,
                                                     │  push_discount_pct
                                                     ▼
                               CallLog row (new columns)
                                                     │  read on Twilio `start`
                                                     ▼
  media_stream → CallHandler(default_language=…)      (seeds greeting language)
              → ToolContext(push_sku_id, push_discount_pct)  (real pricing)
              → build_system_prompt(pushed product, discount) (proactive pitch)
```

*Rejected alternative:* passing targeting as Twilio `<Parameter>`s — clunky for product/discount, not persisted, awkward for the scheduled path.

---

## 3. Data model changes

`src/domain/models.py`:

- **`CallLog`** — add:
  - `initial_language: str | None` — `VARCHAR(10)` (e.g. `ta-IN`); the seeded starting language for this call.
  - `push_sku_id: int | None` — `INTEGER`, soft ref to `skus.id`.
  - `push_discount_pct: float | None` — `FLOAT`, extra discount percentage.
- **`CallSchedule`** — add the same three (campaign-level): `language`, `push_sku_id`, `push_discount_pct`.

### Migration
- New idempotent, non-destructive script `scripts/add_call_targeting_columns.py`, mirroring `scripts/add_recording_columns.py`, using `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for `call_logs` and `call_schedules` (Postgres/live DB).
- SQLite test DB picks the columns up automatically via `Base.metadata.create_all`.

---

## 4. Backend API changes

### Supported-languages source of truth
- `settings` holds `SUPPORTED_LANGUAGES: list[{code, label}]` for the Sarvam set:
  Hindi `hi-IN`, English `en-IN`, Bengali `bn-IN`, Gujarati `gu-IN`, Kannada `kn-IN`, Malayalam `ml-IN`, Marathi `mr-IN`, Odia `od-IN`, Punjabi `pa-IN`, Tamil `ta-IN`, Telugu `te-IN`.
- **New `GET /api/config/languages`** returns this list for the UI dropdown.

### New product-search endpoint
- **New `GET /api/products?q=&limit=`** — tenant-scoped active SKU search (mirrors `/api/outlets`, uses the `ctx` dependency). Response: `[{sku_id, name, code, pack_size, unit_price_rupees, unit_label}]`.

### Request schema changes (`src/domain/schemas.py`)
Both `StartCallReq` (in `calls.py`) and `ScheduleCreate` gain:
- `language: str` — **required**; must be in `SUPPORTED_LANGUAGES`.
- `push_sku_id: int | None = None`.
- `push_discount_pct: float | None = None`.

**Validation** (applied in both endpoints):
- `language` must be a supported code → else `400`.
- If `push_sku_id` is set: `push_discount_pct` is required and must be in `(0, 100]`, and the SKU must exist and belong to the caller's company/tenant → else `400`.
- If `push_sku_id` is `None`, any `push_discount_pct` is ignored.

### Wiring
- `dialer.initiate_call(db, outlet, to, *, language, push_sku_id=None, push_discount_pct=None)` writes the three fields onto the new `CallLog` columns.
- `POST /calls` passes them through from `StartCallReq`.
- `repo.create_schedule` persists `language`/`push_sku_id`/`push_discount_pct` on the `CallSchedule` row; `scheduler._start_item` passes them from the schedule into `initiate_call`.

---

## 5. Live-call wiring

`src/telephony/media_stream.py`:
- On `start`, read `cl.initial_language`, `cl.push_sku_id`, `cl.push_discount_pct` from the loaded `CallLog`.
- Pass `default_language=cl.initial_language` to `CallHandler`.
- Pass `push_sku_id` / `push_discount_pct` into the `CallHandler` so they reach `ToolContext`, and into `build_system_prompt`.
- Update `_default_handler_factory` signature accordingly (keeps the test injection seam).

`src/voice/call_handler.py`:
- `CallHandler.__init__` accepts `push_sku_id` / `push_discount_pct` and stores them on `self.ctx` (`ToolContext`).
- `default_language` already seeds `self.language` → greeting spoken in the chosen language. **No change to `_on_transcript` language handling.**

---

## 6. Real discount (pricing)

`src/tools/order_tools.py` + `src/domain/pricing.py`:
- `ToolContext` gains `push_sku_id: int | None` and `push_discount_pct: float | None`.
- In `_best_scheme(db, sku, qty)`: if `sku.id == ctx.push_sku_id` and `push_discount_pct` is set, synthesize
  `SchemeSpec(kind="pct", min_qty=1, discount_pct=push_discount_pct, description="Special call offer: {pct}% off")`
  and return whichever of {existing best scheme, synthesized push scheme} yields the **larger** savings at `qty` (better-of).
  - `_best_scheme` is a method/closure with access to `ctx`, or takes `ctx` as a param — implementation detail for the plan.
- Because `get_order_summary` and `place_order` both compute via `_best_scheme` → `quote_line`, spoken totals **and** the confirmed order reflect the discount automatically. No change needed to the "always price via tools" ground-truth rule.

`src/memory/context.py` — `build_system_prompt` gains optional `pushed_product` (name/pack) + `push_discount_pct`. When present, insert a priority-push line, e.g.:

> PRIORITY PUSH (this call): proactively promote **{name} ({pack})** — it has a special extra **{X}% discount** this call. Offer it warmly with the EXACT rupee saving (confirm via tools), and on a clear yes call `add_line_item` then `get_order_summary` to re-read the new total. If they decline, drop it gracefully.

The pushed product does not bypass the upsell/consent flow; it is an additional, higher-priority offer.

---

## 7. Frontend changes

`frontend/src/lib/types.ts` + `frontend/src/lib/api.ts`:
- New types: `LanguageOption {code, label}`, `Product {sku_id, name, code, pack_size, unit_price_rupees, unit_label}`.
- New API helpers: `getLanguages()`, `searchProducts(q)`.
- Extend `POST /calls` and `POST /api/schedules` request bodies with `language`, `push_sku_id?`, `push_discount_pct?`.

`frontend/src/pages/Agent.tsx` (OutletPicker modal) and `frontend/src/components/Schedules.tsx` (ScheduleBuilder modal):
- **Language `<select>`** — required, populated from `getLanguages()`, default from the picked outlet's `language` when available but still an explicit required choice; block submit until chosen.
- **Product picker** — optional search input (reuse the outlet-search pattern) → select one product; show a removable chip when chosen.
- **Discount % field** — a number input shown only once a product is chosen; required in that case, `1–100`.
- Styling via existing `.bb-*` / Tailwind tokens; labels match existing form style.
- Send the new fields in the request body.

---

## 8. Error handling

- API validation returns `400` with a clear detail for: unsupported language, missing/out-of-range discount when a product is pushed, or a pushed SKU outside the tenant.
- If a pushed SKU is later inactive/deleted by call time, pricing falls back silently to the SKU's normal best scheme (no crash); the push prompt line is omitted if the product can't be resolved.
- Frontend disables submit until a language is chosen and (if a product is picked) a valid discount is entered; surfaces API `400` details inline (existing banner pattern).

---

## 9. Testing

- **Pricing:** pushed discount = better-of vs. existing scheme; reflected in `get_order_summary` and in the persisted `Order.total_paise` from `place_order`; when the existing scheme is larger, it wins.
- **API validation:** language required + must be supported; discount required + range when product pushed; pushed SKU tenant check; product-less calls ignore discount.
- **Endpoints:** `GET /api/config/languages` returns the set; `GET /api/products` is tenant-scoped and searchable.
- **Live wiring:** `media_stream` passes `default_language` + push fields into `CallHandler`/`ToolContext` (via the `handler_factory` seam); `build_system_prompt` includes the push line only when set.
- **Scheduler propagation:** fields copied from `CallSchedule` onto each item's `CallLog`.
- **Regression (constraint):** a seeded starting language is still overridden mid-call when `_on_transcript` reports a different `language_code` (mid-call switch untouched).

---

## 10. Out of scope

- Per-outlet language/product within a batch (batch is one setting).
- Stacking the push discount on top of existing schemes.
- Multiple pushed products per call.
- Editing targeting after a schedule is created.
