"""
Testes de integração de Fork/Join entre computadores (MiniPar 2026.2).

Sobe o executável em modo worker ("--worker <porta>") num processo separado,
que faz o papel do computador 2, e roda o programa principal em outro
processo, que faz o papel do computador 1. As subtarefas "on host(...)" vão
pela rede (localhost) até o worker, que executa e devolve os resultados.

Como rodar (na raiz do projeto):
    python -m pytest tests/test_fork_join.py
"""
from __future__ import annotations

import subprocess
import time

import pytest

from test_regressao import OUTPUT_DIR, PREFIX, ROOT, compilar, executar, precisa_gpp
from codegen import CppCodeGenerator

PORTA = 5001   # porta usada pelos programas de exemplo


def _exe(nome: str) -> str:
    return str(OUTPUT_DIR / (PREFIX + nome.replace("/", "_") + CppCodeGenerator.executable_suffix()))


@pytest.fixture
def worker():
    """Inicia um worker do programa indicado e o encerra ao fim do teste."""
    processos: list[subprocess.Popen] = []

    def iniciar(nome: str) -> subprocess.Popen:
        r = compilar(nome)
        assert r.returncode == 0, f"Falha ao compilar {nome}:\n{r.stdout}\n{r.stderr}"
        p = subprocess.Popen([_exe(nome), "--worker", str(PORTA)], cwd=ROOT,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        processos.append(p)
        time.sleep(0.5)   # tempo para abrir a porta
        assert p.poll() is None, f"Worker encerrou ao iniciar:\n{p.stdout.read()}"
        return p

    yield iniciar
    for p in processos:
        p.kill()
        p.wait()


def _log(p: subprocess.Popen) -> str:
    p.kill()
    return p.communicate()[0]


@precisa_gpp
def test_fork_para_host_e_nucleos(worker):
    w = worker("fork_join/exemplo_fork_join")
    exe = executar("fork_join/exemplo_fork_join", timeout=60)
    assert exe.returncode == 0, exe.stderr
    assert "Total dos lotes: 3160" in exe.stdout
    assert "10! = 3628800" in exe.stdout            # calculado pelo worker
    assert "Soma das tarefas da lista: 780" in exe.stdout
    log = _log(w)
    assert "Executando fatorial(i64)" in log          # a subtarefa passou mesmo pelo worker


@precisa_gpp
def test_varias_subtarefas_no_mesmo_host(worker):
    w = worker("fork_join/demo_host")
    exe = executar("fork_join/demo_host", stdin="\n", timeout=120)
    assert exe.returncode == 0, exe.stderr
    assert "Total das 4 subtarefas: 1599999996" in exe.stdout
    assert "[Monitor remoto] Concluiu: Aluno 3" in exe.stdout
    log = _log(w)
    assert log.count("Executando carga(i64,i64)") == 2
    assert "Executando relatorio(s,i64)" in log


@precisa_gpp
def test_host_desligado_gera_erro_claro():
    r = compilar("fork_join/exemplo_fork_join")
    assert r.returncode == 0
    exe = executar("fork_join/exemplo_fork_join", timeout=60)   # sem worker na porta
    assert exe.returncode == 1
    assert "nao foi possivel conectar a 127.0.0.1:5001" in exe.stderr
    assert "--worker 5001" in exe.stderr
