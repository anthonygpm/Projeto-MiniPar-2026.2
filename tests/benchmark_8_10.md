# Benchmarks dos testes 8 a 10

## Resultado observado

Uma execução de cada teste em 10/11/2026, em Linux (WSL2), com processador
Intel Core i5-12450H. Os tempos incluem o trabalho descrito abaixo e não
incluem a compilação nem a impressão dos fractais.

| Teste | Tempo sequencial (s) | Tempo paralelo (s) | Speedup | Comparação |
| --- | ---: | ---: | ---: | --- |
| 8 | 0,115612 | 0,0371021 | 3,11605× | OK |
| 9 | 0,114798 | 0,0357422 | 3,21184× | OK |
| 10 | 0,110428 | 0,0325326 | 3,39438× | OK |

Em todos os casos, as duas execuções processaram 160 atividades e produziram
o checksum 4.854.810. Estes valores são de uma única medição, não médias;
podem variar em outras execuções.

Cada programa executa 160 avaliações, distribuídas em quatro lotes de 40.
O teste 9 acrescenta o cálculo de Mandelbrot em uma quinta tarefa; o teste 10
acrescenta o tapete de Sierpinski em uma sexta. O tapete tem grau 4, com
81 por 81 caracteres, e é exibido no terminal (`#` representa preenchimento).

O benchmark usa `clock()` antes e depois do trabalho, incluindo o custo de
criação e sincronização das tarefas paralelas, e informa o speedup como tempo
sequencial dividido pelo paralelo. O escalonador escolhe as CPUs, portanto
o número de tarefas não garante uso de núcleos físicos distintos. A saída
mostra se os resultados de cada lote e dos fractais coincidem entre as duas
execuções. Os tempos variam conforme a máquina e a carga do sistema.

Para garantir cargas iguais e reproduzíveis, cada atividade usa uma quantidade
determinística de iterações e uma operação acumulada, em vez do atraso com
gerador pseudoaleatório global dos programas Python. O checksum torna o
trabalho observável; ele não é uma medição do tempo dos programas originais.
No teste 10, o Sierpinski também é calculado na execução sequencial para que
os dois tempos incluam o mesmo trabalho, diferente do original do professor,
que desenha com Turtle apenas na etapa paralela.
