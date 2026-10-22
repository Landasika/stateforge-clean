from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
from pathlib import Path

from stateforge.core.ir import ProgramIR


_OPERATORS = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.Lt: "<",
    ast.LtE: "<=",
}

_ALLOWED_OPERANDS = (
    ast.Name,
    ast.Constant,
    ast.Attribute,
    ast.Subscript,
    ast.Slice,
    ast.BinOp,
    ast.UnaryOp,
    ast.Load,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
)


@dataclass(frozen=True)
class PredicateInfo:
    predicate_id: str
    block_id: str
    source_file: str
    line: int
    expression: str
    operator: str | None
    true_successor: str | None
    false_successor: str | None
    literal: str | None = None
    literal_side: str | None = None

    def outcome_for(self, successor: str | None) -> bool | None:
        if successor is None:
            return None
        if successor == self.true_successor:
            return True
        if successor == self.false_successor:
            return False
        return None


@dataclass(frozen=True)
class UnsupportedPredicate:
    block_id: str
    source_file: str
    line: int
    expression: str
    reason: str


@dataclass
class PredicateExtraction:
    predicates: list[PredicateInfo]
    unsupported: list[UnsupportedPredicate]

    def by_block(self) -> dict[str, PredicateInfo]:
        return {predicate.block_id: predicate for predicate in self.predicates}

    def by_id(self) -> dict[str, PredicateInfo]:
        return {predicate.predicate_id: predicate for predicate in self.predicates}

    def get(self, block_id: str) -> PredicateInfo | None:
        return self.by_block().get(block_id)

    def unsupported_for(self, block_id: str) -> UnsupportedPredicate | None:
        for item in self.unsupported:
            if item.block_id == block_id:
                return item
        return None


class PredicateExtractor:
    def __init__(self, ir: ProgramIR):
        self.ir = ir
        self._source_cache: dict[str, tuple[ast.Module | None, str | None]] = {}

    def extract(self, block_ids: list[str] | None = None) -> PredicateExtraction:
        if block_ids is None:
            block_ids = [block_id for block_id in self.ir.blocks
                         if self._is_branch_block(block_id)]
        predicates: list[PredicateInfo] = []
        unsupported: list[UnsupportedPredicate] = []
        for block_id in block_ids:
            item = self.extract_block(block_id)
            if isinstance(item, PredicateInfo):
                predicates.append(item)
            else:
                unsupported.append(item)
        return PredicateExtraction(predicates, unsupported)

    def extract_block(self, block_id: str) -> PredicateInfo | UnsupportedPredicate:
        block = self.ir.blocks.get(block_id)
        if block is None:
            return UnsupportedPredicate(block_id, "", 0, "", "missing_block")
        expression = self._test_expression(block)
        if expression is None:
            return UnsupportedPredicate(
                block_id, block.file, block.start_line, "", "missing_test")
        true_successor, false_successor, reason = self._successors(block_id)
        if reason is not None:
            return UnsupportedPredicate(
                block_id, block.file, block.start_line, expression, reason)
        node = self._test_node(block, expression)
        if isinstance(node, UnsupportedPredicate):
            return node
        test = self._test_of(node)
        if test is None:
            return UnsupportedPredicate(
                block_id, block.file, block.start_line, expression,
                "missing_test")
        supported, detail = self._classify(test)
        if not supported:
            return UnsupportedPredicate(
                block_id, block.file, block.start_line, expression, detail)
        operator = _OPERATORS[type(test.ops[0])]
        literal, literal_side = self._literal(test)
        predicate_id = self._predicate_id(block_id, expression)
        return PredicateInfo(
            predicate_id=predicate_id,
            block_id=block_id,
            source_file=block.file,
            line=block.start_line,
            expression=expression,
            operator=operator,
            true_successor=true_successor,
            false_successor=false_successor,
            literal=literal,
            literal_side=literal_side,
        )

    def _is_branch_block(self, block_id: str) -> bool:
        block = self.ir.blocks[block_id]
        if block.kind == "branch":
            return True
        return any(edge.kind in ("true", "false")
                   for edge in self.ir.outgoing(block_id))

    @staticmethod
    def _test_expression(block) -> str | None:
        for statement in block.statements:
            if statement.startswith("<test> "):
                return statement[len("<test> "):]
        return None

    def _successors(self, block_id: str
                    ) -> tuple[str | None, str | None, str | None]:
        true_targets = []
        false_targets = []
        for edge in self.ir.outgoing(block_id):
            if edge.kind == "true":
                true_targets.append(edge.dst)
            elif edge.kind == "false":
                false_targets.append(edge.dst)
        if len(set(true_targets)) > 1 or len(set(false_targets)) > 1:
            return None, None, "ambiguous_successors"
        true_successor = true_targets[0] if true_targets else None
        false_successor = false_targets[0] if false_targets else None
        if true_successor is None and false_successor is None:
            return None, None, "missing_branch_edges"
        return true_successor, false_successor, None

    def _test_node(self, block, expression: str):
        path = Path(block.file)
        key = str(path)
        if key not in self._source_cache:
            try:
                text = path.read_text(encoding="utf-8")
                self._source_cache[key] = (
                    ast.parse(text, filename=key), None)
            except OSError:
                self._source_cache[key] = (None, "source_unavailable")
            except SyntaxError:
                self._source_cache[key] = (None, "source_syntax_error")
        tree, error = self._source_cache[key]
        if tree is None:
            return UnsupportedPredicate(
                block.id, block.file, block.start_line, expression,
                error or "source_unavailable")
        for node in ast.walk(tree):
            test = self._test_of(node)
            if test is None:
                continue
            if getattr(test, "lineno", None) != block.start_line:
                continue
            if ast.unparse(test) == expression:
                return node
        return UnsupportedPredicate(
            block.id, block.file, block.start_line, expression,
            "source_mismatch")

    @staticmethod
    def _test_of(node) -> ast.expr | None:
        if isinstance(node, (ast.If, ast.While)):
            return node.test
        if isinstance(node, (ast.For, ast.AsyncFor)):
            return node.iter
        return None

    @staticmethod
    def _classify(test: ast.expr) -> tuple[bool, str | None]:
        if isinstance(test, ast.Compare):
            if len(test.ops) > 1 or len(test.comparators) > 1:
                return False, "chained_comparison"
            if type(test.ops[0]) not in _OPERATORS:
                return False, "unsupported_operator"
            for operand in (test.left, test.comparators[0]):
                if not PredicateExtractor._supported_operand(operand):
                    return False, "unsupported_operand"
            return True, None
        if isinstance(test, ast.BoolOp):
            return False, "boolean_expression"
        if isinstance(test, ast.Call):
            return False, "function_call"
        if isinstance(test, ast.UnaryOp):
            return False, "unary_expression"
        return False, "unsupported_expression"

    @staticmethod
    def _supported_operand(node: ast.expr) -> bool:
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp,
                            ast.GeneratorExp, ast.Lambda, ast.Call,
                            ast.BoolOp, ast.IfExp, ast.Compare)):
            return False
        if isinstance(node, ast.Constant):
            return True
        if isinstance(node, ast.Name):
            return True
        if isinstance(node, ast.Attribute):
            return PredicateExtractor._supported_operand(node.value)
        if isinstance(node, ast.Subscript):
            return (PredicateExtractor._supported_operand(node.value)
                    and PredicateExtractor._supported_operand(node.slice))
        if isinstance(node, ast.Slice):
            return all(part is None or PredicateExtractor._supported_operand(part)
                       for part in (node.lower, node.upper, node.step))
        if isinstance(node, ast.BinOp):
            return (PredicateExtractor._supported_operand(node.left)
                    and PredicateExtractor._supported_operand(node.right))
        if isinstance(node, ast.UnaryOp):
            return PredicateExtractor._supported_operand(node.operand)
        return isinstance(node, _ALLOWED_OPERANDS)

    @staticmethod
    def _literal(test: ast.Compare) -> tuple[str | None, str | None]:
        if isinstance(test.left, ast.Constant):
            return ast.unparse(test.left), "left"
        right = test.comparators[0]
        if isinstance(right, ast.Constant):
            return ast.unparse(right), "right"
        return None, None

    def _predicate_id(self, block_id: str, expression: str) -> str:
        digest = hashlib.sha256(
            f"{block_id}|{expression}".encode("utf-8")).hexdigest()[:16]
        predicate_id = f"pred_{digest}"
        while predicate_id in self.ir.blocks:
            predicate_id = f"{predicate_id}_p"
        return predicate_id


def extract_predicates(ir: ProgramIR,
                       block_ids: list[str] | None = None
                       ) -> PredicateExtraction:
    return PredicateExtractor(ir).extract(block_ids)


def extract_predicate(ir: ProgramIR,
                      block_id: str) -> PredicateInfo | UnsupportedPredicate:
    return PredicateExtractor(ir).extract_block(block_id)
