// =====================================================================
// MiniPar — Web 2 (didática)
// Mostra o que cada fase do compilador produz. Independente da Web 1
// (script.js): não compartilham estado nem estilos.
//
//   l5  Tokens em tabela por categoria, com destaque no editor
//   l6  AST como árvore gráfica recolhível (D3)
//   l7  Tabela de símbolos por escopo e erros em cartões ligados à linha
//   l8  TAC e C++ com destaque de sintaxe
// =====================================================================
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const CATEGORIAS = {
    palavra_reservada: "Palavra reservada",
    tipo: "Tipo",
    identificador: "Identificador",
    literal: "Literal",
    operador: "Operador",
    delimitador: "Delimitador",
    fim: "Fim de arquivo",
    desconhecido: "Desconhecido",
};
const FASES = ["tokens", "ast", "semantic", "tac", "cpp"];

// Estado da última análise
const estado = {
    resultado: null,       // JSON de /api/tac (tokens, ast, diagnostics, symbols, tac)
    codigoAnalisado: null, // texto que gerou o resultado (para saber se está desatualizado)
    cpp: null,             // JSON de /api/cpp (gerado sob demanda: chama o g++)
    filtroCategoria: null,
};

// ---------------------------------------------------------------------
// Modos de destaque de sintaxe (CodeMirror)
// ---------------------------------------------------------------------
CodeMirror.defineSimpleMode("minipar", {
    start: [
        { regex: /#.*/, token: "comment" },
        { regex: /"(?:[^\\"]|\\.)*"?/, token: "string" },
        { regex: /\d+(?:\.\d*)?/, token: "number" },
        { regex: /\b(?:true|false)\b/, token: "atom" },
        { regex: /\b(?:number|int|string|bool|void|list|dict)\b/, token: "variable-3" },
        { regex: /\b(?:class|extends|new|func|var|if|else|while|do|for|in|break|continue|return|seq|par|this|c_channel|send|receive|input|print|matrix|fork|join|on|core|host)\b/, token: "keyword" },
        { regex: /[A-Za-z_]\w*/, token: "variable" },
        { regex: /==|!=|<=|>=|&&|\|\||[-+*\/%=<>!]/, token: "operator" },
        { regex: /[{}()\[\]]/, token: "bracket" },
        { regex: /[;,.]/, token: "punctuation" },
    ],
    meta: { lineComment: "#" },
});

// ---------------------------------------------------------------------
// Editor
// ---------------------------------------------------------------------
const editor = CodeMirror.fromTextArea($("#code"), {
    mode: "minipar",
    lineNumbers: true,
    indentUnit: 4,
    tabSize: 4,
    indentWithTabs: false,
    gutters: ["gutter-diag", "CodeMirror-linenumbers"],
    extraKeys: {
        "Ctrl-Enter": () => analisar(),
        "Cmd-Enter": () => analisar(),
        Tab: (cm) => cm.replaceSelection("    "),
    },
});
editor.setValue('# Programa de exemplo\nfunc dobro(x) {\n    return x * 2;\n}\n\nvar t = fork dobro(21) on core(1);\nvar r = join t;\nprint("resultado:", r);\n');

// Marcas temporárias no editor, agrupadas por "grupo" para poder limpar cada uma
const marcas = {};
function limparMarcas(grupo) {
    (marcas[grupo] || []).forEach((m) => m.clear());
    marcas[grupo] = [];
}
function marcar(grupo, de, ate, opcoes) {
    (marcas[grupo] = marcas[grupo] || []).push(editor.markText(de, ate, opcoes));
}
const pos = (linha, col) => ({ line: Math.max(0, linha - 1), ch: Math.max(0, col - 1) });

// Leva o editor até uma linha (1-based) e a destaca por um instante
function irParaLinha(linha, col = 1) {
    if (!linha) return;
    const l = Math.min(Math.max(0, linha - 1), editor.lineCount() - 1);
    editor.focus();
    editor.setCursor({ line: l, ch: Math.max(0, col - 1) });
    editor.scrollIntoView({ line: l, ch: 0 }, 80);
    editor.addLineClass(l, "background", "linha-foco");
    setTimeout(() => editor.removeLineClass(l, "background", "linha-foco"), 1200);
}

editor.on("cursorActivity", () => {
    const c = editor.getCursor();
    $("#cursor-pos").textContent = `linha ${c.line + 1}, coluna ${c.ch + 1}`;
    destacarTokenDoCursor(c);
});
editor.on("change", () => {
    // Resultado antigo deixa de valer: avisa e apaga destaques de posição
    if (estado.resultado && editor.getValue() !== estado.codigoAnalisado) {
        setStatus("O código mudou desde a última análise. Clique em Analisar (Ctrl+Enter).", "");
        limparMarcas("cat"); limparMarcas("hover");
        estado.cpp = null;
    }
});

// ---------------------------------------------------------------------
// Utilidades
// ---------------------------------------------------------------------
function setStatus(texto, tipo) {
    const el = $("#status");
    el.textContent = texto;
    el.className = "status" + (tipo ? " " + tipo : "");
}
function el(tag, attrs = {}, ...filhos) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
        if (k === "class") e.className = v;
        else if (k === "style") e.style.cssText = v;
        else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
        else if (v !== undefined && v !== null) e.setAttribute(k, v);
    }
    for (const f of filhos.flat()) if (f !== null && f !== undefined) e.append(f);
    return e;
}
async function postJSON(rota, corpo) {
    const r = await fetch(rota, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) });
    if (!r.ok && r.headers.get("Content-Type")?.includes("json") === false) throw new Error(`HTTP ${r.status}`);
    return r.json();
}

// ---------------------------------------------------------------------
// Abas
// ---------------------------------------------------------------------
function abrirAba(nome) {
    $$(".aba").forEach((b) => b.classList.toggle("ativa", b.dataset.aba === nome));
    $$(".conteudo").forEach((c) => c.classList.toggle("ativo", c.id === "aba-" + nome));
    if (nome === "cpp") garantirCpp();
    if (nome === "ast" && window.Ast) Ast.aoMostrar();
    if (nome === "tac" && tacView) tacView.refresh();
    if (nome === "cpp" && cppView) cppView.refresh();
}
$$(".aba").forEach((b) => b.addEventListener("click", () => abrirAba(b.dataset.aba)));

// ---------------------------------------------------------------------
// Linha do tempo das fases
// ---------------------------------------------------------------------
function atualizarPipeline(res, ateFase) {
    const parada = res && res.fase_parada;
    const limite = FASES.indexOf(ateFase);
    $$("#pipeline li").forEach((li) => {
        const i = FASES.indexOf(li.dataset.fase);
        li.className = "";
        if (!res || i > limite) return;
        if (parada) {
            const ip = FASES.indexOf(parada);
            if (i < ip) li.classList.add("ok");
            else if (i === ip) li.classList.add("erro");
        } else li.classList.add("ok");
    });
}

// ---------------------------------------------------------------------
// Análise (tokens → AST → semântica → TAC numa só chamada)
// ---------------------------------------------------------------------
async function analisar() {
    const codigo = editor.getValue();
    const btn = $("#btn-analisar");
    btn.disabled = true;
    setStatus("Analisando…");
    $$("#pipeline li").forEach((li) => (li.className = "rodando"));
    try {
        const res = await postJSON("/api/tac", { code: codigo });
        estado.resultado = res;
        estado.codigoAnalisado = codigo;
        estado.cpp = null;
        atualizarPipeline(res, "tac");
        renderTudo(res);
        if (res.ok) setStatus("Análise concluída sem erros: léxica, sintática, semântica e TAC.", "ok");
        else setStatus(`Parou na fase ${nomeFase(res.fase_parada)}. Veja a aba Semântica para os detalhes.`, "erro");
        if (!res.ok) abrirAba(res.fase_parada === "tokens" ? "tokens" : "semantica");
        else if ($(".aba.ativa").dataset.aba === "cpp") garantirCpp();
    } catch (e) {
        setStatus("Falha ao falar com o servidor: " + e.message, "erro");
        atualizarPipeline(null);
    } finally {
        btn.disabled = false;
    }
}
function nomeFase(f) {
    return { tokens: "léxica", ast: "sintática", semantic: "semântica", tac: "de TAC", cpp: "de C++" }[f] || f;
}
$("#btn-analisar").addEventListener("click", analisar);

function renderTudo(res) {
    renderTokens(res.tokens || []);
    if (window.Ast) Ast.render(res.ast || null);
    if (window.renderSemantica) renderSemantica(res);
    if (window.renderTac) renderTac(res);
}

// =====================================================================
// l5 — Tokens em tabela por categoria, com destaque no editor
// =====================================================================
function corCategoria(cat) { return `var(--c-${cat})`; }

function renderTokens(tokens) {
    const visiveis = tokens.filter((t) => t.type !== "END_OF_FILE");
    // chips por categoria, com contagem
    const cont = {};
    visiveis.forEach((t) => (cont[t.category] = (cont[t.category] || 0) + 1));
    const chips = $("#tok-categorias");
    chips.textContent = "";
    if (estado.filtroCategoria && !cont[estado.filtroCategoria]) estado.filtroCategoria = null;
    chips.append(chipCategoria(null, "Todas", visiveis.length));
    Object.keys(CATEGORIAS).forEach((cat) => { if (cont[cat]) chips.append(chipCategoria(cat, CATEGORIAS[cat], cont[cat])); });

    // tabela
    const tbody = $("#tok-tabela tbody");
    tbody.textContent = "";
    if (!visiveis.length) {
        tbody.append(el("tr", {}, el("td", { colspan: 5, class: "vazio" }, "Nenhum token.")));
        return;
    }
    const filtro = estado.filtroCategoria;
    visiveis.forEach((t, i) => {
        if (filtro && t.category !== filtro) return;
        const tr = el("tr", { style: `--tkc:${corCategoria(t.category)}`, "data-i": i },
            el("td", { class: "muted" }, String(i + 1)),
            el("td", { class: "lexema", title: t.lexeme }, t.type === "STRING_LITERAL" ? JSON.stringify(t.lexeme) : t.lexeme),
            el("td", {}, t.type),
            el("td", {}, el("span", { class: "cat" }, CATEGORIAS[t.category] || t.category)),
            el("td", { class: "muted" }, `${t.line}:${t.col}`),
        );
        tr.addEventListener("mouseenter", () => destacarToken(t));
        tr.addEventListener("mouseleave", () => limparMarcas("hover"));
        tr.addEventListener("click", () => {
            editor.focus();
            editor.setSelection(pos(t.line, t.col), pos(t.end_line, t.end_col));
            editor.scrollIntoView(pos(t.line, t.col), 80);
        });
        tbody.append(tr);
    });
    destacarCategoria();
}

function chipCategoria(cat, rotulo, n) {
    const b = el("button", {
        class: "chip", type: "button", "aria-pressed": String(estado.filtroCategoria === cat),
        style: `--tkc:${cat ? corCategoria(cat) : "var(--accent)"}`,
    }, el("span", { class: "ponto" }), rotulo, el("span", { class: "n" }, String(n)));
    b.addEventListener("click", () => {
        estado.filtroCategoria = estado.filtroCategoria === cat ? null : cat;
        renderTokens(estado.resultado ? estado.resultado.tokens : []);
    });
    return b;
}

function destacarToken(t) {
    limparMarcas("hover");
    if (editor.getValue() !== estado.codigoAnalisado) return;
    marcar("hover", pos(t.line, t.col), pos(t.end_line, t.end_col), { className: "tk-hover" });
    editor.scrollIntoView(pos(t.line, t.col), 60);
}

// Categoria escolhida nos chips fica sublinhada no editor
function destacarCategoria() {
    limparMarcas("cat");
    const cat = estado.filtroCategoria;
    if (!cat || !estado.resultado || editor.getValue() !== estado.codigoAnalisado) return;
    estado.resultado.tokens.forEach((t) => {
        if (t.category !== cat || t.type === "END_OF_FILE") return;
        marcar("cat", pos(t.line, t.col), pos(t.end_line, t.end_col),
            { className: "tk-cat cat-" + cat });
    });
}

// Caminho inverso: o cursor no editor destaca a linha da tabela
function destacarTokenDoCursor(c) {
    const res = estado.resultado;
    $$("#tok-tabela tr.atual").forEach((tr) => tr.classList.remove("atual"));
    if (!res || !res.tokens || editor.getValue() !== estado.codigoAnalisado) return;
    const L = c.line + 1, C = c.ch + 1;
    const i = res.tokens.findIndex((t) => t.type !== "END_OF_FILE" &&
        (L > t.line || (L === t.line && C >= t.col)) && (L < t.end_line || (L === t.end_line && C <= t.end_col)));
    if (i < 0) return;
    const tr = $(`#tok-tabela tr[data-i="${i}"]`);
    if (tr) {
        tr.classList.add("atual");
        if ($("#aba-tokens").classList.contains("ativo")) tr.scrollIntoView({ block: "nearest" });
    }
}

// =====================================================================
// l6 — AST como árvore gráfica recolhível (D3)
// =====================================================================
const Ast = (() => {
    const GRUPOS = {
        declaracao: ["Program", "VarDecl", "FuncDecl", "ClassDecl"],
        controle: ["SeqBlock", "ParBlock", "IfStmt", "WhileStmt", "DoWhileStmt", "ForStmt", "BreakStmt", "ContinueStmt", "ReturnStmt"],
        comando: ["Assignment", "PrintStmt", "PropertyAssign", "IndexAssign", "SendStmt"],
        paralelo: ["ForkExpr", "JoinExpr", "CoreTarget", "HostTarget", "CChannelExpr", "ReceiveExpr"],
    };
    const COR = { declaracao: "#d2a8ff", controle: "#79c0ff", comando: "#ffa657", paralelo: "#ff7b72", expressao: "#7ee787" };
    function grupo(tipo) {
        for (const [g, tipos] of Object.entries(GRUPOS)) if (tipos.includes(tipo)) return g;
        return "expressao";
    }
    const ehNo = (v) => v && typeof v === "object" && !Array.isArray(v) && "_type" in v;

    // Filhos de um nó: campos que guardam nós (ou listas de nós), com o nome do campo
    function filhos(obj) {
        const out = [];
        for (const [k, v] of Object.entries(obj)) {
            if (k === "_type" || k === "line" || k.startsWith("__")) continue;
            if (ehNo(v)) out.push({ ...v, __campo: k });
            else if (Array.isArray(v)) v.forEach((x, i) => { if (ehNo(x)) out.push({ ...x, __campo: `${k}[${i}]` }); });
        }
        return out.length ? out : null;
    }
    // Texto curto ao lado do tipo do nó: nome, operador, valor...
    function detalhe(obj) {
        const partes = [];
        const add = (v) => { if (v !== null && v !== undefined && v !== "") partes.push(String(v)); };
        if (obj._type === "StringExpr") add(JSON.stringify(obj.value));
        else if ("value" in obj && !ehNo(obj.value) && typeof obj.value !== "object") add(obj.value);
        add(obj.name);
        add(obj.class_name);
        add(obj.method_name ? "." + obj.method_name + "()" : null);
        add(obj.property_name ? "." + obj.property_name : null);
        add(obj.op);
        if (obj.type && obj.type !== "var" && typeof obj.type === "string") add(": " + obj.type);
        if (obj.superclass) add("extends " + obj.superclass);
        if (obj.iterator_name) add(obj.iterator_name + " in");
        if (Array.isArray(obj.params)) add("(" + obj.params.join(", ") + ")");
        let t = partes.join(" ");
        if (t.length > 28) t = t.slice(0, 27) + "…";
        return t;
    }

    let raiz = null, svg = null, g = null, zoom = null, sujo = false, desenhouAlgumaVez = false;
    const container = () => $("#ast-arvore");
    const visivel = () => $("#aba-ast").classList.contains("ativo");

    function render(ast) {
        const c = container();
        c.textContent = "";
        svg = null; raiz = null; desenhouAlgumaVez = false;
        if (!ast) {
            c.append(el("p", { class: "vazio", style: "padding:12px" }, "A AST não foi gerada: o programa parou na análise léxica ou sintática. Veja a aba Semântica."));
            return;
        }
        raiz = d3.hierarchy(ast, filhos);
        let id = 0;
        raiz.each((d) => {
            d.id = ++id;
            d.tipo = d.data._type;
            d.det = detalhe(d.data);
            d.largura = Math.max(48, 16 + 7.4 * (d.tipo.length + (d.det ? d.det.length + 2 : 0)));
        });
        // Programas grandes começam recolhidos nos comandos, para caber na tela
        if (raiz.descendants().length > 160) recolherEmComandos(false);
        sujo = true;
        if (visivel()) desenhar();
    }

    function criarSvg() {
        const c = container();
        c.textContent = "";
        svg = d3.select(c).append("svg");
        g = svg.append("g");
        zoom = d3.zoom().scaleExtent([0.15, 2.5]).on("zoom", (e) => g.attr("transform", e.transform));
        svg.call(zoom).on("dblclick.zoom", null);
        c.append(el("span", { class: "ast-dica" }, "clique: recolher/expandir e ir à linha · arraste: mover · roda: zoom"));
    }

    function desenhar() {
        if (!raiz) return;
        if (!svg) criarSvg();
        sujo = false;
        // largura de cada nível = maior rótulo visível naquele nível
        const larguraNivel = [];
        raiz.each((d) => { larguraNivel[d.depth] = Math.max(larguraNivel[d.depth] || 0, d.largura); });
        const xNivel = [0];
        for (let i = 1; i < larguraNivel.length; i++) xNivel[i] = xNivel[i - 1] + (larguraNivel[i - 1] || 0) + 40;
        d3.tree().nodeSize([38, 1]).separation((a, b) => (a.parent === b.parent ? 1 : 1.25))(raiz);
        const nos = raiz.descendants();
        nos.forEach((d) => (d.y = xNivel[d.depth]));

        g.selectAll("*").remove();
        g.append("g").selectAll("path").data(raiz.links()).join("path")
            .attr("class", "ligacao")
            .attr("d", (l) => d3.linkHorizontal()({ source: [l.source.y + l.source.largura, l.source.x], target: [l.target.y, l.target.x] }));

        const no = g.append("g").selectAll("g").data(nos, (d) => d.id).join("g")
            .attr("class", (d) => "no" + (d._children ? " recolhido" : ""))
            .attr("transform", (d) => `translate(${d.y},${d.x})`)
            .on("click", (ev, d) => {
                if (d.children) { d._children = d.children; d.children = null; }
                else if (d._children) { d.children = d._children; d._children = null; }
                desenhar();
                if (d.data.line) irParaLinha(d.data.line);
            });
        no.filter((d) => d.data.__campo).append("text").attr("class", "rotulo-campo").attr("x", 2).attr("y", -15).text((d) => d.data.__campo);
        no.append("rect").attr("x", 0).attr("y", -11).attr("height", 22)
            .attr("width", (d) => d.largura)
            .attr("fill", (d) => d3.color(COR[grupo(d.tipo)]).darker(2.6))
            .attr("stroke", (d) => COR[grupo(d.tipo)]);
        const txt = no.append("text").attr("x", 8).attr("y", 4);
        txt.append("tspan").attr("font-weight", 600).text((d) => d.tipo);
        txt.append("tspan").attr("class", "detalhe").attr("dx", 6).text((d) => d.det);
        no.append("title").text((d) => `${d.tipo}${d.data.line ? " · linha " + d.data.line : ""}${d._children ? " · recolhido (" + d._children.length + " filhos)" : ""}`);
        no.filter((d) => d._children).append("text").attr("x", (d) => d.largura + 5).attr("y", 4)
            .attr("class", "detalhe").text((d) => "+" + d._children.length);

        if (!desenhouAlgumaVez) { desenhouAlgumaVez = true; centralizar(); }
    }

    function centralizar() {
        if (!svg || !raiz) return;
        const caixa = g.node().getBBox();
        const W = container().clientWidth, H = container().clientHeight;
        if (!W || !H) return;
        const escala = Math.min(1, (W - 40) / caixa.width, (H - 40) / caixa.height);
        let t;
        if (escala >= 0.7) {
            t = d3.zoomIdentity.translate((W - caixa.width * escala) / 2 - caixa.x * escala, (H - caixa.height * escala) / 2 - caixa.y * escala).scale(escala);
        } else {
            // árvore grande: começa pela raiz, à esquerda, em tamanho legível
            t = d3.zoomIdentity.translate(20, H / 2 - raiz.x * 0.85).scale(0.85);
        }
        svg.call(zoom.transform, t);
    }

    function expandirTudo() {
        if (!raiz) return;
        raiz.each((d) => { if (d._children) { d.children = d._children; d._children = null; } });
        // each não visita filhos recolhidos: repete até não sobrar nenhum
        let algum = true;
        while (algum) {
            algum = false;
            raiz.descendants().forEach((d) => { if (d._children) { d.children = d._children; d._children = null; algum = true; } });
        }
        desenhar(); centralizar();
    }
    function recolherEmComandos(redesenhar = true) {
        if (!raiz) return;
        raiz.descendants().forEach((d) => {
            if (d.depth >= 1 && d.children) { d._children = d.children; d.children = null; }
        });
        if (redesenhar) { desenhar(); centralizar(); }
    }

    $("#ast-expandir").addEventListener("click", expandirTudo);
    $("#ast-recolher").addEventListener("click", () => recolherEmComandos(true));
    $("#ast-centralizar").addEventListener("click", centralizar);
    window.addEventListener("resize", () => { if (visivel() && svg) centralizar(); });

    return {
        render,
        aoMostrar() { if (sujo) desenhar(); else if (svg && !desenhouAlgumaVez) centralizar(); },
    };
})();
window.Ast = Ast;

// =====================================================================
// l7 — Tabela de símbolos por escopo e erros em cartões ligados à linha
// =====================================================================
let linhasMarcadas = [];
function limparDiagnosticosNoEditor() {
    linhasMarcadas.forEach(([l, cls]) => editor.removeLineClass(l, "background", cls));
    linhasMarcadas = [];
    editor.clearGutter("gutter-diag");
}
function marcarDiagnosticosNoEditor(problemas) {
    limparDiagnosticosNoEditor();
    const porLinha = {};
    problemas.forEach((p) => {
        if (!p.line) return;
        const l = Math.min(p.line, editor.lineCount()) - 1;
        (porLinha[l] = porLinha[l] || []).push(p);
    });
    Object.entries(porLinha).forEach(([l, ps]) => {
        l = Number(l);
        const temErro = ps.some((p) => p.kind === "erro");
        const cls = temErro ? "linha-erro" : "linha-aviso";
        editor.addLineClass(l, "background", cls);
        linhasMarcadas.push([l, cls]);
        const marca = el("div", { class: "gutter-marca " + (temErro ? "erro" : "aviso"), title: ps.map((p) => p.message).join("\n") });
        editor.setGutterMarker(l, "gutter-diag", marca);
    });
}
editor.on("change", () => { if (linhasMarcadas.length) limparDiagnosticosNoEditor(); });

const ROTULO_ESCOPO = { global: "global", classe: "classe", metodo: "método", funcao: "função", corpo: "corpo", for: "for", bloco: "bloco", par: "par" };

function renderSemantica(res) {
    const problemas = res.problemas || [];
    const nErros = problemas.filter((p) => p.kind === "erro").length;
    const nAvisos = problemas.length - nErros;
    const badge = $("#badge-erros");
    badge.hidden = problemas.length === 0;
    badge.textContent = nErros || nAvisos;
    badge.classList.toggle("aviso", nErros === 0);
    badge.title = `${nErros} erro(s), ${nAvisos} aviso(s)`;
    marcarDiagnosticosNoEditor(problemas);

    // cartões
    const cartoes = $("#sem-erros");
    cartoes.textContent = "";
    if (!problemas.length) {
        cartoes.append(el("div", { class: "cartao ok" },
            el("span", { class: "tag" }, "ok"), el("span", {}, ""), el("span", {}, ""),
            el("span", { class: "msg" }, res.fase_parada ? "A análise parou, mas sem mensagem de erro reconhecida. Veja o log abaixo." : "Nenhum erro ou aviso: o programa passou nas análises léxica, sintática e semântica.")));
    }
    problemas.forEach((p) => {
        const trecho = p.line && p.line <= editor.lineCount() ? editor.getLine(p.line - 1).trim() : "";
        const c = el("button", { class: "cartao " + p.kind, type: "button", title: p.line ? "Ir para a linha " + p.line : "" },
            el("span", { class: "tag" }, `${p.kind === "erro" ? "Erro" : "Aviso"} ${p.fase}`),
            el("span", { class: "linha" }, p.funcao ? `em ${p.funcao}()` : ""),
            el("span", { class: "linha" }, p.line ? `linha ${p.line}${p.col ? ", col " + p.col : ""}` : ""),
            el("span", { class: "msg" }, p.message),
            trecho ? el("span", { class: "trecho" }, trecho) : null,
        );
        c.addEventListener("click", () => irParaLinha(p.line, p.col || 1));
        cartoes.append(c);
    });
    if (res.fase_parada && !problemas.length && (res.errors || res.log)) {
        cartoes.append(el("pre", { class: "saida" }, (res.errors || "") + (res.log || "")));
    }

    // escopos
    const box = $("#sem-escopos");
    box.textContent = "";
    const escopos = res.escopos || [];
    if (!escopos.length) {
        box.append(el("p", { class: "vazio" }, "A tabela de símbolos não foi montada: o programa parou antes da análise semântica."));
        return;
    }
    const desenharEscopo = (e, nivel) => {
        const det = el("details", { class: "escopo" });
        if (nivel < 2 || e.simbolos.length) det.open = true;
        const resumo = el("summary", {},
            el("span", { class: "tipo-escopo" }, ROTULO_ESCOPO[e.tipo] || e.tipo),
            el("b", {}, e.nome),
            el("span", { class: "muted" }, `${e.simbolos.length} símbolo(s)` + (e.linha ? ` · linha ${e.linha}` : "")));
        if (e.linha) resumo.addEventListener("dblclick", () => irParaLinha(e.linha));
        det.append(resumo);
        const corpo = el("div", { class: "corpo" });
        if (e.simbolos.length) {
            const tb = el("tbody");
            e.simbolos.forEach((sym) => {
                const tr = el("tr", { title: sym.linha ? "Ir para a linha " + sym.linha : "" },
                    el("td", { style: "color:var(--c-identificador)" }, sym.nome),
                    el("td", { style: "color:var(--c-tipo)" }, sym.tipo),
                    el("td", { class: "muted" }, sym.detalhe || ""),
                    el("td", { class: "muted" }, sym.linha ? String(sym.linha) : ""));
                tr.addEventListener("click", () => irParaLinha(sym.linha));
                tb.append(tr);
            });
            corpo.append(el("div", { class: "tabela-wrap", style: "flex:none" },
                el("table", { class: "tabela" },
                    el("thead", {}, el("tr", {}, el("th", {}, "Nome"), el("th", {}, "Tipo"), el("th", {}, "Detalhe"), el("th", {}, "Linha"))), tb)));
        } else {
            corpo.append(el("span", { class: "vazio" }, "nenhum símbolo declarado aqui"));
        }
        if (e.filhos.length) {
            const filhos = el("div", { class: "filhos" });
            e.filhos.forEach((i) => filhos.append(desenharEscopo(escopos[i], nivel + 1)));
            corpo.append(filhos);
        }
        det.append(corpo);
        return det;
    };
    box.append(desenharEscopo(escopos[0], 0));
}
window.renderSemantica = renderSemantica;

// =====================================================================
// l8 — TAC e C++ com destaque de sintaxe
// =====================================================================
CodeMirror.defineSimpleMode("tac", {
    start: [
        { regex: /(?:\/\/|#).*/, token: "comment" },
        { regex: /"(?:[^\\"]|\\.)*"?/, token: "string" },
        { regex: /(func|endfunc)(\s+)([A-Za-z_][\w.]*)/, token: ["keyword", null, "def"] },
        { regex: /(goto)(\s+)([A-Za-z_]\w*)/, token: ["keyword", null, "tag"] },
        { regex: /^[A-Za-z_]\w*:/, token: "tag", sol: true },
        { regex: /\b(?:ifFalse|if|param|call|return|print|fork|join|on|core|host|new|send|receive|input)\b/, token: "keyword" },
        { regex: /\bt\d+\b/, token: "builtin" },
        { regex: /\d+(?:\.\d*)?/, token: "number" },
        { regex: /\b(?:true|false)\b/, token: "atom" },
        { regex: /[A-Za-z_]\w*/, token: "variable" },
        { regex: /==|!=|<=|>=|&&|\|\||[-+*\/%=<>!]/, token: "operator" },
        { regex: /[\[\](),.]/, token: "bracket" },
    ],
    meta: { lineComment: "//" },
});

function criarVisao(id, modo) {
    return CodeMirror.fromTextArea($(id), { mode: modo, readOnly: true, lineNumbers: true, lineWrapping: false });
}

function renderTac(res) {
    if (!tacView) tacView = criarVisao("#tac-view", "tac");
    if (res.tac) {
        const linhas = res.tac.split("\n").filter((l) => l.trim());
        const temps = new Set(res.tac.match(/\bt\d+\b/g) || []);
        const rotulos = linhas.filter((l) => /^[A-Za-z_]\w*:\s*$/.test(l) && !/^func /.test(l)).length;
        tacView.setValue(res.tac);
        $("#aba-tac .ajuda").innerHTML = `<b>Código de três endereços</b>: cada instrução tem no máximo um operador. ` +
            `<code>t0, t1…</code> são temporários e os nomes com <code>:</code> são rótulos de desvio. ` +
            `<span class="muted">(${linhas.length} instruções · ${temps.size} temporários · ${rotulos} rótulos)</span>`;
    } else {
        tacView.setValue(res.fase_parada
            ? `// O TAC não foi gerado: o programa parou na fase ${nomeFase(res.fase_parada)}.\n// Corrija os erros listados na aba Semântica e analise de novo.`
            : "// (vazio)");
    }
    if ($("#aba-tac").classList.contains("ativo")) tacView.refresh();
}
window.renderTac = renderTac;

function renderCpp(res, carregando = false) {
    if (!cppView) cppView = criarVisao("#cpp-view", "text/x-c++src");
    const st = $("#cpp-status");
    if (carregando) {
        st.className = "status-inline";
        st.textContent = "Gerando C++ e compilando com g++ -O3 (leva alguns segundos)…";
        cppView.setValue("");
    } else if (!estado.resultado) {
        st.textContent = "";
    } else if (!estado.resultado.ok) {
        st.className = "status-inline erro";
        st.textContent = "O C++ não foi gerado: corrija antes os erros das fases anteriores.";
        cppView.setValue("");
    } else if (res) {
        // Por padrão mostra só o código traduzido do programa; o runtime é fixo
        const linhas = (res.cpp || "").split("\n");
        const inicio = Math.max(1, res.cpp_inicio_programa || 1);
        const comRuntime = $("#cpp-runtime").checked || inicio === 1;
        cppView.setOption("firstLineNumber", comRuntime ? 1 : inicio);
        cppView.setValue(comRuntime ? res.cpp || "" : linhas.slice(inicio - 1).join("\n"));
        if (res.cpp_compilou) {
            st.className = "status-inline ok";
            st.textContent = `C++ gerado e compilado pelo g++ sem erros: ${linhas.length - inicio + 1} linhas do programa + ${inicio - 1} do runtime.`;
        } else {
            st.className = "status-inline erro";
            st.textContent = "O C++ foi gerado, mas o g++ não compilou. As mensagens do g++ aparecem no terminal onde o servidor está rodando.";
        }
    }
    if ($("#aba-cpp").classList.contains("ativo")) cppView.refresh();
}
window.renderCpp = renderCpp;
$("#cpp-runtime").addEventListener("change", () => renderCpp(estado.cpp));

// ---------------------------------------------------------------------
// C++ (gerado sob demanda, porque chama o g++)
// ---------------------------------------------------------------------
let tacView = null, cppView = null;
async function garantirCpp() {
    if (estado.cpp || !estado.resultado || !estado.resultado.ok) {
        if (window.renderCpp) renderCpp(estado.cpp);
        return;
    }
    const codigo = estado.codigoAnalisado;
    if (window.renderCpp) renderCpp(null, true);
    $$("#pipeline li[data-fase=cpp]").forEach((li) => (li.className = "rodando"));
    try {
        const res = await postJSON("/api/cpp", { code: codigo });
        if (codigo !== estado.codigoAnalisado) return; // análise mais nova chegou antes
        estado.cpp = res;
        const li = $("#pipeline li[data-fase=cpp]");
        li.className = res.ok && res.cpp_compilou ? "ok" : "erro";
        if (window.renderCpp) renderCpp(res);
    } catch (e) {
        if (window.renderCpp) renderCpp({ ok: false, cpp: "", errors: e.message });
    }
}

// ---------------------------------------------------------------------
// Executar e baixar
// ---------------------------------------------------------------------
$("#btn-executar").addEventListener("click", async () => {
    const saida = $("#exec-saida");
    const btn = $("#btn-executar");
    btn.disabled = true;
    saida.textContent = "Compilando e executando…";
    try {
        const d = await postJSON("/api/run", { code: editor.getValue(), stdin: $("#stdin").value });
        saida.textContent = "";
        if (d.stdout) saida.append(d.stdout);
        if (d.stderr) saida.append(el("span", { class: "err" }, (d.stdout ? "\n" : "") + d.stderr));
        if (!d.ok && d.log) saida.append(el("span", { class: "info" }, "\n\n--- log da compilação ---\n" + d.log));
        if (d.ok && !d.stdout) saida.append(el("span", { class: "info" }, "(o programa terminou sem imprimir nada)"));
        saida.append(el("span", { class: "info" }, d.returncode !== null && d.returncode !== undefined ? `\n\n[código de saída: ${d.returncode}]` : ""));
    } catch (e) {
        saida.textContent = "Falha ao falar com o servidor: " + e.message;
    } finally {
        btn.disabled = false;
    }
});

$("#btn-baixar").addEventListener("click", async () => {
    const btn = $("#btn-baixar");
    btn.disabled = true;
    try {
        const r = await fetch("/api/build", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code: editor.getValue() }) });
        if (!r.ok) {
            const d = await r.json().catch(() => ({}));
            $("#exec-saida").textContent = "Não foi possível gerar o executável.\n\n" + (d.log || "");
            return;
        }
        const blob = await r.blob();
        const m = (r.headers.get("Content-Disposition") || "").match(/filename="?([^";]+)"?/);
        const a = el("a", { href: URL.createObjectURL(blob), download: m ? m[1] : "programa" });
        a.click();
        URL.revokeObjectURL(a.href);
    } finally {
        btn.disabled = false;
    }
});

// ---------------------------------------------------------------------
// Programas de teste
// ---------------------------------------------------------------------
async function carregarTestes() {
    try {
        const r = await fetch("/api/exemplos");
        const { tests } = await r.json();
        tests.forEach((t) => $("#test-select").append(new Option(t, t)));
    } catch (e) { /* lista é opcional */ }
}
$("#test-select").addEventListener("change", async (ev) => {
    if (!ev.target.value) return;
    const d = await postJSON("/api/get_test", { filename: ev.target.value });
    if (d.code !== undefined) {
        editor.setValue(d.code);
        analisar();
    }
});

carregarTestes();
analisar();
