from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool


class OrderLookup(CodedTool):
    """Fake order database used by the smoke network."""

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        return f"order {args.get('order_id')} shipped"
