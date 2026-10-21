
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ProposalStatus(str, Enum):
    PROPOSED = "PROPOSED"                     
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"  
    STATE_REQUIRED = "STATE_REQUIRED"         
    UNSUPPORTED = "UNSUPPORTED"               
    INVALID_OUTPUT = "INVALID_OUTPUT"         


@dataclass
class MutationProposal:
    frontier_id: str
    source_kind: str                 
    source_key: str
    operation: str                   
    proposed_value: object
    rationale: str = ""
    confidence: float = 0.0
    status: ProposalStatus = ProposalStatus.PROPOSED
    raw_output: str = ""             
