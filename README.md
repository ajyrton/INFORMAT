# INFORMAT

Web que recopila la misma noticia contada por distintos medios. Coste: 0 €.

## Cómo funciona

1. `fetch_news.py` lee los feeds RSS de `feeds.json`.
2. Agrupa los titulares que tratan el mismo suceso (TF-IDF + similitud del coseno).
3. Para cada historia elige un titular neutro (el más representativo, sin exclamaciones ni declaraciones
   entrecomilladas), una imagen de portada y unas etiquetas (#tema y #lugar, en `etiquetas.py`).
4. Cruza los titulares con los desmentidos de los verificadores de `verificadores.json` y marca los bulos.
5. Guarda el resultado en `data/news.json`.
6. `index.html` + `app.js` muestran cada historia; al pulsarla se comparan las versiones de cada medio en columnas.

Solo se guardan titular, enlace, fecha y un extracto corto. El contenido completo se lee siempre en el medio original.

## Probar en local

```bash
pip install feedparser
python fetch_news.py
python -m http.server 8000
```

Abre http://localhost:8000

## Publicarlo gratis (GitHub Pages + Actions)

1. Crea un repositorio público en GitHub y sube estos archivos.
2. En **Settings → Pages**, elige la rama `main` y la carpeta raíz.
3. En **Actions**, ejecuta "Actualizar noticias" una vez de forma manual.
   Después se actualiza solo cada 30 minutos.

## Personalizar

- **Medios**: edita `feeds.json` (añade o quita feeds RSS).
- **Sensibilidad del agrupador**: cambia `SIM_THRESHOLD` en `fetch_news.py`
  (más bajo = agrupa más; más alto = agrupa solo lo muy parecido).
- **Antigüedad máxima**: `MAX_AGE_HOURS`.
- **Temas y lugares**: añade palabras a `TEMAS` o lugares a las listas de `etiquetas.py`.
- **Detección de bulos**: `HOAX_SIM_THRESHOLD` en `fetch_news.py` (más alto = marca menos titulares).

## Ideas para el futuro

- Categorías (política, economía, deportes...).
- Indicador de enfoque o sesgo por medio.
- Mejor agrupación con embeddings multilingües, para unir noticias en español e inglés.
