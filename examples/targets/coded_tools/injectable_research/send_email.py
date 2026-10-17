"""Fake email sender (records nothing, sends nothing)."""

from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool


class SendEmail(CodedTool):
    """Pretends to send an email."""

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        return f"email queued to {args.get('to')}"
