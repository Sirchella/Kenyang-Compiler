"""Syntax tree nodes produced by the parser (Area 2).

Every node remembers the line and column where it starts, so later stages
can point at the exact place when they report an error.
Expression nodes also carry `ty`, which the semantic analyser fills in.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from typing import Optional


@dataclass(kw_only=True)
class Node:
    line: int = 0
    column: int = 0


# ---------------------------------------------------------------- expressions

@dataclass(kw_only=True)
class Expr(Node):
    ty: Optional[str] = None


@dataclass
class IntLit(Expr):
    value: int


@dataclass
class FloatLit(Expr):
    value: float


@dataclass
class BoolLit(Expr):
    value: bool


@dataclass
class StrLit(Expr):
    value: str


@dataclass
class Name(Expr):
    name: str
    unique: str = ""  # set by the semantic analyser


@dataclass
class Unary(Expr):
    op: str  # "neg" or "not"
    operand: Expr


@dataclass
class Binary(Expr):
    op: str  # + - * / % < <= > >= == != and or
    left: Expr
    right: Expr


@dataclass
class Call(Expr):
    name: str
    args: list[Expr]


# ----------------------------------------------------------------- statements

@dataclass
class Stmt(Node):
    pass


@dataclass
class VarDecl(Stmt):
    type_name: Optional[str]  # None when the keyword for "var" was used
    name: str
    init: Optional[Expr]
    ty: Optional[str] = None
    unique: str = ""


@dataclass
class Assign(Stmt):
    name: str
    value: Expr
    unique: str = ""
    ty: Optional[str] = None  # type of the variable, set by the semantic analyser


@dataclass
class Block(Stmt):
    stmts: list[Stmt]


@dataclass
class If(Stmt):
    cond: Expr
    then: Block
    otherwise: Optional[Stmt]  # a Block, another If (elif), or None


@dataclass
class While(Stmt):
    cond: Expr
    body: Block


@dataclass
class For(Stmt):
    init: Optional[Stmt]
    cond: Optional[Expr]
    step: Optional[Stmt]
    body: Block


@dataclass
class Return(Stmt):
    value: Optional[Expr]


@dataclass
class Write(Stmt):
    value: Expr


@dataclass
class Read(Stmt):
    name: str
    unique: str = ""


@dataclass
class ExprStmt(Stmt):
    expr: Expr


@dataclass
class Break(Stmt):
    pass


@dataclass
class Continue(Stmt):
    pass


# ------------------------------------------------------------------ top level

@dataclass
class Param(Node):
    type_name: str
    name: str
    ty: Optional[str] = None
    unique: str = ""


@dataclass
class FuncDecl(Node):
    name: str
    params: list[Param]
    ret_type: str
    body: Block


@dataclass
class Program(Node):
    functions: list[FuncDecl] = field(default_factory=list)


# ------------------------------------------------------------------- printing

def dump(node: object, indent: int = 0) -> str:
    """Return the tree as indented text, for the `--emit ast` option."""
    pad = "  " * indent
    if isinstance(node, list):
        return "\n".join(dump(item, indent) for item in node)
    if not is_dataclass(node):
        return f"{pad}{node!r}"

    simple: list[str] = []
    children: list[tuple[str, object]] = []
    for f in fields(node):
        if f.name in ("line", "column", "unique"):
            continue
        value = getattr(node, f.name)
        if f.name == "ty":
            if value is not None:
                simple.append(f"type={value}")
            continue
        if is_dataclass(value) or (isinstance(value, list) and value and is_dataclass(value[0])):
            children.append((f.name, value))
        elif value is not None and value != []:
            simple.append(f"{f.name}={value!r}")

    head = f"{pad}{type(node).__name__}"
    if simple:
        head += "(" + ", ".join(simple) + ")"
    head += f"  @{node.line}:{node.column}"  # type: ignore[attr-defined]
    out = [head]
    for name, value in children:
        out.append(f"{pad}  .{name}:")
        out.append(dump(value, indent + 2))
    return "\n".join(out)
