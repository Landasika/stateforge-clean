from __future__ import annotations
import os
from dataclasses import dataclass

@dataclass
class LLMSettings:
    

    api_key: str | None
    base_url: str | None
    model: str | None
    timeout: float

_DEFAULTS = {
    "api_key": "",
    "base_url": "https://open.bigmodel.cn/api/paas/v4",
    "model": "glm-4-flash",
}
_DEFAULT_TIMEOUT = 30
_ENV_VARS = {
    "api_key": "STATEFORGE_LLM_API_KEY",
    "base_url": "STATEFORGE_LLM_BASE_URL",
    "model": "STATEFORGE_LLM_MODEL",
}


def _pick(override: str | None, env_name: str, default: str) -> str:
    
    if override is not None:
        return override
    return os.environ.get(env_name, default)


def llm_settings(**overrides: str | float | None) -> LLMSettings:
    
    raw_timeout = overrides.get("timeout")
    if raw_timeout is None:
        raw_timeout = os.environ.get("STATEFORGE_LLM_TIMEOUT", str(_DEFAULT_TIMEOUT))
    timeout = int(raw_timeout) if isinstance(raw_timeout, str) else float(raw_timeout)
    return LLMSettings(
        api_key=_pick(overrides.get("api_key"), _ENV_VARS["api_key"],
                      _DEFAULTS["api_key"]),
        base_url=_pick(overrides.get("base_url"), _ENV_VARS["base_url"],
                       _DEFAULTS["base_url"]).rstrip("/"),
        model=_pick(overrides.get("model"), _ENV_VARS["model"],
                    _DEFAULTS["model"]),
        timeout=timeout,
    )




@dataclass
class LegacyProviderSettings:
    

    provider: str | None              
    anthropic_api_key: str | None     
    anthropic_auth_token: str | None  
    anthropic_base_url: str           
    openai_api_key: str | None        
    openai_base_url: str | None       
    anthropic_model: str              
    openai_model: str                 
    max_calls: int                    
    ssl_verify: bool                  
_LEGACY_ENV_VARS = {
    "provider": "SF_LLM_PROVIDER",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "anthropic_auth_token": "ANTHROPIC_AUTH_TOKEN",
    "anthropic_base_url": "ANTHROPIC_BASE_URL",
    "openai_api_key": "OPENAI_API_KEY",
    "openai_base_url": "SF_LLM_BASE_URL",
}
_LEGACY_MODEL_ENV = "SF_LLM_MODEL"
def _pick_raw(override: str | None, env_name: str) -> str | None:
    if override is not None:
        return override
    return os.environ.get(env_name)


def legacy_provider_settings(
        **overrides: str | int | bool | None) -> LegacyProviderSettings:
    
    raw_max_calls = overrides.get("max_calls")
    if raw_max_calls is None:
        raw_max_calls = os.environ.get("SF_LLM_MAX_CALLS", "64")
    raw_verify = overrides.get("ssl_verify")
    if raw_verify is None:
        raw_verify = os.environ.get("SF_LLM_SSL_VERIFY", "true")
    return LegacyProviderSettings(
        provider=_pick_raw(overrides.get("provider"),
                           _LEGACY_ENV_VARS["provider"]),
        anthropic_api_key=_pick_raw(overrides.get("anthropic_api_key"),
                                    _LEGACY_ENV_VARS["anthropic_api_key"]),
        anthropic_auth_token=_pick_raw(overrides.get("anthropic_auth_token"),
                                       _LEGACY_ENV_VARS["anthropic_auth_token"]),
        anthropic_base_url=(_pick_raw(overrides.get("anthropic_base_url"),
                                      _LEGACY_ENV_VARS["anthropic_base_url"])
                            or "https://api.anthropic.com").rstrip("/"),
        openai_api_key=_pick_raw(overrides.get("openai_api_key"),
                                 _LEGACY_ENV_VARS["openai_api_key"]),
        openai_base_url=_pick_raw(overrides.get("openai_base_url"),
                                  _LEGACY_ENV_VARS["openai_base_url"]),
        anthropic_model=_pick(overrides.get("anthropic_model"),
                              _LEGACY_MODEL_ENV, "claude-sonnet-5"),
        openai_model=_pick(overrides.get("openai_model"),
                           _LEGACY_MODEL_ENV, "glm-4.6"),
        max_calls=int(raw_max_calls),
        ssl_verify=(raw_verify.lower() != "false" if isinstance(raw_verify, str)
                    else bool(raw_verify)),
    )
