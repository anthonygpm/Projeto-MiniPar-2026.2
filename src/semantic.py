from __future__ import annotations
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from ast_nodes import (
    ASTNode, Program, VarDecl, Assignment, PrintStmt, IdentifierExpr, BinaryExpr,
    UnaryExpr, NumberExpr, StringExpr, BoolExpr, NullExpr, SeqBlock, ParBlock, IfStmt, WhileStmt,
    DoWhileStmt, ForStmt, BreakStmt, ContinueStmt, InputExpr,
    ClassDecl, FuncDecl, ReturnStmt, MethodCall, FuncCallExpr, PropertyAccess, PropertyAssign, NewExpr, ThisExpr,
    CChannelExpr, SendStmt, ReceiveExpr, ListLiteral, MatrixCreateExpr, IndexExpr, IndexAssign,
    ForkExpr, JoinExpr, CoreTarget, HostTarget
)

# Funções nativas: nome -> quantidade de argumentos aceita (None = variável)
_BUILTINS = {
    "exp": 1, "random": 0, "range": None, "len": 1, "to_number": 1, "parse_ints": 1,
    "format": 2, "clock": 0, "int": 1, "floor": 1,
    "write_file": 2,   # write_file(caminho, texto): grava o texto num arquivo (2026.2)
}

# Tipos que podem viajar pela rede num fork ... on host(...)
_SERIALIZABLE_TYPES = ("number", "int", "string", "bool", "list", "matrix", "var", "unknown")

@dataclass
class Symbol:
    name: str
    type: str
    params: List[str] = field(default_factory=list)
    attributes: Dict[str, str] = field(default_factory=dict)
    methods: Dict[str, List[str]] = field(default_factory=dict)
    loop_depth: int = 0          # profundidade de laço onde a tarefa (fork) foi declarada

class SemanticAnalyzer:
    def __init__(self) -> None:
        self._scopes: List[Dict[str, Symbol]] = []
        self._has_errors = False
        self._current_function: Optional[str] = None
        self._current_class: Optional[str] = None
        self._classes: Dict[str, Symbol] = {}
        self._functions: Dict[str, Symbol] = {}
        self._loop_depth = 0
        # Diagnósticos estruturados (linha, tipo, mensagem) para as interfaces
        self.diagnostics: List[Dict[str, object]] = []
        # Fork/Join: tarefas já aguardadas com certeza neste caminho do programa
        self._joined: set = set()
        # Fork/Join: tarefas declaradas (símbolo, linha, contexto) e as que foram usadas depois
        self._task_symbols: List[tuple] = []
        self._referenced_tasks: set = set()
        self._enter_scope()

    def _enter_scope(self) -> None: self._scopes.append({})
    def _exit_scope(self) -> None:
        if len(self._scopes) > 1: self._scopes.pop()

    def _get_context(self) -> str:
        return f" (Funcao: {self._current_function})" if self._current_function else ""

    def _define_symbol(self, name: str, type_: str, line: int, params: Optional[List[str]] = None) -> None:
        if name in self._scopes[-1]:
            print(f"[ERRO SEMANTICO] Linha {line}{self._get_context()}: Variavel '{name}' ja declarada.", file=sys.stderr)
            self._has_errors = True
        else: self._scopes[-1][name] = Symbol(name=name, type=type_, params=params or [])

    def _lookup(self, name: str) -> Optional[Symbol]:
        for scope in reversed(self._scopes):
            if name in scope: return scope[name]
        return None

    def _report(self, line: int, message: str) -> None:
        print(f"[ERRO SEMANTICO] Linha {line}{self._get_context()}: {message}", file=sys.stderr)
        self.diagnostics.append({"kind": "erro", "line": line, "message": message})
        self._has_errors = True

    def _warn(self, line: int, message: str, context: str = "") -> None:
        """Aviso: não interrompe a compilação, mas aponta um provável engano."""
        print(f"[AVISO SEMANTICO] Linha {line}{context}: {message}")
        self.diagnostics.append({"kind": "aviso", "line": line, "message": message})

    def _infer_type(self, node: Optional[ASTNode]) -> str:
        if node is None: return "unknown"
        if isinstance(node, NumberExpr): return "number"
        if isinstance(node, StringExpr): return "string"
        if isinstance(node, BoolExpr): return "bool"
        if isinstance(node, NullExpr): return "null"
        if isinstance(node, InputExpr): return "string"
        if isinstance(node, CChannelExpr): return "c_channel"
        if isinstance(node, ReceiveExpr): return "string"
        if isinstance(node, ListLiteral): return "list"
        if isinstance(node, MatrixCreateExpr): return "matrix"
        if isinstance(node, ForkExpr): return "task"
        if isinstance(node, JoinExpr): return "unknown"   # tipo do retorno da subtarefa
        if isinstance(node, NewExpr): return node.class_name
        if isinstance(node, ThisExpr): return self._current_class or "unknown"
        if isinstance(node, IdentifierExpr):
            sym = self._lookup(node.name)
            return sym.type if sym else "unknown"
        if isinstance(node, UnaryExpr):
            return "bool" if node.op == "!" else self._infer_type(node.operand)
        if isinstance(node, BinaryExpr):
            lt, rt = self._infer_type(node.left), self._infer_type(node.right)
            if node.op in ("==", "!=", "<", ">", "<=", ">=", "&&", "||"): return "bool"
            if node.op == "+" and (lt == "string" or rt == "string"): return "string"
            if node.op == "+" and (lt == "list" or rt == "list"): return "list"
            return "number"
        if isinstance(node, PropertyAccess):
            obj_type = self._infer_type(node.object)
            cls = self._classes.get(obj_type)
            if cls and node.property_name in cls.attributes: return cls.attributes[node.property_name]
            return "unknown"
        if isinstance(node, MethodCall):
            return "unknown"
        if isinstance(node, FuncCallExpr):
            if node.name in ("random", "exp"): return "number"
            if node.name in ("range", "parse_ints"): return "list"
            if node.name == "format": return "string"
            if node.name == "clock": return "number"
            if node.name in ("int", "floor"): return "int"
            return "unknown"
        if isinstance(node, IndexExpr): return "unknown"
        return "unknown"

    def _types_compatible(self, declared: str, actual: str) -> bool:
        if declared in ("var", "unknown") or actual == "unknown": return True
        # null vale como referência a qualquer objeto, e uma variável iniciada com null
        # pode depois receber um objeto (nunca um número, texto ou bool)
        if actual == "null": return declared not in ("number", "int", "string", "bool")
        if declared == "null": return actual not in ("number", "int", "string", "bool")
        if declared == "int" and actual == "number": return True
        if declared == "number" and actual == "int": return True
        return declared == actual

    def _collect_declarations(self, program: Program) -> None:
        for stmt in program.statements:
            if isinstance(stmt, FuncDecl):
                self._functions[stmt.name] = Symbol(stmt.name, "FUNC", params=stmt.params)
            elif isinstance(stmt, ClassDecl):
                attrs = {a.name: a.type for a in stmt.attributes}
                methods = {m.name: m.params for m in stmt.methods}
                self._classes[stmt.name] = Symbol(stmt.name, "CLASS", attributes=attrs, methods=methods)

    def validate_node(self, node: ASTNode) -> None:
        if node is None: return

        if isinstance(node, VarDecl):
            self.validate_node(node.init_value)
            actual_type = self._infer_type(node.init_value)
            declared_type = actual_type if node.type == "var" and actual_type != "unknown" else node.type
            if not self._types_compatible(declared_type, actual_type):
                self._report(node.line, f"Tipo incompativel em '{node.name}': esperado {declared_type}, recebido {actual_type}.")
            self._define_symbol(node.name, declared_type, node.line)
            if isinstance(node.init_value, ForkExpr):
                sym = self._scopes[-1][node.name]
                sym.loop_depth = self._loop_depth
                self._task_symbols.append((sym, node.line, self._get_context()))
        elif isinstance(node, Assignment):
            sym = self._lookup(node.name)
            if sym is None:
                self._report(node.line, f"Variavel '{node.name}' nao declarada.")
            self.validate_node(node.value)
            if sym and isinstance(node.value, ForkExpr):
                # A variável passa a guardar uma tarefa nova, ainda não aguardada
                self._joined.discard(id(sym))
            if sym and not self._types_compatible(sym.type, self._infer_type(node.value)):
                self._report(node.line, f"Tipo incompativel em atribuicao de '{node.name}'.")
        elif isinstance(node, PrintStmt):
            for arg in node.arguments: self.validate_node(arg)
        elif isinstance(node, SendStmt):
            self.validate_node(node.channel)
            self.validate_node(node.message)
        elif isinstance(node, CChannelExpr):
            self.validate_node(node.ip)
            self.validate_node(node.port)
        elif isinstance(node, ReceiveExpr):
            self.validate_node(node.channel)
        elif isinstance(node, ListLiteral):
            for e in node.elements: self.validate_node(e)
        elif isinstance(node, MatrixCreateExpr):
            self.validate_node(node.rows)
            self.validate_node(node.cols)
            self.validate_node(node.init_value)
        elif isinstance(node, IndexExpr):
            self.validate_node(node.object)
            self.validate_node(node.index)
        elif isinstance(node, IndexAssign):
            self.validate_node(node.target)
            self.validate_node(node.value)
        elif isinstance(node, IdentifierExpr):
            sym = self._lookup(node.name)
            if sym is None:
                self._report(node.line, f"Variavel '{node.name}' nao declarada.")
            elif sym.type == "task":
                self._referenced_tasks.add(id(sym))
        elif isinstance(node, BinaryExpr):
            self.validate_node(node.left)
            self.validate_node(node.right)
            if node.op in ("+", "-", "*", "/", "%"):
                lt, rt = self._infer_type(node.left), self._infer_type(node.right)
                if node.op != "+" and (lt not in ("number", "int", "var", "unknown") or rt not in ("number", "int", "var", "unknown")):
                    self._report(node.line, f"Operador '{node.op}' exige operandos numericos.")
        elif isinstance(node, UnaryExpr):
            self.validate_node(node.operand)
        elif isinstance(node, (SeqBlock, ParBlock)):
            self._enter_scope()
            for stmt in node.statements: self._validate_statement(stmt)
            self._exit_scope()
        elif isinstance(node, IfStmt):
            self.validate_node(node.condition)
            # Uma tarefa só conta como aguardada depois do if se houve join nos dois ramos
            before = set(self._joined)
            self._validate_branch(node.then_branch)
            after_then = self._joined
            self._joined = set(before)
            if node.else_branch: self._validate_branch(node.else_branch)
            self._joined = after_then & self._joined
        elif isinstance(node, WhileStmt):
            self.validate_node(node.condition)
            self._loop_depth += 1
            self.validate_node(node.body)
            self._loop_depth -= 1
        elif isinstance(node, DoWhileStmt):
            self._loop_depth += 1
            self.validate_node(node.body)
            self._loop_depth -= 1
            self.validate_node(node.condition)
        elif isinstance(node, ForStmt):
            self._enter_scope()
            if node.iterator_name:
                self.validate_node(node.iterable)
                self._define_symbol(node.iterator_name, "var", node.line)
            else:
                self.validate_node(node.initializer)
                self.validate_node(node.condition)
                self.validate_node(node.increment)
            self._loop_depth += 1
            self.validate_node(node.body)
            self._loop_depth -= 1
            self._exit_scope()
        elif isinstance(node, (BreakStmt, ContinueStmt)):
            if self._loop_depth == 0:
                self._report(node.line, f"'{node.__class__.__name__.replace('Stmt', '').lower()}' usado fora de laco.")
        elif isinstance(node, ClassDecl):
            if node.superclass and node.superclass not in self._classes:
                self._report(node.line, f"Superclasse '{node.superclass}' nao declarada.")
            self._define_symbol(node.name, "CLASS", node.line)
            self._enter_scope()
            old_class = self._current_class
            self._current_class = node.name
            for attr in node.attributes: self.validate_node(attr)
            for method in node.methods: self.validate_node(method)
            self._current_class = old_class
            self._exit_scope()
        elif isinstance(node, FuncDecl):
            self._define_symbol(node.name, "FUNC", node.line, node.params)
            self._enter_scope()
            old_function = self._current_function
            self._current_function = node.name
            old_joined, self._joined = self._joined, set()
            for p in node.params: self._define_symbol(p, "var", node.line)
            self.validate_node(node.body)
            self._joined = old_joined
            self._current_function = old_function
            self._exit_scope()
        elif isinstance(node, ReturnStmt):
            if node.value: self.validate_node(node.value)
        elif isinstance(node, MethodCall):
            obj_type = self._infer_type(node.object)
            cls = self._classes.get(obj_type)
            if cls and node.method_name not in cls.methods:
                self._report(node.line, f"Metodo '{node.method_name}' nao declarado em '{obj_type}'.")
            elif cls and len(cls.methods[node.method_name]) != len(node.arguments):
                self._report(node.line, f"Metodo '{node.method_name}' espera {len(cls.methods[node.method_name])} argumento(s), recebeu {len(node.arguments)}.")
            self.validate_node(node.object)
            for arg in node.arguments: self.validate_node(arg)
        elif isinstance(node, FuncCallExpr):
            if node.name not in self._functions and node.name not in _BUILTINS:
                self._report(node.line, f"Funcao '{node.name}' nao declarada.")
            elif node.name in self._functions and len(self._functions[node.name].params) != len(node.arguments):
                self._report(node.line, f"Funcao '{node.name}' espera {len(self._functions[node.name].params)} argumento(s), recebeu {len(node.arguments)}.")
            elif node.name not in self._functions and _BUILTINS[node.name] is not None and _BUILTINS[node.name] != len(node.arguments):
                self._report(node.line, f"Funcao nativa '{node.name}' espera {_BUILTINS[node.name]} argumento(s), recebeu {len(node.arguments)}.")
            for arg in node.arguments: self.validate_node(arg)
        elif isinstance(node, PropertyAccess):
            self.validate_node(node.object)
            obj_type = self._infer_type(node.object)
            cls = self._classes.get(obj_type)
            if cls and node.property_name not in cls.attributes:
                self._report(node.line, f"Atributo '{node.property_name}' nao declarado em '{obj_type}'.")
        elif isinstance(node, PropertyAssign):
            self.validate_node(node.object)
            self.validate_node(node.value)
            obj_type = self._infer_type(node.object)
            cls = self._classes.get(obj_type)
            if cls and node.property_name not in cls.attributes:
                self._report(node.line, f"Atributo '{node.property_name}' nao declarado em '{obj_type}'.")
        elif isinstance(node, NewExpr):
            if node.class_name not in self._classes:
                self._report(node.line, f"Classe '{node.class_name}' nao declarada.")
            for arg in node.arguments: self.validate_node(arg)
        elif isinstance(node, ThisExpr):
            pass
        elif isinstance(node, InputExpr):
            if node.prompt: self.validate_node(node.prompt)
        elif isinstance(node, ForkExpr):
            self._validate_fork(node)
        elif isinstance(node, JoinExpr):
            self._validate_join(node)

    # ------------------------------------------------------------------
    # Fork / Join
    # ------------------------------------------------------------------
    def _validate_statement(self, stmt: ASTNode) -> None:
        """Valida um comando de um bloco; avisa quando o resultado de um fork é descartado."""
        if isinstance(stmt, ForkExpr):
            self._warn(stmt.line, "Resultado do fork descartado: a tarefa nunca podera ser aguardada com join. Use: var t = fork ...;", self._get_context())
        self.validate_node(stmt)

    def _validate_branch(self, branch: Optional[ASTNode]) -> None:
        if isinstance(branch, (SeqBlock, ParBlock)): self.validate_node(branch)
        else: self._validate_statement(branch)

    def _validate_fork(self, node: ForkExpr) -> None:
        call = node.call
        self.validate_node(call)   # função/método existe e aridade confere
        dest = node.destination
        if isinstance(dest, CoreTarget):
            self.validate_node(dest.index)
            t = self._infer_type(dest.index)
            if t not in ("number", "int", "var", "unknown"):
                self._report(dest.line, f"O numero do nucleo em core(...) deve ser numerico, recebido {t}.")
            elif isinstance(dest.index, NumberExpr) and ("." in dest.index.value or int(dest.index.value) < 1):
                self._report(dest.line, f"core({dest.index.value}) invalido: os nucleos sao numerados com inteiros a partir de 1.")
        elif isinstance(dest, HostTarget):
            self.validate_node(dest.ip)
            self.validate_node(dest.port)
            ip_t, port_t = self._infer_type(dest.ip), self._infer_type(dest.port)
            if ip_t not in ("string", "var", "unknown"):
                self._report(dest.line, f"O endereco em host(ip, porta) deve ser uma string, recebido {ip_t}.")
            if port_t not in ("number", "int", "var", "unknown"):
                self._report(dest.line, f"A porta em host(ip, porta) deve ser numerica, recebido {port_t}.")
            elif isinstance(dest.port, NumberExpr) and ("." in dest.port.value or not 1 <= int(dest.port.value) <= 65535):
                self._report(dest.line, f"Porta {dest.port.value} invalida: use um inteiro entre 1 e 65535.")
            # Outro computador só recebe dados: nada de objetos, canais ou métodos
            if isinstance(call, MethodCall):
                self._report(node.line, f"fork para host(...) exige uma funcao global: o metodo '{call.method_name}' depende de um objeto que nao pode ser enviado pela rede.")
            elif isinstance(call, FuncCallExpr) and call.name not in self._functions:
                self._report(node.line, f"fork para host(...) exige uma funcao declarada no programa; '{call.name}' e nativa.")
            else:
                for i, arg in enumerate(call.arguments, start=1):
                    t = self._infer_type(arg)
                    if t not in _SERIALIZABLE_TYPES:
                        self._report(node.line, f"Argumento {i} de '{call.name}' (tipo {t}) nao pode ser enviado a outro computador; use number, string, bool ou list.")

    def _validate_join(self, node: JoinExpr) -> None:
        self.validate_node(node.task)
        t = self._infer_type(node.task)
        if t not in ("task", "var", "unknown"):
            self._report(node.line, f"'join' espera uma tarefa criada por fork, recebeu {t}.")
            return
        if isinstance(node.task, IdentifierExpr):
            sym = self._lookup(node.task.name)
            # Dentro de laços a mesma linha roda várias vezes: só detecta duplicação
            # no mesmo nível de laço em que a tarefa foi criada.
            if sym and sym.type == "task" and self._loop_depth == sym.loop_depth:
                if id(sym) in self._joined:
                    self._report(node.line, f"Tarefa '{node.task.name}' ja foi aguardada com join (join duplicado).")
                else:
                    self._joined.add(id(sym))

    def _warn_unjoined_tasks(self) -> None:
        for sym, line, context in self._task_symbols:
            if id(sym) not in self._referenced_tasks:
                self._warn(line, f"Tarefa '{sym.name}' criada com fork nunca e aguardada com join; o programa pode terminar antes dela.", context)

    def analyze(self, program: Program) -> bool:
        self._collect_declarations(program)
        for stmt in program.statements: self._validate_statement(stmt)
        self._warn_unjoined_tasks()
        return not self._has_errors
