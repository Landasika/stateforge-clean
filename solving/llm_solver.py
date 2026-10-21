from __future__ import annotations
import json
import re
import time

from stateforge.solving.proposal import MutationProposal, ProposalStatus

SYSTEM_PROMPT = """You are a program analysis assistant. Given a Frontier Semantic Slice of a Python web application, your ONLY task is to determine if a mutation to the CURRENT REQUEST's input field can make the target guard condition more likely to be satisfied.

Rules:
1. You may ONLY propose a mutation to the input source specified in the slice (kind and key).
2. You may NOT modify program logic, source code, or propose multi-request sequences.
3. If the guard depends on persistent state (session, database, file system), return STATE_REQUIRED.
4. If the slice does not contain enough information to infer a candidate, return INSUFFICIENT_EVIDENCE.
5. If the transformation is too complex for you to reason about, return UNSUPPORTED.
6. You may NOT claim that a frontier has been crossed — only actual execution can determine that.

Respond ONLY with a JSON object (no markdown, no explanation outside JSON):
{
  "status": "PROPOSED" | "INSUFFICIENT_EVIDENCE" | "STATE_REQUIRED" | "UNSUPPORTED",
  "source_kind": "<must match slice input_source.kind>",
  "source_key": "<must match slice input_source.key>",
  "operation": "REPLACE",
  "proposed_value": <the value to set>,
  "rationale": "<brief explanation>",
  "confidence": <0.0-1.0>
}"""

USER_TEMPLATE = """## Frontier Semantic Slice

```json
{slice_json}
```

Analyze this slice and return a MutationProposal JSON."""


def _parse_llm_output(raw: str, frontier_id: str) -> MutationProposal:
    
    
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.M)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return MutationProposal(
            frontier_id=frontier_id, source_kind="", source_key="",
            operation="", proposed_value=None,
            status=ProposalStatus.INVALID_OUTPUT, raw_output=raw)
    status_str = obj.get("status", "")
    try:
        status = ProposalStatus(status_str)
    except ValueError:
        return MutationProposal(
            frontier_id=frontier_id,
            source_kind=obj.get("source_kind", ""),
            source_key=obj.get("source_key", ""),
            operation=obj.get("operation", ""),
            proposed_value=obj.get("proposed_value"),
            rationale=obj.get("rationale", ""),
            confidence=obj.get("confidence", 0.0),
            status=ProposalStatus.INVALID_OUTPUT, raw_output=raw)
    return MutationProposal(
        frontier_id=frontier_id,
        source_kind=obj.get("source_kind", ""),
        source_key=obj.get("source_key", ""),
        operation=obj.get("operation", "REPLACE"),
        proposed_value=obj.get("proposed_value"),
        rationale=obj.get("rationale", ""),
        confidence=obj.get("confidence", 0.0),
        status=status, raw_output=raw)


class LLMSemanticSolver:
    

    def __init__(self, provider):
        
        self.provider = provider
    def solve(self, slice_: dict) -> tuple[MutationProposal, float, dict]:
        
        slice_json = json.dumps(slice_, ensure_ascii=False, indent=1)
        t0 = time.monotonic()
        raw = self.provider.complete(SYSTEM_PROMPT,
                                     USER_TEMPLATE.format(
                                         slice_json=slice_json))
        latency = time.monotonic() - t0
        frontier_id = (f"{slice_['target_frontier']['edge'][0]}"
                       f"->{slice_['target_frontier']['edge'][1]}")
        proposal = _parse_llm_output(raw, frontier_id)
        return proposal, latency, {"raw_length": len(raw)}
