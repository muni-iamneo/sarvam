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
