from __future__ import annotations
import os
import subprocess
import sys
from typing import Optional
from ast_nodes import (
    ASTNode, Program, VarDecl, Assignment, PrintStmt, SeqBlock, ParBlock, BinaryExpr, 
    UnaryExpr, NumberExpr, StringExpr, BoolExpr, NullExpr, IdentifierExpr, IfStmt, WhileStmt,
    DoWhileStmt, ForStmt, BreakStmt, ContinueStmt, InputExpr,
    ClassDecl, FuncDecl, ReturnStmt, MethodCall, FuncCallExpr, PropertyAccess, PropertyAssign, NewExpr, ThisExpr,
    CChannelExpr, SendStmt, ReceiveExpr, ListLiteral, MatrixCreateExpr, IndexExpr, IndexAssign,
    ForkExpr, JoinExpr, CoreTarget, HostTarget
)
from cpp_template import _CPP_HEADER


def _walk(node):
    """Percorre todos os nós da AST (inclusive dentro de listas)."""
    if isinstance(node, list):
        for item in node: yield from _walk(item)
        return
    if not isinstance(node, ASTNode): return
    yield node
    for value in vars(node).values(): yield from _walk(value)


class CppCodeGenerator:
    def __init__(self) -> None:
        # Dentro de um método: as lambdas do fork precisam capturar 'this'
        self._in_method = False
        # Funções enviadas a outro computador (fork ... on host): ganham registro no worker
        self._host_functions: set[str] = set()

    def _null_ref_type(self, name: str, default_class: str | None) -> str:
        """Tipo C++ de um campo/variável iniciado com null (2026.2).

        Procura no programa uma atribuição de objeto a esse nome
        (`x = new C()` ou `obj.x = new C()`) e usa a classe encontrada; sem
        isso, um campo de classe vira referência à própria classe (caso da
        árvore: `var esquerda = null;` dentro de `class No`).
        """
        for n in _walk(self._program.statements):
            if isinstance(n, (Assignment, PropertyAssign)) and isinstance(n.value, NewExpr):
                alvo = n.name if isinstance(n, Assignment) else n.property_name
                if alvo == name:
                    return f"std::shared_ptr<{n.value.class_name}>"
        return f"std::shared_ptr<{default_class}>" if default_class else "std::shared_ptr<void>"

    def _scan_host_forks(self, program: Program) -> None:
        for n in _walk(program.statements):
            if isinstance(n, ForkExpr) and isinstance(n.destination, HostTarget) and isinstance(n.call, FuncCallExpr):
                self._host_functions.add(n.call.name)

    @staticmethod
    def _host_functor(name: str) -> str:
        """Objeto-função que o worker usa para chamar `name` com os tipos recebidos."""
        return (f"struct __mp_fn_{name} {{\n"
                f"    static constexpr const char* name = \"{name}\";\n"
                f"    template<typename... A> auto operator()(A&&... a) const {{ return {name}(std::forward<A>(a)...); }}\n"
                f"}};\n\n")

    @staticmethod
    def executable_suffix() -> str:
        """Extensão do executável gerado: '.exe' só no Windows."""
        return ".exe" if sys.platform == "win32" else ""

    @staticmethod
    def gcc_command(cpp_path: str, exe_path: str) -> list[str]:
        """Linha de comando do g++ para a plataforma atual.

        A Winsock (-lws2_32) só existe no Windows; no Linux/macOS os sockets
        fazem parte da libc e não precisam de biblioteca extra.
        """
        cmd = ["g++", "-std=c++20", "-O3", cpp_path, "-o", exe_path, "-pthread"]
        if sys.platform == "win32":
            cmd.append("-lws2_32")
        return cmd

    @staticmethod
    def _escape_string(value: str) -> str:
        res = []
        for ch in value:
            if ch == "\n": res.append("\\n")
            elif ch == "\t": res.append("\\t")
            elif ch == '"': res.append('\\"')
            elif ch == "\\": res.append("\\\\")
            else: res.append(ch)
        return "".join(res)

    def _translate_expression(self, node: Optional[ASTNode]) -> str:
        if node is None: return "0"
        if isinstance(node, NumberExpr):
            # Inteiros em 64 bits (long long), mais próximos dos inteiros do Python:
            # somas longas e o gerador LCG (estado * 1103515245) não estouram 32 bits
            return node.value if "." in node.value else f"{node.value}LL"
        # std::string (e não const char*): permite concatenar com + e indexar s[i]
        if isinstance(node, StringExpr): return f'std::string("{self._escape_string(node.value)}")'
        if isinstance(node, BoolExpr): return "true" if node.value else "false"
        if isinstance(node, NullExpr): return "nullptr"
        if isinstance(node, IdentifierExpr): return node.name
        if isinstance(node, UnaryExpr): return f"({node.op}{self._translate_expression(node.operand)})"
        if isinstance(node, BinaryExpr):
            return f"({self._translate_expression(node.left)} {node.op} {self._translate_expression(node.right)})"
        
        if isinstance(node, NewExpr):
            args = ", ".join(self._translate_expression(a) for a in node.arguments)
            return f"std::make_shared<{node.class_name}>({args})"
        if isinstance(node, ThisExpr): return "this"
        if isinstance(node, PropertyAccess):
            if node.property_name == "size": return f"{self._translate_expression(node.object)}.size()"
            return f"{self._translate_expression(node.object)}->{node.property_name}"
        
        if isinstance(node, MethodCall):
            args = ", ".join(self._translate_expression(a) for a in node.arguments)
            m_name = node.method_name
            if m_name in ("append", "push_back"): return f"{self._translate_expression(node.object)}.push_back({args})"
            if m_name == "pop": return f"__array_pop({self._translate_expression(node.object)})"
            if m_name == "size": return f"{self._translate_expression(node.object)}.size()"
            return f"{self._translate_expression(node.object)}->{m_name}({args})"
        
        if isinstance(node, FuncCallExpr):
            args = ", ".join(self._translate_expression(a) for a in node.arguments)
            if node.name == "exp":
                return f"std::exp({args})"
            if node.name == "random":
                return "random_val()"
            if node.name == "len":
                return f"{self._translate_expression(node.arguments[0])}.size()"
            if node.name == "range":
                return f"__minipar_range({args})"
            if node.name == "to_number":
                return f"std::stod({args})"
            if node.name == "parse_ints":
                return f"__parse_ints({args})"
            if node.name == "format":
                return f"__format({args})"
            if node.name == "clock":
                return "__clock()"
            if node.name == "int":
                return f"__int({args})"
            if node.name == "floor":
                return f"__mp_floor({args})"
            if node.name == "write_file":
                return f"__write_file({args})"
            return f"{node.name}({args})"

        if isinstance(node, CChannelExpr):
            ip = self._translate_expression(node.ip)
            port = self._translate_expression(node.port)
            return f"std::make_shared<MiniParChannel>({ip}, {port})"
        if isinstance(node, ReceiveExpr):
            return f"{self._translate_expression(node.channel)}->receiveData()"
        if isinstance(node, InputExpr):
            if node.prompt:
                return f"input({self._translate_expression(node.prompt)})"
            return "input()"

        if isinstance(node, ForkExpr):
            return self._translate_fork(node)
        if isinstance(node, JoinExpr):
            return f"__join({self._translate_expression(node.task)})"

        if isinstance(node, ListLiteral):
            elems = ", ".join(self._translate_expression(e) for e in node.elements)
            # ["Professor", "Monitor 1"] é lista de textos; as demais seguem numéricas
            if node.elements and all(isinstance(e, StringExpr) for e in node.elements):
                return f"std::vector<std::string>{{{elems}}}"
            # [fork f(1), fork f(2)]: lista de tarefas (o tipo vem dos próprios elementos)
            if node.elements and all(isinstance(e, ForkExpr) for e in node.elements):
                return f"std::vector{{{elems}}}"
            return f"std::vector<double>{{{elems}}}"
        if isinstance(node, MatrixCreateExpr):
            r = self._translate_expression(node.rows)
            c = self._translate_expression(node.cols)
            v = self._translate_expression(node.init_value)
            return f"__make_matrix({r}, {c}, {v})"
        if isinstance(node, IndexExpr):
            # Leitura e escrita passam por __index, que confere os limites
            obj = self._translate_expression(node.object)
            idx = self._translate_expression(node.index)
            return f"__index({obj}, {idx})"

        return "0"

    # ------------------------------------------------------------------
    # Fork / Join
    # ------------------------------------------------------------------
    def _translate_fork(self, node: ForkExpr) -> str:
        """fork f(a, b) on core(n)  ->  __fork(n, [__a0 = a, __a1 = b]() { return f(__a0, __a1); })

        Os argumentos (e o objeto, num método) são avaliados no pai, no momento
        do fork, e copiados para a subtarefa por init-capture: a thread filha
        não enxerga mudanças posteriores nas variáveis do pai.
        """
        call = node.call
        captures = [f"__a{i} = {self._translate_expression(arg)}" for i, arg in enumerate(call.arguments)]
        args = ", ".join(f"__a{i}" for i in range(len(call.arguments)))
        if isinstance(call, MethodCall):
            captures.insert(0, f"__obj = {self._translate_expression(call.object)}")
            body = f"__obj->{call.method_name}({args})"
        else:
            # Traduz como chamada comum (funções nativas viram seus helpers C++)
            captured = [IdentifierExpr(f"__a{i}") for i in range(len(call.arguments))]
            body = self._translate_expression(FuncCallExpr(call.name, captured))
        if self._in_method:
            captures.insert(0, "this")   # funções globais chamadas de dentro de um método

        dest = node.destination
        if isinstance(dest, CoreTarget):
            core = self._translate_expression(dest.index)
        elif isinstance(dest, HostTarget):
            # Outro computador: o worker (mesmo executável com --worker <porta>) executa a função.
            # O semântico garante que é uma função do programa com argumentos serializáveis.
            ip = self._translate_expression(dest.ip)
            port = self._translate_expression(dest.port)
            host_args = "".join(f", {self._translate_expression(a)}" for a in call.arguments)
            return f"__fork_host<__mp_fn_{call.name}>({ip}, {port}{host_args})"
        else:
            core = "0LL"   # sem destino: o sistema operacional escolhe o núcleo
        return f"__fork({core}, [{', '.join(captures)}]() {{ return {body}; }})"

    # ------------------------------------------------------------------
    # Listas criadas vazias: var lista = []; ... lista.append(x);
    # ------------------------------------------------------------------
    def _empty_list_type(self, name: str, following: list) -> str:
        """Tipo C++ de uma lista criada com [] a partir do primeiro append dela.

        O g++ deduz o tipo com uma lambda em contexto não avaliado (C++20):
        decltype([&]() { <declarações até o append>; return <valor>; }()).
        Nada disso é executado; serve só para descobrir o tipo do elemento,
        por exemplo a tarefa de um 'tarefas.append(fork f(k) on core(k + 1))'.
        Sem append encontrado, a lista é de números (std::vector<double>).
        """
        found = self._find_append(name, following, [])
        if found is None:
            return "std::vector<double>"
        replay, value = found
        body = " ".join(replay + [f"return {self._translate_expression(value)};"])
        return f"std::vector<__list_elem_t<decltype([&]() {{ {body} }}())>>"

    def _find_append(self, name: str, stmts: list, replay: list[str]):
        """Procura 'name.append(v)' em stmts, guardando as declarações do caminho até ele."""
        replay = list(replay)
        for stmt in stmts:
            found = self._find_append_in(name, stmt, replay)
            if found is not None:
                return found
            if isinstance(stmt, VarDecl):
                if stmt.name == name:
                    return None   # redeclarada: o append seguinte é de outra lista
                init = self._translate_expression(stmt.init_value) if stmt.init_value else "0LL"
                replay.append(f"auto {stmt.name} = {init};")
        return None

    def _find_append_in(self, name: str, stmt: Optional[ASTNode], replay: list[str]):
        if stmt is None:
            return None
        if (isinstance(stmt, MethodCall) and stmt.method_name in ("append", "push_back")
                and isinstance(stmt.object, IdentifierExpr) and stmt.object.name == name
                and len(stmt.arguments) == 1):
            return replay, stmt.arguments[0]
        if isinstance(stmt, (SeqBlock, ParBlock)):
            return self._find_append(name, stmt.statements, replay)
        if isinstance(stmt, IfStmt):
            return (self._find_append_in(name, stmt.then_branch, replay)
                    or self._find_append_in(name, stmt.else_branch, replay))
        if isinstance(stmt, (WhileStmt, DoWhileStmt)):
            return self._find_append_in(name, stmt.body, replay)
        if isinstance(stmt, ForStmt):
            inner = list(replay)
            if stmt.iterator_name:
                inner.append(f"auto {stmt.iterator_name} = *std::begin({self._translate_expression(stmt.iterable)});")
            elif isinstance(stmt.initializer, VarDecl):
                init = self._translate_expression(stmt.initializer.init_value) if stmt.initializer.init_value else "0LL"
                inner.append(f"auto {stmt.initializer.name} = {init};")
            return self._find_append_in(name, stmt.body, inner)
        return None

    def _translate_block(self, stmts: list, indent: str) -> str:
        """Traduz uma sequência de comandos; listas vazias olham os comandos seguintes."""
        out = []
        for i, stmt in enumerate(stmts):
            if isinstance(stmt, VarDecl) and isinstance(stmt.init_value, ListLiteral) and not stmt.init_value.elements:
                out.append(f"{indent}auto {stmt.name} = {self._empty_list_type(stmt.name, stmts[i + 1:])}{{}};\n")
            else:
                out.append(self._translate_statement(stmt, indent))
        return "".join(out)

    def _has_value_return(self, node: Optional[ASTNode]) -> bool:
        if node is None: return False
        if isinstance(node, ReturnStmt): return node.value is not None
        if isinstance(node, (SeqBlock, ParBlock)):
            return any(self._has_value_return(stmt) for stmt in node.statements)
        if isinstance(node, IfStmt):
            return self._has_value_return(node.then_branch) or self._has_value_return(node.else_branch)
        if isinstance(node, (WhileStmt, DoWhileStmt, ForStmt)):
            return self._has_value_return(node.body)
        return False

    def _uses_float_return(self, node: Optional[ASTNode]) -> bool:
        """Detecta aritmética de ponto flutuante no corpo da função."""
        if node is None:
            return False
        if isinstance(node, BinaryExpr):
            if node.op == "/":
                return True
            return self._uses_float_return(node.left) or self._uses_float_return(node.right)
        if isinstance(node, NumberExpr):
            return "." in node.value
        if isinstance(node, (SeqBlock, ParBlock)):
            return any(self._uses_float_return(stmt) for stmt in node.statements)
        if isinstance(node, IfStmt):
            return self._uses_float_return(node.then_branch) or self._uses_float_return(node.else_branch)
        if isinstance(node, (WhileStmt, DoWhileStmt, ForStmt)):
            return self._uses_float_return(node.body)
        if isinstance(node, ReturnStmt):
            return self._uses_float_return(node.value)
        return False

    def _return_type(self, body: Optional[ASTNode]) -> str:
        if not self._has_value_return(body):
            return "void"
        # auto falha no g++ quando há return double e return 0 (int) na mesma função
        if self._uses_float_return(body):
            return "double"
        return "auto"

    def _translate_statement(self, node: Optional[ASTNode], indent: str = "") -> str:
        if node is None: return ""
        if isinstance(node, VarDecl):
            if isinstance(node.init_value, NullExpr):
                return f"{indent}{self._null_ref_type(node.name, None)} {node.name} = nullptr;\n"
            expr = self._translate_expression(node.init_value) if node.init_value else "0"
            return f"{indent}auto {node.name} = {expr};\n"
        if isinstance(node, Assignment):
            return f"{indent}{node.name} = {self._translate_expression(node.value)};\n"
        if isinstance(node, PropertyAssign):
            obj = self._translate_expression(node.object)
            return f"{indent}{obj}->{node.property_name} = {self._translate_expression(node.value)};\n"
        if isinstance(node, IndexAssign):
            tgt = self._translate_expression(node.target)
            return f"{indent}{tgt} = {self._translate_expression(node.value)};\n"
        
        if isinstance(node, (MethodCall, FuncCallExpr, JoinExpr)):
            return f"{indent}{self._translate_expression(node)};\n"
        if isinstance(node, ForkExpr):
            # "fork f();" sem guardar a tarefa: segue em paralelo e é aguardada no fim do programa
            return f"{indent}__keep_running({self._translate_expression(node)});\n"
        if isinstance(node, ReturnStmt):
            val = self._translate_expression(node.value) if node.value else ""
            return f"{indent}return {val};\n"
        if isinstance(node, BreakStmt):
            return f"{indent}break;\n"
        if isinstance(node, ContinueStmt):
            return f"{indent}continue;\n"
        
        if isinstance(node, SendStmt):
            chan = self._translate_expression(node.channel)
            msg = self._translate_expression(node.message)
            return f"{indent}{chan}->sendData(__to_string({msg}));\n"

        if isinstance(node, PrintStmt):
            parts = []
            for i, arg in enumerate(node.arguments):
                if i > 0:
                    parts.append(' << " "')
                parts.append(f" << {self._translate_expression(arg)}")
            return f"{indent}std::cout{ ''.join(parts) } << std::endl;\n"
        
        if isinstance(node, SeqBlock):
            return f"{indent}{{\n{self._translate_block(node.statements, indent + '    ')}{indent}}}\n"
        if isinstance(node, ParBlock):
            lines = [f"{indent}{{\n", f"{indent}    std::vector<std::thread> __m_thr;\n"]
            for stmt in node.statements:
                lines.append(f"{indent}    __m_thr.emplace_back([&]() {{\n{self._translate_statement(stmt, indent + '        ')}{indent}    }});\n")
            lines.append(f"{indent}    for (auto& t : __m_thr) t.join();\n{indent}}}\n")
            return "".join(lines)
        if isinstance(node, WhileStmt):
            res = f"{indent}while ({self._translate_expression(node.condition)})\n"
            res += self._translate_statement(node.body, indent if isinstance(node.body, (SeqBlock, ParBlock)) else indent + "    ")
            return res
        if isinstance(node, DoWhileStmt):
            res = f"{indent}do\n"
            res += self._translate_statement(node.body, indent if isinstance(node.body, (SeqBlock, ParBlock)) else indent + "    ").rstrip()
            res += f"\n{indent}while ({self._translate_expression(node.condition)});\n"
            return res
        if isinstance(node, ForStmt):
            if node.iterator_name and node.iterable:
                res = f"{indent}for (auto {node.iterator_name} : {self._translate_expression(node.iterable)})\n"
                res += self._translate_statement(node.body, indent if isinstance(node.body, (SeqBlock, ParBlock)) else indent + "    ")
                return res
            init = self._translate_for_part(node.initializer)
            cond = self._translate_expression(node.condition) if node.condition else "true"
            inc = self._translate_for_part(node.increment)
            res = f"{indent}for ({init}; {cond}; {inc})\n"
            res += self._translate_statement(node.body, indent if isinstance(node.body, (SeqBlock, ParBlock)) else indent + "    ")
            return res
        if isinstance(node, IfStmt):
            res = f"{indent}if ({self._translate_expression(node.condition)})\n"
            res += self._translate_statement(node.then_branch, indent if isinstance(node.then_branch, (SeqBlock, ParBlock)) else indent + "    ")
            if node.else_branch:
                res = res.rstrip() + f"\n{indent}else\n"
                if isinstance(node.else_branch, IfStmt):
                    res = res.rstrip() + " " + self._translate_statement(node.else_branch, indent).lstrip()
                else:
                    res += self._translate_statement(node.else_branch, indent if isinstance(node.else_branch, (SeqBlock, ParBlock)) else indent + "    ")
            return res
        return ""

    def _translate_body(self, body: ASTNode, indent: str) -> str:
        """Corpo de função/método: os comandos do bloco, sem chaves extras."""
        if isinstance(body, SeqBlock):
            return self._translate_block(body.statements, indent)
        return self._translate_statement(body, indent)

    def _translate_for_part(self, node: Optional[ASTNode]) -> str:
        if node is None: return ""
        if isinstance(node, VarDecl):
            expr = self._translate_expression(node.init_value) if node.init_value else "0"
            return f"auto {node.name} = {expr}"
        if isinstance(node, Assignment):
            return f"{node.name} = {self._translate_expression(node.value)}"
        if isinstance(node, PropertyAssign):
            return f"{self._translate_expression(node.object)}->{node.property_name} = {self._translate_expression(node.value)}"
        if isinstance(node, IndexAssign):
            return f"{self._translate_expression(node.target)} = {self._translate_expression(node.value)}"
        return self._translate_expression(node)

    def generate(self, program: Program, output_name: str) -> bool:
        cpp_code = _CPP_HEADER
        self._host_functions = set()        # estado limpo a cada compilação (a IDE reutiliza o gerador)
        self._program = program
        self._scan_host_forks(program)

        for node in program.statements:
            if isinstance(node, ClassDecl):
                cpp_code += f"class {node.name}" + (f" : public {node.superclass}" if node.superclass else "") + " {\npublic:\n"
                for attr in node.attributes:
                    if isinstance(attr.init_value, NullExpr):
                        cpp_code += f"    {self._null_ref_type(attr.name, node.name)} {attr.name} = nullptr;\n"
                    elif attr.init_value:
                        init = self._translate_expression(attr.init_value)
                        cpp_code += f"    decltype({init}) {attr.name} = {init};\n"
                    else:
                        cpp_code += f"    double {attr.name} = 0;\n"
                self._in_method = True
                for method in node.methods:
                    params = ", ".join(f"auto {p}" for p in method.params)
                    ret = self._return_type(method.body)
                    cpp_code += f"    {ret} {method.name}({params}) {{\n"
                    cpp_code += self._translate_body(method.body, "        ")
                    cpp_code += "    }\n"
                self._in_method = False
                cpp_code += "};\n\n"
            elif isinstance(node, FuncDecl):
                params = ", ".join(f"auto {p}" for p in node.params)
                ret = self._return_type(node.body)
                cpp_code += f"{ret} {node.name}({params}) {{\n"
                cpp_code += self._translate_body(node.body, "    ")
                cpp_code += "}\n\n"
                if node.name in self._host_functions:
                    cpp_code += self._host_functor(node.name)

        cpp_code += "int main(int argc, char** argv) {\n    #ifdef _WIN32\n        WSADATA wsa;\n        WSAStartup(MAKEWORD(2,2), &wsa);\n    #endif\n\n"
        # "programa --worker 5001": atende forks vindos de outro computador e não roda o programa
        cpp_code += "    if (int __w = __mp_worker_from_args(argc, argv); __w >= 0) return __w;\n\n"
        # Comandos globais viram o corpo do main (um seq { } global é aberto no mesmo nível)
        main_stmts = []
        for node in program.statements:
            if isinstance(node, SeqBlock):
                main_stmts.extend(node.statements)
            elif not isinstance(node, (ClassDecl, FuncDecl)):
                main_stmts.append(node)
        cpp_code += self._translate_block(main_stmts, "    ")
        cpp_code += "\n    return 0;\n}\n"

        os.makedirs("output", exist_ok=True)
        cpp_path = os.path.join("output", f"{output_name}.cpp")
        exe_path = os.path.join("output", output_name + self.executable_suffix())

        with open(cpp_path, "w", encoding="utf-8") as f: f.write(cpp_code)

        print("[CODEGEN] Compilando via g++ com -std=c++20 e -O3...")
        result = subprocess.run(self.gcc_command(cpp_path, exe_path))
        if result.returncode == 0:
            print(f"[SUCESSO] Executavel: {exe_path}")
            return True
        print("[ERRO] Falha na compilacao.", file=sys.stderr)
        return False
