# Lower Kenyang Compiler (`kenyang-compiler`)

![Python](https://img.shields.io/badge/Python-3.14%2B-3776AB?logo=python&logoColor=white)
![Lexer](https://img.shields.io/badge/Lexer-Lark%201.3-2ea44f)
![Language](https://img.shields.io/badge/Language-Lower%20Kenyang%20(ken)-orange)
![Course](https://img.shields.io/badge/Course-Compiler%20Construction%20Fall%202026-blue)

A compiler for a programming language whose keywords are rooted in **Lower Kenyang** (ISO 639-3: `ken`), the language of the Bayangi people of Cameroon. Built in Python using **Lark**.

---

## Language Preview

Programs can be written in **UTF-8 Lower Kenyang orthography** (with or without tone marks) or in **plain ASCII fallback** on any standard keyboard—both produce the exact same token stream:

<table>
<tr>
<th>UTF-8 Lower Kenyang</th>
<th>ASCII Fallback</th>
</tr>
<tr>
<td>

```text
kʉ factorial(pɨ n) : pɨ {
    yat (n <= 1) {
        piti 1;
    } rɔ {
        piti n * factorial(n - 1);
    }
}

kʉ main() : ngwɔ {
    pɨ ans = factorial(5);
    sɔ(ans);
    piti;
}
```

</td>
<td>

```text
kuh factorial(pih n) : pih {
    yat (n <= 1) {
        piti 1;
    } roh {
        piti n * factorial(n - 1);
    }
}

kuh main() : ngwoh {
    pih ans = factorial(5);
    soh(ans);
    piti;
}
```

</td>
</tr>
</table>

---

## Compiler Pipeline & Progress

```text
  [.ken source] --> [1. Lexer] --> [2. Parser & AST] --> [3. Semantic Analyser]
                       done             done                   done
                                                                |
  [Executable] <-- [6. Codegen & Runtime] <-- [5. Optimiser] <-- [4. IR / 3-Address]
      done               done                     done                 done
```

| Area | Scope | Status |
|---|---|---|
| **Area 1** | Language design, 70-word Kenyang lexicon, Lark lexer | Done |
| **Area 2** | Grammar, recursive descent parser, syntax tree | Done |
| **Area 3** | Symbol table, semantic analyser, optimiser | Done |
| **Area 4** | Intermediate code, x86-64 code generator, runtime, virtual machine, command line | Done |

167 automated tests pass. Optimised and unoptimised builds, and the native program and the virtual machine, give identical output on all 14 example programs. The compiler also supports decimal numbers, prints warnings for unused variables and unreachable code, and cleans up the generated assembly.

---

## Quick Start (Windows / Python 3.14+)

```powershell
git clone https://github.com/Sirchella/Kenyang-Compiler.git
cd Kenyang-Compiler
pip install -r requirements.txt
python -m pytest -q
```

The native steps (assembler and linker) run through WSL on Windows (`wsl --install -d Ubuntu`) or directly on Linux. Without them, use `--interpret`.

### Compile and run a program

```powershell
mkdir build

# Build a native executable and run it
python -m src.compiler examples/factorial_utf8.ken -o build/factorial --run

# Run on the virtual machine (no assembler needed)
python -m src.compiler examples/factorial_utf8.ken --interpret

# Show the result of one stage: tokens, ast, ir, ir-opt, asm
python -m src.compiler examples/journey.ken --emit ir-opt --stats

# Turn the optimiser off
python -m src.compiler examples/journey.ken --no-opt --emit asm
```

Errors are reported with file, line, column and a hint, for example:

```text
SemanticError [semantic_error.ken:14:8]: 'cuont' is not declared
    14 |     sɔ(cuont);
       |        ^
  hint: Did you mean 'count'?
```

### Lexer tools

```powershell
python -m src.lexer --check-keywords
python -m src.lexer examples/factorial_utf8.ken --json
```

---

## Repository Map

| Path | Description |
|---|---|
| [`src/lexer.py`](src/lexer.py) | Lark-backed lexer with tone-mark removal and multi-error recovery |
| [`src/parser.py`](src/parser.py), [`src/ast_nodes.py`](src/ast_nodes.py) | Recursive descent parser and syntax tree |
| [`src/semantic.py`](src/semantic.py) | Symbol table, type checking, error messages |
| [`src/ir.py`](src/ir.py) | Three-address intermediate code |
| [`src/optimiser.py`](src/optimiser.py) | Constant folding, value passing, dead code removal, jump clean-up |
| [`src/codegen.py`](src/codegen.py) | x86-64 assembly generator and assembly runtime |
| [`src/toolchain.py`](src/toolchain.py) | Calls the assembler and linker (through WSL on Windows) |
| [`src/interpreter.py`](src/interpreter.py) | Virtual machine for the intermediate code |
| [`src/compiler.py`](src/compiler.py) | Command line that joins all stages |
| [`grammar/kenyang.lark`](grammar/kenyang.lark) | Lexical grammar for UTF-8 Lower Kenyang and the ASCII fallback |
| [`keywords.json`](keywords.json) | The 70 Lower Kenyang keywords (`CORE`, `STANDARD`, `EXTENDED`) |
| [`tests/`](tests/) | 167 `pytest` tests for every stage and end to end |
| [`examples/`](examples/) | 14 sample programs, and `errors/` with programs that contain mistakes or warnings |
| [`docs/project-explainer.md`](docs/project-explainer.md) | Plain-language explanation of the whole project |
| [`docs/demo-guide.md`](docs/demo-guide.md) | Step-by-step script for the demonstration |
| [`docs/language-spec.md`](docs/language-spec.md) | Language specification (v0.2) |
| [`docs/kenyang-research-dossier.md`](docs/kenyang-research-dossier.md) | Linguistic bibliography, alphabet and Unicode rules |
| [`docs/speaker-keywords-master.md`](docs/speaker-keywords-master.md) | Full 70-keyword reference table with citations |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Branching rules, Git workflow, and PR checklist |
| [`project-plan.md`](project-plan.md) | Overall 4-member semester project plan |
