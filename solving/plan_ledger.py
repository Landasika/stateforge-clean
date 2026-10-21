from __future__ import annotations
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from stateforge.solving.goal_checkpoint import GoalCheckpoint
from stateforge.solving.relational_planner import RelationalPlanCandidate
ACHIEVED = "VERIFIED_ACHIEVED"
NOT_ACHIEVED = "VERIFIED_NOT_ACHIEVED"
UNKNOWN = "UNKNOWN"


REASON_AUTH_MISMATCH = "auth-subject-mismatch"
REASON_OWNERSHIP_REFUTED = "identity-ownership-refuted"
REASON_STATE_REFUTED = "state-precondition-refuted"
REASON_RESOURCE_REFUTED = "resource-absent-refuted"
REASON_RELATION_REFUTED = "relation-refuted"
REASON_UNKNOWN_PENDING = "unknown-pending-observation"


@dataclass(frozen=True)
class PlanAttempt:
    
    attempt_id: str
    goal_id: str
    baseline_id: str                 
    plan_signature: str              
    binding: dict                    
    achievement_status: str          
    failed_predicate: str | None = None      
    unknown_reasons: tuple = ()
    evidence_refs: tuple = ()
    observation_point: str = ""
    http_status: object = None       
    exception: str | None = None
    reached_blocks: int | None = None        
    trace_target_covered: bool | None = None
    failure_reason: str | None = None        
    binding_conflicts: tuple = ()
    ts: float = 0.0
    def to_dict(self) -> dict:
        d = asdict(self)
        d["unknown_reasons"] = list(self.unknown_reasons)
        d["evidence_refs"] = list(self.evidence_refs)
        d["binding_conflicts"] = list(self.binding_conflicts)
        return d
    @classmethod
    def from_dict(cls, d: dict) -> "PlanAttempt":
        return cls(**{**d,
                     "unknown_reasons": tuple(d.get("unknown_reasons", ())),
                     "evidence_refs": tuple(d.get("evidence_refs", ())),
                     "binding_conflicts": tuple(
                         d.get("binding_conflicts", ()))})


class PlanLedger:
    

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.attempts: list[PlanAttempt] = []
        if self.path is not None and self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        self.attempts.append(
                            PlanAttempt.from_dict(json.loads(line)))
                    except (ValueError, TypeError):
                        continue                  

    def record(self, attempt: PlanAttempt) -> None:
        self.attempts.append(attempt)
        if self.path is not None:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(attempt.to_dict(),
                                        ensure_ascii=False) + "\n")
            except OSError:
                pass
    def find(self, *, goal_id: str, baseline_id: str,
             plan_signature: str, binding: dict) -> list[PlanAttempt]:
        want = json.dumps(binding, sort_keys=True, ensure_ascii=False)
        return [a for a in self.attempts
                if a.goal_id == goal_id and a.baseline_id == baseline_id
                and a.plan_signature == plan_signature
                and json.dumps(a.binding, sort_keys=True,
                               ensure_ascii=False) == want]

    def should_retry(self, *, goal_id: str, baseline_id: str,
                     plan_signature: str, binding: dict,
                     new_evidence: bool = False) -> tuple[bool, str]:
        
        prior = self.find(goal_id=goal_id, baseline_id=baseline_id,
                          plan_signature=plan_signature, binding=binding)
        if not prior:
            return True, "no-prior-attempt"
        if any(a.achievement_status == ACHIEVED for a in prior):
            return False, "achieved:目标已达成,无需重试"
        if new_evidence:
            return True, "new-evidence:出现新证据,允许同键重试"
        if all(a.achievement_status == UNKNOWN for a in prior):
            return False, ("unknown-pending:同键观测未定,待新证据"
                           "(不可观测≠失败,不触发重规划循环)")
        return False, ("failed-dedup:同键已反证——换绑定/基线/计划"
                       "签名后再试(修复建议见 failure_reason)")

    def failed_constraints(self, goal_id: str) -> list[str]:
        return [a.failed_predicate for a in self.attempts
                if a.goal_id == goal_id and a.achievement_status ==
                NOT_ACHIEVED and a.failed_predicate]




def attribute_failure(evaluation, http_status=None) -> str:
    
    if getattr(evaluation, "auth_binding_truth", None) == "FALSE":
        return REASON_AUTH_MISMATCH
    if getattr(evaluation, "relations_truth", None) == "FALSE":
        fc = getattr(evaluation, "failed_constraint", None) or ""
        if "user_id" in fc:
            return REASON_OWNERSHIP_REFUTED
        if "status" in fc:
            return REASON_STATE_REFUTED
        if "EXISTS" in fc:
            return REASON_RESOURCE_REFUTED
        return REASON_RELATION_REFUTED
    return REASON_UNKNOWN_PENDING
_REPAIRS = {
    REASON_AUTH_MISMATCH: [
        "rebind:以实际执行身份为 ?user 重建目标绑定(该身份自有资源)",
        "re-login:恢复目标身份后重放(注意 auth-rebinding 失效标注)",
    ],
    REASON_OWNERSHIP_REFUTED: [
        "rebind:?order 换为执行身份名下的资源(extract 重建,勿写死 ID)",
        "re-login:以资源属主身份重放整链(链内保持单一 login)",
    ],
    REASON_STATE_REFUTED: [
        "producer:确认状态生产者步在链内且参数满足观测值"
        "(如 pay amount 对照订单 total)",
    ],
    REASON_RESOURCE_REFUTED: [
        "resource:以 extract 重建 ?oid(资源缺席已反证,勿复用旧 ID)",
    ],
    REASON_RELATION_REFUTED: ["relation:检查该关系的生产者与绑定"],
    REASON_UNKNOWN_PENDING: [],           
}


def suggest_repair(reason: str) -> list[str]:
    
    return list(_REPAIRS.get(reason, ()))




def attempt_from_run(candidate: RelationalPlanCandidate, record,
                     evaluation, *, baseline_id: str,
                     binding: dict | None = None,
                     http_status=None, reached_blocks: int | None = None,
                     trace_target_covered: bool | None = None,
                     attempt_seq: int = 0) -> PlanAttempt:
    key_step = record.steps[-1] if record.steps else None
    witness = getattr(evaluation, "witness", None)
    binding = dict(binding or (dict(witness.binding)
                                if witness is not None else {}))
    return PlanAttempt(
        attempt_id=f"{candidate.signature[:8]}-{baseline_id}-{attempt_seq}",
        goal_id=candidate.goal_id,
        baseline_id=baseline_id,
        plan_signature=candidate.signature,
        binding={k: str(v) for k, v in binding.items()},
        achievement_status=evaluation.achievement_status,
        failed_predicate=evaluation.failed_constraint,
        unknown_reasons=tuple(evaluation.unknown_reasons),
        evidence_refs=tuple(evaluation.evidence_refs),
        observation_point=getattr(evaluation, "observation_point", ""),
        http_status=http_status if http_status is not None
        else (key_step.status if key_step else None),
        exception=(key_step.error if key_step else None),
        reached_blocks=reached_blocks,
        trace_target_covered=trace_target_covered,
        failure_reason=attribute_failure(
            evaluation, key_step.status if key_step else None),
        binding_conflicts=tuple(candidate.binding_conflicts),
        ts=time.time())


def checkpoint_from_verified(verified, source_file: str) -> GoalCheckpoint:
    
    if verified.achievement_status != ACHIEVED:
        raise ValueError(
            f"仅 VERIFIED_ACHIEVED 可建检查点,当前 "
            f"{verified.achievement_status}(候选/失败链保留原标记)")
    cand = verified.candidate
    return GoalCheckpoint(
        checkpoint_id=f"vp-{cand.signature}",
        target_block=cand.goal_id,
        source_file=str(source_file),
        goal_constraints=[],
        steps=[dict(s) for s in cand.steps],
        hits=["verified:" + str(verified.witness is not None)],
        step_evidence=[{"action": f"{s.get('method', 'GET')} "
                                  f"{s.get('path', '')}"}
                       for s in cand.steps])
