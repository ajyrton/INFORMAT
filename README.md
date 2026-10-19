# INFORMAT

Web que recopila la misma noticia contada por distintos medios. Coste: 0 €.

## Cómo funciona

1. `fetch_news.py` lee los feeds RSS de `feeds.json`.
2. Agrupa los titulares que tratan el mismo suceso (TF-IDF + similitud del coseno).
3. Para cada historia elige un titular neutro (el más representativo, sin exclamaciones ni declaraciones
   entrecomilladas), una imagen de portada y unas etiquetas (#tema y #lugar, en `etiquetas.py`).
4. Cruza los titulares con los desmentidos de los verificadores de `verificadores.json` y marca los bulos.
5. Etiqueta cada medio como izquierda / centro / derecha según `sesgo_medios.json` (clasificación editorial
   provisional y editable). Con eso la vista de comparación muestra **cómo la cuenta cada lado**.
6. Opcional: `summarize.py` genera con IA un resumen corto del enfoque de la izquierda y de la derecha.
   Sin configurar nada, la web muestra el titular más reciente de cada lado (coste 0).
7. Guarda el resultado en `data/news.json`.
8. `index.html` + `app.js` muestran cada historia; al pulsarla se comparan las versiones de cada medio en columnas.

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

## Orientación de los medios y resúmenes con IA

- **Clasificación**: edita `sesgo_medios.json`. Es provisional y discutible; cuando tengas una fuente que la
  respalde, anótala en `fuente`. Los medios que no aparecen quedan "sin clasificar" y no se asignan a ningún lado.
- **Resúmenes con IA (opcional)**: sirve cualquier API compatible con OpenAI. En
  **Settings → Secrets and variables → Actions** crea los secrets `LLM_API_URL`, `LLM_API_KEY` y `LLM_MODEL`
  (y, si quieres, la variable `LLM_MAX_STORIES`, por defecto 8). Algunos proveedores tienen capa gratuita con
  límites: compruébalos antes. Los resultados se guardan en `data/narrativas_cache.json`. Si la IA falla,
  la web vuelve a mostrar titulares. Los resúmenes pueden contener errores y la web lo indica.

## Ideas para el futuro

- Categorías (política, economía, deportes...).
- Indicador de enfoque o sesgo por medio.
- Mejor agrupación con embeddings multilingües, para unir noticias en español e inglés.
