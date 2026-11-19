# Lower Kenyang Language Specification (v0.2)

**Implementation language:** Python 3.14+ (Lark is used for the lexer)
**Target:** x86-64 Linux machine code, built with the GNU assembler and linker (through WSL on Windows). A virtual machine runs the same program where no assembler is available.

Version 0.2 describes what the finished compiler really accepts. Changes from the v0.1 draft are listed in section 9.

---

## 1. Lexical Rules

1. **Encoding and spelling**
   - Source files are UTF-8 (`.ken` extension recommended).
   - Every keyword has two spellings that mean the same thing: the Lower Kenyang spelling and an ASCII fallback (`ɛ` becomes `eh`, `ɔ` becomes `oh`, `ɨ` becomes `ih`, `ʉ` becomes `uh`, `ŋ` becomes `ng`).
   - Tone marks on keywords are removed before matching, so `sɔ́` and `sɔ` are the same keyword.
2. **Identifiers** (names of variables and functions)
   - An ASCII letter or `_`, then letters, digits or `_`: `[a-zA-Z_][a-zA-Z0-9_]*`.
   - Non-ASCII letters are allowed only in keywords and string literals.
   - A name may not be a keyword. This compiler reserves the 34 keywords of the CORE and STANDARD tiers in `keywords.json`. The 36 EXTENDED keywords are not used by the language, so they can still be used as ordinary names (for example `a` or `te`).
3. **Literals**
   - Whole numbers: `[0-9]+`, from 0 to 9223372036854775807. A minus sign in front is an operator, not part of the number.
   - Decimal numbers: `[0-9]+.[0-9]+`, for example `3.14`. There is no exponent form.
   - Strings: `"..."` with the escapes `\n`, `\t`, `\r`, `\"`, `\\`. Strings may contain any UTF-8 text, including Kenyang letters.
   - Booleans: the keywords `tɛtɛp` (true) and `nse` (false).
4. **Comments and spaces**
   - `// ...` to the end of the line.
   - `/* ... */` over several lines.
   - Spaces, tabs and line breaks are ignored; line and column are tracked for error messages.

---

## 2. Operators and Punctuation

| Group | Symbols |
|---|---|
| Arithmetic | `+`, `-`, `*`, `/`, `%` |
| Comparison | `==`, `!=`, `<`, `<=`, `>`, `>=` |
| Assignment | `=` (a statement, not an expression) |
| Logic (keywords) | `ne` (and), `kɛ` (or), `ka` (not) |
| Punctuation | `(`, `)`, `{`, `}`, `,`, `;`, `:` |

### Priority of operators (highest first)

1. Brackets and function calls: `( expr )`, `f(args)`
2. Unary: `-`, `ka`
3. `*`, `/`, `%`
4. `+`, `-`
5. `<`, `<=`, `>`, `>=`
6. `==`, `!=`
7. `ne` (and)
8. `kɛ` (or)

Operators of the same priority group from left to right, so `10 - 3 - 2` is `5`.

---

## 3. Grammar (EBNF)

```ebnf
program     ::= func_decl*

func_decl   ::= KW_FUNC IDENT "(" param_list? ")" (":" type)? block
param_list  ::= param ("," param)*
param       ::= type IDENT
type        ::= KW_INT | KW_FLOAT | KW_BOOL | KW_STRING | KW_VOID

block       ::= "{" stmt* "}"

stmt        ::= var_decl ";"
              | assign_stmt ";"
              | if_stmt
              | while_stmt
              | for_stmt
              | return_stmt
              | write_stmt
              | read_stmt
              | KW_BREAK ";"
              | KW_CONTINUE ";"
              | call ";"
              | block

var_decl    ::= (type | KW_VAR) IDENT ("=" expr)?
assign_stmt ::= IDENT "=" expr
if_stmt     ::= KW_IF "(" expr ")" block (KW_ELIF "(" expr ")" block)* (KW_ELSE block)?
while_stmt  ::= KW_WHILE "(" expr ")" block
for_stmt    ::= KW_FOR "(" (var_decl | assign_stmt)? ";" expr? ";" assign_stmt? ")" block
return_stmt ::= KW_RETURN expr? ";"
write_stmt  ::= KW_WRITE "(" expr ")" ";"
read_stmt   ::= KW_READ "(" IDENT ")" ";"

expr        ::= or_expr
or_expr     ::= and_expr (KW_OR and_expr)*
and_expr    ::= equality (KW_AND equality)*
equality    ::= relation (("==" | "!=") relation)*
relation    ::= additive (("<" | "<=" | ">" | ">=") additive)*
additive    ::= term (("+" | "-") term)*
term        ::= unary (("*" | "/" | "%") unary)*
unary       ::= ("-" | KW_NOT) unary | primary
primary     ::= INT_LIT | FLOAT_LIT | STRING_LIT | KW_TRUE | KW_FALSE | IDENT | call | "(" expr ")"
call        ::= IDENT "(" (expr ("," expr)*)? ")"
```

The grammar has no left recursion. Every choice can be made by looking at the next token (one token of look-ahead), which is why a hand-written recursive descent parser is enough.

---

## 4. Meaning of a Program

### Types

| Type | Keyword | Values |
|---|---|---|
| Whole number | `pɨ` (`pih`) | 64-bit signed |
| Decimal number | `pɨ_kati` (`pih_kati`) | 64-bit floating point |
| Truth value | `tɛp` (`tehp`) | `tɛtɛp`, `nse` |
| Text | `bɛyɔŋ` (`behyohng`) | string literals; can be stored, passed, returned and written |
| Nothing | `ngwɔ` (`ngwoh`) | return type of a function that gives no value |

The only automatic change of type is from a whole number to a decimal: a whole number may be used wherever a decimal is expected (in a calculation with a decimal, a declaration, an assignment, an argument or a return). A decimal can never become a whole number. `%` needs two whole numbers. `ŋati` (`ngati`) declares a variable whose type is taken from its first value: `ŋati k = 5;` makes `k` an int.

### Variables and scope

- A variable lives from its declaration to the end of the block it is declared in.
- A name may not be declared twice in the same block. An inner block may reuse a name from an outer block.
- A variable declared without a value starts at 0 (`pɨ`, `tɛp`) or as the empty string (`bɛyɔŋ`).

### Functions

- All code lives inside functions. Functions may call each other in any order and may call themselves.
- If no return type is given, the function returns nothing.
- A function with a return type must reach a `piti value;` on every path.
- The program must have a function called `main` with no parameters and no return value. Running the program means running `main`.

### Statements

| Statement | Meaning |
|---|---|
| `sɔ(e);` | Print the value of `e` and a line break. A bool prints as `tɛtɛp` or `nse`. A decimal prints with six digits after the point. |
| `pay(x);` | Read a whole number from the input into the int variable `x`. Leading spaces, line breaks and non-ASCII bytes (for example a byte-order mark that some terminals add) are skipped; reading stops at the first character that is not a digit. If there is no number, `x` becomes 0. |
| `yat ... rɔ_yat ... rɔ ...` | Choose the first branch whose condition is true. |
| `kʉ_te (c) { }` | Repeat while `c` is true. |
| `pay_te (init; c; step) { }` | Run `init` once, then repeat while `c` is true, running `step` after each pass. |
| `kati;` | Leave the nearest loop. |
| `chak;` | Skip to the next pass of the nearest loop. |
| `piti e;` | Leave the function and give back `e`. |

`ne` and `kɛ` stop early: in `a ne b`, `b` is not evaluated when `a` is false; in `a kɛ b`, `b` is not evaluated when `a` is true.

Division and remainder cut toward zero (`-17 / 5` is `-3`, `-17 % 5` is `-2`). Whole numbers wrap around at 64 bits. Dividing by zero, whole or decimal, stops the program with `runtime error: division by zero` and exit code 1.

---

## 5. Keywords Reserved but Not Yet Used

These words are recognised and cannot be used as names, but the compiler gives them no meaning yet:

`ɛyɔŋ` (char), `ngwɔ_nɛ` (null), `fɔ` (then), `yat_bɛ` (switch), `mpok` (case), `rɔ_mpok` (default), `burɛ` (const), `bhɔŋ_kʉ` (main), `rɛsɛ` (println), `pay_bɛ` (len), `piti_pɨ` (to_int), `piti_bɛyɔŋ` (to_str).

Using the char type gives the message "the type is not supported in this version".

---

## 6. Example Program

**UTF-8 Lower Kenyang**
```text
kʉ main() : ngwɔ {
    pɨ x = 2 + 3 * 4;
    sɔ(x);
}
```

**ASCII fallback (same program)**
```text
kuh main() : ngwoh {
    pih x = 2 + 3 * 4;
    soh(x);
}
```

Output: `14`

---

## 7. Errors

Every error names the file, line and column, shows the source line with a marker, and where possible adds a hint. The compiler reports all errors of one stage in a single run and does not start the next stage until the current one is clean.

| Stage | Kind | Example |
|---|---|---|
| Lexer | `LexError` | `Unexpected character '@'`, `Unterminated string literal` |
| Parser | `ParseError` | `expected ';' after the declaration but found 'yat'` |
| Semantic analyser | `SemanticError` | `'cuont' is not declared` with `hint: Did you mean 'count'?` |

---

### Warnings

A warning does not stop the build. It is shown when the program is legal but probably careless.

| Warning | Meaning |
|---|---|
| `variable 'x' is never used` | A variable is declared and never read. Names that start with `_` and function parameters are not reported. |
| `this code can never run` | A statement follows `piti`, `kati`, `chak`, or an `if` whose branches all return. |

---

## 8. Interfaces Between Stages

| From | To | Form |
|---|---|---|
| Lexer (`src/lexer.py`) | Parser | `list[Token]` with `type`, `lexeme`, `line`, `column` |
| Parser (`src/parser.py`) | Semantic analyser | `ast_nodes.Program` (syntax tree) |
| Semantic analyser (`src/semantic.py`) | IR generator | the same tree, with `ty` on every expression and `unique` on every variable |
| IR generator (`src/ir.py`) | Optimiser | `IRProgram`: one list of three-address instructions per function |
| Optimiser (`src/optimiser.py`) | Code generator and virtual machine | a shorter `IRProgram` |
| Code generator (`src/codegen.py`) | Assembler and linker | x86-64 assembly text |

---

## 9. Changes from v0.1

- Statements at the top level are no longer allowed; all code is inside functions.
- Added `for`, `elif`, `break`, `continue` and the `var` keyword (`ŋati`).
- Added the full priority table and the rules for types, scope and evaluation.
- `sɔ` always ends the printed value with a line break.
- The compiler uses the CORE and STANDARD keyword tiers; EXTENDED words stay free for use as names.
- Added decimal numbers (`pɨ_kati`) with automatic widening from whole numbers.
- Added warnings for unused variables and unreachable code.
- Char is recognised but not compiled.
