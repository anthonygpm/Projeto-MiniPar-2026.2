// Web 2 (didática): mostra o que cada fase do compilador produz.
// Arquivo independente da Web 1 (script.js) — não compartilham estado.
const $ = (s) => document.querySelector(s);

function setStatus(texto, tipo) {
    const el = $("#status");
    el.textContent = texto;
    el.className = "status" + (tipo ? " " + tipo : "");
}

async function carregarTestes() {
    try {
        const r = await fetch("/api/tests");
        const { tests } = await r.json();
        const sel = $("#test-select");
        tests.forEach((t) => sel.append(new Option(t, t)));
    } catch (e) { /* lista de testes é opcional */ }
}

$("#test-select").addEventListener("change", async (ev) => {
    if (!ev.target.value) return;
    const r = await fetch("/api/get_test", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: ev.target.value }),
    });
    const d = await r.json();
    if (d.code !== undefined) $("#code").value = d.code;
});

async function baixarExecutavel(rota, corpo) {
    const r = await fetch(rota, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) });
    if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        setStatus("Não foi possível gerar o executável.", "erro");
        $("#saida").textContent = d.log || JSON.stringify(d, null, 2);
        return;
    }
    const blob = await r.blob();
    const nome = (r.headers.get("Content-Disposition") || "").match(/filename="?([^";]+)"?/);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = nome ? nome[1] : "programa";
    a.click();
    URL.revokeObjectURL(a.href);
    setStatus("Executável baixado.", "ok");
}

async function chamarFase(botao) {
    document.querySelectorAll(".fase").forEach((b) => b.classList.toggle("ativa", b === botao));
    const rota = botao.dataset.rota;
    const corpo = { code: $("#code").value, stdin: $("#stdin").value };
    setStatus("Processando " + botao.textContent.trim() + "…");
    $("#saida").textContent = "";
    try {
        if (botao.dataset.download) return await baixarExecutavel(rota, corpo);
        const r = await fetch(rota, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) });
        if (r.status === 404) { setStatus("Rota " + rota + " ainda não existe no servidor.", "erro"); return; }
        const d = await r.json();
        setStatus(d.ok ? "Fase concluída sem erros." : "A fase encontrou erros.", d.ok ? "ok" : "erro");
        // Visualização provisória: JSON bruto. As visões gráficas (l5–l8) substituem isto.
        $("#saida").textContent = JSON.stringify(d, null, 2);
    } catch (e) {
        setStatus("Falha ao falar com o servidor: " + e.message, "erro");
    }
}

document.querySelectorAll(".fase").forEach((b) => b.addEventListener("click", () => chamarFase(b)));
carregarTestes();
