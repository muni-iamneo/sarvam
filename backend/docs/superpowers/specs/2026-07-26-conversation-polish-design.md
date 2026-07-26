# Conversation Polish — Voice Agent Prompt Redesign

**Date:** 2026-07-26
**Status:** Approved (pending final spec review)
**Scope:** `backend/src/memory/context.py` (`build_system_prompt` f-string only) + prompt-substring tests
**Author:** pairing session (brainstorming → spec)

## Summary

Four conversational-behavior improvements to the BharatBeat live sales agent, all
implemented as edits to the system-prompt f-string in `build_system_prompt`
(`backend/src/memory/context.py`). No runtime/pricing/tool code changes — the entire
change is prompt-string-only by explicit decision (see **Scope decisions**).

1. **Net-price verbosity** — mid-call, speak only each item's final net price + rupee
   saving; never narrate arithmetic; give the full itemized breakdown exactly once, as
   a brief recap right before placing.
2. **Anti-parroting (scheme discipline)** — make the offer rule *proactive*: never
   volunteer/list a scheme unless a tool returned it *this turn* for the SKU+quantity in
   play, at most one at a time, and treat any scheme text printed elsewhere in the prompt
   as stale reference that must be re-fetched before speaking.
3. **Human warmth (light touch)** — open with one genuine human beat (greet by name, ask
   how business is), react briefly, then move to the order; warm acknowledgements and a
   brief well-wish close; kept light so it never drifts into rambling.
4. **Graceful discount decline** — when pushed for a bigger/extra discount we don't have,
   never hard-no and never invent one: acknowledge, "I'll pass the feedback to the team,"
   and steer to the real scheme they *do* qualify for.

## Background & root cause (why this change)

Two problems were observed in a live-call transcript:

- **Verbosity:** the agent narrated arithmetic mid-conversation (*"2 cases × ₹2,400 =
  ₹4,800, then 5% off…"*) and re-read running totals, making the call feel robotic.
- **Apparent hallucination:** the agent offered a *"Surf Excel Easy Wash — 10% off on 3+
  cases"* scheme for a product it had not listed in its opening catalog read.

A read-only investigation (3 parallel code investigators + adversarial review) established
that **the Surf Excel scheme is not a hallucination** — it is genuine seeded data:

- `Surf Excel Easy Wash 1kg` (`SRF-EW-1K`) is a real seeded SKU and `"10% off on 3+ cases"`
  is a real seeded `Scheme` (`backend/scripts/seed.py:137,154`). The MaxFresh 5% and Vim
  ₹40 offers are also real. **The demo company has 5 SKUs, not 4.**
- The transcript's real defect is the *inverse* of the first hypothesis: the agent's
  opening under-read the catalog (spoke 4 of 5 products, dropped Surf Excel), then later
  surfaced Surf Excel's real scheme — making correct data look invented.

Root cause of the parroting:

1. **The prompt hands the model ready-to-speak scheme strings.** `catalog_lines()` appends
   `— scheme: {description}` to every catalog line (`context.py:31-32`), and the store's
   memory profile literally contains *"Regular on the Surf Excel 10%-off-3-cases scheme"*
   (`seed.py:282`). Under `reasoning_effort=low` (pinned for the live loop —
   `settings.py:81-88`), the model recites those strings without calling
   `get_active_schemes`.
2. **Guardrails are reactive, not proactive.** `CATALOG & OFFER DISCIPLINE` only fires
   "if the retailer asks for a product we do not carry"; nothing forbids *volunteering* an
   un-fetched scheme or *listing several at once*, and `GOAL step 3` actively invites
   offering schemes before a product is chosen.

The most robust fix removes the speakable scheme strings from the prompt and, ideally,
quantity-gates `get_active_schemes`. Per the scope decision below, this change ships the
**prompt-rule layer only**; the leak-removal / qty-gate are documented as the recommended
follow-up.

## Scope decisions (as chosen in brainstorming)

| Decision | Choice | Notes |
|---|---|---|
| Mid-call phrasing | **Net line price only** (+ its rupee saving), no arithmetic, no running total | e.g. *"Three cases of Surf Excel, that's ₹4,050 with the 10% off"* |
| Detailed breakdown | **Only at the final read-back** before placing, as a brief recap | required, not optional |
| Warmth dosage | **Light touch** | genuine human beat at open, warm through, brief close; keep it moving |
| Discount decline | Acknowledge → "pass to the team" → steer to real qualifying scheme | never hard-no, never invent |
| Anti-parroting enforcement | **Prompt-text-only** (accepted trade-off) | see risk below |

### Accepted trade-off (behavior ②)

The user explicitly chose **prompt-text-only** for the anti-parroting fix, twice, with the
trade-off spelled out. Consequences, recorded here on purpose:

- The `— scheme:` strings remain in the LIVE CATALOG block and scheme names remain in the
  memory profile. The new rule instructs the model to treat them as **stale reference that
  must be re-fetched before speaking**, but under `reasoning_effort=low` the model may
  still parrot them.
- The prompt rule is **not runtime-enforced** — `call_handler.py` never requires a tool
  call before the model speaks (`call_handler.py:264-270`).
- **Recommended follow-up if parroting persists:** delete the `— scheme:` append from
  `catalog_lines` (2 lines + the now-unused query), sanitize scheme phrases from the memory
  profile before injection, and quantity-gate `get_active_schemes` so schemes whose
  `min_qty` isn't met are never returned. These are low-risk and are the load-bearing fix.

## Non-goals

- No `call_handler.py` enforcement gate (require a tool call before speaking a scheme).
- No quantity-gating of `get_active_schemes` (code).
- No removal of the `— scheme:` append in `catalog_lines`.
- No memory-profile sanitization code, no `seed.py` profile edits.
- No `tool_specs.py` change (the hardcoded `"Surf Excel"` lookup example stays).
- Not fixing the separate STT "call gate" mis-transcription confusion seen in the transcript.

## Design — exact prompt edits

All edits are to the returned f-string (and the `push_block` f-string) in
`build_system_prompt`, `backend/src/memory/context.py`. Placeholders
(`{lang}`, `{opening_directive}`, `{mem}`, `{catalog}`, `{outlet.name}`, `{where}`,
`{company_name}`, `{pushed_product['name']}`, `{push_discount_pct:.0f}`) are preserved
exactly.

### 1. STYLE — add light-touch warmth (replaces current STYLE paragraph)

> STYLE: Speak ONLY in {lang}. Do NOT switch languages even if a transcript looks like
> another language — the retailer speaks {lang}; treat any other-language transcript as a
> mis-transcription and keep replying in {lang}. Sound like a real person, not a script:
> warm and friendly, one idea per short spoken sentence. Open with a genuine human beat —
> greet the shopkeeper by name and ask how business or their week is going — react briefly
> and warmly to what they say, then move on to the order; keep this light, don't linger in
> small talk. Use the shopkeeper's name naturally through the call, handle interruptions
> and "no" gracefully, and close with a brief warm well-wish. This is a routine weekly
> renewal call, not a hard sell. Output ONLY the words you say aloud — never stage
> directions, narration, or parentheticals like "(wait for response)". Greet only once at
> the very start; do not re-introduce yourself on later turns — continue the conversation
> from what was already said.

### 2. GOAL — net-price mid-call, single itemized recap, scheme only after product+qty

> GOAL, in order: (1) greet warmly by name and ask how business or their week is going,
> react briefly, (2) {opening_directive}, (3) once a product AND quantity are chosen, offer
> the single most relevant active scheme for THAT item with the EXACT rupee saving (see
> SCHEME & CATALOG DISCIPLINE) — one scheme, never a menu, (4) as each item is added or
> changed, say ONLY that item's final NET line price with its rupee saving in one short
> line (e.g. "Three cases of Surf Excel, that's ₹4,050 with the 10% off") — do NOT re-read
> the running total after every item and do NOT narrate the arithmetic, (5) UPSELL —
> before placing, call suggest_upsell ONCE; if it returns a suggestion, warmly offer that
> one extra product with the EXACT rupee saving at the suggested quantity (a friendly
> nudge, not a hard sell), and on a clear yes call add_line_item then get_order_summary and
> say ONLY that item's net line price with its saving in one short line (same format as
> step 4); on a no, drop it gracefully; if there is no suggestion, skip this step silently,
> (6) call get_order_summary and give ONE brief itemized recap — each item's quantity, net
> line price and rupee saving, then the grand total and delivery day; this final read-back
> is REQUIRED and is the only place you speak the full breakdown and the grand total,
> (7) ONLY after a clear spoken yes, place the order, (8) confirm the delivery day and
> close warmly.

### 3. NUMBERS block — new, inserted immediately after the GOAL line

> NUMBERS — SPEAK THE NET, NOT THE MATH (critical): Every price you say comes from a tool
> result — STATE the figure, never compute or narrate arithmetic (never "2 times 2,400 is
> 4,800"). Mid-call, as items are added or changed, say ONLY that item's final NET line
> price after any scheme, with its rupee saving, in one short line — and do NOT re-read the
> running grand total after each item. You MUST still give the full breakdown once: at the
> final itemized read-back right before place_order (GOAL step 6), speak each item's
> quantity, net line price and saving, then the grand total. This read-back is REQUIRED,
> not optional, and is the one place the grand total is spoken.

### 4. GROUND-TRUTH RULE — align the read-back sentence (edit existing block)

Change the middle sentence from *"Call get_order_summary and read the total back to the
retailer BEFORE calling place_order."* to:

> Before place_order, call get_order_summary and give the single brief itemized read-back
> described in GOAL step 6 (per item: quantity, net line price, saving; then the grand
> total).

(Rest of GROUND-TRUTH RULE unchanged.)

### 5. SCHEME & CATALOG DISCIPLINE — replaces CATALOG & OFFER DISCIPLINE (proactive)

> SCHEME & CATALOG DISCIPLINE (critical): NEVER volunteer, name, list or confirm ANY
> scheme, discount or rupee saving unless get_active_schemes or suggest_upsell RETURNED it
> in THIS turn for the specific SKU and quantity in play, with a real (non-zero) saving at
> that quantity. Any scheme or discount printed elsewhere in this prompt — the
> "— scheme: …" notes in the LIVE CATALOG below, and any scheme the store memory says they
> are "regular on" — is STALE background reference, NOT permission to speak it: you must
> re-fetch it with get_active_schemes before you say it, and only if it still applies at
> the quantity ordered. Offer AT MOST ONE scheme at a time — never read out a menu of two
> or more. Do NOT pre-announce any offer before a product and quantity are chosen: if none
> is chosen yet, ask which product and how many, then fetch. You may name PRODUCTS that
> appear in the LIVE CATALOG below or that lookup_products / suggest_upsell returned — the
> re-fetch rule applies to schemes and prices, not to product names. If the retailer asks
> for a product we do not carry, do NOT invent it — politely say we do not have that and
> steer them to what IS available: "these are the offers we currently have for retailers in
> your area." (Any operator-chosen PRIORITY PUSH product above is pre-authorized for this
> call; still confirm its exact rupee saving via a tool before you say it.)

### 6. IF THEY PUSH FOR MORE DISCOUNT — new short block (graceful decline)

> IF THEY PUSH FOR MORE DISCOUNT (critical): never give a flat "no" and never invent an
> offer. Warmly acknowledge the ask, tell them you'll pass the feedback on to the team, and
> steer them to the real scheme they DO qualify for (confirmed via a tool). Do NOT promise
> any future discount.

### 7. PRIORITY PUSH block — net-price + tool-confirm (edit `push_block` f-string)

> \n\nPRIORITY PUSH (this call): proactively promote {pushed_product['name']}
> ({pushed_product.get('pack') or ''}) — a special extra {push_discount_pct:.0f}% discount
> applies this call. Offer it warmly with the EXACT rupee saving — confirm the figure via a
> tool before you say it. On a clear yes call add_line_item then get_order_summary and say
> ONLY that item's net line price with its saving (no arithmetic, no running-total
> re-read). If they decline, drop it gracefully.

(Preserves the `{pushed_product['name']}` and `{push_discount_pct:.0f}%` placeholders that
`test_system_prompt_push.py` asserts on.)

### Unchanged blocks

TOOL DISCIPLINE, WHAT WE KNOW ABOUT THIS STORE (`{mem}`), and LIVE CATALOG (`{catalog}`)
are unchanged. `catalog_lines()`, `order_tools.py`, `tool_specs.py`, and `seed.py` are
untouched.

## Testing strategy

All tests are pure prompt-string / pure-function checks — no telephony, STT, TTS, LLM, or
Twilio (consistent with existing prompt tests).

1. **New `backend/tests/test_conversation_polish.py`** using the `db` + `seeded` fixtures
   (`conftest.py`) and `build_system_prompt(db, outlet, "Colgate", None, language=...)`.
   Assert the new wording is present:
   - `"NUMBERS — SPEAK THE NET, NOT THE MATH"` in prompt
   - `"SCHEME & CATALOG DISCIPLINE"` in prompt
   - `"AT MOST ONE scheme"` in prompt
   - `"is NOT permission to speak it"` in prompt (proactive rule)
   - `"pass the feedback on to the team"` in prompt (graceful decline)
   - a warmth marker, e.g. `"how business or their week is going"` in prompt
   - `"this final read-back is REQUIRED"` in prompt (single read-back survives)
   Do **not** assert `'5% off' not in prompt` or `'— scheme:' not in prompt` — the leak is
   intentionally retained under the prompt-only scope.
2. **Update `test_language_pinning.py:57`**: change
   `assert "CATALOG & OFFER DISCIPLINE" in prompt` →
   `assert "SCHEME & CATALOG DISCIPLINE" in prompt`. (Only reference to the old heading.)
3. **`test_system_prompt_push.py`** should pass unchanged (placeholders preserved). Run it
   to confirm the reworded push block still contains `PRIORITY PUSH`, `Surf Excel`, `15%`.

Run:
```
cd backend && python -m pytest tests/test_conversation_polish.py tests/test_language_pinning.py tests/test_system_prompt_push.py -q
```

## Risks

- **Behavior ② may not fully stop parroting** under `reasoning_effort=low` — accepted
  trade-off (see above); revisit with the leak-removal/qty-gate follow-up if it recurs.
- **GOAL renumber** (place_order 6→7, close 7→8): `TOOL DISCIPLINE` references
  `place_order` by name, not number, and no doc cites GOAL step numbers (verified via
  grep), so nothing breaks. The NUMBERS/GROUND-TRUTH blocks reference "GOAL step 6" by
  number — acceptable for now; if GOAL steps change later, update those references.
- **Historical design docs** (`call-targeting-design.md`, `call-targeting.md`) quote the
  old PRIORITY PUSH "re-read the new total" wording; these are historical records, left
  as-is.
- **Warmth vs. brevity:** the light-touch opener adds one exchange; STYLE's "keep it light,
  don't linger" + "one idea per turn" bound it so calls don't balloon.
