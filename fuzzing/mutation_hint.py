
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MutationHint:
    frontier_id: str             
    guard_id: str                
    source_kind: str             
    source_key: str
    current_value: object         
    target_value: object          
    operator: str                 
    desired_polarity: str         
    reason: str                   
    confidence: float = 1.0
    transform_chain: tuple = ()   
