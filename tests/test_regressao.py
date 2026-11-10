"""
Testes de regressão do compilador MiniPar 2026.2.

Para cada programa de teste:
  1. compila o .minipar (Léxico -> Sintático -> Semântico -> TAC -> C++ -> g++);
  2. executa o binário gerado;
  3. compara a saída com tests/expected_results/<teste>.expected.txt
     (e o TAC com <teste>.expected.tac, quando existir).

Os casos com saída esperada são descobertos automaticamente: basta criar
tests/expected_results/<nome>.expected.txt para que tests/<nome>.minipar
entre na regressão. Ajustes por teste (entrada, tolerância) ficam em CONFIG.

Como rodar (na raiz do projeto):
    python -m pytest            # tudo
    python -m pytest -k teste4  # só um teste
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "tests"
EXPECTED_DIR = TESTS_DIR / "expected_results"
OUTPUT_DIR = ROOT / "output"
PREFIX = "regressao_"          # prefixo dos binários gerados aqui, para não sobrescrever os da IDE

sys.path.insert(0, str(ROOT / "src"))
from codegen import CppCodeGenerator  # noqa: E402

# ----------------------------------------------------------------------
# Configuração por teste
#   stdin      : texto enviado à entrada padrão do programa
#   tolerancia : diferença máxima aceita entre números (0 = comparação exata).
#                O Teste 4 usa pesos iniciais aleatórios no Python do enunciado,
#                então os valores previstos só podem bater aproximadamente.
#   timeout    : segundos de execução antes de considerar travado
#   worker     : porta de um worker ("programa --worker <porta>") iniciado antes,
#                para programas com fork ... on host(...)
# ----------------------------------------------------------------------
CONFIG: dict[str, dict] = {
    "teste4_rede_neural_xor": {"tolerancia": 0.05},
    "teste6_quicksort_classes": {"stdin": "10 -3 -40 80 70 -100\n"},
    "exemplo_fork_join": {"worker": 5001},
    "teste11_minicompilador": {"stdin": "\n"},   # Enter: compila as 3 expressoes do Teste 11
}

# Programas que DEVEM ser rejeitados pelo compilador (erros de propósito)
DEVE_FALHAR = {"fork_join/erros_fork_join"}

GPP_DISPONIVEL = shutil.which("g++") is not None
precisa_gpp = pytest.mark.skipif(not GPP_DISPONIVEL, reason="g++ não encontrado no PATH")


# ----------------------------------------------------------------------
# Utilitários
# ----------------------------------------------------------------------
def _nome(path: Path) -> str:
    """Nome do teste relativo a tests/, sem extensão (ex.: 'fork_join/exemplo_fork_join')."""
    return path.relative_to(TESTS_DIR).with_suffix("").as_posix()


def _todos_os_programas() -> list[str]:
    return sorted(_nome(p) for p in TESTS_DIR.rglob("*.minipar"))


def _resolver(base: str) -> str:
    """Nome do arquivo esperado -> programa em tests/ ou numa subpasta (ex.: fork_join/)."""
    achados = [_nome(p) for p in TESTS_DIR.rglob(f"{base}.minipar")]
    assert len(achados) == 1, f"Esperado exatamente um {base}.minipar em tests/, achados: {achados}"
    return achados[0]


def _casos_com_saida_esperada() -> list[str]:
    return sorted(p.name[: -len(".expected.txt")] for p in EXPECTED_DIR.glob("*.expected.txt"))


def compilar(nome: str) -> subprocess.CompletedProcess:
    """Roda o compilador completo (python main.py) sobre tests/<nome>.minipar."""
    fonte = TESTS_DIR / f"{nome}.minipar"
    saida = PREFIX + nome.replace("/", "_")
    return subprocess.run(
        [sys.executable, "main.py", str(fonte), saida],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=180,
    )


def executar(nome: str, stdin: str = "", timeout: int = 60) -> subprocess.CompletedProcess:
    exe = OUTPUT_DIR / (PREFIX + nome.replace("/", "_") + CppCodeGenerator.executable_suffix())
    assert exe.exists(), f"Executável não gerado: {exe}"
    return subprocess.run(
        [str(exe)], input=stdin, cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )


def normalizar(texto: str) -> list[str]:
    """Linhas comparáveis: sem acentos/emojis, espaços colapsados, sem linhas vazias.

    Os programas de teste evitam acentos (o console do Windows não usa UTF-8
    por padrão), enquanto os arquivos esperados seguem o texto do enunciado.
    """
    linhas = []
    for linha in texto.splitlines():
        sem_acento = unicodedata.normalize("NFKD", linha).encode("ascii", "ignore").decode()
        limpa = " ".join(sem_acento.split())
        if limpa:
            linhas.append(limpa)
    return linhas


_NUMERO = re.compile(r"^-?\d+(\.\d+)?$")


def linhas_equivalentes(esperada: str, obtida: str, tolerancia: float) -> bool:
    if esperada == obtida:
        return True
    if tolerancia <= 0:
        return False
    # Compara token a token; números podem diferir até a tolerância
    tok_e = re.findall(r"-?\d+\.\d+|-?\d+|[^\s\d-]+|-", esperada)
    tok_o = re.findall(r"-?\d+\.\d+|-?\d+|[^\s\d-]+|-", obtida)
    if len(tok_e) != len(tok_o):
        return False
    for a, b in zip(tok_e, tok_o):
        if _NUMERO.match(a) and _NUMERO.match(b):
            # O valor pode variar até a tolerância, mas o formato (casas decimais) não
            casas_a = len(a.split(".")[1]) if "." in a else 0
            casas_b = len(b.split(".")[1]) if "." in b else 0
            if casas_a != casas_b or abs(float(a) - float(b)) > tolerancia:
                return False
        elif a != b:
            return False
    return True


def conferir_subsequencia(esperado: list[str], obtido: list[str], tolerancia: float) -> None:
    """Cada linha esperada deve aparecer na saída, na mesma ordem.

    A saída pode ter linhas extras: os arquivos esperados do enunciado omitem
    trechos repetitivos (ex.: iterações 5 a 49 do Teste 3).
    """
    pos = 0
    for linha in esperado:
        while pos < len(obtido) and not linhas_equivalentes(linha, obtido[pos], tolerancia):
            pos += 1
        if pos == len(obtido):
            contexto = "\n".join(obtido[-15:])
            pytest.fail(
                f"Linha esperada não encontrada (na ordem): {linha!r}\n"
                f"--- últimas linhas da saída ---\n{contexto}"
            )
        pos += 1


# ----------------------------------------------------------------------
# Testes
# ----------------------------------------------------------------------
@precisa_gpp
@pytest.mark.parametrize("nome", [n for n in _todos_os_programas() if n not in DEVE_FALHAR])
def test_compila(nome: str) -> None:
    """Todo programa de teste válido passa por todas as fases e gera executável."""
    r = compilar(nome)
    assert r.returncode == 0, f"Falha ao compilar {nome}:\n{r.stdout}\n{r.stderr}"


@pytest.mark.parametrize("nome", sorted(DEVE_FALHAR))
def test_programa_invalido_e_rejeitado(nome: str) -> None:
    r = compilar(nome)
    assert r.returncode != 0, f"{nome} deveria ser rejeitado pelo compilador"
    assert "[ERRO SEMANTICO]" in r.stderr


@precisa_gpp
@pytest.mark.parametrize("nome", _casos_com_saida_esperada())
def test_saida_esperada(nome: str) -> None:
    cfg = CONFIG.get(nome, {})
    programa = _resolver(nome)
    r = compilar(programa)
    assert r.returncode == 0, f"Falha ao compilar {programa}:\n{r.stdout}\n{r.stderr}"

    stdin = cfg.get("stdin", "")
    worker = None
    if "worker" in cfg:   # o mesmo executável faz o papel do outro computador
        exe_path = OUTPUT_DIR / (PREFIX + programa.replace("/", "_") + CppCodeGenerator.executable_suffix())
        worker = subprocess.Popen([str(exe_path), "--worker", str(cfg["worker"])], cwd=ROOT,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        exe = executar(programa, stdin=stdin, timeout=cfg.get("timeout", 60))
    finally:
        if worker:
            worker.kill()
            worker.wait()
    assert exe.returncode == 0, f"{nome} terminou com código {exe.returncode}:\n{exe.stderr}"

    esperado = normalizar((EXPECTED_DIR / f"{nome}.expected.txt").read_text(encoding="utf-8"))
    # A entrada digitada aparece no arquivo esperado (eco do terminal), mas não na saída do programa
    entradas = set(normalizar(stdin))
    esperado = [linha for linha in esperado if linha not in entradas]

    conferir_subsequencia(esperado, normalizar(exe.stdout), cfg.get("tolerancia", 0.0))


@pytest.mark.parametrize(
    "nome", sorted(p.name[: -len(".expected.tac")] for p in EXPECTED_DIR.glob("*.expected.tac"))
)
def test_tac_esperado(nome: str) -> None:
    """O código de três endereços gerado deve bater com o esperado."""
    from lexer import Lexer
    from parser import Parser
    from tac import TACGenerator

    fonte = (TESTS_DIR / f"{nome}.minipar").read_text(encoding="utf-8")
    programa = Parser(Lexer(fonte).tokenize()).parse()
    obtido = TACGenerator().generate_text(programa)
    esperado = (EXPECTED_DIR / f"{nome}.expected.tac").read_text(encoding="utf-8")
    assert normalizar(obtido) == normalizar(esperado)


@pytest.mark.parametrize(
    "plataforma, suffix, com_winsock",
    [("win32", ".exe", True), ("linux", "", False), ("darwin", "", False)],
)
def test_link_multiplataforma(monkeypatch, plataforma: str, suffix: str, com_winsock: bool) -> None:
    """-lws2_32 e a extensão .exe só aparecem no Windows."""
    monkeypatch.setattr(sys, "platform", plataforma)
    assert CppCodeGenerator.executable_suffix() == suffix
    cmd = CppCodeGenerator.gcc_command("prog.cpp", "prog" + suffix)
    assert ("-lws2_32" in cmd) == com_winsock
    assert "-pthread" in cmd and "-std=c++20" in cmd
