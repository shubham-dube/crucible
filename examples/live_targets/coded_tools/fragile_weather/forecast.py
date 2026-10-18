"""Seeded defect: the upstream service is down for some cities."""

from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool


class Forecast(CodedTool):
    """Fake weather client; 'Raichur' simulates an upstream outage."""

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> Any:
        city = str(args.get("city", ""))
        if city.lower() == "raichur":
            raise RuntimeError("upstream weather service returned HTTP 503")
        return f"{city}: 31C, clear skies"
