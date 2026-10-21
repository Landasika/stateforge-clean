from __future__ import annotations
from dataclasses import dataclass

SUPPORTED_OPS = {"Eq", "NotEq", "Lt", "LtE", "Gt", "GtE"}
OP_SYMBOL = {"Eq": "==", "NotEq": "!=", "Lt": "<", "LtE": "<=", "Gt": ">",
             "GtE": ">=", "truthy": "truthy"}


@dataclass(frozen=True)
class BranchGuard:
    guard_id: str                 
    source_block: str             
    target_block: str             
    polarity: str                 
    expression: str               
    op: str                       
    lineno: int
    col_offset: int
    status: str = "ok"            
