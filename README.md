# Compilador MiniPar 2026.2

Compilador da linguagem **MiniPar**, uma linguagem imperativa e orientada a objetos com
blocos paralelos, canais de comunicação e, a partir desta versão, paralelismo explícito
com **Fork/Join** em núcleos da CPU e em outros computadores.

O compilador é escrito em Python e gera C++20, que é compilado com `g++ -O3` em um
executável nativo. Ele tem três interfaces: menu no terminal, IDE web (Web 1) e uma
interface didática (Web 2), que mostra o resultado de cada fase do compilador.

> Projeto da disciplina de Compiladores — Instituto de Computação, Universidade Federal
> de Alagoas (UFAL), prof. Arturo Hernandez Dominguez, 2026.2.

## Equipe

| Integrante | Matrícula |
| --- | --- |
| Anthony Gabriel Paulino de Moura | 202407213 |
| Pedro Cabral Gomes | 202407410 |
| Lucas Teodosio Maciel de Oliveira | 202433572 |
| Vinicius Gabriel Silva Santiago | 202407222 |

## Pipeline

```
código .minipar
   │  Lexer            src/lexer.py        → tokens
   │  Parser           src/parser.py       → AST (src/ast_nodes.py)
   │  Semântico        src/semantic.py     → AST validada + tabela de símbolos
   │  Gerador TAC      src/tac.py          → output/<nome>.tac
   │  Gerador C++      src/codegen.py      → output/<nome>.cpp  (runtime em src/cpp_template.py)
   ▼  g++ -std=c++20 -O3 -pthread          → output/<nome>[.exe]
```

## Requisitos

- Python 3.10 ou superior (testado com 3.13)
- `g++` com suporte a C++20 (Linux: g++ 11+; Windows: MinGW-w64)
- Dependências Python: `pip install -r requeriments.txt` (Flask e pytest)

No Windows, o compilador acrescenta `-lws2_32` e gera `.exe` automaticamente.

## Como usar

### Compilar e executar um programa

```bash
python main.py tests/teste8_paralelo.minipar
./output/teste8_paralelo            # Linux
.\output\teste8_paralelo.exe        # Windows (PowerShell)
```

### Menu interativo e interfaces web

```bash
python main.py
```

- **[1] Modo Terminal:** lista os programas de `tests/` e roda um ou todos.
- **[2] Modo Web:** abre o servidor em `http://127.0.0.1:5000`.
  - `/`: **Web 1**, IDE com explorador de arquivos, editor, C++ e TAC gerados e terminal.
  - `/didatico`: **Web 2**, interface didática com tokens por categoria, AST gráfica,
    erros ligados à linha, tabela de símbolos por escopo, TAC, C++ e execução com stdin.

## A linguagem em um exemplo

```minipar
func dobro(x) {
    return x * 2;
}

var t1 = fork dobro(20) on core(1);                 # núcleo 1 da CPU
var t2 = fork dobro(21);                            # o sistema operacional escolhe
var t3 = fork dobro(22) on host("192.168.0.12", 5001);  # outro computador

print("Resultados:", join t1, join t2, join t3);    # 40 42 44
```

Novidades da versão 2026.2:

| Recurso | Exemplo |
| --- | --- |
| Fork em núcleo | `var t = fork f(x) on core(2);` |
| Fork em outro computador | `var t = fork f(x) on host(ip, 5001);` |
| Fork sem destino | `var t = fork f(x);` |
| Join (devolve o retorno de `f`) | `var r = join t;` · `join t1 + join t2` |
| Forks em listas e laços | `tarefas.append(fork f(k) on core(k + 1));` |
| `null` | `var esquerda = null;` |
| Texto + número | `print("total: " + n);` |
| Gravar arquivo | `write_file("saida.arm", codigo);` |
| Builtins de benchmark | `clock()`, `int(x)`, `floor(x)`, `format(x, casas)` |

A gramática completa está em [`BNF-grammar.md`](BNF-grammar.md).

## Fork em outro computador

O destino `host(ip, porta)` envia a chamada para outro computador que roda o **mesmo
programa compilado** em modo worker.

1. Compile o programa nos dois computadores:
   `python main.py tests/fork_join/demo_host.minipar`
2. No computador 2, libere a porta no firewall (Windows, PowerShell como administrador):
   `New-NetFirewallRule -DisplayName "MiniPar worker" -Direction Inbound -Protocol TCP -LocalPort 5001 -Action Allow`
3. No computador 2, inicie o worker: `.\output\demo_host.exe --worker 5001`
4. No computador 1, teste a conexão (`Test-NetConnection <ip> -Port 5001`) e rode
   `.\output\demo_host.exe`, informando o IP do computador 2.

Para testar em um só computador, abra dois terminais e deixe o IP em branco
(`127.0.0.1`).

Os argumentos enviados pela rede podem ser números, textos, booleanos e listas. Métodos,
objetos e canais ficam no computador local; o semântico rejeita esses casos com uma
mensagem explicando o motivo.

**Problemas comuns no Windows**
- O executável fecha sem mensagem: desative o Anaconda (`conda deactivate`), que coloca
  no PATH uma `libstdc++` incompatível com o MinGW.
- `ping` não responde: o Windows bloqueia ICMP; use `Test-NetConnection`.

## Programas de teste

| Teste | Arquivo(s) em `tests/` | Assunto |
| --- | --- | --- |
| 1 | `teste1_calculadora_cliente_servidor`, `dois_computadores/teste1_*` | Calculadora cliente-servidor com canais |
| 2 | `teste2_fatorial_fibonacci_par`, `dois_computadores/teste2_*` | Fatorial e Fibonacci em paralelo |
| 3 | `teste3_neuronio` | Neurônio simples com classes |
| 4 | `teste4_rede_neural_xor` | Rede neural XOR |
| 5 | `teste5_recomendacao` | Recomendação de produtos |
| 6 | `teste6_quicksort_classes` | Quicksort com classes (lê o vetor do teclado) |
| 7 | `teste7_quicksort_iterativo_tac` | Quicksort iterativo e TAC |
| 8 | `teste8_sequencial`, `teste8_paralelo`, `dois_computadores/teste8_paralelo_host` | Benchmark de avaliação de atividades com fork/join |
| 9 | `teste9_sequencial`, `teste9_paralelo` | Teste 8 + fractal de Mandelbrot |
| 10 | `teste10_sequencial`, `teste10_paralelo` | Teste 9 + tapete de Sierpinski |
| 11 | `teste11/teste11_minicompilador` | Minicompilador de expressões para Assembly ARMv7 |

Exemplos de Fork/Join ficam em `tests/fork_join/`. O `erros_fork_join.minipar` mostra os
erros semânticos de fork/join.

### Teste 11 no CPULATOR

1. `python main.py tests/teste11/teste11_minicompilador.minipar` e execute o binário,
   apertando Enter para usar as 3 expressões do enunciado.
2. Em [cpulator.01xz.net](https://cpulator.01xz.net/), escolha **ARMv7 generic** e cole
   um dos arquivos `tests/teste11/arm/teste11_expressaoN.arm` (também gerados em `output/`).
3. Compile and Load (F5), Continue (F3): o resultado fica em `r8`
   (22, −84 e 22 para as três expressões).

## Testes automatizados

```bash
python -m pytest              # todos (cerca de 3 minutos)
python -m pytest -k teste4    # só um
```

| Arquivo | O que verifica |
| --- | --- |
| `tests/test_regressao.py` | Todos os programas compilam; as saídas batem com `tests/expected_results/`; TAC do Teste 7; comando do g++ em Linux e Windows |
| `tests/test_fork_join.py` | Fork para um worker real, várias subtarefas no mesmo host, erro claro com o worker desligado |
| `tests/test_dois_computadores.py` | Testes 1, 2 e 8 com processos separados conversando por TCP |
| `tests/test_teste11.py` | `.arm` do Teste 11 iguais aos versionados e, com `arm-linux-gnueabihf-as` e `qemu-arm` instalados, executados com `r8` correto |
| `tests/test_benchmark_8_10.py` | Testes 8 a 10 paralelos com resultados iguais aos sequenciais |

Para incluir um programa na regressão, crie `tests/expected_results/<nome>.expected.txt`
com a saída esperada.

## Estrutura do repositório

```
├── main.py                 ponto de entrada (CLI e escolha de interface)
├── menu.py                 menu do modo terminal
├── test_orchestrator.py    sessões de teste com dois terminais
├── app.py, web_pipeline.py servidor Flask e API das fases (/api/*)
├── templates/, static/     páginas da Web 1 e da Web 2
├── src/                    compilador (lexer, parser, AST, semântico, TAC, C++ e runtime)
├── tests/                  programas MiniPar, saídas esperadas e testes pytest
├── BNF-grammar.md          gramática da linguagem
└── output/                 arquivos gerados (.tac, .cpp, executáveis, .arm)
```

## Créditos

Esta versão parte do compilador MiniPar 2026.1
([minipar-improvement](https://github.com/luizwhirl/minipar-improvement)), de Emanuele
Vitória de Jesus Lima, Jose Lucas de Oliveira Quintela e Luiz Miguel de Melo Bomfim.
