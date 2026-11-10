"""
Teste 11 (MiniCompilador de expressões infixadas em MiniPar 2026.2).

Executa tests/teste11/teste11_minicompilador.minipar para as 3 expressões do
enunciado e confere o Assembly ARMv7 gravado em output/teste11_expressaoN.arm:

1. o arquivo gerado é igual ao versionado em tests/teste11/arm/;
2. se houver assembler e emulador ARM na máquina (arm-linux-gnueabihf-as e
   qemu-arm), o .arm é montado e executado, e o valor final de r8 tem que ser
   o resultado da expressão. Sem essas ferramentas, essa parte é pulada.

Como rodar (na raiz do projeto):
    python -m pytest tests/test_teste11.py
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from test_regressao import OUTPUT_DIR, ROOT, compilar, executar, precisa_gpp

PROGRAMA = "teste11/teste11_minicompilador"
ARM_VERSIONADO = ROOT / "tests" / "teste11" / "arm"
ESPERADO = {1: 22, 2: -84, 3: 22}   # ((2+4)*7)-(5*4), ((10 -8*7)+4)*2, ((2+4)*7)-(5*4)


@pytest.fixture(scope="module")
def arquivos_arm():
    r = compilar(PROGRAMA)
    assert r.returncode == 0, f"Falha ao compilar:\n{r.stdout}\n{r.stderr}"
    for k in ESPERADO:
        (OUTPUT_DIR / f"teste11_expressao{k}.arm").unlink(missing_ok=True)
    exe = executar(PROGRAMA, stdin="\n", timeout=30)
    assert exe.returncode == 0, exe.stderr
    return {k: OUTPUT_DIR / f"teste11_expressao{k}.arm" for k in ESPERADO}


@precisa_gpp
@pytest.mark.parametrize("k", sorted(ESPERADO))
def test_arm_gerado_igual_ao_versionado(arquivos_arm, k):
    gerado = arquivos_arm[k]
    assert gerado.exists(), f"{gerado} nao foi gravado"
    assert gerado.read_text() == (ARM_VERSIONADO / gerado.name).read_text()


@precisa_gpp
@pytest.mark.skipif(not (shutil.which("arm-linux-gnueabihf-as") and shutil.which("qemu-arm")),
                    reason="assembler/emulador ARM nao instalados")
@pytest.mark.parametrize("k", sorted(ESPERADO))
def test_arm_executa_e_r8_tem_o_resultado(arquivos_arm, k, tmp_path: Path):
    # Igual ao CPULATOR, trocando o laco final "b ." por uma saida que devolve r8
    fonte = arquivos_arm[k].read_text()
    linhas = [("    MOV    r0, r8\n    MOV    r7, #1\n    SVC    #0" if l.strip().startswith("b .") else l)
              for l in fonte.splitlines()]
    (tmp_path / "p.s").write_text("\n".join(linhas) + "\n")
    subprocess.run(["arm-linux-gnueabihf-as", "-march=armv7-a", "p.s", "-o", "p.o"], cwd=tmp_path, check=True)
    subprocess.run(["arm-linux-gnueabihf-ld", "p.o", "-o", "p"], cwd=tmp_path, check=True)
    codigo = subprocess.run(["qemu-arm", str(tmp_path / "p")], timeout=10).returncode
    assert codigo == ESPERADO[k] % 256   # o codigo de saida e o byte baixo de r8
