"""Optimiser (Area 3).

Works on the intermediate code and makes it shorter without changing what the
program does. Four ideas are used, repeated until nothing changes:

1. Constant folding: `3 * 4` is worked out now, not when the program runs.
2. Constant and copy propagation: if `x` is known to be 5, use 5 in its place.
3. Dead code removal: delete instructions whose result is never used, and
   delete code that can never be reached.
4. Jump clean-up: remove jumps to the very next line and labels nobody uses.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from src.ir import (
    BinOp, CallInstr, FloatConst, Instr, IntConst, IRFunction, IRProgram, Jump, JumpIfFalse,
    JumpIfTrue, Label, Move, Operand, ReadInstr, ReturnInstr, UnOp, Var, WriteInstr,
)

INT_MIN = -(2 ** 63)
INT_MAX = 2 ** 63 - 1


def wrap(value: int) -> int:
    """Keep a number inside 64 bits the way the processor does."""
    return (value + 2 ** 63) % 2 ** 64 - 2 ** 63


def trunc_div(a: int, b: int) -> int:
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def trunc_mod(a: int, b: int) -> int:
    return a - b * trunc_div(a, b)


def fold_binary(op: str, a: int, b: int) -> int | None:
    """Return the answer, or None when it cannot be worked out safely."""
    if op == "+":
        return wrap(a + b)
    if op == "-":
        return wrap(a - b)
    if op == "*":
        return wrap(a * b)
    if op in ("/", "%"):
        if b == 0:
            return None  # leave it, so the program reports the error when it runs
        return wrap(trunc_div(a, b)) if op == "/" else trunc_mod(a, b)
    if op == "<":
        return int(a < b)
    if op == "<=":
        return int(a <= b)
    if op == ">":
        return int(a > b)
    if op == ">=":
        return int(a >= b)
    if op == "==":
        return int(a == b)
    if op == "!=":
        return int(a != b)
    return None


def fold_float(op: str, a: float, b: float) -> Operand | None:
    """Work out a calculation on two decimal numbers (operators end in a dot)."""
    if op == "+.":
        return FloatConst(a + b)
    if op == "-.":
        return FloatConst(a - b)
    if op == "*.":
        return FloatConst(a * b)
    if op == "/.":
        return FloatConst(a / b) if b != 0 else None
    table = {"<.": a < b, "<=.": a <= b, ">.": a > b, ">=.": a >= b, "==.": a == b, "!=.": a != b}
    return IntConst(int(table[op])) if op in table else None


@dataclass
class Stats:
    before: int
    after: int

    @property
    def removed(self) -> int:
        return self.before - self.after


# ------------------------------------------------------- pass 1: propagation

def propagate(body: list[Instr]) -> list[Instr]:
    """Fold constants and pass known values forward inside straight-line code."""
    known: dict[str, Operand] = {}
    out: list[Instr] = []

    def value(op: Operand) -> Operand:
        return known.get(op.name, op) if isinstance(op, Var) else op

    def forget(name: str) -> None:
        known.pop(name, None)
        for key in [k for k, v in known.items() if isinstance(v, Var) and v.name == name]:
            del known[key]

    for instr in body:
        if isinstance(instr, Label):
            known.clear()
            out.append(instr)
        elif isinstance(instr, Move):
            src = value(instr.src)
            forget(instr.dst.name)
            if src != instr.dst:
                known[instr.dst.name] = src
            out.append(Move(instr.dst, src))
        elif isinstance(instr, BinOp):
            left, right = value(instr.left), value(instr.right)
            forget(instr.dst.name)
            result = simplify_binary(instr.op, left, right)
            if result is not None:
                known[instr.dst.name] = result
                out.append(Move(instr.dst, result))
            else:
                out.append(BinOp(instr.dst, instr.op, left, right))
        elif isinstance(instr, UnOp):
            operand = value(instr.operand)
            forget(instr.dst.name)
            folded_op: Operand | None = None
            if isinstance(operand, IntConst):
                if instr.op == "neg":
                    folded_op = IntConst(wrap(-operand.value))
                elif instr.op == "not":
                    folded_op = IntConst(int(operand.value == 0))
                elif instr.op == "itof":
                    folded_op = FloatConst(float(operand.value))
            elif isinstance(operand, FloatConst) and instr.op == "fneg":
                folded_op = FloatConst(-operand.value)
            if folded_op is not None:
                known[instr.dst.name] = folded_op
                out.append(Move(instr.dst, folded_op))
            else:
                out.append(UnOp(instr.dst, instr.op, operand))
        elif isinstance(instr, JumpIfFalse):
            cond = value(instr.cond)
            if isinstance(cond, IntConst):
                if cond.value == 0:
                    out.append(Jump(instr.target))
            else:
                out.append(JumpIfFalse(cond, instr.target))
        elif isinstance(instr, JumpIfTrue):
            cond = value(instr.cond)
            if isinstance(cond, IntConst):
                if cond.value != 0:
                    out.append(Jump(instr.target))
            else:
                out.append(JumpIfTrue(cond, instr.target))
        elif isinstance(instr, CallInstr):
            args = [value(a) for a in instr.args]
            if instr.dst is not None:
                forget(instr.dst.name)
            out.append(CallInstr(instr.dst, instr.name, args))
        elif isinstance(instr, ReturnInstr):
            out.append(ReturnInstr(value(instr.value) if instr.value is not None else None))
        elif isinstance(instr, WriteInstr):
            out.append(WriteInstr(value(instr.value), instr.ty))
        elif isinstance(instr, ReadInstr):
            forget(instr.dst.name)
            out.append(instr)
        else:
            out.append(instr)
    return out


def simplify_binary(op: str, left: Operand, right: Operand) -> Operand | None:
    """Fold two constants, or apply a simple rule such as x + 0 = x."""
    if isinstance(left, IntConst) and isinstance(right, IntConst):
        folded = fold_binary(op, left.value, right.value)
        return IntConst(folded) if folded is not None else None
    if isinstance(left, FloatConst) and isinstance(right, FloatConst):
        return fold_float(op, left.value, right.value)
    if op == "+":
        if right == IntConst(0):
            return left
        if left == IntConst(0):
            return right
    if op == "-" and right == IntConst(0):
        return left
    if op == "*":
        if right == IntConst(1):
            return left
        if left == IntConst(1):
            return right
        if IntConst(0) in (left, right):
            return IntConst(0)
    if op == "/" and right == IntConst(1):
        return left
    return None


# ----------------------------------------------------- pass 2: dead code

def remove_unreachable(body: list[Instr]) -> list[Instr]:
    """Delete instructions that follow a jump or return until the next label."""
    out: list[Instr] = []
    dead = False
    for instr in body:
        if isinstance(instr, Label):
            dead = False
        if dead:
            continue
        out.append(instr)
        if isinstance(instr, (Jump, ReturnInstr)):
            dead = True
    return out


def used_names(body: list[Instr]) -> set[str]:
    used: set[str] = set()

    def use(op: Operand | None) -> None:
        if isinstance(op, Var):
            used.add(op.name)

    for instr in body:
        if isinstance(instr, Move):
            use(instr.src)
        elif isinstance(instr, BinOp):
            use(instr.left)
            use(instr.right)
        elif isinstance(instr, UnOp):
            use(instr.operand)
        elif isinstance(instr, (JumpIfFalse, JumpIfTrue)):
            use(instr.cond)
        elif isinstance(instr, CallInstr):
            for a in instr.args:
                use(a)
        elif isinstance(instr, ReturnInstr):
            use(instr.value)
        elif isinstance(instr, WriteInstr):
            use(instr.value)
    return used


def remove_dead_stores(body: list[Instr]) -> list[Instr]:
    """Delete assignments to names that are never read."""
    used = used_names(body)
    out: list[Instr] = []
    for instr in body:
        if isinstance(instr, (Move, UnOp)) and instr.dst.name not in used:
            continue
        if isinstance(instr, BinOp) and instr.dst.name not in used:
            divides = instr.op in ("/", "%", "/.")
            safe = isinstance(instr.right, (IntConst, FloatConst)) and instr.right.value != 0
            if not divides or safe:
                continue
        if isinstance(instr, CallInstr) and instr.dst is not None and instr.dst.name not in used:
            out.append(replace(instr, dst=None))
            continue
        out.append(instr)
    return out


# ------------------------------------------------------ pass 3: jump clean-up

def clean_jumps(body: list[Instr]) -> list[Instr]:
    out = list(body)
    changed = True
    while changed:
        changed = False
        for i, instr in enumerate(out):
            if isinstance(instr, Jump):
                j = i + 1
                while j < len(out) and isinstance(out[j], Label):
                    if out[j].name == instr.target:  # type: ignore[union-attr]
                        del out[i]
                        changed = True
                        break
                    j += 1
                if changed:
                    break
        used = {i.target for i in out if isinstance(i, (Jump, JumpIfFalse, JumpIfTrue))}
        kept = [i for i in out if not (isinstance(i, Label) and i.name not in used)]
        if len(kept) != len(out):
            out = kept
            changed = True
    return out


# ------------------------------------------------------------------ driver

def optimise_function(func: IRFunction) -> IRFunction:
    body = func.body
    for _ in range(20):
        new = clean_jumps(remove_dead_stores(remove_unreachable(propagate(body))))
        if new == body:
            break
        body = new
    return IRFunction(func.name, func.params, func.ret_type, body)


def optimise(program: IRProgram) -> tuple[IRProgram, Stats]:
    before = program.instruction_count()
    result = IRProgram([optimise_function(f) for f in program.functions], program.strings)
    return result, Stats(before, result.instruction_count())
