"""Fake order status lookup that never exposes sly_data."""

from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool


class OrderStatus(CodedTool):
    """Returns a shipping status for an order id."""

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        order_id = str(args.get("order_id", "")).strip()
        if not order_id:
            return "Error: order_id is required"
        return f"Order {order_id} shipped on 2026-10-15 and arrives in 2 days."
