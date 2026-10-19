#!/usr/bin/env python3
"""Lee feeds RSS de varios medios, agrupa las noticias que tratan lo mismo
y guarda el resultado en data/news.json.

Solo se guardan titular, enlace, fecha y un extracto corto: el contenido
completo siempre se lee en la web del medio.

Uso:
    python fetch_news.py            # descarga feeds reales
    python fetch_news.py --sample sample_items.json   # usa datos de prueba
"""
import argparse
import hashlib
import html
import json
import math
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

from etiquetas import etiquetas
from summarize import add_narratives

ROOT = Path(__file__).parent
# Orientación editorial de cada medio (ver sesgo_medios.json): 5 niveles -> 3 lados
BUCKET = {"izquierda": "izquierda", "centro-izquierda": "izquierda", "centro": "centro",
          "centro-derecha": "derecha", "derecha": "derecha"}
MAX_AGE_HOURS = 48          # ignorar noticias más antiguas
SIM_THRESHOLD = 0.30        # similitud mínima para agrupar (0-1)
MAX_PER_FEED = 40
SNIPPET_LEN = 200
# Entradilla de la página de cada noticia: las primeras frases del texto que el medio
# publica en su feed. Se limita a propósito (derechos de autor): el artículo completo
# se lee siempre en la web del medio.
LEAD_LEN = 500
HOAX_MAX_AGE_DAYS = 14      # antigüedad máxima de los desmentidos
HOAX_SIM_THRESHOLD = 0.30   # similitud mínima entre un titular y un desmentido para marcarlo como bulo

# Titulares de verificadores que indican que algo es falso o engañoso
# (se comparan sin tildes y en minúsculas).
HOAX_RE = re.compile(
    r"^(no|tampoco)\b|\bes falso\b|\bbulo|\bfals[oa]s?\b|\bno es\b|\bno son\b|\bno hay\b"
    r"|\bno fue\b|\bno ha\b|\bno muestra|\bno corresponde|\bmanipulad|\bmontaje|\btrucad"
    r"|\b(hech|cread|generad)[oa]s? con (ia|inteligencia artificial)"
    r"|\b(es|son) de (19|20)\d\d\b|\bse grabo en (19|20)\d\d|\benganos[oa]|\bfake\b")
REAL_RE = re.compile(r"^(es|son) reales?\b|\bes cierto\b|\bes verdad\b")
# Noticias que informan SOBRE un bulo (lo desmienten o lo denuncian): no son bulos.
REPORTS_HOAX_RE = re.compile(
    r"\bfals[oa]s?\b|\bfalsamente\b|\bbulos?\b|\bdesmient|\bdesinforma|\bfake\b|\bmanipulad"
    r"|\b(hech|cread|generad)[oa]s? con (ia|inteligencia artificial)|\bno es (cierto|verdad)\b|\bverific")

STOPWORDS = set("""
a al algo ante con contra cual cuando de del desde donde durante e el ella ellos en entre era es esta este esto
estos fue ha han hasta hay la las le les lo los mas me mi muy no nos o otra otro para pero por que se sin sobre
su sus tras un una uno unas unos y ya the of to in and for on is are was were at by with from as an be this that
it its after over new says say will has have not but their his her who what how
""".split())


def normalize(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()


def tokens(text: str):
    return [t for t in re.findall(r"[a-z0-9]{3,}", normalize(text)) if t not in STOPWORDS]


def clean_snippet(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= SNIPPET_LEN else text[:SNIPPET_LEN].rsplit(" ", 1)[0] + "…"


def lead_text(entry) -> str:
    """Primeras frases del texto del feed (resumen o contenido), cortadas en un punto."""
    texts = [entry.get("summary", "")] + [c.get("value", "") for c in entry.get("content", []) or []]
    # párrafos completos en el orden en que aparecen, del texto más largo
    raw = max(texts, key=lambda t: len(re.sub(r"<[^>]+>", "", t or "")))
    paras = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(p))).strip()
             for p in re.split(r"(?i)</p>|<br\s*/?>|\n{2,}", raw or "")]
    text = re.sub(r"\s+([,.;:)»])", r"\1", " ".join(p for p in paras if p))
    if len(text) <= LEAD_LEN:
        return text
    cut = text[:LEAD_LEN]
    end = max(cut.rfind(". "), cut.rfind(".» "), cut.rfind('." '))
    return cut[:end + 1] if end > LEAD_LEN * 0.4 else cut.rsplit(" ", 1)[0] + "…"


def parse_date(entry):
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def find_image(entry):
    """URL de la imagen que el medio publica en su feed (la de mayor anchura), o None."""
    best, best_w = None, -1
    for key in ("media_content", "media_thumbnail"):
        for m in entry.get(key, []) or []:
            url, kind = m.get("url", ""), str(m.get("type", "") or m.get("medium", "image"))
            if url.startswith("https://") and ("image" in kind or key == "media_thumbnail"):
                w = int(m.get("width") or 0)
                if w > best_w:
                    best, best_w = url, w
    if best:
        return best
    for link in entry.get("links", []):
        if link.get("rel") == "enclosure" and str(link.get("type", "")).startswith("image") \
                and link.get("href", "").startswith("https://"):
            return link["href"]
    m = re.search(r'<img[^>]+src="(https://[^"]+)"', entry.get("summary", ""))
    return html.unescape(m.group(1)) if m else None


def fetch_items(feeds, max_age_hours=MAX_AGE_HOURS):
    import feedparser  # pip install feedparser (solo hace falta al descargar feeds)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    items = []
    for f in feeds:
        try:
            parsed = feedparser.parse(f["url"], agent="INFORMAT/1.0")
        except Exception as e:  # noqa: BLE001
            print(f"[!] {f['medio']}: {e}", file=sys.stderr)
            continue
        n = 0
        for e in parsed.entries[:MAX_PER_FEED]:
            date = parse_date(e) or datetime.now(timezone.utc)
            if date < cutoff:
                continue
            title = re.sub(r"\s+", " ", html.unescape(e.get("title", ""))).strip()
            link = e.get("link")
            if not title or not link:
                continue
            items.append({
                "medio": f["medio"], "idioma": f.get("idioma", "es"),
                "titulo": title, "enlace": link,
                "extracto": clean_snippet(e.get("summary", "")),
                "entradilla": lead_text(e),
                "fecha": date.isoformat(),
                "imagen": find_image(e),
                "categorias": [t["term"] for t in e.get("tags", []) if t.get("term")][:8],
            })
            n += 1
        print(f"[ok] {f['medio']}: {n} noticias", file=sys.stderr)
    return items


def load_bias():
    """medio -> etiqueta detallada (ej. 'centro-izquierda'). Sin archivo, nada se clasifica."""
    path = ROOT / "sesgo_medios.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {m: lab for m, lab in data.get("medios", {}).items() if lab in BUCKET}


def tag_bias(items, bias):
    """Añade 'sesgo' (izquierda/centro/derecha) y 'sesgo_detalle' a cada noticia clasificada."""
    for it in items:
        label = bias.get(it["medio"])
        if label:
            it["sesgo"], it["sesgo_detalle"] = BUCKET[label], label


# ---------- Agrupación (TF-IDF + coseno, sin dependencias extra) ----------

def build_vectors(items):
    docs = []
    for it in items:
        # el titular pesa el doble que el extracto
        docs.append(Counter(tokens(it["titulo"]) * 2 + tokens(it["extracto"])))
    df = Counter()
    for d in docs:
        df.update(d.keys())
    n = len(docs)
    vecs = []
    for d in docs:
        v = {t: (1 + math.log(c)) * math.log((n + 1) / (df[t] + 0.5)) for t, c in d.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({t: x / norm for t, x in v.items()})
    return vecs


def cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


def cluster(items, vecs):
    """Agrupación greedy: cada noticia se une al grupo más parecido
    (si supera el umbral y ese grupo aún no tiene noticia de su mismo medio)."""
    order = sorted(range(len(items)), key=lambda i: items[i]["fecha"], reverse=True)
    groups = []  # {"members": [idx], "centroid": dict}
    for i in order:
        best, best_sim = None, 0.0
        for g in groups:
            if any(items[m]["medio"] == items[i]["medio"] for m in g["members"]):
                continue
            sim = max(cosine(vecs[i], vecs[m]) for m in g["members"])
            if sim > best_sim:
                best, best_sim = g, sim
        if best is not None and best_sim >= SIM_THRESHOLD:
            best["members"].append(i)
        else:
            groups.append({"members": [i]})
    return groups


def is_hoax_debunk(item):
    """True si el titular del verificador desmiente algo (falso, manipulado, sacado de contexto)."""
    t = normalize(item["titulo"]).strip()
    return bool(HOAX_RE.search(t)) and not REAL_RE.search(t)


def flag_hoaxes(items, vecs, hoaxes, hoax_vecs):
    """Devuelve {índice de noticia: desmentido} para los titulares que un verificador
    ha desmentido. Se ignoran las noticias que solo informan sobre el bulo."""
    flagged = {}
    for i, (it, v) in enumerate(zip(items, vecs)):
        if REPORTS_HOAX_RE.search(normalize(it["titulo"] + " " + it["extracto"])):
            continue
        best, best_sim = None, HOAX_SIM_THRESHOLD
        for h, hv in zip(hoaxes, hoax_vecs):
            sim = cosine(v, hv)
            if sim >= best_sim:
                best, best_sim = h, sim
        if best is not None:
            flagged[i] = {k: best[k] for k in ("medio", "titulo", "enlace")}
    return flagged


# Rasgos de un titular poco neutro: exclamaciones, preguntas y declaraciones entrecomilladas
LOADED_RE = re.compile(r"[!¡?¿]|[«»\"“”]")


def neutral_index(idxs, items, vecs, flagged):
    """Elige el titular más representativo del grupo: el que más se parece a los demás,
    en español si lo hay, sin bulos y penalizando signos de sensacionalismo."""
    def score(i):
        others = [j for j in idxs if j != i]
        sim = sum(cosine(vecs[i], vecs[j]) for j in others) / len(others) if others else 0.0
        if LOADED_RE.search(items[i]["titulo"]):
            sim -= 0.15
        return (i not in flagged, items[i]["idioma"] == "es", sim)
    return max(idxs, key=score)


def build_output(items, groups, vecs, flagged=None):
    fields = ("medio", "idioma", "titulo", "enlace", "extracto", "entradilla", "fecha", "imagen",
              "sesgo", "sesgo_detalle")
    flagged = flagged or {}
    out = []
    for g in groups:
        idxs = sorted(g["members"], key=lambda i: items[i]["fecha"], reverse=True)
        neutral = neutral_index(idxs, items, vecs, flagged)
        fuentes = []
        for i in idxs:
            f = {k: items[i][k] for k in fields if items[i].get(k)}
            if len(f.get("entradilla", "")) <= len(f.get("extracto", "")):
                f.pop("entradilla", None)  # no aporta nada nuevo
            if i in flagged:
                f["bulo"] = flagged[i]
            fuentes.append(f)
        # id estable entre actualizaciones: el enlace de la noticia más antigua del grupo
        story = {
            "id": hashlib.sha1(items[idxs[-1]]["enlace"].encode("utf-8")).hexdigest()[:10],
            "titulo": items[neutral]["titulo"],
            "titulo_medio": items[neutral]["medio"],
            "fecha": max(f["fecha"] for f in fuentes),
            "num_medios": len({f["medio"] for f in fuentes}),
            "imagen": items[neutral].get("imagen") or next((f["imagen"] for f in fuentes if f.get("imagen")), None),
            **etiquetas([items[i] for i in idxs]),
            "fuentes": fuentes,
        }
        if not story["imagen"]:
            del story["imagen"]
        out.append(story)
    # primero las más cubiertas, luego las más recientes
    out.sort(key=lambda x: (x["num_medios"], x["fecha"]), reverse=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", help="JSON con noticias de prueba en vez de descargar feeds")
    args = ap.parse_args()

    if args.sample:
        items = json.loads(Path(args.sample).read_text(encoding="utf-8"))
        checks = []
    else:
        feeds = json.loads((ROOT / "feeds.json").read_text(encoding="utf-8"))
        items = fetch_items(feeds)
        checkers = json.loads((ROOT / "verificadores.json").read_text(encoding="utf-8"))
        checks = fetch_items(checkers, max_age_hours=HOAX_MAX_AGE_DAYS * 24)

    if not items:
        print("No se obtuvieron noticias; no se sobrescribe news.json", file=sys.stderr)
        sys.exit(1)

    tag_bias(items, load_bias())
    hoaxes = sorted((c for c in checks if is_hoax_debunk(c)), key=lambda x: x["fecha"], reverse=True)
    # vectores comunes para que noticias y bulos compartan el mismo IDF
    vecs = build_vectors(items + hoaxes)
    news_vecs, hoax_vecs = vecs[:len(items)], vecs[len(items):]
    groups = cluster(items, news_vecs)
    flagged = flag_hoaxes(items, news_vecs, hoaxes, hoax_vecs)
    historias = build_output(items, groups, news_vecs, flagged)
    add_narratives(historias, ROOT)  # opcional: solo con LLM_API_* configuradas
    result = {
        "actualizado": datetime.now(timezone.utc).isoformat(),
        "total_noticias": len(items),
        "historias": historias,
    }
    out = ROOT / "data" / "news.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    multi = sum(1 for h in result["historias"] if h["num_medios"] > 1)
    print(f"{len(items)} noticias -> {len(result['historias'])} historias ({multi} con varios medios)")
    print(f"{len(checks)} verificaciones -> {len(hoaxes)} desmentidos -> "
          f"{len(flagged)} titulares marcados como bulo")


if __name__ == "__main__":
    main()
