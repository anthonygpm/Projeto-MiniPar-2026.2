"""
Testes 1 e 2 do enunciado em "dois computadores" (MiniPar 2026.2).

Cada computador é simulado por um processo separado na mesma máquina
(127.0.0.1). Os programas ficam em tests/dois_computadores/ e pedem o IP do
outro computador ao iniciar (Enter = 127.0.0.1).

Também cobre o Teste 1 original (cliente e servidor como threads de um só
programa), que travava antes da correção do canal (MiniParChannel).

Como rodar (na raiz do projeto):
    python -m pytest tests/test_dois_computadores.py
"""
from __future__ import annotations

import subprocess
import time

from test_regressao import OUTPUT_DIR, PREFIX, ROOT, compilar, executar, precisa_gpp
from codegen import CppCodeGenerator


def _exe(nome: str) -> str:
    return str(OUTPUT_DIR / (PREFIX + nome.replace("/", "_") + CppCodeGenerator.executable_suffix()))


def _compilar(nome: str) -> None:
    r = compilar(nome)
    assert r.returncode == 0, f"Falha ao compilar {nome}:\n{r.stdout}\n{r.stderr}"


@precisa_gpp
def test_teste1_original_nao_trava():
    """Cliente e servidor no mesmo programa (par): três mensagens seguidas pelo canal."""
    _compilar("teste1_calculadora_cliente_servidor")
    for _ in range(3):   # o defeito antigo aparecia em todas as execuções
        exe = executar("teste1_calculadora_cliente_servidor", stdin="+\n3\n5\n", timeout=20)
        assert exe.returncode == 0, exe.stderr
        assert "Resultado: 8" in exe.stdout


@precisa_gpp
def test_teste1_cliente_e_servidor_separados():
    _compilar("dois_computadores/teste1_servidor")
    _compilar("dois_computadores/teste1_cliente")
    servidor = subprocess.Popen([_exe("dois_computadores/teste1_servidor")], cwd=ROOT, text=True,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        servidor.stdin.write("\n")   # IP do cliente: Enter = 127.0.0.1
        servidor.stdin.flush()
        time.sleep(0.3)
        cliente = executar("dois_computadores/teste1_cliente",
                           stdin="\n+\n3\n5\n/\n10\n4\nfim\n", timeout=30)
        log_servidor = servidor.communicate(timeout=15)[0]
    finally:
        servidor.kill()
    assert cliente.returncode == 0, cliente.stderr
    assert "Resultado: 8" in cliente.stdout
    assert "Resultado: 2.5" in cliente.stdout
    assert "Servidor recebeu: 3 + 5 | resultado: 8" in log_servidor
    assert "Servidor recebeu: 10 / 4 | resultado: 2.5" in log_servidor
    assert "Cliente encerrou a calculadora." in log_servidor


@precisa_gpp
def test_teste2_fibonacci_no_outro_computador():
    nome = "dois_computadores/teste2_dois_computadores"
    _compilar(nome)
    worker = subprocess.Popen([_exe(nome), "--worker", "5001"], cwd=ROOT, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        time.sleep(0.5)
        exe = executar(nome, stdin="\n", timeout=30)
    finally:
        worker.kill()
    log = worker.communicate()[0]
    assert exe.returncode == 0, exe.stderr
    assert "Fatorial de 5 (computador 1): 120" in exe.stdout
    assert "Fibonacci (computador 2): [0, 1, 1, 2, 3, 5, 8, 13]" in exe.stdout
    assert "Executando fibonacci(i64)" in log
