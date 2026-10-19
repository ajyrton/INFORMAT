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
import html
import json
import math
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
MAX_AGE_HOURS = 48          # ignorar noticias más antiguas
SIM_THRESHOLD = 0.30        # similitud mínima para agrupar (0-1)
MAX_PER_FEED = 40
SNIPPET_LEN = 200
HOAX_MAX_AGE_DAYS = 14      # antigüedad máxima de los desmentidos
HOAX_SIM_THRESHOLD = 0.20   # similitud mínima para enlazar un bulo con una noticia

# Titulares de verificadores que indican que algo es falso o engañoso
# (se comparan sin tildes y en minúsculas).
HOAX_RE = re.compile(
    r"^(no|tampoco)\b|\bes falso\b|\bbulo|\bfals[oa]s?\b|\bno es\b|\bno son\b|\bno hay\b"
    r"|\bno fue\b|\bno ha\b|\bno muestra|\bno corresponde|\bmanipulad|\bmontaje|\btrucad"
    r"|\b(hech|cread|generad)[oa]s? con (ia|inteligencia artificial)"
    r"|\b(es|son) de (19|20)\d\d\b|\bse grabo en (19|20)\d\d|\benganos[oa]|\bfake\b")
REAL_RE = re.compile(r"^(es|son) reales?\b|\bes cierto\b|\bes verdad\b")

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


def parse_date(entry):
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def fetch_items(feeds, max_age_hours=MAX_AGE_HOURS):
    import feedparser  # pip install feedparser (solo hace falta al descargar feeds)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    items = []
    for f in feeds:
        try:
            parsed = feedparser.parse(f["url"], agent="NoticiasContrastadas/1.0")
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
                "fecha": date.isoformat(),
            })
            n += 1
        print(f"[ok] {f['medio']}: {n} noticias", file=sys.stderr)
    return items


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


def link_hoaxes(groups, vecs, hoax_vecs):
    """Para cada bulo, devuelve los índices de grupo con los que guarda relación."""
    links = []
    for hv in hoax_vecs:
        related = [gi for gi, g in enumerate(groups)
                   if max(cosine(hv, vecs[m]) for m in g["members"]) >= HOAX_SIM_THRESHOLD]
        links.append(related)
    return links


def build_output(items, groups, hoaxes=(), hoax_links=()):
    fields = ("medio", "idioma", "titulo", "enlace", "extracto", "fecha")
    related = {}
    for h, gis in zip(hoaxes, hoax_links):
        for gi in gis:
            related.setdefault(gi, []).append({k: h[k] for k in ("medio", "titulo", "enlace")})
    out = []
    for gi, g in enumerate(groups):
        members = sorted((items[i] for i in g["members"]), key=lambda x: x["fecha"], reverse=True)
        story = {
            "titulo": members[0]["titulo"],
            "fecha": max(m["fecha"] for m in members),
            "num_medios": len({m["medio"] for m in members}),
            "fuentes": [{k: m[k] for k in fields} for m in members],
        }
        if gi in related:
            story["bulos_relacionados"] = related[gi]
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

    hoaxes = sorted((c for c in checks if is_hoax_debunk(c)), key=lambda x: x["fecha"], reverse=True)
    # vectores comunes para que noticias y bulos compartan el mismo IDF
    vecs = build_vectors(items + hoaxes)
    news_vecs, hoax_vecs = vecs[:len(items)], vecs[len(items):]
    groups = cluster(items, news_vecs)
    hoax_links = link_hoaxes(groups, news_vecs, hoax_vecs)
    historias = build_output(items, groups, hoaxes, hoax_links)
    result = {
        "actualizado": datetime.now(timezone.utc).isoformat(),
        "total_noticias": len(items),
        "historias": historias,
        "bulos": [{k: h[k] for k in ("medio", "titulo", "enlace", "extracto", "fecha")} for h in hoaxes],
    }
    out = ROOT / "data" / "news.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    multi = sum(1 for h in result["historias"] if h["num_medios"] > 1)
    print(f"{len(items)} noticias -> {len(result['historias'])} historias ({multi} con varios medios)")
    print(f"{len(checks)} verificaciones -> {len(hoaxes)} bulos desmentidos, "
          f"{sum(1 for h in historias if 'bulos_relacionados' in h)} noticias con bulo relacionado")


if __name__ == "__main__":
    main()
