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


class _LexerComPosicao(Lexer):
    """Lexer que também anota onde cada token TERMINA (end_line, end_col).

    O _make_token é chamado logo depois de o token ser consumido, então a
    posição atual do lexer é o fim dele. Isso permite à Web 2 destacar o
    trecho exato no editor, inclusive strings com aspas e escapes.
    """
    def _make_token(self, token_type, lexeme, line, col):
        tok = super()._make_token(token_type, lexeme, line, col)
        tok.end_line, tok.end_col = self._line, self._col
        return tok


def token_to_dict(t: Token) -> dict[str, Any]:
    end_line = getattr(t, "end_line", t.line)
    end_col = getattr(t, "end_col", t.col + len(t.lexeme))
    return {"type": t.type.name, "category": token_category(t.type),
            "lexeme": t.lexeme, "line": t.line, "col": t.col,
            "end_line": end_line, "end_col": end_col}


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


# ----------------------------------------------------------------------
# l7 — tabela de símbolos por escopo e problemas (erros/avisos) por linha
# ----------------------------------------------------------------------
import re  # noqa: E402

from ast_nodes import ClassDecl, ForStmt, FuncDecl, ParBlock, SeqBlock  # noqa: E402


class _AnalisadorComEscopos(SemanticAnalyzer):
    """SemanticAnalyzer que guarda uma cópia de cada escopo antes de descartá-lo.

    O analisador original empilha um dicionário por escopo e o descarta ao
    sair dele; aqui sobrescrevemos _enter_scope/_exit_scope só para registrar
    o conteúdo, sem mudar nenhuma regra semântica. O nó que está sendo
    validado no momento diz que tipo de escopo foi aberto (função, classe,
    for, bloco).
    """

    def __init__(self) -> None:
        self._pilha_nos: list = []
        self._pilha_escopos: list[int] = []
        self._linhas: dict = {}          # (id do escopo, nome) -> linha da declaração
        self.escopos: list[dict[str, Any]] = []
        super().__init__()               # já abre o escopo global

    def validate_node(self, node) -> None:
        self._pilha_nos.append(node)
        try:
            super().validate_node(node)
        finally:
            self._pilha_nos.pop()

    def _define_symbol(self, name, type_, line, params=None) -> None:
        super()._define_symbol(name, type_, line, params)
        self._linhas.setdefault((id(self._scopes[-1]), name), line)

    def _enter_scope(self) -> None:
        super()._enter_scope()
        node = self._pilha_nos[-1] if self._pilha_nos else None
        pai = self._pilha_escopos[-1] if self._pilha_escopos else None
        tipo, nome = "global", "Escopo global"
        if isinstance(node, FuncDecl):
            if self._current_class:
                tipo, nome = "metodo", f"método {self._current_class}.{node.name}({', '.join(node.params)})"
            else:
                tipo, nome = "funcao", f"função {node.name}({', '.join(node.params)})"
        elif isinstance(node, ClassDecl):
            tipo, nome = "classe", f"classe {node.name}" + (f" extends {node.superclass}" if node.superclass else "")
        elif isinstance(node, ForStmt):
            tipo, nome = "for", "laço for"
        elif isinstance(node, ParBlock):
            tipo, nome = "par", "bloco par"
        elif isinstance(node, SeqBlock):
            pai_reg = self.escopos[pai] if pai is not None else None
            if pai_reg and pai_reg["tipo"] in ("funcao", "metodo") and not pai_reg["filhos"]:
                tipo, nome = "corpo", "corpo"
            else:
                tipo, nome = "bloco", "bloco { }"
        linha = getattr(node, "line", None) if node is not None else None
        if isinstance(node, (SeqBlock, ParBlock)):
            # o parser não anota a linha dos blocos: usa o 1º comando ou o dono do bloco
            if node.statements:
                linha = getattr(node.statements[0], "line", linha)
            elif pai is not None:
                linha = self.escopos[pai]["linha"]
        reg = {"id": len(self.escopos), "pai": pai, "tipo": tipo, "nome": nome,
               "linha": linha,
               "simbolos": [], "filhos": [], "_dict": self._scopes[-1]}
        self.escopos.append(reg)
        if pai is not None:
            self.escopos[pai]["filhos"].append(reg["id"])
        self._pilha_escopos.append(reg["id"])

    def _exit_scope(self) -> None:
        if len(self._scopes) > 1 and self._pilha_escopos:
            self._fotografar(self._pilha_escopos.pop())
        super()._exit_scope()

    def _fotografar(self, idx: int) -> None:
        reg = self.escopos[idx]
        escopo = reg["_dict"]
        simbolos = []
        for nome, sym in escopo.items():
            item = {"nome": nome, "tipo": sym.type, "linha": self._linhas.get((id(escopo), nome))}
            if sym.type == "FUNC":
                item["tipo"] = "método" if reg["tipo"] == "classe" else "função"
                item["detalhe"] = "(" + ", ".join(sym.params) + ")"
            elif sym.type == "CLASS":
                item["tipo"] = "classe"
                c = self._classes.get(nome)
                if c:
                    item["detalhe"] = (f"atributos: {', '.join(c.attributes) or '—'} · "
                                       f"métodos: {', '.join(c.methods) or '—'}")
            simbolos.append(item)
        reg["simbolos"] = simbolos

    def resultado_escopos(self) -> list[dict[str, Any]]:
        # o escopo global nunca é desempilhado: fotografa no fim
        if self.escopos:
            self._fotografar(0)
        return [{k: v for k, v in r.items() if k != "_dict"} for r in self.escopos]


_RE_PROBLEMA = re.compile(
    r"^\[(ERRO|AVISO)(?: ([A-ZÁÉÍÓÚÇ]+))?\]\s*(?:Linha (\d+)(?:, coluna (\d+))?)?(?: \(Funcao: ([^)]+)\))?:?\s*(.*)$")
_FASE_DO_ROTULO = {"LEXICO": "léxica", "SINTATICO": "sintática", "SEMANTICO": "semântica",
                   "INTERNO": "interno", None: "compilação"}


def extrair_problemas(*textos: str) -> list[dict[str, Any]]:
    """Lê as mensagens [ERRO ...]/[AVISO ...] que as fases imprimem.

    Usa o texto impresso (e não só sem.diagnostics) porque algumas mensagens,
    como erro léxico, sintático e variável redeclarada, só existem ali.
    """
    vistos, out = set(), []
    for texto in textos:
        for linha in (texto or "").splitlines():
            m = _RE_PROBLEMA.match(linha.strip())
            if not m:
                continue
            nivel, rotulo, ln, col, funcao, msg = m.groups()
            if not msg or "Falha na Analise Semantica" in msg:
                continue
            chave = (nivel, ln, msg)
            if chave in vistos:
                continue
            vistos.add(chave)
            out.append({"kind": "erro" if nivel == "ERRO" else "aviso",
                        "fase": _FASE_DO_ROTULO.get(rotulo, (rotulo or "").lower()),
                        "line": int(ln) if ln else None, "col": int(col) if col else None,
                        "funcao": funcao, "message": msg})
    out.sort(key=lambda p: (p["line"] is None, p["line"] or 0, p["kind"] != "erro"))
    return out


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
            tokens = _LexerComPosicao(code).tokenize()
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
            sem = _AnalisadorComEscopos()
            res["ok"] = sem.analyze(program)
            res["diagnostics"] = sem.diagnostics
            res["symbols"] = _symbols(sem)
            res["escopos"] = sem.resultado_escopos()
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
            res["problemas"] = extrair_problemas(res["errors"], res["log"])
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
    # O C++ começa com o runtime fixo (cpp_template._CPP_HEADER); a Web 2 mostra
    # por padrão só o que foi traduzido do programa, a partir desta linha.
    from cpp_template import _CPP_HEADER
    inicio = len(_CPP_HEADER.splitlines()) + 1 if cpp.startswith(_CPP_HEADER) else 1
    return {"cpp": cpp, "cpp_compilou": bool(compilou), "cpp_inicio_programa": inicio}


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
