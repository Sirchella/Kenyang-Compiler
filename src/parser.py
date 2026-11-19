"""Recursive descent parser for the Lower Kenyang language (Area 2).

It reads the token list from the lexer and builds the syntax tree.
When it finds a mistake it records an error, skips to a safe place
(the next `;` or `}`) and keeps going, so one run reports many mistakes.
"""

from __future__ import annotations

from src import ast_nodes as ast
from src.diagnostics import Diagnostic
from src.lexer import Token

TYPE_TOKENS = {
    "KW_INT": "int",
    "KW_BOOL": "bool",
    "KW_STRING": "string",
    "KW_VOID": "void",
    "KW_FLOAT": "float",
    "KW_CHAR": "char",
}

ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"', "r": "\r", "0": "\0"}

EQUALITY_OPS = {"EQ": "==", "NEQ": "!="}
RELATION_OPS = {"LT": "<", "LE": "<=", "GT": ">", "GE": ">="}
ADD_OPS = {"PLUS": "+", "MINUS": "-"}
MUL_OPS = {"STAR": "*", "SLASH": "/", "PERCENT": "%"}

STATEMENT_STARTS = {
    "KW_IF", "KW_WHILE", "KW_FOR", "KW_RETURN", "KW_WRITE", "KW_READ",
    "KW_BREAK", "KW_CONTINUE", "KW_VAR", *TYPE_TOKENS,
}


class ParseError(Exception):
    def __init__(self, message: str, token: Token, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.token = token
        self.hint = hint


def decode_string(raw: str) -> str:
    """Turn the text of a string literal (with quotes) into its real value."""
    body = raw[1:-1]
    out: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body):
            out.append(ESCAPES.get(body[i + 1], body[i + 1]))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


class Parser:
    def __init__(self, tokens: list[Token], source: str = "") -> None:
        self.tokens = tokens
        self.pos = 0
        self.source_lines = source.splitlines() or [""]
        self.errors: list[Diagnostic] = []
        last = tokens[-1] if tokens else None
        line = last.end_line if last else 1
        col = last.end_column if last else 1
        self.eof = Token("EOF", "end of file", line, col, line, col)

    # ------------------------------------------------------------ token tools

    @property
    def tok(self) -> Token:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else self.eof

    def at(self, *types: str) -> bool:
        return self.tok.type in types

    def advance(self) -> Token:
        token = self.tok
        if self.pos < len(self.tokens):
            self.pos += 1
        return token

    def expect(self, type_: str, what: str, hint: str | None = None) -> Token:
        if self.tok.type != type_:
            found = self.tok.lexeme if self.tok.type != "EOF" else "end of file"
            where = self.tok
            if type_ == "SEMI" and self.pos > 0:
                # a missing ';' is best shown right after the previous token
                prev = self.tokens[self.pos - 1]
                where = Token(where.type, where.lexeme, prev.end_line, prev.end_column,
                              prev.end_line, prev.end_column)
            raise ParseError(f"expected {what} but found '{found}'", where, hint)
        return self.advance()

    def report(self, err: ParseError) -> None:
        tok = err.token
        line_text = self.source_lines[tok.line - 1] if 1 <= tok.line <= len(self.source_lines) else ""
        self.errors.append(
            Diagnostic("ParseError", err.message, tok.line, tok.column, line_text, err.hint)
        )

    def synchronise(self) -> None:
        """Skip forward to a place where a new statement can start."""
        while not self.at("EOF"):
            if self.at("SEMI"):
                self.advance()
                return
            if self.at("RBRACE", "LBRACE", "KW_FUNC") or self.tok.type in STATEMENT_STARTS:
                return
            self.advance()

    # --------------------------------------------------------------- program

    def parse_program(self) -> ast.Program:
        program = ast.Program(line=1, column=1)
        while not self.at("EOF"):
            if self.at("KW_FUNC"):
                try:
                    program.functions.append(self.parse_function())
                except ParseError as err:
                    self.report(err)
                    self.skip_to_next_function()
            else:
                self.report(ParseError(
                    f"unexpected '{self.tok.lexeme}' outside a function",
                    self.tok,
                    "All code must be inside a function. Put it in main.",
                ))
                self.skip_to_next_function()
        return program

    def skip_to_next_function(self) -> None:
        self.advance()
        while not self.at("EOF") and not self.at("KW_FUNC"):
            self.advance()

    def parse_type(self) -> str:
        if self.tok.type not in TYPE_TOKENS:
            raise ParseError(f"expected a type but found '{self.tok.lexeme}'", self.tok)
        return TYPE_TOKENS[self.advance().type]

    def parse_function(self) -> ast.FuncDecl:
        start = self.expect("KW_FUNC", "the function keyword")
        name = self.expect("IDENT", "a function name")
        self.expect("LPAREN", "'(' after the function name")
        params: list[ast.Param] = []
        if not self.at("RPAREN"):
            while True:
                type_tok = self.tok
                type_name = self.parse_type()
                pname = self.expect("IDENT", "a parameter name")
                params.append(ast.Param(type_name, pname.lexeme, line=type_tok.line, column=type_tok.column))
                if self.at("COMMA"):
                    self.advance()
                else:
                    break
        self.expect("RPAREN", "')' after the parameters")
        ret_type = "void"
        if self.at("COLON"):
            self.advance()
            ret_type = self.parse_type()
        body = self.parse_block()
        return ast.FuncDecl(name.lexeme, params, ret_type, body, line=start.line, column=start.column)

    # ------------------------------------------------------------ statements

    def parse_block(self) -> ast.Block:
        open_tok = self.expect("LBRACE", "'{' to start a block")
        stmts: list[ast.Stmt] = []
        while not self.at("RBRACE", "EOF"):
            before = self.pos
            try:
                stmts.append(self.parse_statement())
            except ParseError as err:
                self.report(err)
                self.synchronise()
                if self.pos == before:
                    self.advance()
        if self.at("EOF"):
            raise ParseError(
                f"missing '}}' for the block opened on line {open_tok.line}",
                self.tok,
                "Add a closing '}'.",
            )
        self.advance()
        return ast.Block(stmts, line=open_tok.line, column=open_tok.column)

    def parse_statement(self) -> ast.Stmt:
        t = self.tok
        kind = t.type
        if kind in TYPE_TOKENS or kind == "KW_VAR":
            return self.parse_var_decl(need_semi=True)
        if kind == "KW_IF":
            self.advance()
            return self.parse_if_rest(t)
        if kind == "KW_WHILE":
            return self.parse_while()
        if kind == "KW_FOR":
            return self.parse_for()
        if kind == "KW_RETURN":
            self.advance()
            value = None if self.at("SEMI") else self.parse_expr()
            self.expect("SEMI", "';' after return")
            return ast.Return(value, line=t.line, column=t.column)
        if kind == "KW_WRITE":
            self.advance()
            self.expect("LPAREN", "'(' after the write keyword")
            value = self.parse_expr()
            self.expect("RPAREN", "')' after the value")
            self.expect("SEMI", "';' after the write statement")
            return ast.Write(value, line=t.line, column=t.column)
        if kind == "KW_READ":
            self.advance()
            self.expect("LPAREN", "'(' after the read keyword")
            target = self.expect("IDENT", "a variable name to read into")
            self.expect("RPAREN", "')' after the variable name")
            self.expect("SEMI", "';' after the read statement")
            return ast.Read(target.lexeme, line=t.line, column=t.column)
        if kind == "KW_BREAK":
            self.advance()
            self.expect("SEMI", "';' after break")
            return ast.Break(line=t.line, column=t.column)
        if kind == "KW_CONTINUE":
            self.advance()
            self.expect("SEMI", "';' after continue")
            return ast.Continue(line=t.line, column=t.column)
        if kind == "LBRACE":
            return self.parse_block()
        if kind == "IDENT" and self.peek_type(1) == "ASSIGN":
            return self.parse_assignment(need_semi=True)

        expr = self.parse_expr()
        if not isinstance(expr, ast.Call):
            raise ParseError(
                "this expression does nothing as a statement",
                t,
                "Only a function call can be used as a statement.",
            )
        self.expect("SEMI", "';' after the statement")
        return ast.ExprStmt(expr, line=t.line, column=t.column)

    def peek_type(self, offset: int) -> str:
        index = self.pos + offset
        return self.tokens[index].type if index < len(self.tokens) else "EOF"

    def parse_var_decl(self, need_semi: bool) -> ast.VarDecl:
        t = self.advance()
        type_name = None if t.type == "KW_VAR" else TYPE_TOKENS[t.type]
        name = self.expect("IDENT", "a variable name")
        init = None
        if self.at("ASSIGN"):
            self.advance()
            init = self.parse_expr()
        if need_semi:
            self.expect("SEMI", "';' after the declaration")
        return ast.VarDecl(type_name, name.lexeme, init, line=t.line, column=t.column)

    def parse_assignment(self, need_semi: bool) -> ast.Assign:
        name = self.expect("IDENT", "a variable name")
        self.expect("ASSIGN", "'='")
        value = self.parse_expr()
        if need_semi:
            self.expect("SEMI", "';' after the assignment")
        return ast.Assign(name.lexeme, value, line=name.line, column=name.column)

    def parse_condition(self, what: str) -> ast.Expr:
        self.expect("LPAREN", f"'(' after {what}")
        cond = self.parse_expr()
        self.expect("RPAREN", "')' after the condition")
        return cond

    def parse_if_rest(self, start: Token) -> ast.If:
        cond = self.parse_condition("the if keyword")
        then = self.parse_block()
        otherwise: ast.Stmt | None = None
        if self.at("KW_ELIF"):
            elif_tok = self.advance()
            otherwise = self.parse_if_rest(elif_tok)
        elif self.at("KW_ELSE"):
            self.advance()
            otherwise = self.parse_block()
        return ast.If(cond, then, otherwise, line=start.line, column=start.column)

    def parse_while(self) -> ast.While:
        t = self.advance()
        cond = self.parse_condition("the while keyword")
        body = self.parse_block()
        return ast.While(cond, body, line=t.line, column=t.column)

    def parse_for(self) -> ast.For:
        t = self.advance()
        self.expect("LPAREN", "'(' after the for keyword")
        init: ast.Stmt | None = None
        if not self.at("SEMI"):
            if self.tok.type in TYPE_TOKENS or self.at("KW_VAR"):
                init = self.parse_var_decl(need_semi=False)
            else:
                init = self.parse_assignment(need_semi=False)
        self.expect("SEMI", "';' after the loop start")
        cond = None if self.at("SEMI") else self.parse_expr()
        self.expect("SEMI", "';' after the loop condition")
        step = None if self.at("RPAREN") else self.parse_assignment(need_semi=False)
        self.expect("RPAREN", "')' after the loop step")
        body = self.parse_block()
        return ast.For(init, cond, step, body, line=t.line, column=t.column)

    # ----------------------------------------------------------- expressions

    def parse_expr(self) -> ast.Expr:
        return self.parse_or()

    def parse_or(self) -> ast.Expr:
        left = self.parse_and()
        while self.at("KW_OR"):
            op = self.advance()
            left = ast.Binary("or", left, self.parse_and(), line=op.line, column=op.column)
        return left

    def parse_and(self) -> ast.Expr:
        left = self.parse_equality()
        while self.at("KW_AND"):
            op = self.advance()
            left = ast.Binary("and", left, self.parse_equality(), line=op.line, column=op.column)
        return left

    def parse_equality(self) -> ast.Expr:
        left = self.parse_relation()
        while self.tok.type in EQUALITY_OPS:
            op = self.advance()
            left = ast.Binary(EQUALITY_OPS[op.type], left, self.parse_relation(), line=op.line, column=op.column)
        return left

    def parse_relation(self) -> ast.Expr:
        left = self.parse_additive()
        while self.tok.type in RELATION_OPS:
            op = self.advance()
            left = ast.Binary(RELATION_OPS[op.type], left, self.parse_additive(), line=op.line, column=op.column)
        return left

    def parse_additive(self) -> ast.Expr:
        left = self.parse_term()
        while self.tok.type in ADD_OPS:
            op = self.advance()
            left = ast.Binary(ADD_OPS[op.type], left, self.parse_term(), line=op.line, column=op.column)
        return left

    def parse_term(self) -> ast.Expr:
        left = self.parse_unary()
        while self.tok.type in MUL_OPS:
            op = self.advance()
            left = ast.Binary(MUL_OPS[op.type], left, self.parse_unary(), line=op.line, column=op.column)
        return left

    def parse_unary(self) -> ast.Expr:
        if self.at("MINUS"):
            op = self.advance()
            return ast.Unary("neg", self.parse_unary(), line=op.line, column=op.column)
        if self.at("KW_NOT"):
            op = self.advance()
            return ast.Unary("not", self.parse_unary(), line=op.line, column=op.column)
        return self.parse_primary()

    def parse_primary(self) -> ast.Expr:
        t = self.tok
        if t.type == "INT_LIT":
            self.advance()
            return ast.IntLit(int(t.lexeme), line=t.line, column=t.column)
        if t.type == "STRING_LIT":
            self.advance()
            return ast.StrLit(decode_string(t.lexeme), line=t.line, column=t.column)
        if t.type == "KW_TRUE":
            self.advance()
            return ast.BoolLit(True, line=t.line, column=t.column)
        if t.type == "KW_FALSE":
            self.advance()
            return ast.BoolLit(False, line=t.line, column=t.column)
        if t.type == "FLOAT_LIT":
            self.advance()
            return ast.FloatLit(float(t.lexeme), line=t.line, column=t.column)
        if t.type == "IDENT":
            self.advance()
            if self.at("LPAREN"):
                self.advance()
                args: list[ast.Expr] = []
                if not self.at("RPAREN"):
                    while True:
                        args.append(self.parse_expr())
                        if self.at("COMMA"):
                            self.advance()
                        else:
                            break
                self.expect("RPAREN", "')' after the arguments")
                return ast.Call(t.lexeme, args, line=t.line, column=t.column)
            return ast.Name(t.lexeme, line=t.line, column=t.column)
        if t.type == "LPAREN":
            self.advance()
            inner = self.parse_expr()
            self.expect("RPAREN", "')' to close the bracket")
            return inner
        found = t.lexeme if t.type != "EOF" else "end of file"
        raise ParseError(f"expected a value but found '{found}'", t)


def parse(tokens: list[Token], source: str = "") -> tuple[ast.Program, list[Diagnostic]]:
    parser = Parser(tokens, source)
    program = parser.parse_program()
    return program, parser.errors
