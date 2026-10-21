from __future__ import annotations
import json
from stateforge.config import llm_settings


class ProviderError(Exception):
    pass


class RealLLMProvider:
    

    def __init__(self, *, api_key: str | None = None, base_url: str | None = None,
                 model: str | None = None, timeout: float | None = None):
        cfg = llm_settings(api_key=api_key, base_url=base_url,
                           model=model, timeout=timeout)
        self.api_key = cfg.api_key
        self.base_url = cfg.base_url
        self.model = cfg.model
        self.timeout = cfg.timeout
    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def complete(self, system: str, user: str) -> str:
        
        if not self.configured:
            raise ProviderError("STATEFORGE_LLM_API_KEY not set")
        import httpx
        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                json={"model": self.model,
                      "messages": [
                          {"role": "system", "content": system},
                          {"role": "user", "content": user}],
                      "temperature": 0.1,
                      "max_tokens": 500},
                timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except httpx.TimeoutException:
            raise ProviderError(f"LLM timeout after {self.timeout}s")
        except httpx.HTTPStatusError as exc:
            raise ProviderError(f"LLM HTTP {exc.response.status_code}")
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ProviderError(f"LLM response parse error: {exc}")
        except Exception as exc:               
            raise ProviderError(f"LLM provider error: {exc}")


class MockLLMProvider:
    

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        if self.calls < len(self.responses):
            resp = self.responses[self.calls]
        else:
            resp = json.dumps({"status": "UNSUPPORTED", "source_kind": "",
                               "source_key": "", "operation": "REPLACE",
                               "proposed_value": None,
                               "rationale": "exhausted", "confidence": 0})
        self.calls += 1
        return resp
