"""Structural analysis of shell commands for guard.py (Harness Hardening v1.1).

The guard must distinguish *executing* an operation from *mentioning* it as text/data. A
substring search over the raw command cannot do that: a grep pattern, a heredoc JSON payload
or a Python string that merely contains a forbidden word looks identical to a real call.

This module parses a Bash/PowerShell command into simple commands (command word + arguments
+ redirections), follows the constructs that really execute code (command substitution,
``bash -c``/``pwsh -Command``/``eval``/``iex`` strings, heredocs fed to an interpreter,
``python -c`` and ``python -`` bodies, wrappers such as ``env``/``xargs``/``sudo``) and treats
everything else (quoted arguments, heredocs written to files, here-strings) as data.

Fail closed: whenever the structure cannot be established (unbalanced quotes, unterminated
heredoc, process substitution, a command word that is itself a variable, code of an
interpreter we cannot parse, stdin piped into a shell) the affected text is reported as
*opaque* and the guard evaluates it with the conservative legacy text rules.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

MAX_DEPTH = 6

# Leading words that run the rest of the line as a command.
_WRAPPERS = {
    "sudo",
    "nohup",
    "time",
    "command",
    "builtin",
    "exec",
    "nice",
    "stdbuf",
    "unbuffer",
    "doas",
    "wsl",
    "start",
    "call",
}
_OPTION_WRAPPERS = {"env", "timeout", "xargs", "start-process", "saps", "start-job"}
_SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "fish", "git-bash"}
_PWSH = {"pwsh", "powershell"}
_CMD = {"cmd"}
_EVAL = {"eval", "invoke-expression", "iex"}
_SOURCE = {".", "source"}
_RESERVED = {
    "if",
    "then",
    "else",
    "elif",
    "fi",
    "do",
    "done",
    "while",
    "until",
    "!",
    "{",
    "}",
    "function",
    "foreach",
    "try",
    "catch",
    "finally",
}
_PY_RE = re.compile(r"^(python(\d+(\.\d+)?)?w?|py|pypy\d*)(\.exe)?$", re.IGNORECASE)
_PY_RUNNERS = {"uv", "poetry", "pipenv", "pdm", "hatch", "rye", "conda", "mamba", "micromamba"}
_PY_VALUE_OPTS = {"-W", "-X", "--check-hash-based-pycs"}
_OPAQUE_INTERPRETERS = {"node", "deno", "bun", "perl", "ruby", "php", "lua", "osascript"}
_OPAQUE_CODE_OPTS = {"-e", "-p", "-r", "--eval", "--print", "eval"}
_NULL_TARGETS = {"/dev/null", "$null", "nul", "nul:"}

_EXEC_PRIMITIVES = {
    "system",
    "popen",
    "run",
    "call",
    "check_call",
    "check_output",
    "Popen",
    "getoutput",
    "getstatusoutput",
    "spawnl",
    "spawnlp",
    "spawnv",
    "spawnvp",
    "execl",
    "execlp",
    "execv",
    "execvp",
    "execve",
    "startfile",
}
_DYNAMIC_PRIMITIVES = {
    "exec",
    "eval",
    "compile",
    "__import__",
    "import_module",
    "run_path",
    "run_module",
    "SourceFileLoader",
    "spec_from_file_location",
    "load_source",
}
_WRITE_FUNCS = {
    "remove",
    "unlink",
    "rename",
    "renames",
    "replace",
    "rmdir",
    "removedirs",
    "makedirs",
    "mkdir",
    "truncate",
    "chmod",
    "chown",
    "link",
    "symlink",
    "copy",
    "copy2",
    "copyfile",
    "copyfileobj",
    "copytree",
    "copymode",
    "copystat",
    "move",
    "rmtree",
    "make_archive",
    "unpack_archive",
    "write_text",
    "write_bytes",
    "touch",
    "symlink_to",
    "hardlink_to",
    "writestr",
    "extractall",
}
_OPEN_FUNCS = {"open", "fdopen"}
_PATH_WRITE_METHODS = {
    "write_text",
    "write_bytes",
    "touch",
    "mkdir",
    "rmdir",
    "unlink",
    "symlink_to",
    "hardlink_to",
    "chmod",
    "writestr",
    "extractall",
}


@dataclass
class Word:
    text: str  # value after quote removal (placeholders for substitutions)
    quoted: bool = False
    active: bool = False  # contains a command substitution


@dataclass
class Redirect:
    op: str
    target: Word | None  # None = fd duplication (2>&1)


@dataclass
class SimpleCommand:
    words: list[Word] = field(default_factory=list)
    redirects: list[Redirect] = field(default_factory=list)
    heredocs: list[tuple[str, bool]] = field(default_factory=list)  # (body, expands)
    here_strings: list[Word] = field(default_factory=list)
    pipeline_index: int = 0
    call_operator: bool = False  # PowerShell `& <cmd>`


@dataclass
class PythonReport:
    ok: bool
    code: str = ""
    human_script: bool = False
    aws_cli: bool = False
    writes: list[str | None] = field(default_factory=list)  # None = unresolved target
    fragments: list[str] = field(default_factory=list)  # constant fragments of write targets
    shell_strings: list[str] = field(default_factory=list)  # commands handed to a shell
    opaque_exec: bool = False
    strings: list[str] = field(default_factory=list)


@dataclass
class Invocation:
    """A resolved command: argv after peeling wrappers, with the redirections of its line."""

    argv: list[Word]
    redirects: list[Redirect]
    assignments: list[str]


@dataclass
class Analysis:
    ok: bool = True
    invocations: list[Invocation] = field(default_factory=list)
    python: list[PythonReport] = field(default_factory=list)
    opaque: list[str] = field(default_factory=list)  # text to evaluate with legacy rules
    reasons: list[str] = field(default_factory=list)  # why something became opaque

    def extend(self, other: Analysis) -> None:
        self.ok = self.ok and other.ok
        self.invocations += other.invocations
        self.python += other.python
        self.opaque += other.opaque
        self.reasons += other.reasons


class _LexError(Exception):
    pass


# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------
_OPERATORS = ("&&", "||", ";;", "|&", ";", "|", "&", "\n", "(", ")", "{", "}")
_REDIRECT_RE = re.compile(r"(\d*|&)(>>|>\||>&|>|<<<|<<-|<<|<&|<>|<)")
_WORD_BREAK = " \t\r\n;|&(){}<>"


def _matching_paren(text: str, start: int) -> int:
    """Index of the ')' closing the '(' at text[start-1]; quote aware."""
    depth = 1
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "'":
            end = text.find("'", i + 1)
            if end < 0:
                raise _LexError("comilla simple sin cerrar en sustitucion")
            i = end + 1
            continue
        if ch == '"':
            i = _skip_double(text, i + 1)
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise _LexError("sustitucion $( sin cerrar")


def _skip_double(text: str, i: int) -> int:
    """Index just past the '"' closing a double-quoted string that starts at text[i]."""
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == '"':
            return i + 1
        if text.startswith("$(", i):
            i = _matching_paren(text, i + 2) + 1
            continue
        i += 1
    raise _LexError("comilla doble sin cerrar")


def _inner_substitutions(body: str, dialect: str) -> list[str]:
    found: list[str] = []
    i = 0
    while i < len(body):
        if body.startswith("$(", i):
            end = _matching_paren(body, i + 2)
            found.append(body[i + 2 : end])
            i = end + 1
            continue
        if body[i] == "`" and dialect == "bash":
            end = body.find("`", i + 1)
            if end < 0:
                raise _LexError("backtick sin cerrar")
            found.append(body[i + 1 : end])
            i = end + 1
            continue
        i += 1
    return found


class _Lexer:
    """Incremental tokenizer: yields Word, ("redirect", op) or an operator string.

    Incremental so that a heredoc registered on a line is consumed at that line's newline.
    """

    def __init__(self, text: str, dialect: str) -> None:
        self.text = text
        self.dialect = dialect
        self.i = 0
        self.substitutions: list[str] = []
        self.pending_heredocs: list[tuple[SimpleCommand, str, bool, bool]] = []
        self.buffer: list[object] = []

    def next(self) -> object | None:
        if self.buffer:
            return self.buffer.pop(0)
        text = self.text
        while self.i < len(text):
            ch = text[self.i]
            if ch == "\n":
                self.i += 1
                self.read_heredoc_bodies()
                return "\n"
            if ch in " \t\r":
                self.i += 1
                continue
            if ch == "#" and (self.i == 0 or text[self.i - 1] in " \t\n;|&(){}"):
                end = text.find("\n", self.i)
                self.i = len(text) if end < 0 else end
                continue
            if text.startswith(("<(", ">("), self.i):
                raise _LexError("sustitucion de procesos no soportada")
            if not text.startswith("&&", self.i):
                redirect = _REDIRECT_RE.match(text, self.i)
                if redirect and not (
                    redirect.group(1) == "&" and redirect.group(2) not in (">", ">>")
                ):
                    self.i = redirect.end()
                    return ("redirect", redirect.group(0))
            op = next((o for o in _OPERATORS if text.startswith(o, self.i)), None)
            if op:
                self.i += len(op)
                return op
            return self.word()
        return None

    def next_word(self) -> Word | None:
        token = self.next()
        if isinstance(token, Word):
            return token
        if token is not None:
            self.buffer.insert(0, token)
        return None

    def word(self) -> Word:
        text = self.text
        parts: list[str] = []
        quoted = active = False
        while self.i < len(text):
            ch = text[self.i]
            if ch in _WORD_BREAK:
                break
            if ch == "\\" and self.dialect == "bash":
                parts.append(text[self.i + 1 : self.i + 2])
                self.i += 2
                continue
            if ch == "`" and self.dialect == "powershell":
                parts.append(text[self.i + 1 : self.i + 2])
                self.i += 2
                continue
            if ch == "`":
                end = text.find("`", self.i + 1)
                if end < 0:
                    raise _LexError("backtick sin cerrar")
                self.substitutions.append(text[self.i + 1 : end])
                parts.append("\x00")
                active = True
                self.i = end + 1
                continue
            if self.dialect == "powershell" and text.startswith(("@'", '@"'), self.i):
                closing = "\n" + text[self.i + 1] + "@"
                end = text.find(closing, self.i)
                if end < 0:
                    raise _LexError("here-string sin cerrar")
                body = text[self.i + 2 : end]
                if text[self.i + 1] == '"' and "$(" in body:
                    active = True
                    self.substitutions.extend(_inner_substitutions(body, self.dialect))
                parts.append(body)
                quoted = True
                self.i = end + len(closing)
                continue
            if ch == "'":
                end = text.find("'", self.i + 1)
                if end < 0:
                    raise _LexError("comilla simple sin cerrar")
                parts.append(text[self.i + 1 : end])
                quoted = True
                self.i = end + 1
                continue
            if ch == '"':
                end = _skip_double(text, self.i + 1)
                body = text[self.i + 1 : end - 1]
                if "$(" in body or ("`" in body and self.dialect == "bash"):
                    active = True
                    self.substitutions.extend(_inner_substitutions(body, self.dialect))
                if self.dialect == "bash":
                    body = re.sub(r'\\([\\"$`])', r"\1", body)
                parts.append(body)
                quoted = True
                self.i = end
                continue
            if text.startswith("${", self.i):
                end = text.find("}", self.i)
                if end < 0:
                    raise _LexError("${ sin cerrar")
                parts.append(text[self.i : end + 1])
                self.i = end + 1
                continue
            if text.startswith("$(", self.i):
                end = _matching_paren(text, self.i + 2)
                self.substitutions.append(text[self.i + 2 : end])
                parts.append("\x00")
                active = True
                self.i = end + 1
                continue
            parts.append(ch)
            self.i += 1
        return Word("".join(parts), quoted, active)

    def read_heredoc_bodies(self) -> None:
        text = self.text
        for command, delimiter, strip_tabs, expands in self.pending_heredocs:
            lines: list[str] = []
            while True:
                if self.i >= len(text):
                    raise _LexError("heredoc sin terminar")
                end = text.find("\n", self.i)
                line = text[self.i :] if end < 0 else text[self.i : end]
                self.i = len(text) if end < 0 else end + 1
                check = line.lstrip("\t") if strip_tabs else line
                if check.rstrip("\r") == delimiter:
                    break
                lines.append(line)
            body = "\n".join(lines)
            command.heredocs.append((body, expands))
            if expands and ("$(" in body or "`" in body):
                self.substitutions.extend(_inner_substitutions(body, self.dialect))
        self.pending_heredocs = []


def _simple_commands(text: str, dialect: str) -> tuple[list[SimpleCommand], list[str]]:
    lexer = _Lexer(text, dialect)
    commands: list[SimpleCommand] = []
    current = SimpleCommand()
    pipeline_index = 0

    def flush() -> None:
        if current.words or current.redirects or current.heredocs or current.here_strings:
            current.pipeline_index = pipeline_index
            commands.append(current)

    while (token := lexer.next()) is not None:
        if isinstance(token, Word):
            current.words.append(token)
            continue
        if isinstance(token, tuple):
            op = token[1].lstrip("0123456789&")
            target = lexer.next_word()
            if target is None:
                raise _LexError("redireccion sin destino")
            if op in ("<<", "<<-"):
                lexer.pending_heredocs.append(
                    (current, target.text, op == "<<-", not target.quoted)
                )
            elif op == "<<<":
                current.here_strings.append(target)
            elif op in (">&", "<&") and re.fullmatch(r"\d+|-", target.text):
                current.redirects.append(Redirect(op, None))
            else:
                current.redirects.append(Redirect(token[1], target))
            continue
        # PowerShell call operator: `& <cmd>` at command start
        if token == "&" and dialect == "powershell" and not current.words:
            current.call_operator = True
            continue
        flush()
        pipeline_index = pipeline_index + 1 if token in ("|", "|&") else 0
        current = SimpleCommand()
    if lexer.pending_heredocs:
        lexer.read_heredoc_bodies()
    flush()
    return commands, lexer.substitutions


# ---------------------------------------------------------------------------
# Command resolution
# ---------------------------------------------------------------------------
def basename(value: str) -> str:
    return re.split(r"[\\/]", value.strip().strip("'\""))[-1].lower()


def _is_assignment(word: Word) -> bool:
    return not word.quoted and re.match(r"^[A-Za-z_][A-Za-z0-9_]*\+?=", word.text) is not None


def _peel(argv: list[Word]) -> tuple[list[Word], list[str]]:
    """Drop leading assignments, reserved words and pure wrappers."""
    assignments: list[str] = []
    changed = True
    while argv and changed:
        changed = False
        while argv and _is_assignment(argv[0]):
            assignments.append(argv[0].text)
            argv = argv[1:]
            changed = True
        while argv and argv[0].text.lower() in _RESERVED and not argv[0].quoted:
            argv = argv[1:]
            changed = True
        if argv and basename(argv[0].text) in _WRAPPERS:
            argv = argv[1:]
            while argv and argv[0].text.startswith("-") and not argv[0].quoted:
                argv = argv[1:]
            changed = True
    return argv, assignments


def _analyze_text(text: str, dialect: str, depth: int) -> Analysis:
    result = Analysis()
    if depth > MAX_DEPTH:
        result.ok = False
        result.opaque.append(text)
        result.reasons.append("anidamiento excesivo")
        return result
    try:
        commands, substitutions = _simple_commands(text, dialect)
    except _LexError as error:
        result.ok = False
        result.opaque.append(text)
        result.reasons.append(str(error))
        return result
    for inner in substitutions:
        result.extend(_analyze_text(inner, dialect, depth + 1))
    for command in commands:
        _analyze_command(command, dialect, depth, result)
    return result


def _analyze_command(command: SimpleCommand, dialect: str, depth: int, result: Analysis) -> None:
    argv, assignments = _peel(list(command.words))
    heredocs = command.heredocs
    stdin_code = "\n".join(body for body, _ in heredocs)
    if command.here_strings:
        stdin_code = "\n".join([stdin_code, *(w.text for w in command.here_strings)])
    while argv:
        word = argv[0]
        if dialect == "powershell" and word.text.startswith("$") and not command.call_operator:
            # PowerShell: a leading `$x` is an expression, never a command, unless it is invoked
            # with the call operator. `$x = <cmd> ...` runs <cmd>: continue with the right side.
            if len(argv) > 1 and argv[1].text in ("=", "+=", "-=", "??="):
                argv = argv[2:]
                continue
            _head, sep, tail = word.text.partition("=")
            if sep and tail and not word.quoted:
                argv = [Word(tail), *argv[1:]]
                continue
            return
        if word.active or word.text.startswith("$") or "\x00" in word.text:
            result.ok = False
            result.opaque.append(" ".join(w.text for w in command.words))
            result.reasons.append("palabra de comando dinamica")
            return
        name = basename(word.text)
        if name.endswith(".exe"):
            name = name[:-4]
        rest = argv[1:]
        if name in _OPTION_WRAPPERS:
            argv = _skip_wrapper_options(name, rest)
            continue
        if name in _EVAL:
            result.extend(_analyze_text(" ".join(w.text for w in rest), dialect, depth + 1))
            return
        if name in _SHELLS or name in _PWSH or name in _CMD:
            code = _shell_code_arg(name, rest)
            if code is not None:
                sub_dialect = "powershell" if name in _PWSH else "bash"
                result.extend(_analyze_text(code, sub_dialect, depth + 1))
                return
            script = next((w for w in rest if not w.text.startswith("-")), None)
            if script is None:
                if stdin_code:
                    sub_dialect = "powershell" if name in _PWSH else "bash"
                    result.extend(_analyze_text(stdin_code, sub_dialect, depth + 1))
                elif command.pipeline_index > 0:
                    result.ok = False
                    result.opaque.append(" ".join(w.text for w in command.words))
                    result.reasons.append("stdin canalizado a un shell")
                result.invocations.append(Invocation(argv, command.redirects, assignments))
                return
            argv = [script, *rest[rest.index(script) + 1 :]]
            result.invocations.append(Invocation(argv, command.redirects, assignments))
            return
        if name in _SOURCE and rest:
            argv = rest
            continue
        if name in _PY_RUNNERS:
            argv = _skip_runner(rest)
            continue
        if _PY_RE.match(name):
            _analyze_python_invocation(command, argv, stdin_code, result)
            result.invocations.append(Invocation(argv, command.redirects, assignments))
            return
        if name in _OPAQUE_INTERPRETERS:
            code_words = [
                rest[i + 1].text
                for i, w in enumerate(rest[:-1])
                if w.text in _OPAQUE_CODE_OPTS or w.text.startswith("-e")
            ]
            if code_words or (stdin_code and not any(not w.text.startswith("-") for w in rest)):
                result.opaque.extend(code_words or [stdin_code])
                result.reasons.append(f"codigo {name} no analizable")
            elif command.pipeline_index > 0 and not any(not w.text.startswith("-") for w in rest):
                result.ok = False
                result.opaque.append(" ".join(w.text for w in command.words))
                result.reasons.append("stdin canalizado a un interprete")
            result.invocations.append(Invocation(argv, command.redirects, assignments))
            return
        result.invocations.append(Invocation(argv, command.redirects, assignments))
        return
    if command.redirects or assignments:
        result.invocations.append(Invocation([], command.redirects, assignments))


def _skip_wrapper_options(name: str, rest: list[Word]) -> list[Word]:
    index = 0
    while index < len(rest):
        text = rest[index].text
        if name == "env" and (
            _is_assignment(rest[index]) or text in ("-i", "--ignore-environment")
        ):
            index += 1
            continue
        if name == "env" and text in ("-u", "--unset", "-C", "--chdir", "-S"):
            index += 2
            continue
        if name == "timeout" and (text.startswith("-") or re.fullmatch(r"[\d.]+[smhd]?", text)):
            index += 1
            continue
        if name in ("start-process", "saps", "start-job") and text.lower() in (
            "-filepath",
            "-argumentlist",
            "-wait",
            "-nonewwindow",
            "-passthru",
            "-scriptblock",
        ):
            index += 1
            continue
        if name == "xargs" and text.startswith("-"):
            index += 2 if text in ("-I", "-n", "-P", "-L", "-d", "-a", "-s", "-E") else 1
            continue
        break
    return rest[index:]


def _skip_runner(rest: list[Word]) -> list[Word]:
    index = 0
    while index < len(rest):
        text = rest[index].text
        if text in ("run", "exec", "--"):
            index += 1
            continue
        if text in ("-n", "--name", "-p", "--prefix", "--python", "--with", "--env"):
            index += 2
            continue
        if text.startswith("-"):
            index += 1
            continue
        break
    return rest[index:]


def _shell_code_arg(name: str, rest: list[Word]) -> str | None:
    flags = {"-c"} if name in _SHELLS else {"/c", "/k", "/r"} if name in _CMD else set()
    if name in _PWSH:
        flags = {"-c", "-command", "-encodedcommand", "-ec", "-e"}
    for index, word in enumerate(rest):
        lowered = word.text.lower()
        if lowered in flags or (name in _SHELLS and re.fullmatch(r"-[a-z]*c[a-z]*", lowered)):
            if lowered in ("-encodedcommand", "-ec", "-e"):
                return "\x00encoded"  # opaque on purpose: becomes a dynamic command word
            remainder = rest[index + 1 :]
            if name in _CMD or name in _PWSH:
                return " ".join(w.text for w in remainder)
            return remainder[0].text if remainder else ""
    return None


def _analyze_python_invocation(
    command: SimpleCommand, argv: list[Word], stdin_code: str, result: Analysis
) -> None:
    rest = argv[1:]
    index = 0
    while index < len(rest):
        text = rest[index].text
        if text == "-c":
            code = rest[index + 1].text if index + 1 < len(rest) else ""
            result.python.append(analyze_python(code))
            return
        if text == "-m":
            return
        if text in _PY_VALUE_OPTS:
            index += 2
            continue
        if text == "-":
            break
        if text.startswith("-") and len(text) > 1:
            if text.startswith("-c") and len(text) > 2:
                result.python.append(analyze_python(text[2:]))
                return
            index += 1
            continue
        return  # script path: behavior of the script itself is not inspected here
    if stdin_code:
        result.python.append(analyze_python(stdin_code))
    elif command.pipeline_index > 0:
        result.ok = False
        result.opaque.append(" ".join(w.text for w in command.words))
        result.reasons.append("stdin canalizado a python")


def analyze(command: str, dialect: str = "bash") -> Analysis:
    return _analyze_text(command, "powershell" if dialect == "powershell" else "bash", 0)


# ---------------------------------------------------------------------------
# Python (ast)
# ---------------------------------------------------------------------------
def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _strings_in(node: ast.AST) -> list[str]:
    return [
        n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


class _Resolver:
    def __init__(self, tree: ast.AST) -> None:
        self.names: dict[str, list[ast.expr]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.names.setdefault(target.id, []).append(node.value)
            elif isinstance(node, ast.AnnAssign | ast.AugAssign) and isinstance(
                node.target, ast.Name
            ):
                if node.value is not None:
                    self.names.setdefault(node.target.id, []).append(node.value)
            elif isinstance(node, ast.withitem) and isinstance(node.optional_vars, ast.Name):
                self.names.setdefault(node.optional_vars.id, []).append(node.context_expr)
            elif isinstance(node, ast.For | ast.comprehension) and isinstance(
                node.target, ast.Name
            ):
                self.names.setdefault(node.target.id, []).append(ast.Name("<loop>"))

    def resolve(self, node: ast.expr | None, depth: int = 0) -> str | None:
        if node is None or depth > 8:
            return None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            values = self.names.get(node.id) or []
            resolved = {self.resolve(v, depth + 1) for v in values}
            if len(resolved) == 1 and None not in resolved:
                return resolved.pop()
            return None
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in ("Path", "PurePath", "PosixPath", "WindowsPath", "join", "joinpath"):
                base = []
                if name == "joinpath" and isinstance(node.func, ast.Attribute):
                    base = [self.resolve(node.func.value, depth + 1)]
                parts = base + [self.resolve(arg, depth + 1) for arg in node.args]
                if parts and None not in parts:
                    return "/".join(str(p) for p in parts)
            if name in ("resolve", "absolute", "expanduser") and isinstance(
                node.func, ast.Attribute
            ):
                return self.resolve(node.func.value, depth + 1)
            return None
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div | ast.Add):
            left = self.resolve(node.left, depth + 1)
            right = self.resolve(node.right, depth + 1)
            if left is None or right is None:
                return None
            return f"{left}/{right}" if isinstance(node.op, ast.Div) else left + right
        return None


def _mode_writes(mode: ast.expr | None) -> bool:
    if mode is None:
        return False
    if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
        return any(flag in mode.value for flag in "wax+")
    return True  # non-constant mode: assume it can write


def analyze_python(code: str) -> PythonReport:
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return PythonReport(ok=False, code=code)
    report = PythonReport(ok=True, code=code, strings=_strings_in(tree))
    resolver = _Resolver(tree)

    def write(target: ast.expr | None) -> None:
        report.writes.append(resolver.resolve(target))
        if target is not None:
            report.fragments.extend(_strings_in(target))
            if isinstance(target, ast.Name):
                for value in resolver.names.get(target.id, []):
                    report.fragments.extend(_strings_in(value))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            modules = [alias.name for alias in node.names]
            if isinstance(node, ast.ImportFrom):
                modules = [f"{node.module or ''}.{m}" for m in modules] + [node.module or ""]
            if any(m.split(".")[-1] == "approve" for m in modules if m):
                report.human_script = True
            if any(m.split(".")[0] == "boto3" for m in modules if m):
                report.aws_cli = True
            continue
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)
        receiver = node.func.value if isinstance(node.func, ast.Attribute) else None
        if name in _EXEC_PRIMITIVES and _looks_like_process_call(node):
            first = node.args[0] if node.args else None
            literal = isinstance(first, ast.Constant) or (
                isinstance(first, ast.List | ast.Tuple)
                and all(isinstance(item, ast.Constant) for item in first.elts)
            )
            if not literal:
                report.opaque_exec = True
            report.shell_strings.append(" ".join(_strings_in(first)) if first is not None else "")
            continue
        if name in _DYNAMIC_PRIMITIVES:
            report.opaque_exec = True
            if any("approve" in s for s in _strings_in(node)):
                report.human_script = True
            continue
        if name in _OPEN_FUNCS:
            mode = node.args[1] if len(node.args) > 1 else None
            mode = next((k.value for k in node.keywords if k.arg == "mode"), mode)
            if receiver is not None and name == "open" and not _is_module(receiver):
                mode = node.args[0] if node.args else mode
                mode = next((k.value for k in node.keywords if k.arg == "mode"), mode)
                if _mode_writes(mode):
                    write(receiver)
                continue
            if _mode_writes(mode):
                write(node.args[0] if node.args else None)
            continue
        if receiver is not None and not _is_module(receiver):
            # Method call on an object: only pathlib/zipfile write methods count. `str.replace`
            # (2 args), `list.remove` or `dict.copy` are not filesystem writes.
            one_arg_move = name in ("rename", "replace") and len(node.args) == 1
            if name in _PATH_WRITE_METHODS or one_arg_move:
                write(receiver)
                if name in ("rename", "replace", "symlink_to", "hardlink_to"):
                    write(node.args[0] if node.args else None)
            continue
        if name in _WRITE_FUNCS:
            if name in ("copy", "copy2", "copyfile", "copytree", "move", "copymode", "copystat"):
                write(node.args[1] if len(node.args) > 1 else None)
                continue
            for arg in node.args[:2] or [None]:
                write(arg)
    return report


def _is_module(node: ast.expr) -> bool:
    return isinstance(node, ast.Name) and node.id in (
        "os",
        "shutil",
        "io",
        "codecs",
        "pathlib",
        "tempfile",
        "zipfile",
        "tarfile",
        "subprocess",
        "sys",
    )


def _looks_like_process_call(node: ast.Call) -> bool:
    """`run`/`call` are also common method names: only treat subprocess-like calls as exec."""
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return func.value.id in ("subprocess", "sp", "os")
    return isinstance(func, ast.Name)
