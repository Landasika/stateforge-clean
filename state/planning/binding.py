from __future__ import annotations
import re
import secrets
from typing import Any

ITEMS = [{"sku": "book", "price": 100, "qty": 1}]

_SLOT_RE = re.compile(r"\?(\w+)")


class BindingContext:
    def __init__(self, salt: str | None = None):
        self.bindings: dict[str, Any] = {}
        self._fresh: dict[str, str] = {}
        self.salt = salt or secrets.token_hex(4)

    def fresh(self, key: str) -> str:
        
        if key not in self._fresh:
            self._fresh[key] = f"sf_{key}_{self.salt}"
        return self._fresh[key]

    def render(self, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        if value.startswith("@fresh:"):
            return self.fresh(value[len("@fresh:"):])
        if value == "@items":
            return ITEMS
        if value.startswith("?"):
            return self.bindings.get(value[1:])
        if "?" in value:  
            return _SLOT_RE.sub(
                lambda m: str(self.bindings.get(m.group(1), m.group(0))), value
            )
        return value

    def render_step(self, step):
        
        json_body = {k: self.render(v) for k, v in step.json.items()}
        headers = {k: self.render(v) for k, v in step.headers.items()}
        route = step.action.partition(" ")[2]
        for name, v in step.path.items():
            route = route.replace(f"<int:{name}>", str(self.render(v)))
            route = route.replace(f"<{name}>", str(self.render(v)))
        return route, json_body, headers

    def absorb(self, extract: dict[str, str], payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        for resp_key, slot in extract.items():
            if resp_key in payload:
                self.bindings[slot.lstrip("?")] = payload[resp_key]
