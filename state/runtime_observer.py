from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Protocol, runtime_checkable
class Evidence(str, Enum):
    RUNTIME_VERIFIED = "runtime_verified"      
    CONTROL_FLOW_PROXY = "control_flow_proxy"  
    UNKNOWN = "unknown"                        
SCOPE_SESSION = "session"    
SCOPE_USER = "user"          
SCOPE_RESOURCE = "resource"  
SCOPE_GLOBAL = "global"      
SCOPE_UNKNOWN = "unknown"    
SCOPES = frozenset({SCOPE_SESSION, SCOPE_USER, SCOPE_RESOURCE,
                    SCOPE_GLOBAL, SCOPE_UNKNOWN})

@dataclass(frozen=True)
class StateKey:
    

    predicate: str
    entity: str = "*"
    scope: str = SCOPE_GLOBAL
    def __post_init__(self) -> None:
        if not isinstance(self.predicate, str) or not self.predicate:
            raise ValueError("predicate 必须是非空字符串")
        if not isinstance(self.entity, str) or not self.entity:
            raise ValueError("entity 必须是非空字符串(全局用 '*')")
        if self.scope not in SCOPES:
            raise ValueError(f"scope 必须是 {sorted(SCOPES)} 之一: {self.scope!r}")
    def render(self) -> str:
        return f"{self.predicate}{{{self.entity}@{self.scope}}}"
@dataclass(frozen=True)
class StateObservation:
    

    key: StateKey
    value: bool
    evidence: Evidence
    source: str = ""
    subject: str | None = None
    observed_value: object = None
    value_kind: str | None = None
    observed_at: int = -1

    def render(self) -> str:
        
        return f"{self.key.render()}={self.value}"

    def to_dict(self) -> dict:
        d = {"key": self.key.render(), "value": self.value,
             "evidence": self.evidence.value, "source": self.source}
        if self.subject is not None:
            d["subject"] = self.subject
        if self.value_kind is not None:
            d["observed_value"] = self.observed_value
            d["value_kind"] = self.value_kind
        if self.observed_at != -1:
            d["observed_at"] = self.observed_at
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "StateObservation":
        pred, entity, scope = _parse_rendered(d["key"])
        return cls(key=StateKey(pred, entity, scope), value=bool(d["value"]),
                   evidence=Evidence(d["evidence"]), source=d.get("source", ""),
                   subject=d.get("subject"),
                   observed_value=d.get("observed_value"),
                   value_kind=d.get("value_kind"),
                   observed_at=int(d.get("observed_at", -1)))
VALUE_KIND_ENUM = "ENUM"
VALUE_KIND_BOOLEAN = "BOOLEAN"
VALUE_KIND_NUMBER = "NUMBER"
VALUE_KIND_STRING = "STRING"
VALUE_KIND_NULL = "NULL"          
VALUE_KIND_MISSING = "MISSING"    
VALUE_KIND_UNKNOWN = "UNKNOWN"    
VALUE_KINDS = frozenset({VALUE_KIND_ENUM, VALUE_KIND_BOOLEAN,
                         VALUE_KIND_NUMBER, VALUE_KIND_STRING,
                         VALUE_KIND_NULL, VALUE_KIND_MISSING,
                         VALUE_KIND_UNKNOWN})

def _parse_rendered(rendered: str) -> tuple[str, str, str]:
    
    if not (rendered.endswith("}") and "{" in rendered and "@" in rendered):
        raise ValueError(f"非 StateKey.render 形态: {rendered!r}")
    pred, sep, rest = rendered.partition("{")
    entity, at, scope = rest[:-1].rpartition("@")     
    if not (sep and at and pred and entity and scope):
        raise ValueError(f"非 StateKey.render 形态: {rendered!r}")
    return pred, entity, scope




@runtime_checkable
class RuntimeObserver(Protocol):
    

    name: str
    subject_families: dict[str, str]

    def observe(self) -> list[StateObservation]: ...


RUNTIME_VERIFIED = "runtime_verified"   
OBSERVABLE = "observable"
NOT_OBSERVABLE = "not_observable"
UNPROBED = "unprobed"
OBSERVABILITY_STATUSES = frozenset({OBSERVABLE, NOT_OBSERVABLE, UNPROBED})


def observability_of(declared: dict[str, str], subject: str) -> str:
    if not declared:
        return UNPROBED
    if subject in declared:
        return declared[subject]
    root = subject.split(".", 1)[0]
    return declared.get(f"{root}.*", UNPROBED)

class NullObserver:
    

    name = "null"
    subject_families: dict[str, str] = {}

    def observe(self) -> list[StateObservation]:
        return []

def control_flow_proxy_observation(atom: str,
                                   source: str = "reached_state_atoms"
                                   ) -> StateObservation:
    
    return StateObservation(key=StateKey(predicate=atom, entity="*",
                                         scope=SCOPE_UNKNOWN),
                            value=True, evidence=Evidence.CONTROL_FLOW_PROXY,
                            source=source)



@dataclass
class StateEvidenceLedger:
    observer_name: str = ""
    _verified: dict = field(default_factory=dict)   
    _proxy: dict = field(default_factory=dict)      
    def record(self, observations: Iterable[StateObservation]
               ) -> list[StateObservation]:
        novel: list[StateObservation] = []
        for obs in observations or ():
            if obs.evidence is not Evidence.RUNTIME_VERIFIED:
                continue                      
            dedup = (obs.key.render(), obs.value)
            if dedup not in self._verified:
                self._verified[dedup] = obs
                novel.append(obs)
        return novel

    def record_proxy(self, atoms: Iterable[str],
                     source: str = "reached_state_atoms") -> list[StateObservation]:
        
        novel: list[StateObservation] = []
        for atom in atoms or ():
            obs = control_flow_proxy_observation(atom, source)
            if obs.key.render() not in self._proxy:
                self._proxy[obs.key.render()] = obs
                novel.append(obs)
        return novel
    @property
    def verified_keys(self) -> set[str]:
        return {render for render, _value in self._verified}

    @property
    def verified_observations(self) -> list[StateObservation]:
        return list(self._verified.values())

    @property
    def proxy_atoms(self) -> set[str]:
        return set(self._proxy)
    def to_payload(self) -> dict:
        
        return {
            "evidence_version": 1,
            "observer": self.observer_name,
            "verified_atoms": sorted(self.verified_keys),
            "verified": [obs.to_dict() for obs in
                         sorted(self.verified_observations,
                                key=lambda o: (o.key.render(), o.value))],
            "proxy_atoms": sorted(self.proxy_atoms),
        }

    def load_payload(self, payload: dict) -> None:
        self.observer_name = payload.get("observer", self.observer_name)
        for d in payload.get("verified", []):
            try:
                self.record([StateObservation.from_dict(d)])
            except (KeyError, ValueError):
                continue                     
