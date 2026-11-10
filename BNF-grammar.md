# Gramática Formal BNF — Linguagem MiniPar 2026.1

**Projeto:** MiniPar-Improvement — Compilador da Linguagem MiniPar 2026.1 Orientada a Objetos  
**Autores:** Emanuele Vitória de Jesus Lima · Jose Lucas de Oliveira Quintela · Luiz Miguel de Melo Bomfim  
**Instituição:** Universidade Federal de Alagoas — Instituto de Computação · Ciência da Computação  
**Disciplina:** Compiladores — Prof. Arturo Hernandez Dominguez  
**Repositório:** https://github.com/luizwhirl/minipar-improvement  

---

> Esta gramática foi derivada diretamente da implementação real do compilador
> (arquivos `src/lexer.py`, `src/parser.py` e `src/ast_nodes.py`), cruzada com
> o relatório técnico do projeto e as especificações formais fornecidas pelo professor.
> Ela descreve **toda** a sintaxe aceita pelo compilador MiniPar 2026.1.
>
> **Acréscimos 2026.2:** paralelismo com `fork` e `join`, com a subtarefa
> alocada a um núcleo da CPU (`core`) ou a outro computador (`host`).
> Ver a seção 6.3 e as produções marcadas na gramática consolidada.

---

## Sumário

1. [Notação utilizada](#1-notação-utilizada)
2. [Tokens (Análise Léxica)](#2-tokens-análise-léxica)
3. [Programa](#3-programa)
4. [Declarações](#4-declarações)
5. [Comandos](#5-comandos)
6. [Blocos Sequencial e Paralelo](#6-blocos-sequencial-e-paralelo)
7. [Estruturas de Controle](#7-estruturas-de-controle)
8. [Orientação a Objetos](#8-orientação-a-objetos)
9. [Funções](#9-funções)
10. [Expressões](#10-expressões)
11. [Comunicação por Canais](#11-comunicação-por-canais)
12. [Coleções](#12-coleções)
13. [Entrada e Saída](#13-entrada-e-saída)
14. [Tipos e Literais](#14-tipos-e-literais)
15. [Biblioteca Nativa](#15-biblioteca-nativa)
16. [Comentários](#16-comentários)
17. [Gramática Consolidada (BNF Completa)](#17-gramática-consolidada-bnf-completa)

---

## 1. Notação utilizada

| Símbolo | Significado |
|---------|-------------|
| `::=` | Definição de produção |
| `\|` | Alternativa (ou) |
| `{ x }` | Zero ou mais repetições de `x` |
| `[ x ]` | Opcional (zero ou uma ocorrência de `x`) |
| `( x )` | Agrupamento |
| `"token"` | Terminal literal (palavra reservada ou símbolo) |
| `<não-terminal>` | Símbolo não-terminal |

---

## 2. Tokens (Análise Léxica)

O analisador léxico (`src/lexer.py`) produz os seguintes tokens a partir do código-fonte.  
Comentários iniciados por `#` são descartados pelo lexer antes da geração de tokens.

### 2.1 Palavras Reservadas

```
class  extends  new  func  var
if  else  while  do  for  in
break  continue  return
seq  par  this
c_channel  send  receive  input  print  matrix
fork  join  on  core  host          (2026.2)
true  false
number  int  string  bool  void  list  dict
```

### 2.2 Literais

```bnf
<NUMBER>         ::= <digito> { <digito> } [ "." <digito> { <digito> } ]
<STRING_LITERAL> ::= '"' { <caractere> } '"'
<BOOL_LITERAL>   ::= "true" | "false"
<IDENTIFIER>     ::= ( <letra> | "_" ) { <letra> | <digito> | "_" }
```

### 2.3 Operadores

| Categoria | Tokens |
|-----------|--------|
| Aritméticos | `+`  `-`  `*`  `/`  `%` |
| Relacionais | `==`  `!=`  `<`  `>`  `<=`  `>=` |
| Lógicos | `&&`  `\|\|`  `!` |
| Atribuição | `=` |

### 2.4 Delimitadores

```
(  )  {  }  [  ]  .  ;  ,
```

### 2.5 Tipos declaráveis

```bnf
<tipo> ::= "number" | "int" | "string" | "bool" | "void" | "list" | "dict"
```

---

## 3. Programa

O programa MiniPar é uma sequência de zero ou mais declarações e comandos no nível global.

```bnf
<programa> ::= { <declaracao_global> | <comando> }

<declaracao_global> ::= <declaracao_classe>
                      | <declaracao_funcao>
                      | <declaracao_variavel>
```

---

## 4. Declarações

### 4.1 Declaração de Variável

```bnf
<declaracao_variavel> ::= "var" <IDENTIFIER> [ "=" <expressao> ] ";"
                        | <tipo> <IDENTIFIER> [ "=" <expressao> ] ";"
```

**Exemplos:**

```minipar
var x = 42;
var nome = "MiniPar";
number total = 0;
bool ativo = true;
```

### 4.2 Declaração de Função

```bnf
<declaracao_funcao> ::= "func" <IDENTIFIER> "(" [ <lista_parametros> ] ")" <bloco_seq>

<lista_parametros> ::= <parametro> { "," <parametro> }

<parametro> ::= [ <tipo> ] <IDENTIFIER>
```

**Exemplos:**

```minipar
func somar(a, b) {
    return a + b;
}

func calcular(number x, number y) {
    return x * y;
}
```

### 4.3 Declaração de Classe

```bnf
<declaracao_classe> ::= "class" <IDENTIFIER> [ "extends" <IDENTIFIER> ] "{"
                            { <membro_classe> }
                        "}"

<membro_classe> ::= "var" <declaracao_variavel>
                  | "func" <declaracao_funcao>
```

**Exemplos:**

```minipar
class Animal {
    var nome = "Animal";
    func falar() {
        print("...");
    }
}

class Cachorro extends Animal {
    func falar() {
        print("Au!");
    }
}
```

---

## 5. Comandos

```bnf
<comando> ::= <declaracao_variavel>
            | <atribuicao>
            | <bloco_seq>
            | <bloco_par>
            | <comando_if>
            | <comando_while>
            | <comando_do_while>
            | <comando_for>
            | <comando_print>
            | <comando_send>
            | <comando_return>
            | <comando_break>
            | <comando_continue>
            | <chamada_funcao> ";"
            | <chamada_metodo> ";"
            | <expressao_fork> ";"          (* 2026.2 *)
            | <expressao_join> ";"          (* 2026.2 *)
```

### 5.1 Atribuição

A atribuição suporta identificadores simples, propriedades de objetos e indexação de coleções:

```bnf
<atribuicao> ::= <alvo_atribuicao> "=" <expressao> ";"

<alvo_atribuicao> ::= <IDENTIFIER>
                    | <expressao_posfixo> "." <IDENTIFIER>
                    | <expressao_posfixo> "[" <expressao> "]"
```

**Exemplos:**

```minipar
x = 10;
objeto.campo = 42;
lista[0] = "primeiro";
```

### 5.2 Comando Print

```bnf
<comando_print> ::= "print" "(" [ <expressao> { "," <expressao> } ] ")" ";"
```

**Exemplos:**

```minipar
print("Olá, mundo!");
print("Valor:", x, "e", y);
```

### 5.3 Comando Return

```bnf
<comando_return> ::= "return" [ <expressao> ] ";"
```

### 5.4 Comandos Break e Continue

```bnf
<comando_break>    ::= "break" ";"
<comando_continue> ::= "continue" ";"
```

> `break` e `continue` são válidos somente dentro de laços (`while`, `do-while`, `for`).  
> O analisador semântico reporta erro se forem usados fora de laço.

---

## 6. Blocos Sequencial e Paralelo

### 6.1 Bloco Sequencial (SEQ)

Executa os comandos internos em ordem, da mesma forma que um bloco tradicional.

```bnf
<bloco_seq> ::= "seq" "{" { <comando> } "}"
              | "{" { <comando> } "}"
```

O `seq` é opcional: blocos com chaves `{ }` são tratados como sequenciais por padrão.

### 6.2 Bloco Paralelo (PAR)

Cada comando interno é executado como uma `std::thread` independente em C++.  
As threads são sincronizadas por `join()` ao final do bloco.

```bnf
<bloco_par> ::= "par" "{" { <comando> } "}"
```

**Exemplo:**

```minipar
par {
    seq { print("Thread A"); }
    seq { print("Thread B"); }
    seq { print("Thread C"); }
}
```

### 6.3 Fork e Join (2026.2)

- **Fork:** a tarefa principal dispara uma subtarefa independente e continua
  executando. A subtarefa é sempre uma chamada de função ou de método.
- **Join:** a tarefa principal (pai) espera a subtarefa terminar e coleta o
  valor que ela retornou.

O destino de cada subtarefa faz parte da produção, porque ela pode ir para
um **núcleo da CPU** ou para **outro computador**:

```bnf
<expressao_fork> ::= "fork" <chamada> [ "on" <destino_fork> ]

<chamada>        ::= <chamada_funcao>
                   | <chamada_metodo>

<destino_fork>   ::= "core" "(" <expressao> ")"
                   | "host" "(" <expressao> "," <expressao> ")"

<expressao_join> ::= "join" <expressao_unaria>
```

| Destino | Significado |
|---------|-------------|
| `on core(n)` | Executa no núcleo `n` da CPU (núcleos numerados a partir de 1) |
| `on host(ip, porta)` | Envia a chamada a outro computador, que executa e devolve o resultado |
| *(sem `on`)* | O sistema operacional escolhe o núcleo |

O valor de `fork` é um identificador de tarefa (tipo `task`), guardado numa
variável ou numa lista. `join` recebe essa tarefa e vale o retorno da
subtarefa. Os dois podem aparecer sozinhos como comando (`join t;`).

**Exemplo:**

```minipar
func avaliar_lote(avaliador, inicio, fim) { ... return soma; }

var t1 = fork avaliar_lote("Professor", 0, 40) on core(1);
var t2 = fork avaliar_lote("Monitor 1", 40, 80) on core(2);
var t3 = fork fatorial(10) on host("192.168.0.12", 5001);

# fork dentro de laço, com as tarefas numa lista
var tarefas = [];
for (var k = 0; k < 4; k = k + 1) {
    tarefas.append(fork avaliar_lote("Monitor", k * 10, k * 10 + 10) on core(k + 1));
}

var total = join t1 + join t2;      # espera as duas e soma os resultados
print("10! =", join t3);
for (var t in tarefas) { print(join t); }
```

**Código de três endereços gerado** para:

```minipar
func avaliar_lote(avaliador, inicio, fim) { return fim - inicio; }
var t1 = fork avaliar_lote("Professor", 0, 40) on core(1);
var r = join t1;
```

```
func avaliar_lote:
t0 = fim - inicio
return t0
endfunc avaliar_lote
param "Professor"
param 0
param 40
t2 = fork avaliar_lote, 3 on core 1
t1 = t2
t3 = join t1
r = t3
```

`fork` funciona como um `call` que não espera: os argumentos vão por `param`
e o temporário recebe o identificador da tarefa. O temporário `t1` é pulado
porque o programa já usa uma variável com esse nome.

---

## 7. Estruturas de Controle

### 7.1 If / Else

```bnf
<comando_if> ::= "if" "(" <expressao> ")" <comando>
                 [ "else" <comando> ]
```

**Exemplos:**

```minipar
if (x > 0) {
    print("positivo");
}

if (x > 0) {
    print("positivo");
} else {
    print("negativo ou zero");
}

# Encadeamento if-else-if
if (x > 0) {
    print("positivo");
} else if (x < 0) {
    print("negativo");
} else {
    print("zero");
}
```

### 7.2 While

```bnf
<comando_while> ::= "while" "(" <expressao> ")" <comando>
```

**Exemplo:**

```minipar
while (i < 10) {
    i = i + 1;
}
```

### 7.3 Do-While

```bnf
<comando_do_while> ::= "do" <comando> "while" "(" <expressao> ")" [ ";" ]
```

**Exemplo:**

```minipar
do {
    tentativas = tentativas + 1;
} while (tentativas < 5);
```

### 7.4 For

O `for` suporta tanto o estilo clássico (inicializador; condição; incremento) quanto o estilo iterador (`for var x in colecao`):

```bnf
<comando_for> ::= "for" "(" <for_classico> | <for_iterador> ")" <comando>

<for_classico> ::= [ <inicializador_for> ] ";" [ <expressao> ] ";" [ <incremento_for> ]

<inicializador_for> ::= "var" <IDENTIFIER> [ "=" <expressao> ]
                      | <tipo> <IDENTIFIER> [ "=" <expressao> ]
                      | <alvo_atribuicao> "=" <expressao>
                      | <expressao>

<incremento_for>    ::= <alvo_atribuicao> "=" <expressao>
                      | <expressao>

<for_iterador>      ::= "var" <IDENTIFIER> "in" <expressao>
```

**Exemplos:**

```minipar
# For clássico
for (var i = 0; i < 10; i = i + 1) {
    print(i);
}

# For iterador
for (var item in lista) {
    print(item);
}

# For com range()
for (var i in range(5)) {
    print(i);
}
```

---

## 8. Orientação a Objetos

### 8.1 Instanciação com new

```bnf
<expressao_new> ::= "new" <IDENTIFIER> "(" [ <lista_argumentos> ] ")"
```

**Exemplo:**

```minipar
var obj = new MinhaClasse();
var rede = new RedeNeural(0.5);
```

### 8.2 Acesso a Propriedades

```bnf
<acesso_propriedade> ::= <expressao_posfixo> "." <IDENTIFIER>
```

**Exemplo:**

```minipar
print(neuronio.peso);
```

### 8.3 Chamada de Método

```bnf
<chamada_metodo> ::= <expressao_posfixo> "." <IDENTIFIER> "(" [ <lista_argumentos> ] ")"
```

**Exemplo:**

```minipar
neuronio.treinar();
algoritmo.ordenar();
rede.feedforward(x1, x2);
```

### 8.4 Atribuição de Propriedade

```bnf
<atrib_propriedade> ::= <expressao_posfixo> "." <IDENTIFIER> "=" <expressao> ";"
```

**Exemplo:**

```minipar
this.peso = this.peso + 0.01;
obj.nome = "novo";
```

### 8.5 Referência a this

Dentro de métodos de uma classe, `this` refere-se à instância corrente.

```bnf
<expressao_this> ::= "this"
```

### 8.6 Herança

```bnf
<declaracao_classe> ::= "class" <IDENTIFIER> "extends" <IDENTIFIER> "{"
                            { <membro_classe> }
                        "}"
```

**Exemplo:**

```minipar
class Cachorro extends Animal {
    func latir() {
        print("Au!");
    }
}
```

---

## 9. Funções

### 9.1 Chamada de Função

```bnf
<chamada_funcao> ::= <IDENTIFIER> "(" [ <lista_argumentos> ] ")"

<lista_argumentos> ::= <expressao> { "," <expressao> }
```

### 9.2 Recursão

Funções podem se chamar recursivamente sem nenhuma sintaxe especial:

```minipar
func fatorial(n) {
    if (n <= 1) {
        return 1;
    }
    return n * fatorial(n - 1);
}
```

---

## 10. Expressões

As expressões seguem a hierarquia de precedência implementada no parser (da menor para a maior precedência):

```bnf
<expressao> ::= <expressao_fork>                    (* 2026.2 *)
              | <expressao_ou>

<expressao_ou>  ::= <expressao_e> { "||" <expressao_e> }

<expressao_e>   ::= <expressao_comp> { "&&" <expressao_comp> }

<expressao_comp> ::= <expressao_termo>
                     { ( "==" | "!=" | "<" | ">" | "<=" | ">=" ) <expressao_termo> }

<expressao_termo> ::= <expressao_fator> { ( "+" | "-" ) <expressao_fator> }

<expressao_fator> ::= <expressao_unaria> { ( "*" | "/" | "%" ) <expressao_unaria> }

<expressao_unaria> ::= ( "-" | "+" | "!" ) <expressao_unaria>
                     | "join" <expressao_unaria>        (* 2026.2 *)
                     | <expressao_posfixo>

<expressao_posfixo> ::= <expressao_primaria>
                        { "." <IDENTIFIER> [ "(" [ <lista_argumentos> ] ")" ]
                        | "[" <expressao> "]"
                        }

<expressao_primaria> ::= <NUMBER>
                       | <STRING_LITERAL>
                       | <BOOL_LITERAL>
                       | <IDENTIFIER> [ "(" [ <lista_argumentos> ] ")" ]
                       | "this"
                       | <expressao_new>
                       | <expressao_c_channel>
                       | <expressao_receive>
                       | <expressao_input>
                       | <expressao_lista>
                       | <expressao_matrix>
                       | "(" <expressao> ")"
```

### Tabela de Precedência (maior nível = avaliado primeiro)

| Nível | Operadores | Associatividade |
|-------|-----------|-----------------|
| 7 (mais alta) | `()` `[]` `.` (posfixo) | esquerda |
| 6 | `!` `-` (unário) `+` (unário) `join` | direita |
| 5 | `*` `/` `%` | esquerda |
| 4 | `+` `-` | esquerda |
| 3 | `==` `!=` `<` `>` `<=` `>=` | esquerda |
| 2 | `&&` | esquerda |
| 1 | `\|\|` | esquerda |
| 0 (mais baixa) | `fork` *chamada* `on` *destino* | não se combina com operadores |

---

## 11. Comunicação por Canais

A comunicação entre processos/computadores é feita via canais TCP implementados pela classe `MiniParChannel` no C++ gerado.

### 11.1 Criação de Canal

```bnf
<expressao_c_channel> ::= "c_channel" "(" <expressao> "," <expressao> ")"
```

O primeiro argumento é o endereço IP (string) e o segundo é a porta (número).

**Exemplo:**

```minipar
var canal = c_channel("127.0.0.1", 5000);
var canal_remoto = c_channel("192.168.1.10", 8080);
```

### 11.2 Envio de Mensagem (Send)

```bnf
<comando_send> ::= "send" "(" <expressao> "," <expressao> ")" ";"
```

O primeiro argumento é o canal e o segundo é a mensagem a enviar.

**Exemplo:**

```minipar
send(canal, "Hello Server");
send(canal, resultado);
```

### 11.3 Recebimento de Mensagem (Receive)

```bnf
<expressao_receive> ::= "receive" "(" <expressao> ")"
```

**Exemplo:**

```minipar
var mensagem = receive(canal);
var dado = receive(c_channel("127.0.0.1", 5000));
```

---

## 12. Coleções

### 12.1 Lista (Array)

```bnf
<expressao_lista> ::= "[" [ <expressao> { "," <expressao> } ] "]"
```

**Exemplos:**

```minipar
var vazio = [];
var numeros = [1, 2, 3, 4, 5];
var misto = [0, "texto", true];
```

### 12.2 Indexação

```bnf
<expressao_indice> ::= <expressao_posfixo> "[" <expressao> "]"
```

**Exemplo:**

```minipar
var primeiro = lista[0];
var ultimo = lista[len(lista) - 1];
```

### 12.3 Atribuição por Índice

```bnf
<atrib_indice> ::= <expressao_posfixo> "[" <expressao> "]" "=" <expressao> ";"
```

**Exemplo:**

```minipar
lista[0] = 99;
matriz[i][j] = "#";
```

### 12.4 Matriz (Matrix)

Cria uma matriz bidimensional de `linhas × colunas` inicializada com um valor padrão.

```bnf
<expressao_matrix> ::= "matrix" "(" <expressao> "," <expressao> "," <expressao> ")"
```

**Exemplo:**

```minipar
var tela = matrix(9, 9, " ");       # matriz 9×9 de espaços
var zeros = matrix(3, 3, 0);        # matriz 3×3 de zeros
```

---

## 13. Entrada e Saída

### 13.1 Saída (Print)

```bnf
<comando_print> ::= "print" "(" [ <expressao> { "," <expressao> } ] ")" ";"
```

Múltiplos argumentos são impressos separados por espaço seguidos de `\n`.

### 13.2 Entrada (Input)

```bnf
<expressao_input> ::= "input" "(" [ <expressao> ] ")"
```

Lê uma linha da entrada padrão (stdin). O argumento opcional é exibido como prompt antes da leitura.

**Exemplos:**

```minipar
var nome = input("Seu nome: ");
var valor = input();
var numero = to_number(input("Digite um número: "));
```

---

## 14. Tipos e Literais

### 14.1 Número

```bnf
<literal_numero> ::= <digito> { <digito> } [ "." { <digito> } ]
```

Representa inteiros e ponto flutuante. No C++ gerado, literais inteiros são de 64 bits
(`long long`, ex.: `42` vira `42LL`) e literais com ponto são `double`. Assim, somas longas
e o gerador LCG dos testes 8–10 (`estado * 1103515245 + 12345`) não estouram 32 bits.

> Atenção: `/` entre dois inteiros faz divisão inteira no C++ gerado (`7 / 2` vale `3`).
> Para divisão real, use um operando com ponto: `7 / 2.0`.


**Exemplos:** `0`, `42`, `3.14`, `0.5`

### 14.2 String

```bnf
<literal_string> ::= '"' { <caractere_string> } '"'

<caractere_string> ::= <qualquer_caractere_exceto_aspas_e_barra>
                     | "\\" "n"    # newline
                     | "\\" "t"    # tab
                     | "\\" '"'    # aspas duplas
                     | "\\" "\\"   # barra invertida
```

### 14.3 Booleano

```bnf
<literal_bool> ::= "true" | "false"
```

### 14.4 Identificador

```bnf
<IDENTIFIER> ::= ( <letra> | "_" ) { <letra> | <digito> | "_" }

<letra>  ::= "A" | ... | "Z" | "a" | ... | "z"
<digito> ::= "0" | ... | "9"
```

---

## 15. Biblioteca Nativa

As seguintes funções são reconhecidas pelo analisador semântico e traduzidas diretamente pelo gerador de código C++:

| Função MiniPar | Assinatura | Descrição |
|---------------|------------|-----------|
| `print(...)` | `print(expr, ...)` | Imprime na saída padrão |
| `input([prompt])` | `input()` / `input(expr)` | Lê linha do stdin |
| `exp(x)` | `exp(number)` → `number` | Exponencial natural (eˣ) |
| `random()` | `random()` → `number` | Número aleatório entre 0 e 1 |
| `range(n)` / `range(a,b)` | `range(int)` → `list` | Gera sequência inteira |
| `len(col)` | `len(list\|string)` → `number` | Comprimento de coleção |
| `to_number(s)` | `to_number(string)` → `number` | Converte string para número |
| `parse_ints(s)` | `parse_ints(string)` → `list` | Parseia inteiros de string separados por espaço |
| `format(x, casas)` | `format(number, int)` → `string` | Número com casas decimais fixas, como `f"{x:.4f}"` (2026.2) |
| `clock()` | `clock()` → `number` | Relógio de alta precisão em segundos, como `time.perf_counter()` (2026.2) |
| `int(x)` | `int(number\|string)` → `int` | Inteiro de 64 bits, truncando em direção a zero (2026.2) |
| `floor(x)` | `floor(number)` → `int` | Maior inteiro ≤ x, em 64 bits (2026.2) |

Indexação de string (2026.2): `s[i]` devolve um texto de 1 caractere, como no Python.
Índices negativos contam do fim (`s[-1]`). Em listas, matrizes e strings, um índice fora
dos limites encerra o programa com `[ERRO DE EXECUCAO] Indice i fora dos limites`.


### Métodos de Lista (acesso via ponto)

| Método | Descrição |
|--------|-----------|
| `.append(v)` / `.push_back(v)` | Adiciona elemento ao final |
| `.pop()` | Remove e retorna o último elemento |
| `.size()` | Retorna o tamanho da lista |

---

## 16. Comentários

```bnf
<comentario> ::= "#" { <qualquer_caractere> } <fim_de_linha>
```

Comentários iniciam com `#` e vão até o final da linha. São descartados pelo lexer.

**Exemplos:**

```minipar
# Isso é um comentário de linha inteira
var x = 10; # Comentário ao final da linha
```

---

## 17. Gramática Consolidada (BNF Completa)

A seguir a gramática completa em formato BNF, em ordem de definição:

```bnf
(* ============================================================ *)
(*       GRAMÁTICA BNF — LINGUAGEM MINIPAR 2026.1               *)
(*       Compilador: minipar-improvement                        *)
(*       Repositório: github.com/luizwhirl/minipar-improvement  *)
(* ============================================================ *)


(* ─── ESTRUTURA GLOBAL ─── *)

<programa> ::= { <declaracao_global> | <comando> }

<declaracao_global> ::= <declaracao_classe>
                      | <declaracao_funcao>
                      | <declaracao_variavel>


(* ─── DECLARAÇÕES ─── *)

<declaracao_variavel> ::= "var" <IDENTIFIER> [ "=" <expressao> ] ";"
                        | <tipo> <IDENTIFIER> [ "=" <expressao> ] ";"

<declaracao_funcao>   ::= "func" <IDENTIFIER> "(" [ <lista_parametros> ] ")" <bloco_seq>

<lista_parametros>    ::= <parametro> { "," <parametro> }
<parametro>           ::= [ <tipo> ] <IDENTIFIER>

<declaracao_classe>   ::= "class" <IDENTIFIER> [ "extends" <IDENTIFIER> ]
                          "{" { <membro_classe> } "}"

<membro_classe>       ::= "var" <declaracao_variavel>
                        | "func" <declaracao_funcao>


(* ─── COMANDOS ─── *)

<comando> ::= <declaracao_variavel>
            | <atribuicao>
            | <bloco_seq>
            | <bloco_par>
            | <comando_if>
            | <comando_while>
            | <comando_do_while>
            | <comando_for>
            | <comando_print>
            | <comando_send>
            | <comando_return>
            | <comando_break>
            | <comando_continue>
            | <chamada_funcao> ";"
            | <chamada_metodo> ";"
            | <expressao_fork> ";"          (* 2026.2 *)
            | <expressao_join> ";"          (* 2026.2 *)

<atribuicao>        ::= <alvo_atribuicao> "=" <expressao> ";"
<alvo_atribuicao>   ::= <IDENTIFIER>
                      | <expressao_posfixo> "." <IDENTIFIER>
                      | <expressao_posfixo> "[" <expressao> "]"

<comando_print>     ::= "print" "(" [ <expressao> { "," <expressao> } ] ")" ";"
<comando_send>      ::= "send"  "(" <expressao> "," <expressao> ")" ";"
<comando_return>    ::= "return" [ <expressao> ] ";"
<comando_break>     ::= "break" ";"
<comando_continue>  ::= "continue" ";"


(* ─── BLOCOS ─── *)

<bloco_seq> ::= "seq" "{" { <comando> } "}"
              | "{" { <comando> } "}"

<bloco_par> ::= "par" "{" { <comando> } "}"


(* ─── ESTRUTURAS DE CONTROLE ─── *)

<comando_if>       ::= "if" "(" <expressao> ")" <comando> [ "else" <comando> ]

<comando_while>    ::= "while" "(" <expressao> ")" <comando>

<comando_do_while> ::= "do" <comando> "while" "(" <expressao> ")" [ ";" ]

<comando_for>      ::= "for" "(" <for_cabecalho> ")" <comando>

<for_cabecalho>    ::= <for_classico>
                     | <for_iterador>

<for_classico>     ::= [ <inicializador_for> ] ";" [ <expressao> ] ";" [ <incremento_for> ]

<inicializador_for> ::= "var"  <IDENTIFIER> [ "=" <expressao> ]
                      | <tipo> <IDENTIFIER> [ "=" <expressao> ]
                      | <alvo_atribuicao> "=" <expressao>
                      | <expressao>

<incremento_for>   ::= <alvo_atribuicao> "=" <expressao>
                     | <expressao>

<for_iterador>     ::= "var" <IDENTIFIER> "in" <expressao>


(* ─── ORIENTAÇÃO A OBJETOS ─── *)

<expressao_new>         ::= "new" <IDENTIFIER> "(" [ <lista_argumentos> ] ")"
<acesso_propriedade>    ::= <expressao_posfixo> "." <IDENTIFIER>
<chamada_metodo>        ::= <expressao_posfixo> "." <IDENTIFIER> "(" [ <lista_argumentos> ] ")"
<atrib_propriedade>     ::= <expressao_posfixo> "." <IDENTIFIER> "=" <expressao> ";"
<expressao_this>        ::= "this"


(* ─── COMUNICAÇÃO POR CANAIS ─── *)

<expressao_c_channel>   ::= "c_channel" "(" <expressao> "," <expressao> ")"
<expressao_receive>     ::= "receive" "(" <expressao> ")"
(* send já listado em <comando_send> *)


(* ─── COLEÇÕES ─── *)

<expressao_lista>   ::= "[" [ <expressao> { "," <expressao> } ] "]"
<expressao_indice>  ::= <expressao_posfixo> "[" <expressao> "]"
<atrib_indice>      ::= <expressao_posfixo> "[" <expressao> "]" "=" <expressao> ";"
<expressao_matrix>  ::= "matrix" "(" <expressao> "," <expressao> "," <expressao> ")"


(* ─── ENTRADA E SAÍDA ─── *)

<expressao_input>   ::= "input" "(" [ <expressao> ] ")"
(* print já listado em <comando_print> *)


(* ─── FORK E JOIN (2026.2) ─── *)

<expressao_fork>     ::= "fork" <chamada> [ "on" <destino_fork> ]
<chamada>            ::= <chamada_funcao> | <chamada_metodo>
<destino_fork>       ::= "core" "(" <expressao> ")"
                       | "host" "(" <expressao> "," <expressao> ")"
<expressao_join>     ::= "join" <expressao_unaria>


(* ─── EXPRESSÕES (hierarquia de precedência) ─── *)

<expressao>          ::= <expressao_fork>
                       | <expressao_ou>

<expressao_ou>       ::= <expressao_e> { "||" <expressao_e> }

<expressao_e>        ::= <expressao_comp> { "&&" <expressao_comp> }

<expressao_comp>     ::= <expressao_termo>
                         { ( "==" | "!=" | "<" | ">" | "<=" | ">=" )
                           <expressao_termo> }

<expressao_termo>    ::= <expressao_fator> { ( "+" | "-" ) <expressao_fator> }

<expressao_fator>    ::= <expressao_unaria> { ( "*" | "/" | "%" ) <expressao_unaria> }

<expressao_unaria>   ::= ( "-" | "+" | "!" ) <expressao_unaria>
                       | "join" <expressao_unaria>
                       | <expressao_posfixo>

<expressao_posfixo>  ::= <expressao_primaria>
                         { "." <IDENTIFIER> [ "(" [ <lista_argumentos> ] ")" ]
                         | "[" <expressao> "]"
                         }

<expressao_primaria> ::= <NUMBER>
                       | <STRING_LITERAL>
                       | <BOOL_LITERAL>
                       | <IDENTIFIER> [ "(" [ <lista_argumentos> ] ")" ]
                       | "this"
                       | <expressao_new>
                       | <expressao_c_channel>
                       | <expressao_receive>
                       | <expressao_input>
                       | <expressao_lista>
                       | <expressao_matrix>
                       | "(" <expressao> ")"

<lista_argumentos>   ::= <expressao> { "," <expressao> }
<chamada_funcao>     ::= <IDENTIFIER> "(" [ <lista_argumentos> ] ")"


(* ─── TIPOS E LITERAIS ─── *)

<tipo>           ::= "number" | "int" | "string" | "bool" | "void" | "list" | "dict"

<NUMBER>         ::= <digito> { <digito> } [ "." { <digito> } ]
<STRING_LITERAL> ::= '"' { <caractere_string> } '"'
<BOOL_LITERAL>   ::= "true" | "false"
<IDENTIFIER>     ::= ( <letra> | "_" ) { <letra> | <digito> | "_" }

<caractere_string> ::= <qualquer_char_exceto_aspas_e_barra>
                     | "\n" | "\t" | '\"' | "\\"

<letra>  ::= "A" | ... | "Z" | "a" | ... | "z"
<digito> ::= "0" | ... | "9"


(* ─── COMENTÁRIOS ─── *)

<comentario> ::= "#" { <qualquer_char> } <nova_linha>
(* Descartados pelo lexer — não aparecem na AST *)
```

---

## Notas de Implementação

### Inferência de Tipos

O analisador semântico (`src/semantic.py`) usa inferência simples de tipos com as seguintes regras:

| Expressão | Tipo inferido |
|-----------|--------------|
| Literal numérico | `number` |
| Literal string | `string` |
| Literal booleano | `bool` |
| Lista literal `[...]` | `list` |
| `fork f(...)` (2026.2) | `task` |
| `join t` (2026.2) | `unknown` (tipo do retorno da subtarefa) |
| `matrix(...)` | `matrix` |
| `c_channel(...)` | `c_channel` |
| `receive(...)` | `string` |
| `input(...)` | `string` |
| `new Classe(...)` | `Classe` |
| `this` | nome da classe atual |
| `op` relacional / lógico | `bool` |
| `"a" + "b"` (concatenação) | `string` |
| Operação aritmética | `number` |
| Identificador | tipo declarado na tabela de símbolos |
| Desconhecido | `unknown` (compatível com qualquer tipo) |

### Regras Semânticas Verificadas

| Regra | Erro reportado |
|-------|---------------|
| Redeclaração no mesmo escopo | `Variável 'x' já declarada.` |
| Uso antes de declaração | `Variável 'x' não declarada.` |
| Incompatibilidade de tipos | `Tipo incompatível em atribuição de 'x'.` |
| Função não declarada | `Função 'f' não declarada.` |
| Aridade errada (função) | `Função 'f' espera N argumento(s), recebeu M.` |
| Classe não declarada | `Classe 'C' não declarada.` |
| Superclasse não declarada | `Superclasse 'S' não declarada.` |
| Método inexistente | `Método 'm' não declarado em 'C'.` |
| Atributo inexistente | `Atributo 'a' não declarado em 'C'.` |
| `break`/`continue` fora de laço | `'break' usado fora de laço de repetição.` |
| **(2026.2)** Núcleo inválido | `core(0) invalido: os nucleos sao numerados com inteiros a partir de 1.` |
| **(2026.2)** Núcleo não numérico | `O numero do nucleo em core(...) deve ser numerico, recebido string.` |
| **(2026.2)** Host com ip/porta inválidos | `O endereco em host(ip, porta) deve ser uma string...` · `Porta 70000 invalida...` |
| **(2026.2)** Método enviado a outro computador | `fork para host(...) exige uma funcao global...` |
| **(2026.2)** Função nativa enviada a outro computador | `fork para host(...) exige uma funcao declarada no programa...` |
| **(2026.2)** Argumento não serializável no host | `Argumento 1 de 'f' (tipo c_channel) nao pode ser enviado a outro computador...` |
| **(2026.2)** `join` de algo que não é tarefa | `'join' espera uma tarefa criada por fork, recebeu number.` |
| **(2026.2)** `join` duplicado | `Tarefa 't' ja foi aguardada com join (join duplicado).` |
| **(2026.2)** Aviso: resultado do fork descartado | `Resultado do fork descartado: a tarefa nunca podera ser aguardada com join.` |
| **(2026.2)** Aviso: tarefa nunca aguardada | `Tarefa 't' criada com fork nunca e aguardada com join...` |

> O `join` duplicado é detectado por caminho do programa: depois de um `if`,
> a tarefa só conta como aguardada se houve `join` nos dois ramos. Dentro de
> laços, a verificação vale só no mesmo nível de laço em que a tarefa foi criada.

### Geração de Código C++20

| Construto MiniPar | Código C++ gerado |
|-------------------|------------------|
| `class C { ... }` | `class C { public: ... };` |
| `new C(args)` | `std::make_shared<C>(args)` |
| `obj.metodo(args)` | `obj->metodo(args)` |
| `obj.campo` | `obj->campo` |
| `par { a; b; }` | `std::vector<std::thread>` + `emplace_back` + `join` |
| `c_channel(ip, porta)` | `std::make_shared<MiniParChannel>(ip, porta)` |
| `send(canal, msg)` | `canal->sendData(__to_string(msg))` |
| `receive(canal)` | `canal->receiveData()` |
| `[1, 2, 3]` | `std::vector<double>{1LL, 2LL, 3LL}` |
| `lista[i]` | `__index(lista, i)` (confere os limites) |
| `matrix(l, c, v)` | `__make_matrix(l, c, v)` |
| `exp(x)` | `std::exp(x)` |
| `random()` | `random_val()` |
| `to_number(s)` | `std::stod(s)` |
| `len(x)` | `x.size()` |
| `range(n)` | `__minipar_range(n)` |
| `input(p)` | `input(p)` (helper C++) |
| `format(x, n)` / `clock()` / `int(x)` / `floor(x)` | `__format` / `__clock` / `__int` / `__mp_floor` |

---

*Gramática gerada em 15 de junho de 2026 — MiniPar-Improvement v2026.1*
