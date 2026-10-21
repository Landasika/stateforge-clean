from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StateDomain(str, Enum):
    SESSION = "SESSION"
    DATABASE = "DATABASE"
    FILE = "FILE"


class StateOperation(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    DELETE = "DELETE"


class Relevance(str, Enum):
    CONTROL = "CONTROL"           
    NON_CONTROL = "NON_CONTROL"   
    UNKNOWN = "UNKNOWN"           

class PredicateOp(str, Enum):
    EQ = "EQ"
    NE = "NE"
    EXISTS = "EXISTS"
    NOT_EXISTS = "NOT_EXISTS"
    IN = "IN"
    NOT_IN = "NOT_IN"
    TRUTHY = "TRUTHY"
    FALSY = "FALSY"


@dataclass(frozen=True)
class StructuredPredicate:
    operator: PredicateOp
    subject: str                   
    value: Any = None              

    def to_dict(self) -> dict:
        return {"operator": self.operator.value,
                "subject": self.subject,
                "value": self.value}

    @classmethod
    def from_dict(cls, d: dict) -> "StructuredPredicate":
        return cls(PredicateOp(d["operator"]), d["subject"], d.get("value"))


@dataclass(frozen=True)
class StateFactCandidate:
    candidate_id: str              
    domain: StateDomain
    object_ref: str                
    operation: StateOperation
    source_file: str
    function_name: str | None
    lineno: int
    block_id: str | None           
    predicate: str | None          
    structured_predicate: StructuredPredicate | None
    written_value: Any             
    relevance: Relevance
    evidence: tuple[str, ...]      

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "domain": self.domain.value,
            "object_ref": self.object_ref,
            "operation": self.operation.value,
            "source_file": self.source_file,
            "function_name": self.function_name,
            "lineno": self.lineno,
            "block_id": self.block_id,
            "predicate": self.predicate,
            "structured_predicate": (
                self.structured_predicate.to_dict()
                if self.structured_predicate else None),
            "written_value": self.written_value,
            "relevance": self.relevance.value,
            "evidence": list(self.evidence),
        }
