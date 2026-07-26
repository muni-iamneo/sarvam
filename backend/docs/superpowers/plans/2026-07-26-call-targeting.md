# Call Targeting (Language + Product Push) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let operators pick a starting language (required) and optionally push one product with a real extra discount, from both the "start a call" and "schedule calls" flows — without altering the mid-call language-switch pipeline.

**Architecture:** Persist targeting (`initial_language`, `push_sku_id`, `push_discount_pct`) on `CallLog` (and `CallSchedule` for batches). The live media stream reads it off the loaded `CallLog`, seeds `CallHandler.default_language`, applies the discount through the existing pricing path, and injects a priority-push line into the system prompt.

**Tech Stack:** FastAPI + SQLAlchemy async (SQLite in tests via `create_all`, Postgres in prod via idempotent ALTER scripts), pydantic-settings, React + TypeScript + Tailwind, pytest (`asyncio_mode=auto`).

Run all backend tests with: `cd backend && .venv/bin/python -m pytest -q`

---

### Task 1: DB columns + migration + test conftest

**Files:**
- Modify: `src/domain/models.py` (`CallLog` ~302-321, `CallSchedule` ~268-283)
- Create: `scripts/add_call_targeting_columns.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Add columns.** `CallLog` += `initial_language: Mapped[str|None] = mapped_column(String(10), default=None)`, `push_sku_id: Mapped[int|None] = mapped_column(Integer, index=True, default=None)`, `push_discount_pct: Mapped[float|None] = mapped_column(Float, default=None)`. `CallSchedule` += `language: Mapped[str|None] = mapped_column(String(10), default=None)`, `push_sku_id`, `push_discount_pct` (same types).
- [ ] **Step 2: Migration script** mirroring `add_recording_columns.py` with `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for `call_logs` (initial_language VARCHAR(10), push_sku_id INTEGER, push_discount_pct DOUBLE PRECISION) and `call_schedules` (language VARCHAR(10), push_sku_id INTEGER, push_discount_pct DOUBLE PRECISION).
- [ ] **Step 3: conftest** — async in-memory SQLite (`sqlite+aiosqlite://`, `StaticPool`, `check_same_thread=False`) with `create_all`; fixtures: `db` (AsyncSession) and `seeded` (Company code="colgate", Brand, Sku #A must-sell + Sku #B, a `pct` Scheme on #A, an Outlet) returning ids; plus an `client` fixture (httpx AsyncClient against `app` with `get_db` overridden to the test session).
- [ ] **Step 4: Smoke test** `tests/test_targeting_columns.py::test_calllog_roundtrips_targeting` — insert a `CallLog(initial_language="ta-IN", push_sku_id=<A>, push_discount_pct=15.0)`, read back, assert fields.
- [ ] **Step 5: Run** `pytest tests/test_targeting_columns.py -q` → PASS. Commit.

---

### Task 2: Pure `better_scheme` (better-of discount)

**Files:** Modify `src/domain/pricing.py`; Test `tests/test_push_discount.py`

- [ ] **Step 1: Failing test** — `better_scheme(base, push, unit_price, qty)` returns the larger-savings spec; base-only when push None; push-only when base None; base wins when it saves more.

```python
from src.domain.pricing import SchemeSpec, better_scheme, scheme_savings_paise
BASE = SchemeSpec(kind="pct", min_qty=1, discount_pct=5.0, description="5%")
PUSH = SchemeSpec(kind="pct", min_qty=1, discount_pct=15.0, description="15%")
def test_push_wins_when_bigger():
    got = better_scheme(BASE, PUSH, 100000, 3); assert got.discount_pct == 15.0
def test_base_wins_when_bigger():
    got = better_scheme(PUSH, BASE, 100000, 3); assert got.discount_pct == 15.0  # push arg is BASE here
def test_none_base():
    assert better_scheme(None, PUSH, 100000, 3) is PUSH
def test_none_push():
    assert better_scheme(BASE, None, 100000, 3) is BASE
```

- [ ] **Step 2:** Run → FAIL (no `better_scheme`).
- [ ] **Step 3: Implement** (append to pricing.py):

```python
def better_scheme(base: Optional[SchemeSpec], push: Optional[SchemeSpec],
                  unit_price_paise: int, qty: int) -> Optional[SchemeSpec]:
    """Return whichever of base/push yields the larger savings at qty (better-of, never stacked)."""
    if push is None:
        return base
    if base is None:
        return push
    push_sav = scheme_savings_paise(unit_price_paise, qty, push)
    base_sav = scheme_savings_paise(unit_price_paise, qty, base)
    return push if push_sav >= base_sav else base
```

- [ ] **Step 4:** Run → PASS. Commit.

---

### Task 3: Apply push discount in order tools

**Files:** Modify `src/tools/order_tools.py`; Test `tests/test_push_discount.py`

- [ ] **Step 1: Failing DB test** (uses `seeded`): build `ToolContext(db, outlet, push_sku_id=<A>, push_discount_pct=50.0)`, `cart={A:1}`, call `get_order_summary` → line total reflects 50% off (larger than the seeded 5% scheme); with no push, total reflects the base scheme; pushing a huge % also flows into `place_order` total.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement:**
  - `ToolContext` += `push_sku_id: Optional[int] = None`, `push_discount_pct: Optional[float] = None`.
  - Change `_best_scheme(db, sku, qty)` → `_best_scheme(ctx, sku, qty)`; compute base best from `ctx.db` as today, then:

```python
    if ctx.push_sku_id == sku.id and ctx.push_discount_pct:
        push = SchemeSpec(kind="pct", min_qty=1, discount_pct=ctx.push_discount_pct,
                          description=f"Special call offer: {ctx.push_discount_pct:.0f}% off")
        best = better_scheme(best, push, sku.unit_price_paise, qty)
    return best
```

  - Update both callers in `get_order_summary` and `place_order`: `spec = await _best_scheme(ctx, sku, qty)`.
  - Import `better_scheme` from `src.domain.pricing`.
- [ ] **Step 4:** Run → PASS (and re-run `tests/test_upsell.py` — unaffected). Commit.

---

### Task 4: System-prompt push line + language hint

**Files:** Modify `src/memory/context.py`; Test `tests/test_system_prompt_push.py`

- [ ] **Step 1: Failing test** (uses `seeded`): `build_system_prompt(..., language="ta-IN", pushed_product={"name":"Surf Excel","pack":"48-case"}, push_discount_pct=15.0)` → returned prompt contains `"Surf Excel"`, `"15%"`, and `"PRIORITY PUSH"`; with no push args the prompt contains none of those and no "PRIORITY PUSH".
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement** — extend signature `build_system_prompt(db, outlet, company_name="the company", memory_profile=None, *, language=None, pushed_product=None, push_discount_pct=None)`; set `lang = language or outlet.language or "hi-IN"`; when `pushed_product and push_discount_pct`, append a block:

```
PRIORITY PUSH (this call): proactively promote {name} ({pack}) — a special extra {pct:.0f}% discount applies this call. Offer it warmly with the EXACT rupee saving (confirm via tools), and on a clear yes call add_line_item then get_order_summary to re-read the new total. If they decline, drop it gracefully.
```

- [ ] **Step 4:** Run → PASS. Commit.

---

### Task 5: Supported languages + pure targeting validator

**Files:** Modify `src/core/config/settings.py`; Create `src/domain/targeting.py`; Test `tests/test_targeting_validation.py`

- [ ] **Step 1:** Add module-level constants to settings.py (outside `Settings`): `SUPPORTED_LANGUAGES: list[dict[str,str]]` = the 11 Sarvam languages (hi/en/bn/gu/kn/ml/mr/od/pa/ta/te -IN with labels), and `SUPPORTED_LANGUAGE_CODES = frozenset(l["code"] for l in SUPPORTED_LANGUAGES)`.
- [ ] **Step 2: Failing test** for `validate_targeting`: unsupported language raises; push_sku_id set without discount raises; discount out of `(0,100]` raises; valid language alone passes; valid language + sku + 15.0 passes.
- [ ] **Step 3:** Run → FAIL.
- [ ] **Step 4: Implement** `src/domain/targeting.py`:

```python
from typing import Optional
from src.core.config.settings import SUPPORTED_LANGUAGE_CODES

class TargetingError(ValueError):
    """Invalid call-targeting input (maps to HTTP 400)."""

def validate_targeting(language: str, push_sku_id: Optional[int], push_discount_pct: Optional[float]) -> None:
    if language not in SUPPORTED_LANGUAGE_CODES:
        raise TargetingError(f"unsupported language '{language}'")
    if push_sku_id is not None:
        if push_discount_pct is None:
            raise TargetingError("push_discount_pct required when a product is pushed")
        if not (0 < push_discount_pct <= 100):
            raise TargetingError("push_discount_pct must be between 0 and 100")
```

- [ ] **Step 5:** Run → PASS. Commit.

---

### Task 6: `ProductOut`/`LanguageOut` schemas, repo search, endpoints

**Files:** Modify `src/domain/schemas.py`, `src/domain/repository.py`, `src/api/dashboard.py`; Test `tests/test_call_targeting_api.py`

- [ ] **Step 1: Failing API test** (uses `client`+`seeded`): `GET /api/config/languages` returns a list containing `{"code":"ta-IN","label":"Tamil"}`; `GET /api/products?q=<A-name>` returns the seeded SKU with `sku_id`/`name`/`unit_price_rupees`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement:**
  - schemas: `class ProductOut(BaseModel): sku_id:int; name:str; code:str; pack_size:Optional[str]=None; unit_price_rupees:float; unit_label:str` and `class LanguageOut(BaseModel): code:str; label:str`.
  - repository: `list_products(db, cid, q=None, limit=25) -> list[s.ProductOut]` (active SKUs, `company_id==cid`, `name.ilike` when q, order must-sell then name, limit).
  - dashboard.py: `@router.get("/config/languages", response_model=list[s.LanguageOut])` returning `SUPPORTED_LANGUAGES` (no ctx); `@router.get("/products", response_model=list[s.ProductOut])` with `q`, `limit=25`, `c=Depends(ctx)` → `repo.list_products`.
- [ ] **Step 4:** Run → PASS. Commit.

---

### Task 7: Start-call flow — request fields, validation, dialer

**Files:** Modify `src/api/calls.py` (`StartCallReq` 37-39, `start_call` 60-72), `src/telephony/dialer.py`; Test `tests/test_call_targeting_api.py`

- [ ] **Step 1: Failing tests:** POST `/calls` with unsupported language → 400; with `push_sku_id` + no discount → 400; with a `push_sku_id` from another tenant → 400; happy path (monkeypatch `src.api.calls.initiate_call` to capture kwargs) → asserts `language`/`push_sku_id`/`push_discount_pct` forwarded.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement:**
  - `StartCallReq` += `language: str`, `push_sku_id: int | None = None`, `push_discount_pct: float | None = None`.
  - In `start_call`: after outlet lookup, `try: validate_targeting(req.language, req.push_sku_id, req.push_discount_pct) except TargetingError as e: raise HTTPException(400, str(e))`; if `req.push_sku_id`, verify the SKU exists AND `Sku.company_id == outlet.company_id` else `HTTPException(400,"pushed product not in this company")`; pass the three fields as kwargs to `initiate_call`.
  - `dialer.initiate_call(db, outlet, to=None, *, language=None, push_sku_id=None, push_discount_pct=None)` → set them on the new `CallLog(...)`.
- [ ] **Step 4:** Run → PASS. Commit.

---

### Task 8: Schedule flow — request fields, validation, repo, scheduler

**Files:** Modify `src/domain/schemas.py` (`ScheduleCreate` 229-233), `src/api/schedules.py`, `src/domain/repository.py` (`create_schedule`), `src/telephony/scheduler.py` (`_start_item`, `run_once` call site); Test `tests/test_call_targeting_api.py`, `tests/test_scheduler_targeting.py`

- [ ] **Step 1: Failing tests:** (a) repo — `create_schedule` with language+push persists them on the `CallSchedule` row (read back via `db`); (b) api — POST `/api/schedules` bad language → 400; (c) scheduler — `_start_item` calls the injected `dial` with `language`/`push_sku_id`/`push_discount_pct` kwargs from the schedule (fake `dial` captures kwargs; fake session yields a queued item+schedule).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement:**
  - `ScheduleCreate` += `language: str`, `push_sku_id: int|None=None`, `push_discount_pct: float|None=None`.
  - `create_schedule` endpoint: `validate_targeting(...)` → 400 on `TargetingError`; SKU tenant check as in Task 7.
  - `repository.create_schedule`: set `language`/`push_sku_id`/`push_discount_pct` on the `m.CallSchedule(...)`.
  - `scheduler`: change `run_once` to `await self._start_item(db, schedule, item, now)` and `_start_item(self, db, schedule, item, now)` to pass `language=schedule.language, push_sku_id=schedule.push_sku_id, push_discount_pct=schedule.push_discount_pct` into `self._dial(...)`.
- [ ] **Step 4:** Run → PASS. Commit.

---

### Task 9: Live-call wiring — CallHandler + media_stream

**Files:** Modify `src/voice/call_handler.py` (`__init__` 50-85), `src/telephony/media_stream.py` (`_default_handler_factory` 58-61, `run_media_stream` start block 89-125); Test `tests/test_call_targeting_wiring.py`

- [ ] **Step 1: Failing tests:** (a) `CallHandler(..., default_language="ta-IN", push_sku_id=7, push_discount_pct=15.0)` sets `self.language=="ta-IN"` and `self.ctx.push_sku_id==7`, `self.ctx.push_discount_pct==15.0`; (b) `_default_handler_factory(db, outlet, prompt, send, emit, language="kn-IN", push_sku_id=3, push_discount_pct=20.0)` returns a `CallHandler` with those on `self.ctx` and `self.language=="kn-IN"`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement:**
  - `CallHandler.__init__` += `push_sku_id=None, push_discount_pct=None`; build `self.ctx = ToolContext(db=db, outlet=outlet, push_sku_id=push_sku_id, push_discount_pct=push_discount_pct)`.
  - `_default_handler_factory(db, outlet, system_prompt, send_audio, emit, *, language=None, push_sku_id=None, push_discount_pct=None)` → pass `default_language=language` + push kwargs.
  - `run_media_stream` start block: after loading `cl`, resolve `push_sku = SELECT Sku WHERE id==cl.push_sku_id` when set; call `build_system_prompt(..., language=cl.initial_language, pushed_product={"name":push_sku.name,"pack":push_sku.pack_size} if push_sku else None, push_discount_pct=cl.push_discount_pct)`; call `handler_factory(..., language=cl.initial_language, push_sku_id=cl.push_sku_id, push_discount_pct=cl.push_discount_pct)`. Guard all `cl` reads (cl may be None for non-digit call_id).
- [ ] **Step 4:** Run → PASS. Then run the WHOLE suite `pytest -q` → PASS. Commit.

---

### Task 10: Frontend types + API helpers

**Files:** Modify `frontend/src/lib/types.ts`, `frontend/src/lib/api.ts`

- [ ] **Step 1:** types.ts: `export interface Product { sku_id:number; name:string; code:string; pack_size?:string|null; unit_price_rupees:number; unit_label:string }` and `export interface LanguageOption { code:string; label:string }`.
- [ ] **Step 2:** api.ts: `export const getLanguages = () => api<LanguageOption[]>('/api/config/languages')` and `export const searchProducts = (q:string) => api<Product[]>('/api/products?q='+encodeURIComponent(q)+'&limit=25')` (import types).
- [ ] **Step 3:** Verify `cd frontend && npx tsc --noEmit` (or `npm run build`) → no new errors. Commit.

---

### Task 11: Agent.tsx OutletPicker — language + product + discount

**Files:** Modify `frontend/src/pages/Agent.tsx` (`OutletPicker` 21-184)

- [ ] **Step 1:** Add state `language`, `pushProduct: Product|null`, `pushDiscount: string`, product search state. Load languages via `useQuery(['languages'], getLanguages)`; default `language` to the picked outlet's `language` if in the list once picked. Add a required `<select>` (disabled placeholder "Select language"), a product search + pick (chip when chosen, clearable), and a discount % number input shown when a product is picked.
- [ ] **Step 2:** Gate `start()`/button on `picked && language && (!pushProduct || (pushDiscount within 1..100))`. Extend body: `{ outlet_id, to?, language, push_sku_id?: pushProduct.sku_id, push_discount_pct?: Number(pushDiscount) }`.
- [ ] **Step 3:** `npx tsc --noEmit` clean; manual check the modal renders. Commit.

---

### Task 12: Schedules.tsx ScheduleBuilder — language + product + discount

**Files:** Modify `frontend/src/components/Schedules.tsx` (`ScheduleBuilder` 58-278)

- [ ] **Step 1:** Same three controls (campaign-level), same gating, extend the POST body with `language`, `push_sku_id?`, `push_discount_pct?`.
- [ ] **Step 2:** `npx tsc --noEmit` clean. Commit.

---

### Task 13: Final verification

- [ ] **Step 1:** `cd backend && .venv/bin/python -m pytest -q` → all pass.
- [ ] **Step 2:** `cd frontend && npx tsc --noEmit` (or `npm run build`) → clean.
- [ ] **Step 3:** Update the spec status to Implemented; commit.

---

## Self-review

- **Spec coverage:** data model+migration (T1) · real better-of discount (T2/T3) · push prompt line + language hint (T4) · supported languages + validation (T5) · products/languages endpoints (T6) · start-call fields/validation/dialer (T7) · schedule fields/validation/repo/scheduler (T8) · live wiring + mid-call switch untouched i.e. no change to `_on_transcript` (T9) · frontend both modals (T10-12) · required language enforced by non-defaulted `language: str` + UI gating · batch = one setting (schedule-level columns). All spec sections mapped.
- **Placeholder scan:** none — pure-function code is inline; edit sites have exact locations.
- **Type consistency:** `better_scheme`, `validate_targeting`, `TargetingError`, `ProductOut{sku_id,...}`, `LanguageOut{code,label}`, `ToolContext.push_sku_id/push_discount_pct`, `initiate_call(..., *, language, push_sku_id, push_discount_pct)`, `_best_scheme(ctx, sku, qty)` used consistently across tasks.
