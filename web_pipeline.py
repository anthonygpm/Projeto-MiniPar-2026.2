"""
Ponte entre a Web 2 (didática) e as fases do compilador MiniPar.

Roda as fases dentro do próprio processo Python (sem subprocesso) para
devolver o que cada uma produz em formato JSON: tokens, AST, diagnósticos
semânticos, TAC e C++.
"""
from __future__ import annotations

import dataclasses
import os
import sys
from enum import Enum
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from ast_nodes import ASTNode  # noqa: E402


# ----------------------------------------------------------------------
# l4 — AST -> dict, genérico, por reflexão
# ----------------------------------------------------------------------
def ast_to_dict(node: Any) -> Any:
    """Converte qualquer nó da AST (e o que houver dentro dele) em dict/list.

    Não há um caso por tipo de nó: os nós são dataclasses, então
    `dataclasses.fields()` lista os campos de qualquer um — inclusive nós
    criados depois (ForkExpr, JoinExpr, CoreTarget, HostTarget...).
    Cada nó vira {"_type": "NomeDaClasse", campo: valor, ...}.
    """
    if isinstance(node, ASTNode) and dataclasses.is_dataclass(node):
        out: dict[str, Any] = {"_type": type(node).__name__}
        for f in dataclasses.fields(node):
            out[f.name] = ast_to_dict(getattr(node, f.name))
        return out
    if isinstance(node, ASTNode):
        # nó que não é dataclass (não deveria existir, mas não quebra)
        out = {"_type": type(node).__name__}
        for k, v in vars(node).items():
            out[k] = ast_to_dict(v)
        return out
    if isinstance(node, (list, tuple)):
        return [ast_to_dict(x) for x in node]
    if isinstance(node, dict):
        return {str(k): ast_to_dict(v) for k, v in node.items()}
    if isinstance(node, Enum):
        return node.name
    if node is None or isinstance(node, (str, int, float, bool)):
        return node
    return str(node)


# ----------------------------------------------------------------------
# l2 — execução das fases para os endpoints da Web 2
# ----------------------------------------------------------------------
import contextlib  # noqa: E402
import io  # noqa: E402
import threading  # noqa: E402
import uuid  # noqa: E402

from lexer import KEYWORDS, Lexer, Token, TokenType  # noqa: E402
from parser import Parser  # noqa: E402
from semantic import SemanticAnalyzer  # noqa: E402
from tac import TACGenerator  # noqa: E402

# As fases escrevem em stdout/stderr com print; redirecionamos esses fluxos,
# que são globais do processo. O lock impede que duas requisições simultâneas
# misturem as mensagens uma da outra.
_LOCK = threading.Lock()

FASES = ("tokens", "ast", "semantic", "tac", "cpp")

_KEYWORD_TYPES = {t.name for t in KEYWORDS.values()} - {"BOOL_LITERAL", "TYPE"}
_LITERAIS = {"NUMBER", "STRING_LITERAL", "BOOL_LITERAL"}
_DELIMITADORES = {"LPAREN", "RPAREN", "LBRACE", "RBRACE", "LBRACKET", "RBRACKET",
                  "DOT", "SEMICOLON", "COMMA"}


def token_category(t: TokenType) -> str:
    """Categoria didática do token (as mesmas seções da BNF, item 2)."""
    n = t.name
    if n == "IDENTIFIER": return "identificador"
    if n in _LITERAIS: return "literal"
    if n == "TYPE": return "tipo"
    if n in _KEYWORD_TYPES: return "palavra_reservada"
    if n in _DELIMITADORES: return "delimitador"
    if n == "END_OF_FILE": return "fim"
    if n == "UNKNOWN": return "desconhecido"
    return "operador"


def token_to_dict(t: Token) -> dict[str, Any]:
    return {"type": t.type.name, "category": token_category(t.type),
            "lexeme": t.lexeme, "line": t.line, "col": t.col}


def _symbols(sem: SemanticAnalyzer) -> dict[str, Any]:
    """Tabela de símbolos ao fim da análise.

    O analisador descarta os escopos internos (funções, blocos) ao sair
    deles, então aqui só restam o escopo global, as funções e as classes.
    """
    return {
        "globais": [{"nome": s.name, "tipo": s.type} for s in sem._scopes[0].values()
                    if s.type not in ("FUNC", "CLASS")],
        "funcoes": [{"nome": s.name, "parametros": list(s.params)} for s in sem._functions.values()],
        "classes": [{"nome": s.name, "atributos": dict(s.attributes),
                     "metodos": {m: list(p) for m, p in s.methods.items()}}
                    for s in sem._classes.values()],
    }


def run_phases(code: str, ate: str = "semantic") -> dict[str, Any]:
    """Roda as fases do compilador até `ate` (inclusive) e devolve um dict JSON.

    Campos: ok, fase_parada (onde parou com erro, ou None), log (stdout das
    fases), errors (stderr) e, conforme a fase: tokens, ast, diagnostics,
    symbols, tac, cpp, cpp_compilou.
    """
    if ate not in FASES:
        raise ValueError(f"fase desconhecida: {ate}")
    alvo = FASES.index(ate)
    res: dict[str, Any] = {"ok": True, "fase_parada": None}
    out, err = io.StringIO(), io.StringIO()
    fase = "tokens"
    with _LOCK, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            tokens = Lexer(code).tokenize()
            res["tokens"] = [token_to_dict(t) for t in tokens]
            desconhecidos = [t for t in tokens if t.type is TokenType.UNKNOWN]
            for t in desconhecidos:
                print(f"[ERRO LEXICO] Linha {t.line}, coluna {t.col}: simbolo desconhecido {t.lexeme!r}",
                      file=sys.stderr)
            if desconhecidos:
                res["ok"] = False
            if alvo == 0 or not res["ok"]:
                return res

            fase = "ast"
            program = Parser(tokens).parse()      # erro sintático => sys.exit(1)
            res["ast"] = ast_to_dict(program)
            if alvo == 1:
                return res

            fase = "semantic"
            sem = SemanticAnalyzer()
            res["ok"] = sem.analyze(program)
            res["diagnostics"] = sem.diagnostics
            res["symbols"] = _symbols(sem)
            if alvo == 2 or not res["ok"]:
                return res

            fase = "tac"
            res["tac"] = TACGenerator().generate_text(program)
            if alvo == 3:
                return res

            fase = "cpp"
            res.update(_gerar_cpp(program))
        except SystemExit:
            res["ok"] = False                     # o parser encerra com sys.exit
        except Exception as e:                    # bug do compilador: mostra na tela
            res["ok"] = False
            print(f"[ERRO INTERNO] {type(e).__name__}: {e}", file=sys.stderr)
        finally:
            if not res["ok"]:
                res["fase_parada"] = fase
            res["log"], res["errors"] = out.getvalue(), err.getvalue()
    return res


def _gerar_cpp(program) -> dict[str, Any]:
    """Gera o C++ reutilizando o CppCodeGenerator sem alterá-lo.

    O generate() atual monta o texto, grava em output/<nome>.cpp e já chama
    o g++; aqui lemos o .cpp gravado e informamos se o g++ compilou.
    """
    from codegen import CppCodeGenerator
    nome = "web2_cpp_" + uuid.uuid4().hex[:8]
    compilou = CppCodeGenerator().generate(program, nome)
    cpp_path = os.path.join("output", nome + ".cpp")
    cpp = ""
    if os.path.exists(cpp_path):
        with open(cpp_path, encoding="utf-8") as f:
            cpp = f.read()
    # remove os arquivos temporários desta visualização
    for ext in (".cpp", ".exe", ""):
        p = os.path.join("output", nome + ext)
        if os.path.isfile(p):
            with contextlib.suppress(OSError):
                os.remove(p)
    return {"cpp": cpp, "cpp_compilou": bool(compilou)}


# ----------------------------------------------------------------------
# l3 — gerar o executável (para download) e executá-lo com stdin
# ----------------------------------------------------------------------
TEMP_DIR = "temp_code"
OUTPUT_DIR = "output"


def _achar_executavel(nome: str) -> str | None:
    # Hoje o codegen sempre grava "<nome>.exe"; depois da correção
    # multiplataforma (p1), no Linux o arquivo fica sem extensão.
    for cand in (nome + ".exe", nome):
        p = os.path.join(OUTPUT_DIR, cand)
        if os.path.isfile(p):
            return p
    return None


def build_executable(code: str) -> dict[str, Any]:
    """Compila `code` até o executável com o pipeline completo do main.py.

    Devolve {ok, exe (caminho ou None), log}. O nome é único por requisição
    para que duas abas não sobrescrevam o executável uma da outra.
    """
    from main import compile_file
    nome = "web2_" + uuid.uuid4().hex[:8]
    os.makedirs(TEMP_DIR, exist_ok=True)
    fonte = os.path.join(TEMP_DIR, nome + ".minipar")
    with open(fonte, "w", encoding="utf-8") as f:
        f.write(code)
    out = io.StringIO()
    with _LOCK, contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            ok = bool(compile_file(fonte, nome))
        except SystemExit:
            ok = False
        except Exception as e:
            print(f"[ERRO INTERNO] {type(e).__name__}: {e}", file=sys.stderr)
            ok = False
    exe = _achar_executavel(nome) if ok else None
    return {"ok": ok and exe is not None, "exe": exe, "log": out.getvalue()}


def run_executable(code: str, stdin: str = "", timeout: int = 30) -> dict[str, Any]:
    """Compila e executa; `stdin` alimenta os input() (uma resposta por linha)."""
    import subprocess
    b = build_executable(code)
    res: dict[str, Any] = {"ok": False, "log": b["log"], "stdout": "", "stderr": "",
                           "returncode": None}
    if not b["ok"]:
        res["stderr"] = "Falha na compilação; veja o log."
        return res
    if stdin and not stdin.endswith("\n"):
        stdin += "\n"
    try:
        p = subprocess.run([os.path.abspath(b["exe"])], input=stdin, capture_output=True,
                           text=True, timeout=timeout)
        res.update(ok=p.returncode == 0, stdout=p.stdout, stderr=p.stderr,
                   returncode=p.returncode)
    except subprocess.TimeoutExpired as e:
        res["stdout"] = (e.stdout.decode() if isinstance(e.stdout, bytes) else e.stdout) or ""
        res["stderr"] = (f"Tempo limite de {timeout} s excedido (laço infinito, ou o programa "
                         "espera mais entradas do que as enviadas em stdin?).")
    return res
