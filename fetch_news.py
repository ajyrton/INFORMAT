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


def fetch_items(feeds):
    import feedparser  # pip install feedparser (solo hace falta al descargar feeds)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
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


def cluster(items):
    """Agrupación greedy: cada noticia se une al grupo más parecido
    (si supera el umbral y ese grupo aún no tiene noticia de su mismo medio)."""
    vecs = build_vectors(items)
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


def build_output(items, groups):
    out = []
    for g in groups:
        members = sorted((items[i] for i in g["members"]), key=lambda x: x["fecha"], reverse=True)
        out.append({
            "titulo": members[0]["titulo"],
            "fecha": max(m["fecha"] for m in members),
            "num_medios": len({m["medio"] for m in members}),
            "fuentes": [{k: m[k] for k in ("medio", "idioma", "titulo", "enlace", "extracto", "fecha")}
                        for m in members],
        })
    # primero las más cubiertas, luego las más recientes
    out.sort(key=lambda x: (x["num_medios"], x["fecha"]), reverse=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", help="JSON con noticias de prueba en vez de descargar feeds")
    args = ap.parse_args()

    if args.sample:
        items = json.loads(Path(args.sample).read_text(encoding="utf-8"))
    else:
        feeds = json.loads((ROOT / "feeds.json").read_text(encoding="utf-8"))
        items = fetch_items(feeds)

    if not items:
        print("No se obtuvieron noticias; no se sobrescribe news.json", file=sys.stderr)
        sys.exit(1)

    groups = cluster(items)
    result = {
        "actualizado": datetime.now(timezone.utc).isoformat(),
        "total_noticias": len(items),
        "historias": build_output(items, groups),
    }
    out = ROOT / "data" / "news.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    multi = sum(1 for h in result["historias"] if h["num_medios"] > 1)
    print(f"{len(items)} noticias -> {len(result['historias'])} historias ({multi} con varios medios)")


if __name__ == "__main__":
    main()
