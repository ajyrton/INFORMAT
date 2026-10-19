"""Etiquetas (#) de cada historia: tema general y lugar donde sucede.

Todo funciona con listas de palabras, sin dependencias externas. Para afinar
los resultados basta con añadir palabras a TEMAS o lugares a LUGARES.
"""
import re
import unicodedata
from collections import Counter
from urllib.parse import urlparse


def plain(text: str) -> str:
    """Quita tildes conservando la longitud del texto (para poder mirar mayúsculas)."""
    return "".join(unicodedata.normalize("NFKD", c)[0] for c in text)


# ---------------------------------------------------------------- Temas

# tema -> raíces de palabra (sin tildes, en minúsculas; se buscan al inicio de palabra)
TEMAS = {
    "Política": """gobierno congreso senado elecciones electoral psoe vox sumar podemos ministr parlament
        diputad alcald candidat votacion moncloa feijoo sanchez ayuso generalitat xunta lehendakari
        president referendum coalicion oposicion investidura legislatura ferraz genova
        government election parliament minister senator lawmaker congress democrat republican""",
    "Economía": """economi inflacion ipc paro desemple salari pib impuest hacienda bolsa ibex empresa
        banco bce tipos de interes hipotec alquiler aranceles arancel mercado inversion deficit deuda
        pension autonomos exportac importac petroleo gasolina factura beneficios
        economy inflation market tariff bank stocks shares investor recession trade""",
    "Delincuencia": """detenid detencion detiene asesin homicid crimen criminal robo robar atraco ladron
        narcotrafic droga estafa agresion agresor violencia de genero machista apunal acuchill tiroteo
        prision carcel condena condenad secuestr fraude blanqueo corrupcion trafico de
        murder arrested arrest police shooting stabbing jailed prison crime gang smuggling""",
    "Sucesos": """accidente incendio fallecid herid derrumb explosion rescat ahogad choque colision
        atropell desaparecid naufragio
        accident fire crash collapse explosion rescue drowned missing""",
    "Clima": """dana lluvia temporal tormenta inundac sequia ola de calor clima climatic aemet alerta roja
        alerta naranja huracan tifon granizo nevad calentamiento emisiones
        climate storm flood hurricane wildfire heatwave drought typhoon""",
    "Guerra": """guerra ataque bombarde ejercito misil dron militar tropas alto el fuego ofensiva
        invasion rehenes milicia otan hamas hezbola
        war attack strike missile drone military troops ceasefire offensive invasion hostages nato""",
    "Deportes": """futbol liga champions laliga real madrid atletico gol tenis baloncesto nba formula 1
        alcaraz nadal mundial seleccion entrenador fichaje olimpic ciclismo tour de francia motogp
        football soccer tennis basketball olympic coach striker tournament""",
    "Cultura": """cine pelicula serie musica concierto libro novela museo exposicion teatro festival
        artista escritor cantante netflix oscar goya album gira
        film movie music concert novel museum exhibition theatre singer album""",
    "Ciencia": """cientific investigador nasa espacio marte luna planeta cohete satelite
        descubrimiento fosil
        scientist science study space mars moon planet rocket satellite discovery""",
    "Tecnología": """tecnolog inteligencia artificial chatgpt openai google apple microsoft
        ciberataque hacker redes sociales algoritmo movil
        technology artificial intelligence cyberattack hacker social media algorithm smartphone""",
    "Salud": """salud hospital sanidad sanitari medic enfermedad virus vacuna cancer paciente
        epidemia brote urgencias farmac
        health hospital disease virus vaccine cancer patient outbreak""",
    "Sociedad": """educacion huelga colegio escuela universidad igualdad migrante inmigra refugiad
        religion iglesia papa vivienda okupa desahucio feminis lgtb
        education strike school university equality migrant immigration refugee church pope housing""",
}

# Secciones habituales en las URL y en las etiquetas RSS de los medios
SECCIONES = {
    "economia": "Economía", "business": "Economía", "economy": "Economía", "mercados": "Economía",
    "politica": "Política", "politics": "Política",
    "sucesos": "Sucesos", "tribunales": "Delincuencia",
    "deportes": "Deportes", "sport": "Deportes", "sports": "Deportes", "football": "Deportes",
    "cultura": "Cultura", "culture": "Cultura", "cine": "Cultura", "musica": "Cultura", "television": "Cultura",
    "ciencia": "Ciencia", "science": "Ciencia",
    "tecnologia": "Tecnología", "technology": "Tecnología",
    "salud": "Salud", "health": "Salud",
    "sociedad": "Sociedad", "society": "Sociedad", "educacion": "Sociedad",
    "clima": "Clima", "medio-ambiente": "Clima", "environment": "Clima", "climate": "Clima",
}

# Las raíces se separan por espacios, salvo estas frases, que se buscan enteras
_FRASES = {"violencia de genero", "trafico de", "tipos de interes", "ola de calor", "alerta roja", "alerta naranja",
           "alto el fuego", "real madrid", "formula 1", "tour de francia", "inteligencia artificial",
           "redes sociales", "artificial intelligence", "social media"}


def _compile_temas():
    out = {}
    for tema, raices in TEMAS.items():
        texto = " ".join(raices.split())
        words = []
        for f in sorted(_FRASES, key=len, reverse=True):
            if f in texto:
                words.append(f)
                texto = texto.replace(f, " ")
        words += texto.split()
        out[tema] = re.compile(r"\b(" + "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in words) + r")")
    return out


_TEMA_RE = _compile_temas()


def temas(fuentes, max_temas=2):
    score = Counter()
    for f in fuentes:
        titulo = plain(f["titulo"]).lower()
        texto = titulo + " " + plain(f.get("extracto", "")).lower()
        for tema, rx in _TEMA_RE.items():
            score[tema] += 2 * len(rx.findall(titulo)) + len(rx.findall(texto))
        # la sección de la URL es fiable; las etiquetas RSS a veces son genéricas (pesan menos)
        for p in urlparse(f.get("enlace", "")).path.lower().split("/"):
            if p in SECCIONES:
                score[SECCIONES[p]] += 3
        for t in f.get("categorias", []):
            p = plain(t).lower().replace(" ", "-")
            if p in SECCIONES:
                score[SECCIONES[p]] += 1
    ranked = [(t, s) for t, s in score.most_common() if s >= 2]
    if not ranked:
        return []
    top = ranked[0][1]
    return [t for t, s in ranked[:max_temas] if s >= top / 2]


# ---------------------------------------------------------------- Lugares

# nivel: 3 = ciudad, 2 = región, 1 = país. Los alias en MAYÚSCULAS distinguen mayúsculas (siglas).
_ESP_CIUDADES = """Madrid; Barcelona; Valencia; Sevilla; Zaragoza; Málaga; Murcia; Palma|Palma de Mallorca; Bilbao;
Alicante|Alacant; Córdoba; Valladolid; Vigo; Gijón; Granada; A Coruña|La Coruña; Vitoria|Vitoria-Gasteiz; Elche;
Oviedo; Santander; Pamplona|Iruña; San Sebastián|Donostia; Almería; Burgos; Salamanca; Albacete; Logroño;
Badajoz; Huelva; Cádiz; Jerez|Jerez de la Frontera; Lleida|Lérida; Tarragona; Girona|Gerona; Cáceres; Jaén;
Ourense; Lugo; Pontevedra; Santiago de Compostela; Castellón|Castelló; Toledo; Ciudad Real; Cuenca; Guadalajara;
Segovia; Ávila; Soria; Palencia; Zamora; Teruel; Huesca; Gandia|Gandía; Dénia|Denia; Paiporta; Torrent;
Algeciras; Marbella; Benidorm; Cartagena; Las Palmas|Las Palmas de Gran Canaria; Santa Cruz de Tenerife;
Tenerife; Gran Canaria; Lanzarote; Fuerteventura; Ibiza|Eivissa; Mallorca; Menorca; Hospitalet|L'Hospitalet;
Badalona; Sabadell; Terrassa; Móstoles; Alcalá de Henares; Getafe; Leganés; Fuenlabrada; Alcorcón; Torrejón;
Parla; Mérida; Ponferrada; Ferrol; Sagunto|Sagunt; Torrevieja; Orihuela; Lorca; Motril; Estepona"""
_ESP_REGIONES = """Andalucía; Aragón; Asturias; Baleares|Islas Baleares|Illes Balears; Canarias|Islas Canarias;
Cantabria; Castilla y León; Castilla-La Mancha|Castilla La Mancha; Cataluña|Catalunya; Comunidad Valenciana|Comunitat Valenciana;
Extremadura; Galicia; Comunidad de Madrid; Región de Murcia; Navarra; País Vasco|Euskadi; La Rioja; Ceuta; Melilla"""
_MUNDO_CIUDADES = """París|Paris; Londres|London; Berlín|Berlin; Roma|Rome; Bruselas|Brussels; Moscú|Moscow;
Kiev|Kyiv; Pekín|Beijing; Jerusalén|Jerusalem; Tel Aviv; Nueva York|New York; Los Ángeles|Los Angeles;
Lisboa|Lisbon; Ámsterdam|Amsterdam; Ginebra|Geneva; Estrasburgo|Strasbourg; Buenos Aires; Ciudad de México|Mexico City;
Bogotá; Caracas; La Habana|Havana; Lima; Quito; Montevideo; Teherán|Tehran; Beirut; Damasco|Damascus; Kabul;
Saint-Denis; Marsella|Marseille; Lyon; Milán|Milan; Nápoles|Naples; Múnich|Munich; Viena|Vienna; Varsovia|Warsaw;
Estambul|Istanbul; El Cairo|Cairo; Jartum|Khartoum; Nairobi; Tokio|Tokyo; Seúl|Seoul; Hong Kong; Sídney|Sydney;
Florida; Texas; California; Miami; Chicago; Gaza|Franja de Gaza|Gaza Strip; Cisjordania|West Bank"""
_PAISES = """España|Spain; Francia|France; Alemania|Germany; Italia|Italy; Portugal; Reino Unido|United Kingdom|Gran Bretaña|Britain|UK;
Irlanda|Ireland; Países Bajos|Holanda|Netherlands; Bélgica|Belgium; Suiza|Switzerland; Austria; Polonia|Poland;
Grecia|Greece; Suecia|Sweden; Noruega|Norway; Dinamarca|Denmark; Finlandia|Finland; Hungría|Hungary; Rumanía|Romania;
Rusia|Russia; Ucrania|Ukraine; Bielorrusia|Belarus; Turquía|Turkey|Türkiye; Israel; Palestina|Palestine; Líbano|Lebanon;
Siria|Syria; Irán|Iran; Irak|Iraq; Arabia Saudí|Arabia Saudita|Saudi Arabia; Yemen; Catar|Qatar; Egipto|Egypt;
Marruecos|Morocco; Argelia|Algeria; Túnez|Tunisia; Libia|Libya; Sudán|Sudan; Etiopía|Ethiopia; Kenia|Kenya;
Nigeria; Sudáfrica|South Africa; Congo; Mali|Malí; China; Japón|Japan; Corea del Sur|South Korea;
Corea del Norte|North Korea; India; Pakistán|Pakistan; Afganistán|Afghanistan; Indonesia; Filipinas|Philippines;
Vietnam; Tailandia|Thailand; Myanmar|Birmania; Taiwán|Taiwan; Australia; Nueva Zelanda|New Zealand;
Estados Unidos|United States|EEUU|EE.UU.|EE UU|USA|US; Canadá|Canada; México|Mexico; Cuba; Venezuela; Colombia;
Perú|Peru; Ecuador; Bolivia; Chile; Argentina; Uruguay; Paraguay; Brasil|Brazil; Panamá|Panama; Costa Rica;
Nicaragua; Honduras; Guatemala; El Salvador; Haití|Haiti; República Dominicana|Dominican Republic;
Puerto Rico; Groenlandia|Greenland"""


def _parse(bloque, nivel):
    out = []
    for entrada in bloque.replace("\n", " ").split(";"):
        alias = [a.strip() for a in entrada.split("|") if a.strip()]
        if alias:
            out.append((alias[0], nivel, alias))
    return out


LUGARES = _parse(_ESP_CIUDADES, 3) + _parse(_MUNDO_CIUDADES, 3) + _parse(_ESP_REGIONES, 2) + _parse(_PAISES, 1)
ESPANA = {n for n, _, _ in _parse(_ESP_CIUDADES, 3) + _parse(_ESP_REGIONES, 2)}


def _alias_re(a):
    if a.isupper() or "." in a:  # siglas: tal cual, distinguiendo mayúsculas
        return re.compile(r"(?<![\w.])" + re.escape(a) + r"(?![\w])"), False
    return re.compile(r"\b" + re.escape(plain(a).lower()).replace(r"\ ", r"[\s-]+") + r"\b"), True


_LUGARES_RE = [(nombre, nivel, [_alias_re(a) for a in alias]) for nombre, nivel, alias in LUGARES]


def _menciones(texto):
    """Lugares mencionados en un texto (exigiendo mayúscula inicial salvo en siglas)."""
    bajo = plain(texto).lower()
    found = set()
    for nombre, nivel, regs in _LUGARES_RE:
        for rx, normal in regs:
            for m in rx.finditer(bajo if normal else texto):
                if not normal or texto[m.start()].isupper():
                    found.add(nombre)
                    break
            if nombre in found:
                break
    return found


def lugares(fuentes, max_lugares=2):
    score = Counter()
    for f in fuentes:
        for n in _menciones(f["titulo"]):
            score[n] += 2
        for n in _menciones(f.get("extracto", "")):
            score[n] += 1
        for n in _menciones(" ; ".join(f.get("categorias", []))):
            score[n] += 2
    if not score:
        return []
    nivel = {n: lv for n, lv, _ in LUGARES}
    if any(n in ESPANA for n in score):
        score.pop("España", None)
    ranked = sorted(score, key=lambda n: (score[n], nivel[n]), reverse=True)
    top = score[ranked[0]]
    return [n for n in ranked[:max_lugares] if score[n] >= max(2, top / 2)]


def hashtag(nombre):
    """'Castilla y León' -> 'CastillaYLeón'."""
    return "".join(w[:1].upper() + w[1:] for w in re.split(r"[\s\-']+", nombre) if w)


def etiquetas(fuentes):
    return {"temas": temas(fuentes), "lugares": [hashtag(l) for l in lugares(fuentes)]}
