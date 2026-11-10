"""Valida os benchmarks sem depender de valores fixos para os tempos."""
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from codegen import CppCodeGenerator


@unittest.skipUnless(shutil.which("g++"), "g++ nao encontrado")
class BenchmarkTests(unittest.TestCase):
    def test_benchmarks(self):
        for numero in (8, 9, 10):
            with self.subTest(teste=numero):
                nome = f"teste{numero}_paralelo"
                compilacao = subprocess.run(
                    [sys.executable, "main.py", f"tests/{nome}.minipar", nome],
                    cwd=ROOT, capture_output=True, text=True, timeout=180,
                )
                self.assertEqual(compilacao.returncode, 0, compilacao.stdout + compilacao.stderr)
                exe = ROOT / "output" / (nome + CppCodeGenerator.executable_suffix())
                execucao = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, text=True, timeout=60)
                self.assertEqual(execucao.returncode, 0, execucao.stderr)
                saida = execucao.stdout
                for linha in ("Atividades: 160", "Checksum sequencial: 4854810",
                              "Checksum paralelo: 4854810", "Resultados: OK"):
                    self.assertIn(linha + "\n", saida)
                for campo in ("Tempo sequencial (s)", "Tempo paralelo (s)", "Speedup"):
                    valor = re.search(re.escape(campo) + r":\s*([0-9.eE+-]+)", saida)
                    self.assertIsNotNone(valor, campo)
                    self.assertGreater(float(valor.group(1)), 0)

                if numero >= 9:
                    linhas = saida.split("Mandelbrot:\n", 1)[1].splitlines()[:20]
                    esperado = (ROOT / "tests" / "expected_results" / f"teste{numero}_sequencial.expected.txt").read_text(encoding="utf-8").splitlines()[-20:]
                    self.assertEqual(linhas, ["".join(linha[1:-1].split(", ")) for linha in esperado])

                if numero == 10:
                    linhas = saida.split("Sierpinski grau 4 (81 x 81):\n", 1)[1].splitlines()[:81]
                    tapete = ["#"]
                    for _ in range(4):
                        largura = len(tapete[0])
                        tapete = ([linha * 3 for linha in tapete]
                                  + [linha + " " * largura + linha for linha in tapete]
                                  + [linha * 3 for linha in tapete])
                    self.assertEqual(linhas, tapete)


if __name__ == "__main__":
    unittest.main()
