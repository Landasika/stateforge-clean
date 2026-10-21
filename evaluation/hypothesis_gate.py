from __future__ import annotations
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Verdict(str, Enum):
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    UNCERTAIN = "UNCERTAIN"


class TriState(str, Enum):
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    UNCERTAIN = "UNCERTAIN"


class Mitigation(str, Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    UNCERTAIN = "UNCERTAIN"


@dataclass
class Hypothesis:
    hid: str                          
    candidate: str                    
    source: str                       
    sink: str                         
    known_flow: str                   
    known_guards: list[str]           
    endpoint: str                     
    gt_verdict: Verdict = Verdict.UNCERTAIN
    gt_category: str = ""
@dataclass
class VerificationResult:
    hid: str
    verdict: Verdict
    source_control: TriState
    sink_reachability: TriState
    security_mitigation: Mitigation
    evidence: list[str] = field(default_factory=list)
    rationale: str = ""
    missing_evidence: list[str] = field(default_factory=list)
    
    tokens_used: int = 0
    tool_calls: int = 0
    files_read: int = 0

def build_hypotheses_from_analyzer(app_dir: str | Path) -> list[Hypothesis]:
    
    from stateforge.analysis.analyzer import analyze
    from stateforge.core.model import AppModel

    model = analyze(Path(app_dir), "flask")
    hypotheses = []
    hid = 0

    for ep in model.endpoints:
        
        if ep.preconditions or ep.guards:
            hid += 1
            hypotheses.append(Hypothesis(
                hid=f"H{hid:03d}",
                candidate=f"Endpoint {ep.route} has state-dependent behavior",
                source=f"{ep.file}:{ep.func}",
                sink=f"{ep.route}",
                known_flow=" → ".join(
                    [p.var for p in ep.preconditions] or
                    [g.kind for g in ep.guards]),
                known_guards=[g.kind for g in ep.guards],
                endpoint=f"{ep.methods[0]} {ep.route}",
            ))

        
        for eff in ep.effects:
            hid += 1
            hypotheses.append(Hypothesis(
                hid=f"H{hid:03d}",
                candidate=f"Endpoint {ep.route} modifies state variable"
                           f" {eff.var}",
                source=f"{ep.file}:{ep.func}",
                sink=f"{eff.var} := {eff.value}",
                known_flow=f"{ep.route} → {eff.var}",
                known_guards=[g.kind for g in ep.guards],
                endpoint=f"{ep.methods[0]} {ep.route}",
            ))

    return hypotheses


def annotate_ground_truth(hypotheses: list[Hypothesis],
                          gt_file: str | Path) -> list[Hypothesis]:
    
    gt = json.loads(Path(gt_file).read_text(encoding="utf-8"))
    for h in hypotheses:
        for entry in gt.get("vulnerabilities", []):
            if (entry.get("endpoint", "") in h.endpoint
                    or entry.get("var", "") in h.candidate):
                h.gt_verdict = Verdict.CONFIRMED
                h.gt_category = entry.get("category", "")
                break
        
        if h.gt_verdict == Verdict.UNCERTAIN and h.known_guards:
            h.gt_verdict = Verdict.REJECTED
    return hypotheses

def hypothesis_to_prompt(h: Hypothesis) -> str:
    
    guards_text = "\n".join(f"  - {g}" for g in h.known_guards) or "  (none)"
    return f"""Verify the following security hypothesis.

## Hypothesis {h.hid}

**Candidate:** {h.candidate}

**Source:** {h.source}
**Sink:** {h.sink}
**Known flow:** {h.known_flow}
**Known guards:**
{guards_text}

**Endpoint:** {h.endpoint}

## Task

Determine whether this candidate constitutes a security-relevant condition
based on the available evidence. You may read source files and search for
additional context, but focus ONLY on verifying this hypothesis.

## Required Output (JSON only)

```json
{{
  "verdict": "CONFIRMED" | "REJECTED" | "UNCERTAIN",
  "source_control": "CONFIRMED" | "REJECTED" | "UNCERTAIN",
  "sink_reachability": "CONFIRMED" | "REJECTED" | "UNCERTAIN",
  "security_mitigation": "PRESENT" | "ABSENT" | "UNCERTAIN",
  "evidence": ["file:line description", ...],
  "rationale": "...",
  "missing_evidence": ["...", ...]
}}
```

Rules:
- Do NOT assign confidence scores.
- Evidence must cite specific file:line locations.
- If you cannot determine the answer, use UNCERTAIN.
- Verify ONLY this hypothesis. Do not audit the entire application.
"""


def hypothesis_to_bundled_prompt(hypotheses: list[Hypothesis]) -> str:
    
    items = []
    for h in hypotheses:
        guards = "; ".join(h.known_guards) or "none"
        items.append(
            f"- {h.hid}: {h.candidate} (source={h.source}, "
            f"sink={h.sink}, guards={guards})")
    listing = "\n".join(items)
    return f"""Verify the following {len(hypotheses)} security hypotheses.

{listing}

For each hypothesis, provide the JSON verdict in the same format as individual
verification. Process them in order. You may read source files as needed.
"""


def repository_audit_prompt(app_dir: str) -> str:
    
    return f"""Audit the web application in {app_dir} for security vulnerabilities.

Explore the codebase, identify potential security issues, and for each:
- State what you found
- Cite evidence (file:line)
- Classify as CONFIRMED/REJECTED/UNCERTAIN

Focus on: authentication bypass, authorization issues, business logic flaws,
injection vulnerabilities, and state manipulation.
"""


def score_hva(results: list[VerificationResult],
              hypotheses: list[Hypothesis]) -> dict:
    
    gt_map = {h.hid: h.gt_verdict for h in hypotheses}
    correct = total = completed = 0
    grounded = 0
    for r in results:
        h_gt = gt_map.get(r.hid)
        if h_gt is None:
            continue
        total += 1
        if r.verdict != Verdict.UNCERTAIN:
            completed += 1
            if r.verdict == h_gt:
                correct += 1
        if r.evidence and any(":" in e for e in r.evidence):
            grounded += 1

    return {
        "hva": round(correct / max(completed, 1), 4),
        "hcr": round(completed / max(total, 1), 4),
        "egr": round(grounded / max(total, 1), 4),
        "total": total,
        "completed": completed,
        "correct": correct,
        "grounded": grounded,
    }
