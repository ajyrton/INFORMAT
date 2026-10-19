(async function () {
  const list = document.getElementById("list");
  const empty = document.getElementById("empty");
  const q = document.getElementById("q");
  const multi = document.getElementById("multi");
  const lang = document.getElementById("lang");
  const updated = document.getElementById("updated");

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

  function render() {
    const term = q.value.trim().toLowerCase();
    const onlyMulti = multi.checked;
    const l = lang.value;

    const stories = data.historias.filter((h) => {
      if (onlyMulti && h.num_medios < 2) return false;
      if (l && !h.fuentes.some((f) => f.idioma === l)) return false;
      if (term) {
        const hay = h.fuentes.map((f) => f.medio + " " + f.titulo).join(" ").toLowerCase();
        if (!hay.includes(term)) return false;
      }
      return true;
    });

    empty.hidden = stories.length > 0;
    list.innerHTML = stories.map((h) => `
      <article class="story">
        <h2>${esc(h.titulo)}</h2>
        <div class="badges">
          <span class="badge ${h.num_medios >= 3 ? "hot" : ""}">${h.num_medios} ${h.num_medios === 1 ? "medio" : "medios"}</span>
          <span class="badge">${esc(fmt.format(new Date(h.fecha)))}</span>
        </div>
        <ul class="sources">
          ${h.fuentes.map((f) => `
            <li>
              <span class="medio">${esc(f.medio)}</span><span class="lang">${esc(f.idioma)}</span>
              <a href="${esc(safeUrl(f.enlace))}" target="_blank" rel="noopener noreferrer">${esc(f.titulo)}</a>
              ${f.extracto ? `<p>${esc(f.extracto)}</p>` : ""}
            </li>`).join("")}
        </ul>
      </article>`).join("");
  }

  [q, multi, lang].forEach((el) => el.addEventListener("input", render));
  render();
})();
