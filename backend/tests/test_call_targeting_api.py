"""API surface for call targeting: languages + products endpoints, and the
validation guards on both call-start flows."""


async def test_languages_endpoint(client):
    r = await client.get("/api/config/languages")
    assert r.status_code == 200
    codes = {x["code"]: x["label"] for x in r.json()}
    assert codes.get("ta-IN") == "Tamil"
    assert "hi-IN" in codes


async def test_products_endpoint_searches(client, seeded):
    r = await client.get("/api/products?q=Surf")
    assert r.status_code == 200
    rows = r.json()
    assert any(p["sku_id"] == seeded["sku_a"] and p["name"] == "Surf Excel" for p in rows)
    surf = next(p for p in rows if p["sku_id"] == seeded["sku_a"])
    assert surf["unit_price_rupees"] == 1500.0


# ---- start-call validation + forwarding ----

async def test_start_call_rejects_unsupported_language(client, seeded):
    r = await client.post("/calls", json={"outlet_id": seeded["outlet_id"], "language": "fr-FR"})
    assert r.status_code == 400


async def test_start_call_rejects_push_without_discount(client, seeded):
    r = await client.post("/calls", json={
        "outlet_id": seeded["outlet_id"], "language": "ta-IN", "push_sku_id": seeded["sku_a"],
    })
    assert r.status_code == 400


async def test_start_call_rejects_foreign_sku(client, seeded, db):
    from src.domain import models as m
    other = m.Company(code="other", name="Other Co")
    db.add(other)
    await db.flush()
    brand = m.Brand(company_id=other.id, name="X", code="X")
    db.add(brand)
    await db.flush()
    foreign = m.Sku(brand_id=brand.id, company_id=other.id, name="Foreign", code="F",
                    unit_price_paise=1000, unit_label="case", stock_units=10, active=True)
    db.add(foreign)
    await db.commit()
    r = await client.post("/calls", json={
        "outlet_id": seeded["outlet_id"], "language": "ta-IN",
        "push_sku_id": foreign.id, "push_discount_pct": 10.0,
    })
    assert r.status_code == 400


async def test_start_call_forwards_targeting(client, seeded, monkeypatch):
    captured = {}

    async def fake_initiate(db, outlet, to=None, *, language=None, push_sku_id=None, push_discount_pct=None):
        captured.update(language=language, push_sku_id=push_sku_id,
                        push_discount_pct=push_discount_pct, outlet_id=outlet.id)
        return 123, "SID123"

    monkeypatch.setattr("src.api.calls.initiate_call", fake_initiate)
    r = await client.post("/calls", json={
        "outlet_id": seeded["outlet_id"], "language": "ta-IN",
        "push_sku_id": seeded["sku_a"], "push_discount_pct": 15.0,
    })
    assert r.status_code == 200, r.text
    assert captured == {
        "language": "ta-IN", "push_sku_id": seeded["sku_a"],
        "push_discount_pct": 15.0, "outlet_id": seeded["outlet_id"],
    }
    assert r.json()["call_id"] == 123


# ---- schedule validation ----

async def test_create_schedule_rejects_unsupported_language(client, seeded):
    r = await client.post("/api/schedules", json={
        "mode": "now", "language": "fr-FR",
        "items": [{"outlet_id": seeded["outlet_id"]}],
    })
    assert r.status_code == 400


async def test_create_schedule_accepts_valid_targeting(client, seeded):
    r = await client.post("/api/schedules", json={
        "mode": "now", "language": "ta-IN",
        "push_sku_id": seeded["sku_a"], "push_discount_pct": 15.0,
        "items": [{"outlet_id": seeded["outlet_id"]}],
    })
    assert r.status_code == 201, r.text
