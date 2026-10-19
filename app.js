(async function () {
  const $ = (id) => document.getElementById(id);
  const list = $("list");
  const empty = $("empty");
  const q = $("q");
  const multi = $("multi");
  const lang = $("lang");
  const sort = $("sort");
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

  // ---------- Etiquetas (#) ----------
  let activeTag = "";
  const tagFilter = $("tag-filter");
  const tagsOf = (h) => [...(h.temas || []), ...(h.lugares || [])];
  const tagsHtml = (h) => {
    const tags = tagsOf(h);
    return tags.length ? `<div class="tags">${tags.map((t) =>
      `<button type="button" class="tag" data-tag="${esc(t)}">#${esc(t)}</button>`).join("")}</div>` : "";
  };
  function setTag(tag) {
    activeTag = tag;
    tagFilter.hidden = !tag;
    tagFilter.querySelector("span").textContent = "#" + tag;
    render();
  }
  tagFilter.addEventListener("click", () => setTag(""));

  // ---------- Tarjetas ----------
  const visibleFuentes = (h) => h.fuentes.filter((f) => visible(f.medio));
  const img = (url, cls) => url
    ? `<img class="${cls}" src="${esc(safeUrl(url))}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">`
    : "";

  // Titular neutro: el elegido por el script, salvo que su medio esté oculto
  function headline(h, fuentes) {
    if (visible(h.titulo_medio || "")) return { titulo: h.titulo, medio: h.titulo_medio };
    return { titulo: fuentes[0].titulo, medio: fuentes[0].medio };
  }

  // ---------- Narrativa por lado (izquierda / derecha) ----------
  const SB_NAME = { izquierda: "Izquierda", centro: "Centro", derecha: "Derecha" };

  // Cómo lo cuenta cada lado: resumen con IA si existe y todos sus medios están visibles;
  // si no, el titular más reciente de ese lado (las fuentes vienen ordenadas por fecha).
  function narrativeHtml(h, fuentes) {
    if (!fuentes.some((f) => f.sesgo === "izquierda" || f.sesgo === "derecha")) return "";
    const ai = h.narrativa && h.narrativa.modo === "ia" ? h.narrativa : null;
    let usedAi = false;
    const col = (k) => {
      const mine = fuentes.filter((f) => f.sesgo === k);
      if (!mine.length) {
        return `<div class="sb-col ${k}"><h3>${SB_NAME[k]}</h3><p class="sb-none">Sin cobertura en las fuentes mostradas.</p></div>`;
      }
      const d = ai && ai[k] && ai[k].medios.every(visible) ? ai[k] : null;
      if (d) usedAi = true;
      return `<div class="sb-col ${k}"><h3>${SB_NAME[k]}</h3>
        <p>${d ? esc(d.texto) : `«${esc(mine[0].titulo)}»`}</p>
        <p class="sb-by">${esc((d ? d.medios : mine.map((f) => f.medio)).join(", "))}</p></div>`;
    };
    const cols = col("izquierda") + col("derecha");
    return `<div class="sb-narr"><div class="sb-cols">${cols}</div>
      <p class="sb-note">${usedAi ? "Resumen generado por IA a partir de titulares y extractos; puede contener errores."
        : "Titular más reciente de cada lado."}</p></div>`;
  }

  function storyHtml(h, idx, fuentes) {
    const t = headline(h, fuentes);
    const others = h.num_medios - fuentes.length;
    const hoaxes = fuentes.filter((x) => x.bulo).length;
    const image = (fuentes.find((x) => x.medio === t.medio) || {}).imagen || h.imagen ||
      (fuentes.find((x) => x.imagen) || {}).imagen;
    const names = fuentes.slice(0, 4).map((x) => esc(x.medio)).join(" · ") +
      (fuentes.length > 4 ? ` · +${fuentes.length - 4}` : "");
    return `
      <article class="story ${image ? "has-img" : ""}" data-idx="${idx}">
        ${img(image, "thumb")}
        <div class="story-body">
          <div class="badges">
            <span class="badge ${fuentes.length >= 3 ? "hot" : ""}">${fuentes.length} ${fuentes.length === 1 ? "medio" : "medios"}</span>
            <span class="badge">${esc(fmt.format(new Date(h.fecha)))}</span>
            ${others > 0 ? `<span class="badge muted">+${others} en fuentes ocultas</span>` : ""}
            ${hoaxes ? `<span class="badge danger">⚠ ${hoaxes === 1 ? "1 versión desmentida" : `${hoaxes} versiones desmentidas`}</span>` : ""}
          </div>
          <h2><button type="button" class="open">«${esc(t.titulo)}»</button></h2>
          <p class="attrib">Titular de ${esc(t.medio)}</p>
          ${tagsHtml(h)}
          <div class="story-foot">
            <span class="names">${names}</span>
            <button type="button" class="open compare">${fuentes.length > 1 ? `Comparar ${fuentes.length} versiones` : "Ver la noticia"} →</button>
          </div>
        </div>
      </article>`;
  }

  function matches(h, fuentes, term) {
    if (activeTag && !tagsOf(h).includes(activeTag)) return false;
    if (!term) return true;
    const hay = (fuentes.map((f) => f.medio + " " + f.titulo).join(" ") + " " +
      tagsOf(h).map((t) => "#" + t).join(" ")).toLowerCase();
    return hay.includes(term);
  }

  function render() {
    const term = q.value.trim().toLowerCase();
    const onlyMulti = multi.checked;
    const l = lang.value;
    const rows = [];
    data.historias.forEach((h, idx) => {
      const fuentes = visibleFuentes(h);
      if (!fuentes.length) return;
      if (onlyMulti && fuentes.length < 2) return;
      if (l && !fuentes.some((f) => f.idioma === l)) return;
      if (!matches(h, fuentes, term)) return;
      rows.push({ h, idx, fuentes });
    });
    // Orden: más recientes primero (por defecto) o las noticias que cuentan más medios
    const byDate = (a, b) => b.h.fecha.localeCompare(a.h.fecha);
    rows.sort(sort.value === "medios"
      ? (a, b) => b.fuentes.length - a.fuentes.length || byDate(a, b)
      : byDate);
    empty.hidden = rows.length > 0;
    list.innerHTML = rows.map((r) => storyHtml(r.h, r.idx, r.fuentes)).join("");
  }

  // ---------- Vista en columnas: una por medio ----------
  const detail = $("detail");

  function columnHtml(f) {
    const link = esc(safeUrl(f.enlace));
    return `
      <section class="col ${f.bulo ? "is-hoax" : ""}">
        <header class="col-head">${f.bulo ? "⚠ " : ""}${esc(f.medio)}<span class="lang">${esc(f.idioma)}</span>${f.sesgo ? `<span class="sb-chip ${f.sesgo}">${esc(f.sesgo_detalle || f.sesgo)}</span>` : ""}</header>
        ${img(f.imagen, "col-img")}
        ${f.bulo ? `
        <div class="hoax-note">
          <strong>⚠ Bulo: este titular ha sido desmentido</strong>
          <p>Lo confirma <b>${esc(f.bulo.medio)}</b>:
            <a href="${esc(safeUrl(f.bulo.enlace))}" target="_blank" rel="noopener noreferrer">${esc(f.bulo.titulo)}</a></p>
        </div>` : ""}
        <h3><a href="${link}" target="_blank" rel="noopener noreferrer">${esc(f.titulo)}</a></h3>
        <p class="when">${esc(fmt.format(new Date(f.fecha)))}</p>
        ${f.extracto ? `<p class="extract">${esc(f.extracto)}</p>` : ""}
        <a class="read" href="${link}" target="_blank" rel="noopener noreferrer">Leer en ${esc(f.medio)} →</a>
      </section>`;
  }

  function openDetail(idx) {
    const h = data.historias[idx];
    const fuentes = visibleFuentes(h);
    const t = headline(h, fuentes);
    const sbExtra = narrativeHtml(h, fuentes);
    detail.innerHTML = `
      <div class="detail-head">
        <div>
          <h2>«${esc(t.titulo)}»</h2>
          <p class="attrib">Titular de ${esc(t.medio)} · ${fuentes.length} ${fuentes.length === 1 ? "versión" : "versiones"}</p>
          ${tagsHtml(h)}
        </div>
        <button type="button" class="close" aria-label="Cerrar">✕</button>
      </div>
      ${sbExtra ? `<div class="sb-detail">${sbExtra}</div>` : ""}
      <div class="columns" style="--n:${fuentes.length}">${fuentes.map(columnHtml).join("")}</div>`;
    detail.showModal();
    // abrir siempre arriba del todo (el foco automático puede desplazar el panel)
    detail.querySelector(".close").focus({ preventScroll: true });
    detail.scrollTop = 0;
    detail.querySelector(".columns").scrollLeft = 0;
  }

  detail.addEventListener("click", (e) => {
    if (e.target === detail || e.target.closest(".close")) { detail.close(); return; }
    const tag = e.target.closest(".tag");
    if (tag) { detail.close(); setTag(tag.dataset.tag); }
  });

  list.addEventListener("click", (e) => {
    const tag = e.target.closest(".tag");
    if (tag) { setTag(tag.dataset.tag); return; }
    if (e.target.closest("a")) return;
    const card = e.target.closest(".story");
    if (card) openDetail(Number(card.dataset.idx));
  });

  [q, multi, lang, sort].forEach((el) => el.addEventListener("input", render));
  updateSourcesCount();
  render();
})();
