(async function () {
  const $ = (id) => document.getElementById(id);
  const list = $("list");
  const empty = $("empty");
  const q = $("q");
  const multi = $("multi");
  const lang = $("lang");
  const updated = $("updated");
  const sourcesBtn = $("sources-btn");
  const sourcesPanel = $("sources-panel");
  const sourcesCount = $("sources-count");

  let data;
  try {
    const res = await fetch("data/news.json", { cache: "no-cache" });
    data = await res.json();
  } catch (e) {
    list.innerHTML = '<p class="empty">No se pudieron cargar las noticias. ' +
      "Si abres el archivo directamente, usa un servidor local (python -m http.server).</p>";
    return;
  }

  const fmt = new Intl.DateTimeFormat("es-ES", { dateStyle: "medium", timeStyle: "short" });
  updated.textContent = `Actualizado: ${fmt.format(new Date(data.actualizado))} · ` +
    `${data.total_noticias} noticias analizadas`;

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const safeUrl = (u) => (/^https?:\/\//i.test(u) ? u : "#");

  // ---------- Filtro de fuentes (se recuerda en este navegador) ----------
  const uniq = (arr) => [...new Set(arr)].sort((a, b) => a.localeCompare(b, "es"));
  const media = uniq(data.historias.flatMap((h) => h.fuentes.map((f) => f.medio)));
  const STORE_KEY = "nc-fuentes-ocultas";
  let hidden = new Set();
  try { hidden = new Set(JSON.parse(localStorage.getItem(STORE_KEY)) || []); } catch (e) { /* sin storage */ }
  const saveHidden = () => {
    try { localStorage.setItem(STORE_KEY, JSON.stringify([...hidden])); } catch (e) { /* sin storage */ }
  };
  const visible = (medio) => !hidden.has(medio);

  const checkbox = (m) => `<label class="chk"><input type="checkbox" value="${esc(m)}" ${visible(m) ? "checked" : ""}> ${esc(m)}</label>`;
  $("media-list").innerHTML = media.map(checkbox).join("");
  const allBoxes = () => [...sourcesPanel.querySelectorAll("input[type=checkbox]")];

  function updateSourcesCount() {
    const total = media.length;
    const shown = allBoxes().filter((b) => b.checked).length;
    sourcesCount.textContent = shown === total ? "" : `${shown}/${total}`;
  }

  sourcesBtn.addEventListener("click", () => {
    const open = sourcesPanel.hidden;
    sourcesPanel.hidden = !open;
    sourcesBtn.setAttribute("aria-expanded", String(open));
  });
  document.addEventListener("click", (e) => {
    if (!sourcesPanel.hidden && !e.target.closest(".filter")) {
      sourcesPanel.hidden = true;
      sourcesBtn.setAttribute("aria-expanded", "false");
    }
  });
  sourcesPanel.addEventListener("change", (e) => {
    const box = e.target;
    if (box.checked) hidden.delete(box.value); else hidden.add(box.value);
    saveHidden(); updateSourcesCount(); render();
  });
  sourcesPanel.querySelectorAll("[data-all]").forEach((btn) => btn.addEventListener("click", () => {
    const on = btn.dataset.all === "1";
    allBoxes().forEach((b) => { b.checked = on; if (on) hidden.delete(b.value); else hidden.add(b.value); });
    saveHidden(); updateSourcesCount(); render();
  }));

  // ---------- Noticias con versiones ----------
  const selected = new Map(); // índice de historia -> medio elegido

  function storyHtml(h, idx, fuentes) {
    const medio = selected.get(idx);
    const f = fuentes.find((x) => x.medio === medio) || fuentes[0];
    const others = h.num_medios - fuentes.length;
    const hoaxes = fuentes.filter((x) => x.bulo).length;
    return `
      <article class="story" data-idx="${idx}">
        <div class="badges">
          <span class="badge ${fuentes.length >= 3 ? "hot" : ""}">${fuentes.length} ${fuentes.length === 1 ? "versión" : "versiones"}</span>
          <span class="badge">${esc(fmt.format(new Date(h.fecha)))}</span>
          ${others > 0 ? `<span class="badge muted">+${others} en fuentes ocultas</span>` : ""}
          ${hoaxes ? `<span class="badge danger">⚠ ${hoaxes === 1 ? "1 versión desmentida" : `${hoaxes} versiones desmentidas`}</span>` : ""}
        </div>
        ${fuentes.length > 1 ? `
        <div class="versions" role="tablist" aria-label="Versiones de la noticia">
          ${fuentes.map((x) => `<button type="button" role="tab" data-medio="${esc(x.medio)}"
              aria-selected="${x === f}" ${x.bulo ? 'class="is-hoax" title="Desmentido por un verificador"' : ""}>${x.bulo ? "⚠ " : ""}${esc(x.medio)}</button>`).join("")}
        </div>` : ""}
        <div class="version ${f.bulo ? "is-hoax" : ""}" role="tabpanel">
          ${f.bulo ? `
          <div class="hoax-note">
            <strong>⚠ Bulo: este titular ha sido desmentido</strong>
            <p>Lo confirma <b>${esc(f.bulo.medio)}</b>:
              <a href="${esc(safeUrl(f.bulo.enlace))}" target="_blank" rel="noopener noreferrer">${esc(f.bulo.titulo)}</a></p>
          </div>` : ""}
          <p class="medio">${esc(f.medio)}<span class="lang">${esc(f.idioma)}</span>
            <span class="when">${esc(fmt.format(new Date(f.fecha)))}</span></p>
          <h2><a href="${esc(safeUrl(f.enlace))}" target="_blank" rel="noopener noreferrer">${esc(f.titulo)}</a></h2>
          ${f.extracto ? `<p class="extract">${esc(f.extracto)}</p>` : ""}
          <a class="read" href="${esc(safeUrl(f.enlace))}" target="_blank" rel="noopener noreferrer">Leer en ${esc(f.medio)} →</a>
        </div>
      </article>`;
  }

  function visibleFuentes(h) {
    return h.fuentes.filter((f) => visible(f.medio));
  }

  function renderNews(term) {
    const onlyMulti = multi.checked;
    const l = lang.value;
    const rows = [];
    data.historias.forEach((h, idx) => {
      const fuentes = visibleFuentes(h);
      if (!fuentes.length) return;
      if (onlyMulti && fuentes.length < 2) return;
      if (l && !fuentes.some((f) => f.idioma === l)) return;
      if (term) {
        const hay = fuentes.map((f) => f.medio + " " + f.titulo).join(" ").toLowerCase();
        if (!hay.includes(term)) return;
      }
      rows.push(storyHtml(h, idx, fuentes));
    });
    return rows;
  }

  function render() {
    const term = q.value.trim().toLowerCase();
    const rows = renderNews(term);
    empty.hidden = rows.length > 0;
    list.innerHTML = rows.join("");
  }

  // Cambiar de versión sin repintar toda la lista
  list.addEventListener("click", (e) => {
    const btn = e.target.closest(".versions [data-medio]");
    if (!btn) return;
    const card = btn.closest(".story");
    const idx = Number(card.dataset.idx);
    selected.set(idx, btn.dataset.medio);
    const tmp = document.createElement("div");
    tmp.innerHTML = storyHtml(data.historias[idx], idx, visibleFuentes(data.historias[idx]));
    const fresh = tmp.firstElementChild;
    card.replaceWith(fresh);
    fresh.querySelector(`.versions [data-medio="${CSS.escape(btn.dataset.medio)}"]`).focus();
  });
  // Flechas izquierda/derecha para moverse entre versiones
  list.addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
    const btn = e.target.closest(".versions [data-medio]");
    if (!btn) return;
    const tabs = [...btn.parentElement.children];
    const next = tabs[(tabs.indexOf(btn) + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
    next.click();
    e.preventDefault();
  });

  [q, multi, lang].forEach((el) => el.addEventListener("input", render));
  updateSourcesCount();
  render();
})();
