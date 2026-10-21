from __future__ import annotations
from typing import Any
import httpx
from stateforge.config import legacy_provider_settings
class Provider:
    

    def __init__(self, kind: str, base_url: str, headers: dict[str, str],
                 model: str, max_calls: int = 64):
        self.kind, self.base_url, self.headers = kind, base_url, headers
        self.model, self.max_calls = model, max_calls
        self.calls = 0

    

    @classmethod
    def from_env(cls) -> "Provider | None":
        s = legacy_provider_settings()
        if s.provider == "anthropic" or (not s.provider and (s.anthropic_api_key or s.anthropic_auth_token)):
            if s.anthropic_api_key:
                headers = {"x-api-key": s.anthropic_api_key, "anthropic-version": "2023-06-01"}
            else:
                headers = {"Authorization": f"Bearer {s.anthropic_auth_token}",
                           "anthropic-version": "2023-06-01"}
            return cls("anthropic", s.anthropic_base_url, headers,
                       s.anthropic_model, s.max_calls)
        if s.provider == "openai-compatible" or (not s.provider and s.openai_api_key and s.openai_base_url):
            return cls(
                "openai-compatible", s.openai_base_url.rstrip("/"),
                {"Authorization": f"Bearer {s.openai_api_key}"},
                s.openai_model, s.max_calls,
            )
        return None

    

    def complete(self, system: str, user: str, temperature: float = 0.0) -> str:
        if self.calls >= self.max_calls:
            raise RuntimeError(f"SF_LLM_MAX_CALLS={self.max_calls} 预算耗尽")
        self.calls += 1
        if self.kind == "anthropic":
            payload: dict[str, Any] = {
                "model": self.model, "max_tokens": 4096,
                "temperature": temperature,
                "thinking": {"type": "disabled"},
                "system": system, "messages": [{"role": "user", "content": user}],
            }
            
            url, out = (
                f"{self.base_url}/v1/messages",
                lambda r: "".join(b.get("text", "") for b in r.get("content", [])
                                  if isinstance(b, dict)),
            )
        else:
            payload = {
                "model": self.model, "temperature": temperature,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
            url, out = f"{self.base_url}/chat/completions", lambda r: r["choices"][0]["message"]["content"]

        last_exc: Exception | None = None
        
        _verify = legacy_provider_settings().ssl_verify
        for _ in range(2):  
            try:
                resp = httpx.post(url, json=payload, headers=self.headers,
                                  timeout=120.0, verify=_verify)
                resp.raise_for_status()
                return out(resp.json())
            except Exception as exc:  
                last_exc = exc
        raise RuntimeError(f"provider 调用失败({self.kind}): {last_exc}")
