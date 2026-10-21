from __future__ import annotations
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field


HttpMethod = Literal["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]


StateLabel = Literal[
    "authn", "authz", "ownership", "money", "workflow", "single_use", "irrelevant"
]
CandidateSource = Literal["session_access", "db_field", "condition", "ownership_binding", "call"]


class Param(BaseModel):
    name: str
    location: Literal["path", "query", "json", "header", "cookie"]
    py_type: str = "str"
    value_domain: list[str] | None = None


class StateCandidate(BaseModel):
    

    var: str                      
    entity: str | None = None
    attr: str | None = None
    ops: list[Literal["read", "compare", "write"]] = Field(default_factory=list)
    evidence: str                 
    source: CandidateSource
    file: str
    line: int


class StateVar(BaseModel):

    entity: str
    attr: str
    kind: Literal["db_column", "session", "derived"] = "db_column"
    domain: list[str] | None = None
    label: StateLabel | None = None
    security_relevant: bool = False
    rationale: str = ""
    anchors: list[tuple[str, int]] = Field(default_factory=list)  

    @property
    def var(self) -> str:
        return f"{self.entity}.{self.attr}"


class Effect(BaseModel):
    var: str                      
    op: Literal["set", "clear", "check"]
    value: str | None = None
    key: str | None = None        
    file: str
    line: int

class Precondition(BaseModel):
    var: str
    op: Literal["eq", "ne", "in", "truthy", "falsy"]
    value: str | None = None
    key: str | None = None
    file: str
    line: int


class Guard(BaseModel):
    kind: Literal["role", "owner", "token", "custom"]
    present: bool = True          
    detail: str = ""
    file: str
    line: int


class Sink(BaseModel):
    kind: Literal["sql_build", "file_path", "exec", "redirect"]
    file: str
    line: int
    snippet: str = ""


class Endpoint(BaseModel):
    func: str
    route: str
    methods: list[HttpMethod]
    params: list[Param] = Field(default_factory=list)
    guards: list[Guard] = Field(default_factory=list)
    preconditions: list[Precondition] = Field(default_factory=list)
    effects: list[Effect] = Field(default_factory=list)
    sinks: list[Sink] = Field(default_factory=list)
    observes: list[str] = Field(default_factory=list)
    file: str = ""
    line: int = 0


class PlanStep(BaseModel):
    

    action: str                       
    json: dict[str, str] = Field(default_factory=dict)
    path: dict[str, str] = Field(default_factory=dict)      
    headers: dict[str, str] = Field(default_factory=dict)   
    extract: dict[str, str] = Field(default_factory=dict)   

class PlanSegment(BaseModel):
    
    goal: str
    steps: list[PlanStep] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)          


class Invariant(BaseModel):
    

    entity: str
    attr: str
    legal_transitions: list[tuple[str, str]] = Field(default_factory=list)
    one_way: list[str] = Field(default_factory=list)  

    @property
    def var(self) -> str:
        return f"{self.entity}.{self.attr}"


class AppModel(BaseModel):
    

    app_root: str
    framework: Literal["flask", "connexion", "django", "synthetic"]
    endpoints: list[Endpoint] = Field(default_factory=list)
    candidates: list[StateCandidate] = Field(default_factory=list)
    state_vars: list[StateVar] = Field(default_factory=list)
    invariants: list[Invariant] = Field(default_factory=list)
    config_flags: dict[str, int] = Field(default_factory=dict)

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def from_json(cls, path: str | Path) -> "AppModel":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))
