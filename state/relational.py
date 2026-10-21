from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping
class RelOp(str, Enum):
    EQ = "EQ"
    NE = "NE"
    IN = "IN"
    NOT_IN = "NOT_IN"
    TRUTHY = "TRUTHY"
    FALSY = "FALSY"
    EXISTS = "EXISTS"          
    NOT_EXISTS = "NOT_EXISTS"



_NEEDS_RIGHT = frozenset({RelOp.EQ, RelOp.NE, RelOp.IN, RelOp.NOT_IN})


@dataclass(frozen=True)
class Field:
    

    var: str                   
    name: str = ""             
    source_file: str = ""
    source_line: int = 0

    def to_dict(self) -> dict:
        return {"var": self.var, "name": self.name,
                "source_file": self.source_file,
                "source_line": self.source_line}
    @classmethod
    def from_dict(cls, d: Mapping) -> "Field":
        return cls(var=str(d["var"]), name=str(d.get("name", "")),
                   source_file=str(d.get("source_file", "")),
                   source_line=int(d.get("source_line", 0)))
@dataclass(frozen=True)
class Const:
    value: Any = None
    def to_dict(self) -> dict:
        return {"value": self.value}

    @classmethod
    def from_dict(cls, d: Mapping) -> "Const":
        return cls(value=d.get("value"))


def term_from_dict(d: Mapping) -> "Field | Const":
    if "var" in d:
        return Field.from_dict(d)
    return Const.from_dict(d)


@dataclass(frozen=True)
class RelPredicate:
    

    op: RelOp
    left: Field
    right: "Field | Const | None" = None
    origin_op: str = ""          
    source_file: str = ""
    source_line: int = 0
    via_edge: str = ""           
    note: str = ""               

    def to_dict(self) -> dict:
        return {
            "op": self.op.value,
            "left": self.left.to_dict(),
            "right": (self.right.to_dict()
                      if isinstance(self.right, (Field, Const)) else None),
            "origin_op": self.origin_op,
            "source_file": self.source_file,
            "source_line": self.source_line,
            "via_edge": self.via_edge,
            "note": self.note,
        }
    @classmethod
    def from_dict(cls, d: Mapping) -> "RelPredicate":
        right = d.get("right")
        return cls(
            op=RelOp(d["op"]), left=Field.from_dict(d["left"]),
            right=term_from_dict(right) if right is not None else None,
            origin_op=str(d.get("origin_op", "")),
            source_file=str(d.get("source_file", "")),
            source_line=int(d.get("source_line", 0)),
            via_edge=str(d.get("via_edge", "")),
            note=str(d.get("note", "")),
        )

    def render(self) -> str:
        
        lhs = (f"{self.left.var}.{self.left.name}" if self.left.name
               else self.left.var)
        if self.right is None:
            body = f"{self.op.value}({lhs})"
        elif isinstance(self.right, Const):
            body = f"{self.op.value}({lhs}, {self.right.value!r})"
        else:
            rhs = (f"{self.right.var}.{self.right.name}" if self.right.name
                   else self.right.var)
            body = f"{self.op.value}({lhs}, {rhs})"
        anchor = (f"@{self.source_file.rsplit('/', 1)[-1]}:"
                  f"{self.source_line}" if self.source_line else "")
        return body + anchor


@dataclass(frozen=True)
class PathCondition:
    

    var: str                    
    requires: bool              
    kind: str                   
    source_file: str = ""
    source_line: int = 0
    note: str = ""

    def to_dict(self) -> dict:
        return {"var": self.var, "requires": self.requires,
                "kind": self.kind, "source_file": self.source_file,
                "source_line": self.source_line, "note": self.note}

    @classmethod
    def from_dict(cls, d: Mapping) -> "PathCondition":
        return cls(var=str(d["var"]), requires=bool(d["requires"]),
                   kind=str(d.get("kind", "config")),
                   source_file=str(d.get("source_file", "")),
                   source_line=int(d.get("source_line", 0)),
                   note=str(d.get("note", "")))

    def render(self) -> str:
        return (f"path:{self.kind}:{self.var}"
                f"={'true' if self.requires else 'false'}")
@dataclass(frozen=True)
class VarProvenance:
    
    var: str                        
    table: str | None = None        
    key_param: str | None = None    
    origin: tuple[str, ...] = ()    
    auth_subject: bool = False      
    source_file: str = ""
    source_line: int = 0

    def to_dict(self) -> dict:
        return {"var": self.var, "table": self.table,
                "key_param": self.key_param, "origin": list(self.origin),
                "auth_subject": self.auth_subject,
                "source_file": self.source_file,
                "source_line": self.source_line}

    @classmethod
    def from_dict(cls, d: Mapping) -> "VarProvenance":
        return cls(var=str(d["var"]), table=d.get("table"),
                   key_param=d.get("key_param"),
                   origin=tuple(d.get("origin", ())),
                   auth_subject=bool(d.get("auth_subject", False)),
                   source_file=str(d.get("source_file", "")),
                   source_line=int(d.get("source_line", 0)))

    def render(self) -> str:
        head = f"{self.var} <- " + (" | ".join(self.origin) or "?")
        if self.table:
            head += f" [table={self.table}"
            if self.key_param:
                head += f" key={self.key_param}"
            head += "]"
        if self.auth_subject:
            head += " [auth-subject]"
        return head
@dataclass(frozen=True)
class UnresolvableItem:
    

    what: str            
    cause: str
    source_file: str = ""
    source_line: int = 0

    def to_dict(self) -> dict:
        return {"what": self.what, "cause": self.cause,
                "source_file": self.source_file,
                "source_line": self.source_line}

    @classmethod
    def from_dict(cls, d: Mapping) -> "UnresolvableItem":
        return cls(what=str(d["what"]), cause=str(d["cause"]),
                   source_file=str(d.get("source_file", "")),
                   source_line=int(d.get("source_line", 0)))




class _Unknown:
    

    __slots__ = ()

    def __repr__(self) -> str:      
        return "UNKNOWN"

    def __bool__(self) -> bool:     
        raise TypeError("UNKNOWN 无真值;显式与 UNKNOWN 比较,禁止隐式转换")

UNKNOWN: Any = _Unknown()

def resolve(term: "Field | Const", snapshot: Mapping[str, Mapping],
            bindings: Mapping[str, str]) -> Any:
    
    if isinstance(term, Const):
        return term.value
    entity = bindings.get(term.var)
    if entity is None:
        return UNKNOWN
    row = snapshot.get(entity)
    if not isinstance(row, Mapping):
        return UNKNOWN
    if term.name == "":              
        return row
    return row.get(term.name, UNKNOWN)

def evaluate_relation(pred: RelPredicate, snapshot: Mapping[str, Mapping],
                      bindings: Mapping[str, str],
                      enumeration_complete: Mapping[str, bool] | None = None
                      ) -> str:
    
    op = pred.op
    if op in (RelOp.EXISTS, RelOp.NOT_EXISTS):
        entity = bindings.get(pred.left.var)
        if entity is None:
            return "UNKNOWN"
        present = entity in snapshot
        if present:
            return "TRUE" if op is RelOp.EXISTS else "FALSE"
        
        family = str(entity).split(":", 1)[0]
        complete = bool(enumeration_complete.get(family)) \
            if enumeration_complete else False
        if complete:
            return "FALSE" if op is RelOp.EXISTS else "TRUE"
        return "UNKNOWN"
    left = resolve(pred.left, snapshot, bindings)
    if op in (RelOp.TRUTHY, RelOp.FALSY):
        if left is UNKNOWN:
            return "UNKNOWN"
        truth = bool(left)
        return "TRUE" if (truth if op is RelOp.TRUTHY else not truth) \
            else "FALSE"

    if pred.right is None or op not in _NEEDS_RIGHT:
        return "UNKNOWN"                      
    right = resolve(pred.right, snapshot, bindings)
    if left is UNKNOWN or right is UNKNOWN:
        return "UNKNOWN"
    try:
        if op is RelOp.EQ:
            return "TRUE" if left == right else "FALSE"
        if op is RelOp.NE:
            return "TRUE" if left != right else "FALSE"
        if op is RelOp.IN:
            return "TRUE" if left in right else "FALSE"
        return "TRUE" if left not in right else "FALSE"
    except (TypeError, ValueError):           
        return "UNKNOWN"
def evaluate_relations(relations, snapshot: Mapping[str, Mapping],
                       bindings: Mapping[str, str],
                       enumeration_complete: Mapping[str, bool] | None = None
                       ) -> str:
    result = "TRUE"
    for pred in relations:
        v = evaluate_relation(pred, snapshot, bindings,
                              enumeration_complete)
        if v == "FALSE":
            return "FALSE"
        if v == "UNKNOWN":
            result = "UNKNOWN"
    return result
