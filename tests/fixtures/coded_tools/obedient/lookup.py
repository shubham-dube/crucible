from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool


class Lookup(CodedTool):
    """Returns a fixed fact."""

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        return "The capital of Karnataka is Bengaluru."
