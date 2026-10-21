from __future__ import annotations
import re
from dataclasses import dataclass

from stateforge.solving.proposal import MutationProposal, ProposalStatus

_ALLOWED_OPS = {"REPLACE"}
_KIND_TO_ATTR = {"QUERY": "args", "FORM": "form", "JSON": "json",
                 "HEADER": "headers", "COOKIE": "cookies"}


@dataclass
class ValidationResult:
    valid: bool
    rejection_reason: str = ""


def validate(proposal: MutationProposal, slice_: dict) -> ValidationResult:
    tf = slice_["target_frontier"]
    src = slice_["input_source"]

    if proposal.frontier_id != f"{tf['edge'][0]}->{tf['edge'][1]}":
        return ValidationResult(False, "FRONTIER_MISMATCH")

    if src["status"] == "ok":
        
        if proposal.source_kind != src["kind"]:
            return ValidationResult(False, "SOURCE_KIND_MISMATCH")
        if proposal.source_key != src["key"]:
            return ValidationResult(False, "SOURCE_KEY_MISMATCH")
    else:
        
        
        
        
        
        key = re.escape(proposal.source_key)
        pattern = "['\\\"]" + key + "['\\\"]"    
        dataflow_text = " ".join(slice_.get("backward_dataflow", []))
        if not re.search(pattern, dataflow_text):
            return ValidationResult(False,
                                    "SOURCE_NOT_IN_DATAFLOW_SLICE")
    if proposal.operation not in _ALLOWED_OPS:
        return ValidationResult(False, "OPERATION_NOT_ALLOWED")
    try:
        str(proposal.proposed_value)
    except Exception:                          
        return ValidationResult(False, "VALUE_NOT_SERIALIZABLE")
    for fm in slice_.get("failed_mutations", []):
        if str(fm.get("input_id")) == str(proposal.proposed_value):
            return ValidationResult(False, "DUPLICATES_FAILED_MUTATION")
    return ValidationResult(True)
