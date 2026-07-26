"""OpenAI-style function schemas for the renewal-call order tools."""

ORDER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_products",
            "description": "Look up SKUs with live price and stock by name or keyword. Use before quoting any price.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Product name or keyword, e.g. 'Surf Excel'"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_schemes",
            "description": "Get active schemes and the exact ₹ savings for SKUs at given quantities.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku_ids": {"type": "array", "items": {"type": "integer"}},
                    "quantities": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["sku_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_line_item",
            "description": "Add a quantity of a SKU (by sku_id) to the current order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku_id": {"type": "integer"},
                    "qty": {"type": "integer"},
                },
                "required": ["sku_id", "qty"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_line_item",
            "description": "Remove a SKU from the current order.",
            "parameters": {
                "type": "object",
                "properties": {"sku_id": {"type": "integer"}},
                "required": ["sku_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order_summary",
            "description": "Get the itemized order with live prices, applied schemes, and the total in ₹.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "place_order",
            "description": "Confirm and log the order. Only call AFTER the retailer says yes to the read-back total.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "end_call",
            "description": "End the call politely.",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
            },
        },
    },
]
