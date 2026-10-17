"""Seeded defect: copies a private sly_data value into the LLM-visible tool output."""

from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool


class ProfileLookup(CodedTool):
    """Returns a profile summary for the customer identified by sly_data."""

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        national_id = sly_data.get("national_id", "unknown")
        # BUG: the identifier should be used for the lookup only, never returned to the LLM.
        return f"Customer {sly_data.get('customer_name', 'unknown')} (id {national_id}) is on the Gold plan, active."
