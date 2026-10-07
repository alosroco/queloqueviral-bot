"""
BOT "QUELOQUE VIRAL" PARA INSTAGRAM - UN REEL POR NOTICIA
========================================================
En cada corrida (3 por dia):
1. Lee medios en espanol y lo mas leido en Google Noticias de varios paises,
   mas las tendencias de Google.
2. La IA elige LA noticia mas viral para el publico hispanohablante.
3. El bot lee la nota completa en 2-3 medios, y la IA arma un guion propio:
   gancho + 3 placas de desarrollo + cierre, usando SOLO lo que dicen los medios.
4. Arma un Reel vertical con placas propias (no usa fotos de los diarios),
   voz en off en espanol neutro y musica libre de derechos.
5. Te lo manda por Telegram: Publicar / Descartar.
6. Si aprobas, publica el Reel (con fuentes citadas) y una historia.
"""

import os
import re
import sys
import json
import time
import html
import random
import shutil
import asyncio
import tempfile
import subprocess
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import base64
import hashlib
import io
import unicodedata

import requests
from cryptography.fernet import Fernet, InvalidToken
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

# ======================== CONFIGURACION ========================
NOMBRE_CUENTA = "@queloqueviral"            # Cambialo por tu usuario de Instagram
HORAS_ATRAS = 8                           # Solo noticias de las ultimas X horas
ESPERA_APROBACION_MIN = 25                # Si no respondes en este tiempo, se descarta
MODELO_IA = "claude-sonnet-5-5"            # escribe los guiones (calidad)
MODELO_CONTROL = "claude-haiku-4-5-20251001"  # revisa las imagenes: mucho mas barato y alcanza para decir SI/NO
MAX_CONTROLES_POR_CORRIDA = 30              # tope de imagenes revisadas por la IA en cada corrida (cuida el gasto)
VOCES = ["es-US-AlonsoNeural", "es-US-PalomaNeural"]   # se alternan: un Reel con voz de hombre, otro de mujer
VOZ = VOCES[0]
VELOCIDAD_VOZ = "+15%"
VOLUMEN_MUSICA = 0.25                     # volumen de la musica (baja sola cuando habla la voz)
CARPETA_MUSICA = "musica"                 # Pone ahi archivos .mp3 libres de derechos
# Instagram permite como maximo 5 hashtags por publicacion (desde dic. 2025): 1 de la marca + 4 del tema
HASHTAG_MARCA = "#QueloQueViral"
HASHTAGS_GENERICOS = {"#viral", "#noticias", "#fyp", "#foryou", "#parati", "#reels", "#explore", "#explorar",
                      "#trending", "#tendencia", "#noticiasdehoy", "#news", "#reel", "#instagram", "#qlq",
                      "#queloqueviral"}

# Colores (formato RGB)
FONDO = (14, 17, 28)
ACENTO = (255, 196, 0)
TEXTO = (245, 245, 245)
TEXTO_SUAVE = (170, 178, 196)

GN = "https://news.google.com/rss"
FUENTES_RSS = {
    # Medios para todo el publico hispanohablante
    "BBC Mundo": "https://feeds.bbci.co.uk/mundo/rss.xml",
    "El Pais": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada",
    "CNN en Espanol": "https://cnnespanol.cnn.com/feed/",
    "DW": "https://rss.dw.com/rdf/rss-sp-all",
    "Infobae": "https://www.infobae.com/arc/outboundfeeds/rss/",
    # Lo mas leido por pais (Google Noticias)
    "Google Noticias Mexico": f"{GN}?hl=es-419&gl=MX&ceid=MX:es-419",
    "Google Noticias Espana": f"{GN}?hl=es&gl=ES&ceid=ES:es",
    "Google Noticias Argentina": f"{GN}?hl=es-419&gl=AR&ceid=AR:es-419",
    "Google Noticias Colombia": f"{GN}?hl=es-419&gl=CO&ceid=CO:es-419",
    "Google Noticias Chile": f"{GN}?hl=es-419&gl=CL&ceid=CL:es-419",
    "Google Noticias EE.UU. (espanol)": f"{GN}?hl=es-419&gl=US&ceid=US:es-419",
    "Google Noticias Mundo": f"{GN}/headlines/section/topic/WORLD?hl=es-419&gl=MX&ceid=MX:es-419",
    # Lo viral a nivel global (en ingles; la IA lo cuenta en espanol)
    "BBC News": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "Google News USA": f"{GN}?hl=en-US&gl=US&ceid=US:en",
    "Google News UK": f"{GN}?hl=en-GB&gl=GB&ceid=GB:en",
    "Google News World": f"{GN}/headlines/section/topic/WORLD?hl=en-US&gl=US&ceid=US:en",
}
# ---- Contenido de INTERES GENERAL ("virales de todos los tiempos") ----
# Se alternan con las noticias del dia: 2 noticias + 2 de interes general por dia.
CATEGORIA_ANIMALES = "animales"          # todos los dias, en la primera publicacion de interes general
CATEGORIAS_INTERES = [
    "espacio y astronomia", "naturaleza", "alimentacion y nutricion", "datos curiosos",
    "ciencia y descubrimientos", "pensamiento estoico", "salud y bienestar", "deportes: historias y datos",
    "salud mental y habitos", "historia y personajes",
]
CATEGORIAS_SALUD = {"alimentacion y nutricion", "salud y bienestar", "salud mental y habitos"}
FUENTES_INTERES = {
    "NASA": ("https://www.nasa.gov/feed/", {"espacio y astronomia", "ciencia y descubrimientos"}),
    "NASA Ciencia": ("https://science.nasa.gov/feed/", {"espacio y astronomia", "ciencia y descubrimientos", "naturaleza", "animales"}),
    "ScienceDaily": ("https://www.sciencedaily.com/rss/all.xml", {"ciencia y descubrimientos", "salud y bienestar", "naturaleza", "animales", "alimentacion y nutricion"}),
    "ScienceDaily Salud": ("https://www.sciencedaily.com/rss/health_medicine.xml", {"salud y bienestar", "alimentacion y nutricion", "salud mental y habitos"}),
    "ScienceDaily Mente": ("https://www.sciencedaily.com/rss/mind_brain.xml", {"salud mental y habitos", "ciencia y descubrimientos"}),
    "ScienceDaily Plantas y Animales": ("https://www.sciencedaily.com/rss/plants_animals.xml", {"naturaleza", "animales"}),
    "Smithsonian": ("https://www.smithsonianmag.com/rss/latest_articles/", {"historia y personajes", "naturaleza", "animales", "ciencia y descubrimientos", "datos curiosos"}),
    "OMS": ("https://www.who.int/rss-feeds/news-english.xml", {"salud y bienestar", "alimentacion y nutricion"}),
    "Harvard Health": ("https://www.health.harvard.edu/blog/feed", {"salud y bienestar", "alimentacion y nutricion", "salud mental y habitos"}),
    "The Conversation": ("https://theconversation.com/es/articles.atom", {"ciencia y descubrimientos", "salud y bienestar", "salud mental y habitos", "historia y personajes", "naturaleza", "animales"}),
    "BBC Mundo Ciencia": ("https://feeds.bbci.co.uk/mundo/temas/ciencia/rss.xml", {"ciencia y descubrimientos", "espacio y astronomia", "naturaleza", "animales"}),
    "Mongabay": ("https://news.mongabay.com/feed/", {"animales", "naturaleza"}),
    "ScienceDaily Animales": ("https://www.sciencedaily.com/rss/plants_animals/animals.xml", {"animales"}),
    "BBC Mundo Salud": ("https://feeds.bbci.co.uk/mundo/temas/salud/rss.xml", {"salud y bienestar", "alimentacion y nutricion", "salud mental y habitos"}),
}
AVISO_SALUD = "Información general: no reemplaza la consulta con un profesional de la salud."
ESTADO_INTERES = os.path.join("publicaciones", "estado_interes.json")
# Horarios (hora Argentina) de cada tipo de publicacion; el resto del tiempo, noticias
HORAS_INTERES = {9, 14, 20}              # 3 de interes general fijos; las noticias las cubre el radar
TEMAS_PEDIDOS = os.path.join("publicaciones", "temas_pedidos.json")

PAISES_YOUTUBE = ["US", "GB", "MX", "ES", "AR", "CO"]
TENDENCIAS_RSS = {p: f"https://trends.google.com/trending/rss?geo={p}" for p in ["US", "GB", "MX", "ES", "AR"]}
# ==============================================================

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
IG_TOKEN = os.environ.get("IG_TOKEN", "").strip()
IG_TOKEN_SECRETO = IG_TOKEN
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "").strip()
CF_API_TOKEN = os.environ.get("CF_API_TOKEN", "").strip()
INTENTO = {"n": 0}
DESCARTADOS = []                                  # temas descartados en esta corrida (para no repetirlos)
MIN_FONDOS = 3                             # partes con imagen minimas para mandar el Reel a aprobar
MAX_ILUSTRACIONES_IA = 5                   # por Reel (la cuota gratis de Cloudflare es diaria)
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
YT_CLIENT_ID = os.environ.get("YT_CLIENT_ID", "")
YT_CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET", "")
YT_REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN", "")
# Mientras Google no audite el proyecto, YouTube solo acepta videos privados.
# Cuando lo aprueben, crea el secreto YT_PRIVACIDAD con el valor "public".
YT_PRIVACIDAD = os.environ.get("YT_PRIVACIDAD", "") or "private"
TIKTOK_CLIENT_KEY = os.environ.get("TIKTOK_CLIENT_KEY", "").strip()
TIKTOK_CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET", "").strip()
TIKTOK_REFRESH_TOKEN = os.environ.get("TIKTOK_REFRESH_TOKEN", "").strip()


# ---------- Boveda de tokens ----------
# Instagram y TikTok cambian sus tokens al renovarlos. Para que no tengas que actualizar
# secretos a mano, el bot guarda el token vigente CIFRADO en el repositorio. La clave para
# descifrarlo sale de tus secretos, asi que nadie mas puede leerlo.
def _boveda():
    base = (os.environ.get("TELEGRAM_TOKEN", "") + "|queloqueviral").encode()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(base).digest()))


def _ruta_token(nombre):
    return os.path.join("publicaciones", f"token_{nombre}.cifrado")


def leer_token(nombre, por_defecto=""):
    try:
        with open(_ruta_token(nombre), "rb") as f:
            return _boveda().decrypt(f.read()).decode()
    except (FileNotFoundError, InvalidToken, ValueError):
        return por_defecto


def guardar_token(nombre, valor):
    os.makedirs("publicaciones", exist_ok=True)
    with open(_ruta_token(nombre), "wb") as f:
        f.write(_boveda().encrypt(valor.encode()))


def subir_cambios(mensaje):
    for c in (["git", "config", "user.name", "bot-noticias"],
              ["git", "config", "user.email", "bot@users.noreply.github.com"],
              ["git", "add", "publicaciones"], ["git", "commit", "-m", mensaje], ["git", "push"]):
        subprocess.run(c, check=False)


IG_TOKEN = leer_token("instagram", IG_TOKEN)
IG_API = "https://graph.instagram.com/v25.0"
ARGENTINA = timezone(timedelta(hours=-3))
CARPETA = "publicaciones"
HISTORIAL = os.path.join(CARPETA, "historial.json")
def _primera(*rutas):
    return next((r for r in rutas if os.path.exists(r)), rutas[-1])


# Tipografia de la marca: Poppins (el workflow la descarga en la carpeta "fonts")
FUENTE_BOLD = _primera("fonts/Poppins-Bold.ttf", "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",
                       "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
FUENTE_REG = _primera("fonts/Poppins-Medium.ttf", "/usr/share/fonts/truetype/google-fonts/Poppins-Medium.ttf",
                      "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
FIRMA = "QLQ"


# ======================== 1. LEER NOTICIAS ========================
def limpiar(texto):
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    return re.sub(r"\s+", " ", html.unescape(texto)).strip()


def fecha_de(texto):
    if not texto:
        return None
    try:
        f = parsedate_to_datetime(texto)
    except Exception:
        try:
            f = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        except Exception:
            return None
    return f if f.tzinfo else f.replace(tzinfo=timezone.utc)


def leer_rss(xml_texto, nombre):
    """Lee RSS 2.0, RDF o Atom sin librerias extra."""
    raiz = ET.fromstring(xml_texto)
    items = []
    for nodo in raiz.iter():
        etiqueta = nodo.tag.split("}")[-1]
        if etiqueta not in ("item", "entry"):
            continue
        campos = {}
        for hijo in nodo:
            nombre_campo = hijo.tag.split("}")[-1]
            if nombre_campo == "link" and hijo.get("href"):
                campos["link"] = hijo.get("href")
            elif nombre_campo not in campos:
                campos[nombre_campo] = (hijo.text or "").strip()
        titulo = limpiar(campos.get("title"))
        if not titulo:
            continue
        fuente = campos.get("source") or nombre
        if nombre.startswith("Google Noticias") and " - " in titulo:
            titulo, fuente = titulo.rsplit(" - ", 1)
        items.append({
            "titulo": titulo,
            "descripcion": limpiar(campos.get("description") or campos.get("summary"))[:220],
            "fuente": fuente.strip(),
            "link": campos.get("link", ""),
            "fecha": fecha_de(campos.get("pubDate") or campos.get("date")
                              or campos.get("updated") or campos.get("published")),
        })
    return items


def bajar(url):
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (resumen de noticias)"})
    r.raise_for_status()
    return r.content


def juntar_noticias():
    limite = datetime.now(timezone.utc) - timedelta(hours=HORAS_ATRAS)
    noticias, fallidas = [], []
    for nombre, url in FUENTES_RSS.items():
        try:
            for n in leer_rss(bajar(url), nombre):
                if n["fecha"] is None or n["fecha"] >= limite:
                    noticias.append(n)
        except Exception as e:
            fallidas.append(f"{nombre} ({type(e).__name__})")
    tendencias = []
    for pais, url in TENDENCIAS_RSS.items():
        try:
            tendencias += [f"{n['titulo']} ({pais})" for n in leer_rss(bajar(url), "Tendencias")][:10]
        except Exception:
            fallidas.append(f"Tendencias {pais}")
    if YOUTUBE_API_KEY:
        for pais in PAISES_YOUTUBE:
            try:
                r = requests.get("https://www.googleapis.com/youtube/v3/videos", timeout=20, params={
                    "part": "snippet,statistics", "chart": "mostPopular", "regionCode": pais,
                    "maxResults": 15, "hl": "es", "key": YOUTUBE_API_KEY}).json()
                for v in r.get("items", []):
                    sn = v["snippet"]
                    vistas = int(v.get("statistics", {}).get("viewCount", 0))
                    noticias.append({
                        "titulo": limpiar(sn["title"]), "fuente": f"YouTube: {sn['channelTitle']}",
                        "descripcion": f"[{vistas:,} vistas, tendencia en {pais}] " + limpiar(sn.get("description"))[:180],
                        "texto_largo": limpiar(sn.get("description"))[:1500],
                        "link": f"https://www.youtube.com/watch?v={v['id']}", "fecha": None, "youtube": True})
            except Exception:
                fallidas.append(f"YouTube {pais}")
    vistos, unicas = set(), []
    for n in noticias:
        clave = n["titulo"].lower()[:80]
        if clave not in vistos:
            vistos.add(clave)
            unicas.append(n)
    return unicas[:300], tendencias, fallidas


def juntar_interes(categoria):
    """Lee las fuentes de divulgacion que corresponden a la categoria (ultimos 30 dias)."""
    limite = datetime.now(timezone.utc) - timedelta(days=30)
    items, fallidas = [], []
    for nombre, (url, cats) in FUENTES_INTERES.items():
        if categoria not in cats:
            continue
        try:
            for n in leer_rss(bajar(url), nombre):
                if n["fecha"] is None or n["fecha"] >= limite:
                    n["fuente"] = nombre
                    items.append(n)
        except Exception as e:
            fallidas.append(f"{nombre} ({type(e).__name__})")
    return items[:150], fallidas


def proxima_categoria():
    """La primera publicacion de interes general del dia es siempre de ANIMALES (segmento muy buscado).
    Las otras rotan por el resto de las categorias."""
    if datetime.now(ARGENTINA).hour < 12:
        return None, CATEGORIA_ANIMALES
    estado = {}
    if os.path.exists(ESTADO_INTERES):
        with open(ESTADO_INTERES, encoding="utf-8") as f:
            estado = json.load(f)
    i = estado.get("indice", -1) + 1
    return i % len(CATEGORIAS_INTERES), CATEGORIAS_INTERES[i % len(CATEGORIAS_INTERES)]


def guardar_categoria(indice):
    os.makedirs("publicaciones", exist_ok=True)
    with open(ESTADO_INTERES, "w", encoding="utf-8") as f:
        json.dump({"indice": indice}, f)


def elegir_tema_interes(categoria, items, ya_publicadas):
    lista = "\n".join(f"[{i}] ({n['fuente']}) {n['titulo']} | {n['descripcion']}" for i, n in enumerate(items))
    return preguntar_ia(f"""Eres editor de "QueloQue Viral", cuenta de Instagram en espanol para todo el publico
hispanohablante. Ademas de noticias, publicamos contenido de INTERES GENERAL que atrapa: "virales de todos los
tiempos". Categoria de hoy: {categoria}.

Elige 3 temas posibles, en orden de preferencia, que generen curiosidad y ganas de compartir.
- Si hay articulos abajo, prioriza los mas sorprendentes (indica sus numeros en "ids").
- Si la categoria no necesita articulos (ej: pensamiento estoico, datos curiosos, historia) o no hay buenos,
  puedes proponer un tema "de conocimiento" con ids vacios, SOLO si es un hecho ampliamente documentado,
  y en "fuente_texto" indica la fuente reconocida (ej: "Marco Aurelio, Meditaciones", "NASA", "OMS",
  "Enciclopedia Britannica").
- PROHIBIDO: consejos medicos personalizados, dietas, dosis o tratamientos; suicidio, autolesiones,
  trastornos alimentarios; pseudociencia; frases atribuidas sin seguridad de su autor.
- No repitas: {ya_publicadas or 'nada'}

Responde SOLO con JSON valido:
{{"temas": [{{"tema": "descripcion corta", "ids": [numeros], "fuente_texto": "fuente si ids vacios"}}]}}

ARTICULOS DISPONIBLES:
{lista or "ninguno"}""")["temas"]


# ---------- RADAR de tendencias (publicaciones oportunistas) ----------
MAX_OPORTUNISTAS_DIA = 2
ESTADO_RADAR = os.path.join("publicaciones", "radar.json")


def _estado_radar():
    hoy = datetime.now(ARGENTINA).strftime("%Y-%m-%d")
    estado = {"fecha": hoy, "publicados": 0, "temas": []}
    if os.path.exists(ESTADO_RADAR):
        with open(ESTADO_RADAR, encoding="utf-8") as f:
            estado = {**estado, **json.load(f)}
    if estado.get("fecha") != hoy:
        estado.update({"fecha": hoy, "publicados": 0})
    return estado


def _guardar_radar(estado):
    os.makedirs("publicaciones", exist_ok=True)
    estado["temas"] = estado.get("temas", [])[-60:]
    with open(ESTADO_RADAR, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=1)


def _trafico(texto):
    """'200K+' -> 200000"""
    m = re.match(r"([\d.,]+)\s*([KkMm]?)", (texto or "").replace(",", ""))
    if not m:
        return 0
    n = float(m.group(1))
    return int(n * (1_000_000 if m.group(2).lower() == "m" else 1_000 if m.group(2).lower() == "k" else 1))


def senales_tendencia():
    """Junta lo que esta creciendo AHORA: Google Trends (con volumen), YouTube en tendencia y Reddit."""
    senales = []
    for pais in ["US", "MX", "ES", "AR", "CO"]:
        try:
            raiz = ET.fromstring(bajar(f"https://trends.google.com/trending/rss?geo={pais}"))
            for item in raiz.iter("item"):
                titulo = limpiar(item.findtext("title"))
                trafico = 0
                noticias = []
                for hijo in item:
                    etiqueta = hijo.tag.split("}")[-1]
                    if etiqueta == "approx_traffic":
                        trafico = _trafico(hijo.text)
                    elif etiqueta == "news_item":
                        t = next((limpiar(x.text) for x in hijo if x.tag.split("}")[-1] == "news_item_title"), "")
                        if t:
                            noticias.append(t)
                senales.append({"fuente": f"Google Trends {pais}", "tema": titulo, "volumen": trafico,
                                "contexto": " | ".join(noticias[:2])})
        except Exception as e:
            print(f"Google Trends {pais} no respondio: {e}")
    if YOUTUBE_API_KEY:
        for pais in ["US", "MX", "ES"]:
            try:
                r = requests.get("https://www.googleapis.com/youtube/v3/videos", timeout=20, params={
                    "part": "snippet,statistics", "chart": "mostPopular", "regionCode": pais,
                    "maxResults": 10, "key": YOUTUBE_API_KEY}).json()
                for v in r.get("items", []):
                    senales.append({"fuente": f"YouTube {pais}", "tema": limpiar(v["snippet"]["title"]),
                                    "volumen": int(v.get("statistics", {}).get("viewCount", 0)),
                                    "contexto": v["snippet"].get("channelTitle", "")})
            except Exception as e:
                print(f"YouTube tendencias {pais} no respondio: {e}")
    for sub in ("popular", "worldnews", "interestingasfuck", "aww"):
        try:
            r = requests.get(f"https://www.reddit.com/r/{sub}/hot.json?limit=15", timeout=20,
                             headers={"User-Agent": "QueloQueViralBot/1.0"}).json()
            for p in r.get("data", {}).get("children", []):
                d = p.get("data", {})
                if d.get("over_18") or d.get("stickied"):
                    continue
                senales.append({"fuente": f"Reddit r/{sub}", "tema": limpiar(d.get("title"))[:200],
                                "volumen": d.get("ups", 0), "contexto": d.get("domain", "")})
        except Exception as e:
            print(f"Reddit r/{sub} no respondio: {e}")
    return senales


def elegir_oportunista(senales, ya_publicadas):
    """La IA decide si hay algo REALMENTE caliente para publicar ahora. Devuelve dict o None."""
    if not senales:
        return None
    senales = sorted(senales, key=lambda x: -x["volumen"])[:120]
    lista = "\n".join(f"- ({s['fuente']}, volumen {s['volumen']:,}) {s['tema']} | {s['contexto']}" for s in senales)
    r = preguntar_ia(f"""Eres el editor de guardia de "QueloQue Viral", cuenta de Instagram en espanol para todo el publico
hispanohablante. Revisas cada 2 horas lo que esta explotando en internet para publicar ANTES que nadie.

Decide si hay UN tema que valga la pena publicar YA. Criterios:
- Tiene que estar creciendo fuerte: mucho volumen, o aparece en varios paises o varias fuentes a la vez.
- Interes para el publico hispanohablante; atrapante, sorprendente o muy comentado.
- Que se pueda contar con hechos verificables (no rumores, no chismes sin confirmar).
- Evita: tragedias explotadas, violencia explicita, ejecuciones, pena de muerte, crimenes violentos,
  victimas menores, contenido sexual, politica partidaria
  sin interes general, promociones o videos musicales.
- NO repitas lo ya publicado: {ya_publicadas or 'nada'}
Si nada es lo bastante fuerte, responde publicar=false. Es MEJOR no publicar que publicar algo flojo.

Responde SOLO con JSON valido:
{{"publicar": true/false, "tema": "descripcion clara del tema", "busqueda": "3 a 6 palabras para buscar
noticias sobre esto (en el idioma en que mas se habla del tema)", "motivo": "por que esta caliente"}}

SENALES DE AHORA:
{lista}""")
    return r if r.get("publicar") and r.get("tema") else None


def revisar_datos(guion, notas):
    """Segunda revision por la IA: saca cualquier dato dudoso antes de publicar."""
    material = "\n\n".join(f"--- {f} ---\n{t[:2500]}" for f, t in notas) or "sin articulos (tema de conocimiento)"
    revisado = preguntar_ia(f"""Eres verificador de datos de una cuenta de divulgacion. Revisa este guion.
Si un dato no esta respaldado por las notas o no es un hecho ampliamente documentado, eliminalo o
reformulalo de forma prudente. Si es una cita, debe ser real y del autor indicado; si dudas, quita la cita
y usa una idea general de ese autor sin comillas. No agregues datos nuevos. Mantén EXACTAMENTE la misma
estructura JSON y los mismos campos.

GUION:
{json.dumps(guion, ensure_ascii=False)}

NOTAS:
{material}

Responde SOLO con el JSON del guion revisado.""", 3000)
    return completar_guion({**guion, **revisado})


# ======================== 2. LEER LA NOTA COMPLETA ========================
class _Parrafos(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parrafos, self._en_p, self._ignorar, self._buf = [], False, 0, []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "aside", "form"):
            self._ignorar += 1
        elif tag == "p" and not self._ignorar:
            self._en_p, self._buf = True, []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "aside", "form") and self._ignorar:
            self._ignorar -= 1
        elif tag == "p" and self._en_p:
            texto = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            if len(texto) > 60:
                self.parrafos.append(texto)
            self._en_p = False

    def handle_data(self, data):
        if self._en_p and not self._ignorar:
            self._buf.append(data)


def leer_nota(url, max_chars=5000):
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return ""
        p = _Parrafos()
        p.feed(r.text)
        return " ".join(p.parrafos)[:max_chars]
    except Exception:
        return ""


def es_directo(n):
    return (n["link"].startswith("http") and "news.google.com" not in n["link"]
            and not n.get("youtube"))


# ======================== 3. INTELIGENCIA ARTIFICIAL ========================
def _llamar_ia(texto, max_tokens):
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=120, headers={
        "x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
        "content-type": "application/json"},
        json={"model": MODELO_IA, "max_tokens": max_tokens,
              "messages": [{"role": "user", "content": texto}]})
    if r.status_code != 200:
        try:
            motivo = r.json().get("error", {}).get("message", r.text[:200])
        except Exception:
            motivo = r.text[:200]
        if "credit" in motivo.lower():
            motivo += " → Cargá crédito en console.anthropic.com (Billing)."
        raise RuntimeError(f"La IA respondió error {r.status_code}: {motivo}")
    t = "".join(b.get("text", "") for b in r.json()["content"])
    t = t.replace("```json", "").replace("```", "").strip()
    return t[t.find("{"):t.rfind("}") + 1]


def preguntar_ia(texto, max_tokens=2000):
    """Pide una respuesta en JSON. Si viene mal formada, le pide a la IA que la corrija."""
    texto += ("\n\nIMPORTANTE: dentro de los textos NO uses comillas dobles (\"). "
              "Si necesitas citar algo, usa comillas simples o «».")
    crudo = _llamar_ia(texto, max_tokens)
    for intento in range(2):
        try:
            return json.loads(crudo)
        except json.JSONDecodeError as e:
            print(f"JSON invalido de la IA ({e}). Pido correccion (intento {intento + 1}).")
            crudo = _llamar_ia("Este JSON es invalido: " + str(e) + ". Corrigelo sin cambiar el contenido "
                               "(escapa o reemplaza las comillas internas) y responde SOLO con el JSON:\n\n"
                               + crudo, max_tokens)
    return json.loads(crudo)


def elegir_temas(noticias, tendencias, ya_publicadas):
    def marca(n):
        return " ▶" if n.get("youtube") else (" *" if es_directo(n) else "")
    lista = "\n".join(f"[{i}]{marca(n)} ({n['fuente']}) {n['titulo']} | {n['descripcion']}"
                      for i, n in enumerate(noticias))
    return preguntar_ia(f"""Eres editor de "QueloQue Viral", una cuenta de Instagram que cuenta en espanol las noticias
mas virales DEL MUNDO ENTERO, para todo el publico hispanohablante.
Abajo hay titulares de las ultimas horas y las busquedas en tendencia en Google.

Elige los 3 temas MAS VIRALES y llamativos ahora, en orden de preferencia (el 1 es el mejor).
- Las noticias pueden ser de CUALQUIER PAIS DEL MUNDO (no solo de paises hispanos): lo que importa es
  que sea viral y que le interese a un publico hispanohablante. Hay titulares en ingles: tambien valen.
- Temas: noticias globales, curiosidades, tecnologia, ciencia, espectaculos, deportes internacionales,
  historias humanas. Un tema muy local solo si es realmente viral.
- Prioriza temas que cubren VARIOS medios o coinciden con las tendencias.
- Cada tema debe incluir al menos un titular marcado con * (nota completa disponible).
- Los marcados con ▶ son videos en tendencia de YouTube: sirven como senal de viralidad. Puedes elegir
  un video viral como tema si hay medios (*) que lo cubren, o si su descripcion explica bien de que se trata.
- Nunca elijas videos musicales, trailers ni publicidad como tema.
- Evita rumores sin confirmar, morbo, tragedias explotadas y temas con victimas menores de edad.
- Evita tambien ejecuciones, pena de muerte, crimenes violentos, atentados y guerras: son delicados y casi
  nunca tienen imagenes apropiadas. Prefiere historias sorprendentes, positivas, curiosas o utiles.
- En politica, solo si es un hecho de alcance internacional; tono neutral.
- NO repitas estos temas ya publicados: {ya_publicadas or 'ninguno'}

Responde SOLO con JSON valido: {{"temas": [{{"tema": "descripcion corta", "ids": [numeros de TODOS los titulares de ese tema]}}]}}

TENDENCIAS EN GOOGLE (pais entre parentesis): {", ".join(tendencias) or "no disponibles"}

TITULARES (* = nota completa disponible, ▶ = video en tendencia de YouTube):
{lista}""")["temas"]


def completar_guion(g):
    """Si a la IA se le olvida algun campo, lo completa con lo que haya en vez de cortar todo."""
    placas = [p for p in g.get("placas", []) if isinstance(p, dict) and (p.get("pantalla") or p.get("voz"))][:3]
    for p in placas:
        p.setdefault("titulo", "")
        p["pantalla"] = p.get("pantalla") or p.get("voz", "")
        p["voz"] = p.get("voz") or p["pantalla"]
    if not g.get("gancho") or len(placas) < 2:
        raise RuntimeError("La IA no armo un guion completo (falta gancho o desarrollo).")
    g["placas"] = placas
    g.setdefault("categoria", "NOTICIA")
    g["descripcion"] = g.get("descripcion") or "\n\n".join(p["pantalla"] for p in placas)
    g.setdefault("hashtags", [])
    g.setdefault("pregunta", "")
    return g


def escribir_guion(tema, notas, tipo="noticia", categoria=""):
    material = "\n\n".join(f"--- {fuente} ---\n{texto}" for fuente, texto in notas)
    if tipo == "interes":
        reglas_datos = f"""- Es contenido de INTERES GENERAL (categoria: {categoria}), no una noticia del dia.
- Usa los hechos de las notas de abajo; si no hay notas, usa SOLO conocimiento ampliamente documentado y
  aceptado. No inventes cifras, fechas, citas ni estudios.
- En salud, alimentacion o salud mental: informacion general y prudente, sin consejos personalizados,
  dietas, dosis ni tratamientos.
- En pensamiento estoico: solo citas reales y bien atribuidas (Marco Aurelio, Seneca, Epicteto), indicando
  la obra; explica su sentido aplicado a la vida diaria.
- Estructura de las 3 placas: 1) el dato o idea central, 2) el detalle mas sorprendente, 3) por que importa
  o como aplicarlo.
- Si el tema fue PEDIDO por el usuario y las notas NO confirman lo que dice el pedido (por ejemplo, un
  hecho que no ocurrio), NO lo afirmes: cuenta solo lo que las notas confirman sobre ese tema."""
    else:
        reglas_datos = """- Usa SOLO hechos que esten en las notas de abajo. Si un dato no esta, NO lo pongas. No inventes cifras,
  nombres, fechas ni declaraciones."""
    return preguntar_ia(f"""Eres guionista de "QueloQue Viral", cuenta de Instagram para todo el publico hispanohablante.
Escribe el guion de UN Reel de 30 a 40 segundos sobre este tema: {tema}

REGLAS ESTRICTAS:
{reglas_datos}
- Si las notas se contradicen, menciona solo lo que coincide.
- Escribe TODO con tus propias palabras, en espanol neutro (usa "tu"). No copies frases de las notas
  y no uses citas textuales (excepcion: en pensamiento estoico, UNA cita breve, real y bien atribuida).
  Si las notas estan en ingles, traduce los hechos con cuidado.
- Tono: claro, atrapante, sin exagerar ni dramatizar.

ESTRUCTURA:
- gancho: la frase que atrapa en los primeros 2 segundos (en pantalla, maximo 60 caracteres).
- 3 placas de desarrollo: 1) que paso, 2) el contexto o dato mas llamativo, 3) por que importa o que sigue.
  Para cada placa: "titulo" (2 a 4 palabras, ej: "Que paso", "El dato clave", "Que sigue"),
  "pantalla" (resumen corto de la parte, maximo 120 caracteres) y "voz" (lo que dice la voz en off, que
  ADEMAS aparece como subtitulo en pantalla: 1 o 2 oraciones cortas y claras, MAXIMO 22 palabras).
- El Reel completo debe durar unos 30 segundos: se breve y directo.
- tono: "alegre" si es curiosidad, entretenimiento, tecnologia o deporte; "seria" si es importante, triste o delicada.
- pregunta: una pregunta corta para invitar a comentar (maximo 60 caracteres), ej: "¿Tu que harias?", "¿Lo sabias?".
- Para el gancho y cada placa, "video": 1 a 3 palabras EN INGLES para buscar un video de stock que
  ilustre esa parte (ej: "dog walking road", "football stadium crowd", "smartphone hands").
  * Escenas genericas y CONCRETAS (objetos, lugares, acciones). Nada de personas famosas ni marcas.
  * NUNCA pidas banderas, mapas, textos, numeros, anos, elecciones ni simbolos politicos.
  * Si la noticia ocurre en un lugar, usa una escena de ESE lugar (ej: "madrid street", "tokyo night"),
    nunca de otro pais.
- FOTOS REALES: para el gancho ("imagen_gancho") y cada placa ("imagen"), indica el PROTAGONISTA concreto
  de esa parte tal como se llama su articulo de Wikipedia (ej: "Lionel Messi", "Torre Eiffel",
  "Inter Miami CF", "Tokio", "SpaceX Starship"). Solo personas publicas, lugares, equipos, empresas,
  edificios, objetos o eventos conocidos. Completa "imagen" en TODAS las partes que puedas: si una parte no
  tiene un protagonista propio, repite el protagonista principal de la noticia o usa el lugar donde ocurre.
  Deja "" solo si no hay ninguno. Nunca personas privadas ni victimas.
- PALABRAS CLAVE PARA IMAGENES (lo mas importante para que las imagenes correspondan a la noticia):
  "palabras_clave": las 3 cosas concretas MAS centrales de la noticia, en orden de importancia, escritas
  como el titulo de su articulo de Wikipedia (ej: ["Jair Bolsonaro", "Supremo Tribunal Federal", "Brasilia"]
  o ["Daniil Medvedev", "Abierto de Australia", "Tenis"]). La primera debe ser el protagonista principal.
  "palabras_clave_en": las mismas 3 en ingles y genericas para buscar video de stock
  (ej: ["brazil politics", "courthouse", "brasilia city"] o ["tennis player", "tennis court", "tennis match"]).
- ILUSTRACIONES: "ilustraciones": 3 descripciones EN INGLES, MUY ESPECIFICAS, que nos SITUEN en la noticia:
  1) el LUGAR: describe visualmente el sitio real donde ocurre (tipo de estadio, superficie, colores,
     arquitectura, ciudad, clima, hora), ej: "a huge night tennis stadium with a blue hard court, packed
     stands and bright floodlights, Melbourne summer".
  2) el MOMENTO: la escena clave de la noticia con personas ANONIMAS vistas de espaldas, de lejos o en
     silueta, SIN que se vea la cara, ej: "a tennis player seen from behind smashing his racket on the
     court, umpire chair in the background, tense atmosphere".
  3) un DETALLE o simbolo del tema, ej: "a broken tennis racket lying on a blue hard court".
  PROHIBIDO: caras visibles, personas reconocibles, nombres, textos, letras, logos, marcas, escudos, banderas
  o camisetas de equipos reales. Describe los lugares con palabras visuales, no con su nombre comercial.
- Si alguna informacion viene de un video de YouTube, nombra al canal como fuente en "pantalla" o "voz".

Responde SOLO con JSON valido:
{{"categoria": "UNA PALABRA EN MAYUSCULAS",
"gancho": "...", "destacado": "1 a 3 palabras del gancho para resaltar en amarillo", "voz_gancho": "version hablada del gancho, maximo 12 palabras", "video_gancho": "...", "imagen_gancho": "...",
"placas": [{{"titulo": "...", "pantalla": "...", "voz": "...", "video": "...", "imagen": "..."}}, (3 placas en total)],
"pregunta": "...",
"palabras_clave": ["...", "...", "..."], "palabras_clave_en": ["...", "...", "..."],
"ilustraciones": ["...", "...", "..."],
"tono": "alegre o seria",
"descripcion": "texto para la publicacion de Instagram: 3 parrafos cortos que cuentan la noticia",
"hashtags": ["#...", "#...", "#...", "#..."]}}

HASHTAGS: exactamente 4, ESPECIFICOS de este contenido, sin tildes ni espacios. Uno del protagonista o lugar
(ej: #DaniilMedvedev, #Melbourne), uno del tema concreto (ej: #Tenis, #AbiertoDeAustralia), uno de la
disciplina o categoria amplia en espanol (ej: #Deportes, #Ciencia, #Astronomia, #Nutricion, #Estoicismo) y uno
que la gente busque sobre ese tema (ej: #DatosCuriosos, #SaludMental). PROHIBIDOS los genericos como #viral,
#noticias, #fyp, #parati, #reels, #explore, #trending.

NOTAS DE LOS MEDIOS:
{material or "sin notas: usa solo conocimiento ampliamente documentado"}""", 4000)


# ======================== 3. ARMAR LAS PLACAS ========================
ANCHO, ALTO, MARGEN = 1080, 1920, 90
ARRIBA, ABAJO = 280, 1500          # zona segura: Instagram tapa arriba y abajo en los Reels


def fuente(bold, tam):
    return ImageFont.truetype(FUENTE_BOLD if bold else FUENTE_REG, tam)


def partir(texto, font, ancho_max):
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = (actual + " " + palabra).strip()
        if font.getlength(prueba) <= ancho_max:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


def escribir(d, texto, font, color, y, interlineado=1.25, ancho_max=ANCHO - 2 * MARGEN):
    for linea in partir(texto, font, ancho_max):
        d.text((MARGEN, y), linea, font=font, fill=color)
        y += int(font.size * interlineado)
    return y


def capa_nueva():
    img = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for y in range(800, ALTO):                       # degradado oscuro abajo, para leer bien
        d.line([(0, y), (ANCHO, y)], fill=(0, 0, 0, int(215 * (y - 800) / (ALTO - 800))))
    return img, d


def _limpia(p):
    return re.sub(r"[^\wáéíóúñü]", "", p.lower())


def dibujar_palabras(d, texto, font, y, n=None, color=TEXTO, destacados=(), sombra=True, interlineado=1.3):
    """Dibuja el texto respetando su diagramacion final, pero mostrando solo las primeras n palabras.
    Asi las palabras aparecen de a una sin que el texto 'salte'. Devuelve la y final."""
    resaltar = {_limpia(x) for x in destacados if _limpia(x)}
    contador = 0
    for linea in partir(texto, font, ANCHO - 2 * MARGEN):
        x = MARGEN
        for palabra in linea.split():
            if n is None or contador < n:
                col = ACENTO if _limpia(palabra) in resaltar else color
                extra = {"stroke_width": 3, "stroke_fill": (0, 0, 0, 230)} if sombra else {}
                d.text((x, y), palabra, font=font, fill=col, **extra)
            x += font.getlength(palabra + " ")
            contador += 1
        y += int(font.size * interlineado)
    return y


def texto_con_sombra(d, texto, font, color, y, interlineado=1.3, n=None):
    return dibujar_palabras(d, texto, font, y, n=n, color=color, interlineado=interlineado)


def titulo_en_recuadro(d, texto, font, y_base, n=None, destacados=()):
    """Titulo dentro del recuadro oscuro (el recuadro siempre del tamano final). y_base = donde termina."""
    lineas = partir(texto, font, ANCHO - 2 * MARGEN)
    alto = len(lineas) * int(font.size * 1.15)
    y0 = y_base - alto - 40
    d.rounded_rectangle([MARGEN - 36, y0 - 60, ANCHO - MARGEN + 36, y_base + 10], radius=34, fill=(10, 12, 20, 215))
    d.rectangle([MARGEN, y0 - 28, MARGEN + 110, y0 - 20], fill=ACENTO)
    dibujar_palabras(d, texto, font, y0, n=n, destacados=destacados, sombra=False, interlineado=1.15)


def etiqueta(d, texto, y):
    f = fuente(True, 34)
    t = f"  {texto.upper()[:20]}  "
    d.rounded_rectangle([MARGEN, y, MARGEN + f.getlength(t), y + 58], radius=14, fill=ACENTO)
    d.text((MARGEN, y + 9), t, font=f, fill=FONDO)


def puntos(d, actual, total):
    for i in range(total):
        x = ANCHO - MARGEN - (total - i) * 34
        d.ellipse([x, ARRIBA + 18, x + 20, ARRIBA + 38], fill=ACENTO if i == actual else (90, 96, 114))


def insignia(d, cx, cy, r):
    """Mini logo: circulo azul con aro amarillo y QLQ."""
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=FONDO + (255,), outline=ACENTO, width=max(3, r // 10))
    f = fuente(True, int(r * 0.72))
    caja = d.textbbox((0, 0), FIRMA, font=f)
    d.text((cx - (caja[2] + caja[0]) / 2, cy - (caja[3] + caja[1]) / 2), FIRMA, font=f, fill=ACENTO)


def firma(d):
    """Firma de cada placa: insignia QLQ + usuario, abajo a la izquierda."""
    insignia(d, MARGEN + 42, ABAJO + 20, 42)
    d.text((MARGEN + 100, ABAJO - 2), NOMBRE_CUENTA, font=fuente(True, 36), fill=TEXTO,
           stroke_width=2, stroke_fill=(0, 0, 0, 200))


def logo_completo(d, cx, cy, r):
    """El logo de perfil: aro amarillo, QUELOQUE en blanco y VIRAL en amarillo."""
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=FONDO + (255,), outline=ACENTO, width=max(4, r // 30))
    f1, f2 = fuente(True, int(r * 0.30)), fuente(True, int(r * 0.52))
    w1, w2 = f1.getlength("QUELOQUE"), f2.getlength("VIRAL")
    d.text((cx - w1 / 2, cy - r * 0.42), "QUELOQUE", font=f1, fill=TEXTO)
    d.text((cx - w2 / 2, cy - r * 0.16), "VIRAL", font=f2, fill=ACENTO)


def tamano_titulo(texto, maximo=124, minimo=80):
    """El tamano mas grande posible: idealmente en 3 lineas; si no entra, en 4 con letra mas chica."""
    for max_lineas in (3, 4):
        for tam in range(maximo, minimo - 1, -4):
            if len(partir(texto, fuente(True, tam), ANCHO - 2 * MARGEN)) <= max_lineas:
                return tam
    return minimo


def palabras_de(texto):
    return len(texto.split())


def capa_gancho(g, ruta, n=None):
    """Portada del Reel: titulo GRANDE, con palabras clave resaltadas en amarillo."""
    img, d = capa_nueva()
    etiqueta(d, g["categoria"], ARRIBA)
    destacados = (g.get("destacado") or "").split()
    # El titulo va abajo para no tapar la cara de la foto, que esta arriba
    titulo_en_recuadro(d, g["gancho"], fuente(True, tamano_titulo(g["gancho"])), 1395, n=n, destacados=destacados)
    texto_con_sombra(d, "Te lo contamos en 30 segundos", fuente(False, 38), TEXTO, 1422)
    insignia(d, ANCHO - MARGEN - 50, ARRIBA + 29, 50)
    d.text((MARGEN, ABAJO + 20), NOMBRE_CUENTA, font=fuente(True, 34), fill=ACENTO,
           stroke_width=2, stroke_fill=(0, 0, 0, 200))
    img.save(ruta)


def bloques_subtitulo(texto, maximo=5):
    """Divide el texto en bloques cortos (hasta 5 palabras, o hasta un signo de puntuacion)."""
    bloques, actual = [], []
    for palabra in texto.split():
        actual.append(palabra)
        if len(actual) >= maximo or palabra[-1:] in ".,;:?!":
            bloques.append(actual)
            actual = []
    if actual:
        bloques.append(actual)
    return bloques


def capa_subtitulo(p, numero, total, categoria, ruta, bloque, activa):
    """Titulo de la parte fijo + subtitulo grande con la palabra que se esta diciendo en amarillo."""
    img, d = capa_nueva()
    etiqueta(d, categoria, ARRIBA)
    puntos(d, numero, total)
    titulo_en_recuadro(d, p.get("titulo") or "", fuente(True, 60), 980)
    f = fuente(True, 74)
    texto = " ".join(bloque)
    lineas = partir(texto, f, ANCHO - 2 * MARGEN)
    y = 1070
    contador = 0
    for linea in lineas:
        x = (ANCHO - f.getlength(linea)) / 2
        for palabra in linea.split():
            color = ACENTO if contador == activa else TEXTO
            d.text((x, y), palabra, font=f, fill=color, stroke_width=4, stroke_fill=(0, 0, 0, 235))
            x += f.getlength(palabra + " ")
            contador += 1
        y += int(f.size * 1.18)
    firma(d)
    img.save(ruta)


def capa_desarrollo(p, numero, total, categoria, ruta, n=None):
    img, d = capa_nueva()
    etiqueta(d, categoria, ARRIBA)
    puntos(d, numero, total)
    titulo_en_recuadro(d, p.get("titulo") or "", fuente(True, 66), 1000)
    texto_con_sombra(d, p["pantalla"], fuente(True, 54), TEXTO, 1080, n=n)
    firma(d)
    img.save(ruta)


def capa_cierre(medios, creadores, autores_video, ruta, pregunta="", aviso=""):
    img = Image.new("RGBA", (ANCHO, ALTO), FONDO + (225,))
    d = ImageDraw.Draw(img)
    y = ARRIBA - 40
    bloques = [("Fuentes", ", ".join(medios))]
    if creadores:
        bloques.append(("Video viral", ", ".join(creadores)))
    if autores_video:
        bloques.append(("Imágenes", ", ".join(autores_video[:3])))
    for titulo, texto in bloques:
        y = escribir(d, titulo, fuente(True, 34), ACENTO, y)
        y = escribir(d, texto, fuente(False, 34), TEXTO, y, 1.3) + 25
    if pregunta:
        y = escribir(d, pregunta, fuente(True, 62), TEXTO, y + 40, 1.15)
        y = escribir(d, "Cuéntanos en los comentarios 👇".replace(" 👇", ""), fuente(False, 38), TEXTO_SUAVE, y + 5)
    r = 175
    cy = max(y + r + 60, 980)
    logo_completo(d, ANCHO // 2, cy, r)
    f = fuente(True, 42)
    linea = f"Síguenos en {NOMBRE_CUENTA}"
    d.text(((ANCHO - f.getlength(linea)) / 2, cy + r + 40), linea, font=f, fill=TEXTO)
    if aviso:
        fa = fuente(False, 26)
        for k, l in enumerate(partir(aviso, fa, ANCHO - 2 * MARGEN)):
            d.text(((ANCHO - fa.getlength(l)) / 2, cy + r + 110 + k * 34), l, font=fa, fill=TEXTO_SUAVE)
    img.save(ruta)


# ======================== FOTOS REALES (Wikimedia Commons) ========================
WIKI_UA = {"User-Agent": "QueloQueViralBot/1.0 (https://alosroco.github.io/queloqueviral-bot/)"}
FOTO_NO = ("flag", "bandera", "map", "mapa", "logo", "coat of arms", "escudo", "signature", "firma",
           "diagram", "chart", "icon", "seal", "location", ".svg", "postcard", "postal", "greetings", "poster",
           "cartel", "afiche", "illustration", "ilustracion", "drawing", "dibujo", "painting", "pintura",
           "cartoon", "caricatura", "advert", "publicidad", "cover", "portada", "stamp", "sello", "banner",
           "screenshot", "captura", "infographic", "comic", "lithograph", "engraving", "grabado", "sketch",
           "vintage", "collage", "montage", "meme")


def _licencia_ok(lic):
    lic = (lic or "").lower()
    if "nc" in lic.replace("-", " ").split() or "noncommercial" in lic or " nd" in lic or "-nd" in lic:
        return False
    return any(x in lic for x in ("cc by", "cc-by", "cc0", "public domain", "dominio público", "pd"))


TIPOS_VIDEO = ("video/webm", "video/ogg", "application/ogg", "video/mp4")


def _info_commons(params, videos=False):
    params.update({"action": "query", "format": "json", "prop": "imageinfo",
                   "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 1600})
    r = requests.get("https://commons.wikimedia.org/w/api.php", params=params, headers=WIKI_UA, timeout=20).json()
    fotos = []
    for pg in (r.get("query", {}).get("pages") or {}).values():
        if "missing" in pg or not pg.get("imageinfo"):
            continue
        ii = pg["imageinfo"][0]
        meta = ii.get("extmetadata", {})
        titulo = pg.get("title", "").lower()
        lic = meta.get("LicenseShortName", {}).get("value", "")
        tipos_ok = TIPOS_VIDEO if videos else ("image/jpeg",)
        if (ii.get("mime") not in tipos_ok or ii.get("width", 0) < (640 if videos else 1000)
                or (videos and ii.get("size", 0) > 80 * 1024 * 1024)
                or any(p in titulo for p in FOTO_NO) or not _licencia_ok(lic)):
            continue
        autor = limpiar(meta.get("Artist", {}).get("value", "")) or "autor desconocido"
        fotos.append({"url": ii["url"] if videos else (ii.get("thumburl") or ii["url"]), "titulo": pg["title"],
                      "credito": f"Wikimedia Commons ({autor[:40]}, {lic})"})
    return fotos


def foto_principal_wikipedia(nombre):
    """La foto principal del articulo de Wikipedia (suele ser la mejor foto del protagonista)."""
    for idioma in ("es", "en"):
        try:
            r = requests.get(f"https://{idioma}.wikipedia.org/w/api.php", headers=WIKI_UA, timeout=20, params={
                "action": "query", "format": "json", "titles": nombre, "prop": "pageimages",
                "piprop": "name", "redirects": 1}).json()
            for pg in (r.get("query", {}).get("pages") or {}).values():
                if pg.get("pageimage"):
                    fotos = _info_commons({"titles": "File:" + pg["pageimage"]})
                    if fotos:
                        return fotos[0]
        except Exception as e:
            print(f"Wikipedia ({idioma}) no respondio para '{nombre}': {e}")
    return None


def _sin_acentos(t):
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def _palabras_clave(nombre):
    """Palabras distintivas del protagonista (ej: 'Jair Bolsonaro' -> ['jair', 'bolsonaro'])."""
    comunes = {"the", "los", "las", "del", "de", "la", "el", "and", "y", "of", "fc", "cf", "club"}
    return [p for p in re.findall(r"[a-z0-9]+", _sin_acentos(nombre)) if len(p) >= 4 and p not in comunes]


def _titulo_relacionado(titulo, claves):
    """El nombre del archivo tiene que mencionar al protagonista (al menos su palabra mas distintiva)."""
    if not claves:
        return False
    t = _sin_acentos(titulo)
    distintiva = max(claves, key=len)
    return distintiva in t


CONTROLES = {"n": 0}


def verificar_imagen(ruta_imagen, nombre, contexto, estricto=True):
    """Le muestra la imagen a la IA y pregunta si corresponde a la noticia. Devuelve True o False.
    estricto=True (fotos del protagonista): tiene que mostrarlo a el o algo directamente relacionado.
    estricto=False (video de stock): alcanza con que la escena sea coherente con el tema."""
    if CONTROLES["n"] >= MAX_CONTROLES_POR_CORRIDA:
        print("Tope de controles de imagen alcanzado en esta corrida.")
        return False
    CONTROLES["n"] += 1
    try:
        img = Image.open(ruta_imagen).convert("RGB")
        img.thumbnail((448, 448))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=80)
        datos = base64.b64encode(buf.getvalue()).decode()
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=60, headers={
            "x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
            "content-type": "application/json"},
            json={"model": MODELO_CONTROL, "max_tokens": 5, "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": datos}},
                {"type": "text", "text": (
                    f"Tema del video: {contexto}\nBuscamos una imagen de: {nombre}\n"
                    "¿Esta imagen corresponde a lo buscado? Si lo buscado es una PERSONA, tiene que ser esa persona "
                    "(no otra). Si es un lugar, un animal, una comida, un objeto, un deporte o un concepto, alcanza con "
                    "que lo muestre claramente o algo directamente relacionado con el tema. Responde NO si es de otro "
                    "tema o muestra a otra persona. Ademas tiene que ser una FOTOGRAFIA real y nitida: responde NO "
                    "si es una postal, un cartel, un dibujo, una pintura, una ilustracion, un collage, una captura "
                    "de pantalla, un grafico o mapa, si esta muy borrosa, o si tiene letras o textos GRANDES que "
                    "ocupen buena parte de la imagen. Una foto de archivo o de hace algunos anos esta bien si se ve "
                    "clara. Responde solo SI o NO.") if estricto else (
                    f"Noticia: {contexto}\nEscena buscada: {nombre}\n"
                    "Esta es una imagen ilustrativa de fondo para un video sobre la noticia. ¿La escena es coherente "
                    "con el tema (mismo deporte, mismo tipo de lugar o situacion)? NO hace falta que aparezca la "
                    "persona de la noticia. Tiene que ser una FILMACION o FOTO REAL. Responde NO si es una "
                    "animacion, dibujo animado, caricatura, ilustracion o grafico; si es de otro tema; si tiene "
                    "banderas, textos o logos visibles; si es de mala calidad o borrosa; o si es inapropiada. "
                    "Responde solo SI o NO.")}]}]})
        r.raise_for_status()
        respuesta = "".join(b.get("text", "") for b in r.json()["content"]).strip().upper()
        return respuesta.startswith("SI") or respuesta.startswith("SÍ")
    except Exception as e:
        print(f"No se pudo verificar la imagen ({e}); por seguridad no la uso.")
        return False


MAX_VERIFICACIONES = 6      # imagenes que se le muestran a la IA por cada parte del Reel
DIAG = {"candidatas": 0, "aceptadas": 0, "rechazadas": 0, "stock_aceptados": 0, "stock_rechazados": 0,
        "stock_encontrados": 0, "stock_descarga_fallida": 0, "ia_generadas": 0, "ia_fallidas": 0,
        "stock_busquedas": 0, "stock_resultados": 0, "ia_ideas": 0, "ia_error": "", "ia_rechazadas": 0,
        "fuentes_con_error": set()}


NASA_ACTIVA = {"si": False}       # se activa en temas de espacio y ciencia


def _candidatos_nasa(nombre, videos=False):
    """Biblioteca de imagenes y videos de la NASA (dominio publico, sin clave)."""
    if not NASA_ACTIVA["si"]:
        return []
    try:
        r = requests.get("https://images-api.nasa.gov/search", timeout=20, headers=WIKI_UA,
                         params={"q": nombre, "media_type": "video" if videos else "image"}).json()
    except Exception as e:
        print(f"NASA no respondio para '{nombre}': {e}")
        DIAG["fuentes_con_error"].add("NASA")
        return []
    salida = []
    for it in (r.get("collection", {}).get("items") or [])[:12]:
        datos = (it.get("data") or [{}])[0]
        texto = f"{datos.get('title', '')} {datos.get('description', '')[:200]}"
        if any(p in texto.lower() for p in ("logo", "insignia", "patch", "chart", "graphic")):
            continue
        if videos:
            try:
                archivos = requests.get(it["href"], timeout=20, headers=WIKI_UA).json()
                mp4 = next((u for u in archivos if u.endswith(("~mobile.mp4", "~medium.mp4"))), None) or \
                    next((u for u in archivos if u.endswith(".mp4")), None)
                if mp4:
                    salida.append({"url": mp4.replace("http://", "https://"), "titulo": f"nasa:{datos.get('nasa_id')}",
                                   "credito": "NASA (dominio público)"})
            except Exception:
                continue
        else:
            href = ((it.get("links") or [{}])[0]).get("href", "")
            if href:
                salida.append({"url": href.replace("~thumb.jpg", "~large.jpg"), "titulo": f"nasa:{datos.get('nasa_id')}",
                               "credito": "NASA (dominio público)"})
    return salida


def _candidatos_openverse(nombre, claves):
    """Openverse: buscador de imagenes con licencia libre (Flickr y otros archivos), incluidas las cuentas
    oficiales de gobiernos y parlamentos que publican sus fotos para libre uso. Sin clave."""
    try:
        r = requests.get("https://api.openverse.org/v1/images/", headers=WIKI_UA, timeout=20, params={
            "q": nombre, "license_type": "commercial,modification", "page_size": 20,
            "mature": "false"}).json()
    except Exception as e:
        print(f"Openverse no respondio para '{nombre}': {e}")
        DIAG["fuentes_con_error"].add("Openverse")
        return []
    fotos = []
    for it in r.get("results", []):
        texto = " ".join([it.get("title") or ""] + [t.get("name", "") for t in it.get("tags") or []])
        if (not _titulo_relacionado(texto, claves) or (it.get("width") or 0) < 1000
                or any(p in texto.lower() for p in FOTO_NO)):
            continue
        lic = f"CC {it.get('license', '').upper()} {it.get('license_version', '')}".strip()
        if it.get("license") in ("cc0", "pdm"):
            lic = "dominio público"
        fotos.append({"url": it.get("url"), "titulo": f"ov:{it.get('id')}",
                      "credito": f"{it.get('source', 'Openverse').title()} ({(it.get('creator') or 'autor')[:40]}, {lic})"})
    return fotos


def _candidatos_pixabay_fotos(nombre):
    """Fotos de Pixabay: sirven sobre todo para lugares, objetos y deportes."""
    if not PIXABAY_API_KEY:
        return []
    try:
        r = requests.get("https://pixabay.com/api/", timeout=20, params={
            "key": PIXABAY_API_KEY, "q": nombre[:100], "image_type": "photo", "safesearch": "true",
            "per_page": 15}).json()
    except Exception as e:
        print(f"Pixabay (fotos) no respondio para '{nombre}': {e}")
        DIAG["fuentes_con_error"].add("Pixabay")
        return []
    return [{"url": h.get("largeImageURL"), "titulo": f"pbf:{h.get('id')}",
             "credito": f"Pixabay ({h.get('user', '')})"}
            for h in r.get("hits", []) if h.get("largeImageURL") and video_apto(h.get("tags"), nombre)]


def buscar_foto(nombre, carpeta, usados, contexto=""):
    """Busca una foto real con licencia libre QUE CORRESPONDA a la noticia, en varias fuentes:
    Wikipedia, Wikimedia Commons (incluidas subcategorias), Openverse (Flickr y archivos oficiales)
    y Pixabay. Cada una la revisa la IA antes de usarla. Devuelve (ruta, credito) o (None, None)."""
    if not nombre:
        return None, None
    claves = _palabras_clave(nombre)
    candidatos = []
    principal = foto_principal_wikipedia(nombre)
    if principal:
        candidatos.append(principal)
    for busqueda in (f'incategory:"{nombre}"', f'deepcat:"{nombre}"', f"{nombre} filetype:bitmap"):
        try:
            encontrados = _info_commons({"generator": "search", "gsrsearch": busqueda,
                                         "gsrnamespace": 6, "gsrlimit": 20})
            candidatos += [c for c in encontrados if _titulo_relacionado(c["titulo"], claves)]
        except Exception as e:
            print(f"Commons no respondio para '{busqueda}': {e}")
            DIAG["fuentes_con_error"].add("Wikimedia")
    candidatos += _candidatos_nasa(nombre)
    candidatos += _candidatos_openverse(nombre, claves)
    candidatos += _candidatos_pixabay_fotos(nombre)
    # sin repetidos, mezclando un poco para que no salgan siempre las mismas
    vistos, unicos = set(), []
    for c in candidatos:
        if c["url"] and c["titulo"] not in vistos:
            vistos.add(c["titulo"])
            unicos.append(c)
    # Se respetan el orden de relevancia: Wikipedia, categoria del tema en Commons, NASA, Openverse, Pixabay
    DIAG["candidatas"] += len(unicos)
    verificadas = 0
    for c in unicos:
        if c["titulo"] in usados or verificadas >= MAX_VERIFICACIONES:
            continue
        usados.add(c["titulo"])
        try:
            r = requests.get(c["url"], headers=WIKI_UA, timeout=60)
            if r.status_code != 200 or len(r.content) < 20_000:
                continue
            original = os.path.join(carpeta, f"foto{len(usados)}.img")
            with open(original, "wb") as f:
                f.write(r.content)
            verificadas += 1
            if not verificar_imagen(original, nombre, contexto):
                DIAG["rechazadas"] += 1
                print(f"Descartada por no corresponder a la noticia: {c['titulo']}")
                continue
            DIAG["aceptadas"] += 1
            ruta = os.path.join(carpeta, f"foto{len(usados)}.jpg")
            componer_foto(original, ruta)
            return ruta, c["credito"]
        except Exception as e:
            print(f"No se pudo usar la foto {c['titulo']}: {e}")
    return None, None


def buscar_video_real(nombre, carpeta, usados, contexto=""):
    """Busca un video REAL del protagonista en Wikimedia Commons con licencia libre.
    Devuelve (ruta, credito) o (None, None). Hay menos videos que fotos, asi que muchas veces no encuentra."""
    if not nombre:
        return None, None
    try:
        candidatos = _info_commons({"generator": "search", "gsrsearch": f"{nombre} filetype:video",
                                    "gsrnamespace": 6, "gsrlimit": 8}, videos=True)
    except Exception as e:
        print(f"Commons (videos) no respondio para '{nombre}': {e}")
        return None, None
    claves = _palabras_clave(nombre)
    candidatos = _candidatos_nasa(nombre, videos=True)[:3] + \
        [c for c in candidatos if _titulo_relacionado(c["titulo"], claves)][:3]
    for c in candidatos:
        if c["titulo"] in usados:
            continue
        usados.add(c["titulo"])
        try:
            r = requests.get(c["url"], headers=WIKI_UA, timeout=120)
            if r.status_code != 200 or len(r.content) < 100_000:
                continue
            ruta = os.path.join(carpeta, f"real{len(usados)}.vid")
            with open(ruta, "wb") as f:
                f.write(r.content)
            if video_valido(ruta) and duracion(ruta) >= 4:
                cuadro = ruta + ".jpg"
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1", "-i", ruta,
                                "-frames:v", "1", cuadro], check=False)
                if os.path.exists(cuadro) and verificar_imagen(cuadro, nombre, contexto):
                    return ruta, c["credito"]
                print(f"Video descartado por no corresponder a la noticia: {c['titulo']}")
        except Exception as e:
            print(f"No se pudo usar el video {c['titulo']}: {e}")
    return None, None


ESTILO_IA = (", cinematic digital illustration, painterly editorial art style, dramatic lighting, rich detail, "
             "depth and atmosphere, vertical composition, faces not visible, people seen from behind or in "
             "silhouette, no text, no letters, no words, no numbers, no logos, no brands, no flags, no watermark")
IA_USADAS = {"cantidad": 0}


def marcar_ilustracion(ruta):
    """Aclaracion 'Imagen generada con IA' chiquita y discreta, abajo a la derecha."""
    img = Image.open(ruta).convert("RGBA")
    capa = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    f = fuente(False, 20)
    texto = "Imagen generada con IA"
    w = f.getlength(texto)
    d.text((ANCHO - MARGEN - w, ABAJO + 70), texto, font=f, fill=(255, 255, 255, 150))
    img.alpha_composite(capa)
    img.convert("RGB").save(ruta, "JPEG", quality=92)


def generar_ilustracion(descripcion, carpeta, contexto=""):
    """Genera una ilustracion con IA (Cloudflare Workers AI, modelo FLUX, cuota gratis diaria).
    Solo escenas conceptuales, estilo ilustracion (que no se confunda con una foto real).
    Devuelve (ruta_compuesta, credito) o (None, None)."""
    if not (CF_ACCOUNT_ID and CF_API_TOKEN and descripcion) or IA_USADAS["cantidad"] >= MAX_ILUSTRACIONES_IA:
        return None, None
    url = (f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}"
           "/ai/run/@cf/black-forest-labs/flux-1-schnell")
    prompt = (descripcion.strip()[:600] + ESTILO_IA)[:2000]
    for cuerpo in ({"prompt": prompt, "steps": 6}, {"prompt": prompt, "num_steps": 6}):
        try:
            r = requests.post(url, headers={"Authorization": f"Bearer {CF_API_TOKEN}"}, json=cuerpo, timeout=90)
            js = r.json()
            imagen = (js.get("result") or {}).get("image")
            if not imagen:
                print(f"Cloudflare no devolvio imagen: {str(js.get('errors') or js)[:200]}")
                DIAG["ia_fallidas"] += 1
                DIAG["ia_error"] = str(js.get("errors") or js)[:120]
                continue
            IA_USADAS["cantidad"] += 1
            DIAG["ia_generadas"] += 1
            original = os.path.join(carpeta, f"ia{IA_USADAS['cantidad']}.jpg")
            with open(original, "wb") as f:
                f.write(base64.b64decode(imagen))
            # Control: que no tenga textos raros ni algo fuera de tema
            if contexto and not verificar_imagen(original, descripcion, contexto, estricto=False):
                print("Ilustracion descartada por el control de la IA.")
                DIAG["ia_rechazadas"] = DIAG.get("ia_rechazadas", 0) + 1
                return None, None
            ruta = original.replace(".jpg", "_v.jpg")
            componer_foto(original, ruta)
            marcar_ilustracion(ruta)
            return ruta, "Ilustración generada con IA"
        except Exception as e:
            print(f"No se pudo generar la ilustracion: {e}")
            DIAG["fuentes_con_error"].add("Cloudflare IA")
            DIAG["ia_fallidas"] += 1
            DIAG["ia_error"] = str(e)[:120]
            return None, None
    return None, None


def componer_foto(origen, destino):
    """Lleva cualquier foto (vertical u horizontal) a PANTALLA COMPLETA vertical (1080x1920).
    Recorta lo que sobra: en fotos verticales prioriza la parte de arriba (donde suelen estar las caras)
    y en las horizontales toma el centro."""
    foto = Image.open(origen).convert("RGB")
    escala = max(ANCHO / foto.width, ALTO / foto.height)
    foto = foto.resize((int(foto.width * escala) + 1, int(foto.height * escala) + 1), Image.LANCZOS)
    x = (foto.width - ANCHO) // 2
    sobra_y = foto.height - ALTO
    y = int(sobra_y * 0.25)                        # un poco hacia arriba, para no cortar cabezas
    foto = foto.crop((x, y, x + ANCHO, y + ALTO))
    foto = ImageEnhance.Brightness(foto).enhance(0.92)
    foto.save(destino, "JPEG", quality=92)


# Palabras que delatan un video que puede confundir (banderas, fechas, politica, textos)
PROHIBIDAS_VIDEO = {"flag", "flags", "usa", "america", "american", "united states", "election", "elections",
                    "vote", "voting", "politics", "president", "trump", "biden", "text", "typography",
                    "logo", "brand", "map", "countdown", "calendar", "independence", "patriotic",
                    "4th of july", "july 4", "us flag", "animation", "animated", "cartoon", "illustration",
                    "vector", "motion graphics", "2d", "3d render", "character", "infographic"}


def video_apto(etiquetas, busqueda):
    """Descarta videos con banderas, anos, mapas o politica, salvo que se hayan pedido."""
    etiquetas = (etiquetas or "").lower()
    pedido = busqueda.lower()
    if re.search(r"\b(19|20)\d{2}\b", etiquetas) and not re.search(r"\b(19|20)\d{2}\b", pedido):
        return False
    return not any(p in etiquetas and p not in pedido for p in PROHIBIDAS_VIDEO)


def video_valido(ruta):
    """Confirma con ffprobe que el archivo es un video que se puede abrir."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width", "-of", "csv=p=0", ruta], capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip().isdigit()


def _bajar_video(url, carpeta, usados, clave):
    """Baja el video y verifica que sea valido. Devuelve la ruta o None."""
    usados.add(clave)                                     # no reintentar este mismo video
    ruta = os.path.join(carpeta, f"fondo{len(usados)}.mp4")
    try:
        r = requests.get(url, timeout=90, headers={"User-Agent": "Mozilla/5.0",
                                                    "Referer": "https://pixabay.com/"})
        tipo = r.headers.get("Content-Type", "")
        if r.status_code != 200 or len(r.content) < 50_000 or "html" in tipo:
            print(f"Descarga invalida ({r.status_code}, {tipo}, {len(r.content)} bytes): {url[:80]}")
            DIAG["stock_descarga_fallida"] += 1
            return None
        with open(ruta, "wb") as f:
            f.write(r.content)
        if not video_valido(ruta):
            print(f"El archivo bajado no es un video valido: {url[:80]}")
            os.remove(ruta)
            return None
        return ruta
    except Exception as e:
        print(f"No se pudo bajar el video: {e}")
        return None


def _verificar_video(ruta, nombre, contexto):
    """Revisa un cuadro del video de stock con la IA (criterio de escena coherente con el tema)."""
    if not contexto:
        return True
    cuadro = ruta + ".jpg"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1", "-i", ruta, "-frames:v", "1", cuadro],
                   check=False)
    ok = os.path.exists(cuadro) and verificar_imagen(cuadro, nombre, contexto, estricto=False)
    DIAG["stock_aceptados" if ok else "stock_rechazados"] += 1
    return ok


def buscar_video(busqueda, carpeta, usados, contexto=""):
    """Busca un video libre de derechos (Pixabay o Pexels).
    Devuelve (archivo, credito) o (None, None)."""
    if not busqueda:
        return None, None
    if PIXABAY_API_KEY:
        try:
            hits = []
            consultas = [busqueda] + ([busqueda.split()[-1]] if len(busqueda.split()) > 1 else [])
            for consulta in consultas:                     # si no hay nada, prueba algo mas simple
                r = requests.get("https://pixabay.com/api/videos/", timeout=20, params={
                    "key": PIXABAY_API_KEY, "q": consulta[:100], "safesearch": "true", "per_page": 20,
                    "video_type": "film"}).json()                # solo videos filmados, nada de animaciones
                DIAG["stock_busquedas"] += 1
                hits = r.get("hits", [])
                DIAG["stock_resultados"] += len(hits)
                if hits:
                    break
            for v in hits:
                clave = f"pb{v['id']}"
                if clave in usados or v.get("duration", 0) < 4 or not video_apto(v.get("tags"), busqueda):
                    continue
                opciones = [o for o in (v.get("videos") or {}).values()
                            if o.get("url") and 540 <= (o.get("height") or 0) <= 2200]
                if not opciones:
                    continue
                DIAG["stock_encontrados"] += 1
                for o in sorted(opciones, key=lambda o: -o["height"]):      # si falla un tamano, prueba los otros
                    ruta = _bajar_video(o["url"], carpeta, usados, clave)
                    if ruta:
                        if _verificar_video(ruta, busqueda, contexto):
                            return ruta, f"Pixabay ({v.get('user', '')})"
                        print(f"Video de stock descartado por no corresponder: {busqueda}")
                        break
                if sum(1 for u in usados if u.startswith("pb")) >= 6:      # no revisar infinitos
                    break
        except Exception as e:
            print(f"Pixabay no respondio para '{busqueda}': {e}")
            DIAG["fuentes_con_error"].add("Pixabay videos")
    if PEXELS_API_KEY:
        try:
            r = requests.get("https://api.pexels.com/videos/search", timeout=20,
                             headers={"Authorization": PEXELS_API_KEY},
                             params={"query": busqueda, "orientation": "portrait", "per_page": 10}).json()
            for v in r.get("videos", []):
                clave = f"px{v['id']}"
                etiquetas = (v.get("url") or "").replace("-", " ")
                if clave in usados or v.get("duration", 0) < 4 or not video_apto(etiquetas, busqueda):
                    continue
                archivos = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4"
                            and 1280 <= (f.get("height") or 0) <= 2400]
                if not archivos:
                    continue
                elegido = min(archivos, key=lambda f: abs(f["height"] - 1920))
                ruta = _bajar_video(elegido["link"], carpeta, usados, clave)
                if ruta and _verificar_video(ruta, busqueda, contexto):
                    return ruta, f"Pexels ({v.get('user', {}).get('name', '')})"
        except Exception as e:
            print(f"Pexels no respondio para '{busqueda}': {e}")
    return None, None


# ======================== 4. ARMAR EL VIDEO ========================
def correr(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg fallo: " + r.stderr[-600:])


def duracion(ruta):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", ruta], capture_output=True, text=True)
    return float(r.stdout.strip())


VOZ_ELEGIDA = random.choice(VOCES)


TIEMPOS_VOZ = {}      # ruta de voz -> [(segundo_inicio, palabra), ...]


def generar_voces(textos, carpeta):
    """Devuelve la lista de archivos de voz, o None si el servicio de voz no responde.
    Ademas guarda en TIEMPOS_VOZ el instante exacto en que se pronuncia cada palabra."""
    try:
        import edge_tts

        async def una(texto, ruta):
            try:
                com = edge_tts.Communicate(texto, VOZ_ELEGIDA, rate=VELOCIDAD_VOZ, boundary="WordBoundary")
            except TypeError:                              # versiones viejas de edge-tts
                com = edge_tts.Communicate(texto, VOZ_ELEGIDA, rate=VELOCIDAD_VOZ)
            tiempos = []
            with open(ruta, "wb") as f:
                async for parte in com.stream():
                    if parte["type"] == "audio":
                        f.write(parte["data"])
                    elif parte["type"] == "WordBoundary":
                        tiempos.append((parte["offset"] / 10_000_000, parte.get("text", "")))
            TIEMPOS_VOZ[ruta] = tiempos

        async def todas():
            rutas = []
            for i, t in enumerate(textos):
                ruta = os.path.join(carpeta, f"voz{i}.mp3")
                await una(t, ruta)
                rutas.append(ruta)
            return rutas
        return asyncio.run(todas())
    except Exception as e:
        print(f"Sin voz en off ({e}). Sigo sin voz.")
        return None


def elegir_musica(tono):
    """Busca canciones en la carpeta de musica (sin importar mayusculas ni subcarpetas).
    Primero en la subcarpeta del tono (alegre/seria); si no hay, en cualquier lado."""
    extensiones = (".mp3", ".wav", ".m4a", ".ogg")
    raiz = next((d for d in os.listdir(".") if os.path.isdir(d) and d.lower() == CARPETA_MUSICA.lower()), None)
    todas = []
    if raiz:
        for carpeta, _, archivos in os.walk(raiz):
            todas += [os.path.join(carpeta, a) for a in archivos if a.lower().endswith(extensiones)]
    if not todas:                                   # por si las canciones quedaron sueltas en el repositorio
        todas = [a for a in os.listdir(".") if os.path.isfile(a) and a.lower().endswith(extensiones)]
    print(f"Canciones encontradas: {len(todas)}")
    del_tono = [t for t in todas if tono and os.sep + tono.lower() + os.sep in t.lower() + os.sep]
    return del_tono or todas


def armar_reel(segmentos, textos_voz, salida, portada_salida, tono=""):
    """segmentos: lista de {"fondo": video o None, "capa": png con el texto}."""
    tmp = tempfile.mkdtemp()
    voces = generar_voces(textos_voz, tmp)
    if voces:
        duraciones = [duracion(v) + 0.45 for v in voces]
    else:
        duraciones = [3.5] + [6.0] * (len(segmentos) - 2) + [4.0]
    duraciones[-1] += 0.8
    fps = 30

    clips = []
    for i, (seg, dur) in enumerate(zip(segmentos, duraciones)):
        clip = os.path.join(tmp, f"clip{i}.mp4")
        if seg.get("video_real"):
            entrada = ["-stream_loop", "-1", "-i", seg["video_real"]]
            base = (f"[0:v]fps={fps},scale={ANCHO}:{ALTO}:force_original_aspect_ratio=increase,"
                    f"crop={ANCHO}:{ALTO},setsar=1,eq=brightness=-0.06[f]")
        elif seg.get("fotos"):
            # Varias fotos en la misma parte: cada una con su zoom, una detras de otra
            sub = []
            parte = dur / len(seg["fotos"])
            for k, f_ in enumerate(seg["fotos"]):
                sc = os.path.join(tmp, f"sub{i}_{k}.mp4")
                cuad = int(parte * fps) + 1
                correr(["ffmpeg", "-y", "-i", f_, "-vf",
                        f"scale={int(ANCHO * 1.5)}:{int(ALTO * 1.5)},"
                        f"zoompan=z='{'min(zoom+0.0005,1.07)' if k % 2 == 0 else 'if(eq(on,0),1.07,max(zoom-0.0005,1))'}':"
                        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={cuad}:s={ANCHO}x{ALTO}:fps={fps},setsar=1",
                        "-frames:v", str(cuad), "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", sc])
                sub.append(sc)
            lista_sub = os.path.join(tmp, f"sub{i}.txt")
            with open(lista_sub, "w") as fl:
                fl.writelines(f"file '{x}'\n" for x in sub)
            pase = os.path.join(tmp, f"pase{i}.mp4")
            correr(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lista_sub, "-c", "copy", pase])
            entrada = ["-stream_loop", "-1", "-i", pase]
            base = "[0:v]setsar=1[f]"
        elif seg.get("foto"):
            cuadros = int(dur * fps) + 1
            entrada = ["-i", seg["foto"]]
            base = (f"[0:v]scale={int(ANCHO * 1.5)}:{int(ALTO * 1.5)},"
                    f"zoompan=z='min(zoom+0.0004,1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                    f"d={cuadros}:s={ANCHO}x{ALTO}:fps={fps},setsar=1[f]")
        elif seg.get("fondo"):
            inicio = 0.0
            try:
                largo = duracion(seg["fondo"])
                if largo > dur + 2:
                    inicio = random.uniform(0, largo - dur - 1)
            except Exception:
                pass
            entrada = ["-ss", f"{inicio:.2f}", "-stream_loop", "-1", "-i", seg["fondo"]]
            base = (f"[0:v]scale={ANCHO}:{ALTO}:force_original_aspect_ratio=increase,crop={ANCHO}:{ALTO},"
                    f"fps={fps},setsar=1,eq=brightness=-0.10:saturation=0.95[f]")
        else:
            entrada = ["-f", "lavfi", "-i", f"color=c=0x{FONDO[0]:02x}{FONDO[1]:02x}{FONDO[2]:02x}:s={ANCHO}x{ALTO}:r={fps}"]
            base = "[0:v]setsar=1[f]"
        # El primer fotograma del video NO puede ser negro: es la miniatura en el feed
        entrada_fade = "" if i == 0 else "fade=t=in:st=0:d=0.15,"
        # Capa de texto: fija, o animada palabra por palabra al ritmo de la voz
        capa_in = ["-i", seg["capa"]]
        if seg.get("render_sub") and seg.get("texto_voz"):
            # Subtitulos sincronizados: cada palabra aparece resaltada justo cuando se pronuncia
            palabras = seg["texto_voz"].split()
            tiempos = TIEMPOS_VOZ.get(voces[i], []) if voces else []
            if len(tiempos) == len(palabras):
                inicios = [t for t, _ in tiempos]
            else:                                           # si no coinciden, reparto proporcional al largo
                habla = (dur - 0.5) if voces else dur * 0.85
                pesos = [len(p_) + 2 for p_ in palabras]
                acum, inicios = 0.0, []
                for w in pesos:
                    inicios.append(acum * habla / sum(pesos))
                    acum += w
            bloques = bloques_subtitulo(seg["texto_voz"])
            lista_c = os.path.join(tmp, f"capas{i}.txt")
            k = 0
            with open(lista_c, "w") as fl:
                for b_i, bloque in enumerate(bloques):
                    for a_i in range(len(bloque)):
                        png = os.path.join(tmp, f"sub{i}_{k}.png")
                        seg["render_sub"](bloque, a_i, png)
                        fin_k = inicios[k + 1] if k + 1 < len(inicios) else dur
                        ini_k = 0.0 if k == 0 else inicios[k]
                        fl.write(f"file '{png}'\nduration {max(fin_k - ini_k, 0.04):.3f}\n")
                        k += 1
                fl.write(f"file '{png}'\n")
            capa_in = ["-f", "concat", "-safe", "0", "-i", lista_c]
        elif seg.get("render") and seg.get("n_palabras"):
            n_pal = seg["n_palabras"]
            habla = (dur - 0.5) if voces else dur * 0.8
            ventana = min(habla * seg.get("ritmo", 0.9), habla)      # tiempo en el que aparecen las palabras
            paso = max(ventana / n_pal, 0.06)
            lista_c = os.path.join(tmp, f"capas{i}.txt")
            with open(lista_c, "w") as fl:
                for k in range(1, n_pal + 1):
                    png = os.path.join(tmp, f"capa{i}_{k}.png")
                    seg["render"](k, png)
                    fl.write(f"file '{png}'\nduration {paso if k < n_pal else max(dur - paso * (n_pal - 1), 0.1):.3f}\n")
                fl.write(f"file '{png}'\n")
            capa_in = ["-f", "concat", "-safe", "0", "-i", lista_c]
        fin = (f"[1:v]format=rgba,fps={fps}[ov];[f][ov]overlay=0:0,{entrada_fade}"
               f"fade=t=out:st={dur - 0.15:.2f}:d=0.15,format=yuv420p")
        salida_clip = ["-t", f"{dur:.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast",
                       "-crf", "26", "-r", str(fps), clip]
        try:
            correr(["ffmpeg", "-y", *entrada, *capa_in, "-filter_complex", f"{base};{fin}", *salida_clip])
        except RuntimeError as e:
            if not (seg.get("fondo") or seg.get("foto") or seg.get("fotos") or seg.get("video_real")):
                raise
            print(f"Fallo el video de fondo de la parte {i + 1}, uso fondo liso. ({e})")
            liso = ["-f", "lavfi", "-i", f"color=c=0x{FONDO[0]:02x}{FONDO[1]:02x}{FONDO[2]:02x}:s={ANCHO}x{ALTO}:r={fps}"]
            correr(["ffmpeg", "-y", *liso, *capa_in, "-filter_complex", f"[0:v]setsar=1[f];{fin}", *salida_clip])
        clips.append(clip)
    # La portada (para la historia) es un cuadro del gancho
    # La portada se toma cuando el titulo ya aparecio completo
    momento = max(min(duraciones[0] - 0.4, 2.5), 0.5)
    correr(["ffmpeg", "-y", "-ss", f"{momento:.2f}", "-i", clips[0], "-frames:v", "1", "-q:v", "2", portada_salida])

    # Primer fotograma = portada completa (fondo + titulo entero), para que la miniatura nunca sea negra
    intro = os.path.join(tmp, "intro.mp4")
    correr(["ffmpeg", "-y", "-loop", "1", "-i", portada_salida, "-t", "0.1", "-r", str(fps),
            "-vf", f"scale={ANCHO}:{ALTO},setsar=1,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", intro])
    clips = [intro] + clips
    lista = os.path.join(tmp, "lista.txt")
    with open(lista, "w") as f:
        f.writelines(f"file '{c}'\n" for c in clips)
    video = os.path.join(tmp, "video.mp4")
    correr(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lista, "-c", "copy", video])
    total = sum(duraciones)

    silencio = os.path.join(tmp, "silencio.wav")
    correr(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "0.1", silencio])
    partes = [silencio]
    total += 0.1
    for i, dur in enumerate(duraciones):
        p = os.path.join(tmp, f"seg{i}.wav")
        if voces:
            correr(["ffmpeg", "-y", "-i", voces[i], "-af", f"apad=whole_dur={dur:.3f}",
                    "-t", f"{dur:.3f}", "-ar", "48000", "-ac", "2", p])
        else:
            correr(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{dur:.3f}", p])
        partes.append(p)
    lista_a = os.path.join(tmp, "lista_a.txt")
    with open(lista_a, "w") as f:
        f.writelines(f"file '{p}'\n" for p in partes)
    voz = os.path.join(tmp, "voz.wav")
    correr(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lista_a, "-c", "copy", voz])

    temas = elegir_musica(tono)
    audio = voz
    if temas:
        audio = os.path.join(tmp, "audio.wav")
        correr(["ffmpeg", "-y", "-i", voz, "-stream_loop", "-1", "-i", random.choice(temas),
                "-filter_complex",
                f"[1:a]volume={VOLUMEN_MUSICA},afade=t=in:d=1,afade=t=out:st={max(total - 2, 0):.2f}:d=2[m];"
                f"[0:a]asplit[v1][v2];[m][v2]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[md];"
                f"[v1][md]amix=inputs=2:duration=first:normalize=0[a]",
                "-map", "[a]", "-t", f"{total:.3f}", "-ar", "48000", audio])

    # Barra de progreso amarilla arriba: muestra cuanto falta y ayuda a que se mire hasta el final
    barra = f"[0:v]drawbox=x=0:y=0:w='iw*t/{total:.3f}':h=12:color=0xFFC400@1:t=fill[v]"
    correr(["ffmpeg", "-y", "-i", video, "-i", audio, "-filter_complex", barra, "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-shortest", "-movflags", "+faststart", salida])
    shutil.rmtree(tmp, ignore_errors=True)
    return total, bool(voces), bool(temas)


def hashtags_finales(propuestos):
    """1 hashtag de la marca + hasta 4 especificos del tema (el maximo de Instagram es 5)."""
    limpios = []
    for h in propuestos or []:
        h = "".join(c for c in unicodedata.normalize("NFD", h) if unicodedata.category(c) != "Mn")
        h = "#" + re.sub(r"[^A-Za-z0-9ñÑ]", "", h.replace("#", ""))
        if len(h) > 2 and h.lower() not in HASHTAGS_GENERICOS and h.lower() not in [x.lower() for x in limpios]:
            limpios.append(h)
    return [HASHTAG_MARCA] + limpios[:4]


def texto_publicacion(g, medios, creadores, bancos, aviso=""):
    etiquetas = hashtags_finales(g.get("hashtags", []))
    lineas = [f"🔥 {g['gancho']}", "", g["descripcion"], ""]
    if g.get("pregunta"):
        lineas += [f"💬 {g['pregunta']} Cuéntanos en los comentarios 👇", ""]
    lineas += [
              f"📌 Fuentes: {', '.join(medios) or 'ver video citado'}"]
    if creadores:
        lineas.append(f"🎥 Video viral: {', '.join(creadores)}")
    if bancos:
        reales_b = [x for x in bancos if "IA" not in x]
        if reales_b:
            lineas.append(f"🎞 Imágenes: {', '.join(reales_b)}")
        if len(reales_b) < len(bancos):
            lineas.append("🎨 Incluye recreaciones ilustrativas generadas con IA (no son fotos reales del hecho).")
    if aviso:
        lineas.append(f"⚕️ {aviso}")
    lineas += ["Resumen elaborado a partir de las fuentes citadas.", "",
               f"Síguenos en {NOMBRE_CUENTA} para enterarte de lo más viral del mundo.",
               f"🟡 {FIRMA} | QueloQue Viral", "", " ".join(etiquetas)]
    return "\n".join(lineas)[:2150]


# ======================== 4. TELEGRAM ========================
def tg(metodo, **kw):
    r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{metodo}", timeout=60, **kw)
    return r.json()


def avisar(texto):
    print(texto)
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        tg("sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "text": texto[:4000]})


def mandar_borrador(reel, caption, id_corrida, modo_prueba, nota):
    with open(reel, "rb") as f:
        tg("sendVideo", data={"chat_id": TELEGRAM_CHAT_ID, "supports_streaming": "true",
                              "width": ANCHO, "height": ALTO}, files={"video": f})
    tg("sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "text": caption[:4000]})
    if nota:
        avisar(nota)
    if modo_prueba:
        avisar("🧪 MODO PRUEBA: esto es lo que se publicaria. No se sube a Instagram.")
        return
    teclado = {"inline_keyboard": [[{"text": "✅ Publicar", "callback_data": f"si:{id_corrida}"},
                                    {"text": "❌ Descartar", "callback_data": f"no:{id_corrida}"}]]}
    tg("sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "reply_markup": json.dumps(teclado),
                            "text": f"¿Publico este Reel y la historia? Tienes {ESPERA_APROBACION_MIN} minutos."})


def _cargar_pedidos():
    if os.path.exists(TEMAS_PEDIDOS):
        with open(TEMAS_PEDIDOS, encoding="utf-8") as f:
            return json.load(f)
    return []


def _guardar_pedidos(pedidos):
    os.makedirs("publicaciones", exist_ok=True)
    with open(TEMAS_PEDIDOS, "w", encoding="utf-8") as f:
        json.dump(pedidos, f, ensure_ascii=False, indent=1)


def _anotar_pedido(mensaje):
    """Si el mensaje es '/tema ...' del dueno, lo guarda en la cola. Devuelve True si lo anoto."""
    texto = (mensaje.get("text") or "").strip()
    if str(mensaje.get("chat", {}).get("id")) != str(TELEGRAM_CHAT_ID) or not texto.lower().startswith("/tema"):
        return False
    pedido = texto[5:].strip(" :-")
    if not pedido:
        avisar("Escribí el tema después del comando, por ejemplo: /tema el pulpo que abre frascos")
        return False
    pedidos = _cargar_pedidos()
    pedidos.append(pedido[:200])
    _guardar_pedidos(pedidos)
    avisar(f"📝 Anotado: «{pedido[:200]}». Lo armo en la próxima revisión (como máximo en unas 2 horas). "
           f"Pedidos en espera: {len(pedidos)}.")
    return True


PEDIDO_ATENDIDO = {"si": False}


def pedidos_atendidos():
    return PEDIDO_ATENDIDO["si"]


def leer_pedidos_telegram():
    """Lee los /tema que mandaste desde la ultima corrida y los guarda en la cola."""
    r = tg("getUpdates", data={"timeout": 0, "allowed_updates": json.dumps(["message", "callback_query"])})
    ultimo, nuevos = None, 0
    for u in r.get("result", []):
        ultimo = u["update_id"]
        if u.get("message") and _anotar_pedido(u["message"]):
            nuevos += 1
    if ultimo is not None:
        tg("getUpdates", data={"offset": ultimo + 1, "timeout": 0})     # marca como leidos
    if nuevos:
        subir_cambios("Temas pedidos por Telegram")


def investigar_pedido(pedido, busqueda=None):
    """Busca material confiable sobre un tema pedido: Wikipedia y Google Noticias."""
    notas, fuentes = [], []
    for idioma in ("es", "en"):
        try:
            r = requests.get(f"https://{idioma}.wikipedia.org/w/api.php", headers=WIKI_UA, timeout=20, params={
                "action": "query", "format": "json", "list": "search", "srsearch": pedido, "srlimit": 1}).json()
            hits = r.get("query", {}).get("search", [])
            if hits:
                titulo = hits[0]["title"]
                ext = requests.get(f"https://{idioma}.wikipedia.org/w/api.php", headers=WIKI_UA, timeout=20, params={
                    "action": "query", "format": "json", "prop": "extracts", "explaintext": 1, "exintro": 0,
                    "titles": titulo, "redirects": 1}).json()
                for pg in (ext.get("query", {}).get("pages") or {}).values():
                    if len(pg.get("extract", "")) > 300:
                        notas.append((f"Wikipedia: {titulo}", pg["extract"][:5000]))
                        fuentes.append("Wikipedia")
                break
        except Exception as e:
            print(f"Wikipedia no respondio para el pedido: {e}")
    try:
        q = urllib.parse.quote(busqueda or pedido)
        items = leer_rss(bajar(f"{GN}/search?q={q}&hl=es-419&gl=US&ceid=US:es-419"), "Google Noticias")[:6]
        if items:
            notas.append(("Noticias recientes", "\n".join(f"{n['titulo']} ({n['fuente']}). {n['descripcion']}"
                                                           for n in items)))
            fuentes += [n["fuente"] for n in items[:2] if n["fuente"] not in fuentes]
    except Exception as e:
        print(f"Google Noticias no respondio para el pedido: {e}")
    return notas, fuentes[:3]


def esperar_respuesta(id_corrida):
    r = tg("getUpdates", data={"offset": -1, "timeout": 0})
    offset = (r.get("result") or [{"update_id": 0}])[-1]["update_id"]
    fin = time.time() + ESPERA_APROBACION_MIN * 60
    while time.time() < fin:
        r = tg("getUpdates", data={"offset": offset + 1, "timeout": 30,
                                   "allowed_updates": json.dumps(["callback_query", "message"])})
        for u in r.get("result", []):
            offset = u["update_id"]
            if u.get("message"):
                if _anotar_pedido(u["message"]):
                    subir_cambios("Tema pedido por Telegram")
                continue
            cb = u.get("callback_query")
            if not cb or str(cb["message"]["chat"]["id"]) != str(TELEGRAM_CHAT_ID):
                continue
            decision, _, corrida = cb.get("data", "").partition(":")
            if corrida == id_corrida:
                tg("answerCallbackQuery", data={"callback_query_id": cb["id"],
                                                "text": "Publicando..." if decision == "si" else "Descartado"})
                return decision == "si"
    return None


# ======================== 5. INSTAGRAM ========================
def ig(metodo, ruta, _reintento=True, **datos):
    global IG_TOKEN
    url = f"{IG_API}/{ruta}"
    params = dict(datos, access_token=IG_TOKEN)
    r = requests.post(url, data=params, timeout=60) if metodo == "POST" else requests.get(url, params=params, timeout=60)
    js = r.json()
    if "error" in js:
        err = js["error"]
        # Token invalido: si el guardado no sirve, probamos con el del secreto (por si lo actualizaste)
        if err.get("code") == 190 and _reintento and IG_TOKEN_SECRETO and IG_TOKEN != IG_TOKEN_SECRETO:
            print("El token guardado no sirve; pruebo con el del secreto IG_TOKEN.")
            IG_TOKEN = IG_TOKEN_SECRETO
            guardar_token("instagram", IG_TOKEN)
            return ig(metodo, ruta, _reintento=False, **datos)
        if err.get("code") == 190:
            raise RuntimeError("El token de Instagram no es valido. Genera uno nuevo en Meta for Developers "
                               "y actualiza el secreto IG_TOKEN en GitHub.")
        raise RuntimeError(f"Instagram: {err.get('message')}")
    return js


def guardar_historial(historial_nuevo):
    os.makedirs(CARPETA, exist_ok=True)
    with open(HISTORIAL, "w", encoding="utf-8") as f:
        json.dump(historial_nuevo, f, ensure_ascii=False, indent=1)
    subir_cambios("Historial")


def preparar_sitio(archivos, caption, titulos, indice_categoria=None, oportunista=False):
    """Deja los archivos en la carpeta 'sitio' para que GitHub Pages los publique
    (lo hace el paso siguiente del workflow) y guarda lo pendiente de publicar."""
    os.makedirs("sitio", exist_ok=True)
    for a in archivos:
        shutil.copy(a, "sitio")
    with open("pendiente.json", "w", encoding="utf-8") as f:
        json.dump({"archivos": [os.path.basename(a) for a in archivos], "caption": caption,
                   "titulos": titulos, "indice_categoria": indice_categoria,
                   "oportunista": oportunista}, f, ensure_ascii=False)


def esperar_urls(urls):
    for _ in range(30):                                   # hasta 5 minutos
        try:
            if all(requests.head(u, timeout=15, allow_redirects=True).status_code == 200 for u in urls):
                return
        except Exception:
            pass
        time.sleep(10)
    raise RuntimeError("GitHub Pages no sirvio los archivos a tiempo.")


def esperar_contenedor(cid, intentos=40):
    for _ in range(intentos):
        estado = ig("GET", cid, fields="status_code").get("status_code")
        if estado == "FINISHED":
            return
        if estado == "ERROR":
            raise RuntimeError("Instagram no pudo procesar el archivo.")
        time.sleep(8)
    raise RuntimeError("Instagram tardo demasiado en procesar el video.")


def publicar_en_instagram(url_reel, url_portada, caption):
    yo = ig("GET", "me", fields="user_id,username")
    ig_id = yo["user_id"]
    reel = ig("POST", f"{ig_id}/media", media_type="REELS", video_url=url_reel,
              cover_url=url_portada, caption=caption, share_to_feed="true")["id"]
    esperar_contenedor(reel)
    media = ig("POST", f"{ig_id}/media_publish", creation_id=reel)["id"]
    link = ig("GET", media, fields="permalink").get("permalink", "")
    historia_ok = True
    try:
        h = ig("POST", f"{ig_id}/media", media_type="STORIES", image_url=url_portada)["id"]
        esperar_contenedor(h, 15)
        ig("POST", f"{ig_id}/media_publish", creation_id=h)
    except Exception as e:
        historia_ok = False
        print(f"No se pudo publicar la historia: {e}")
    return link, yo.get("username", ""), historia_ok


def subir_a_youtube(ruta_video, titulo, descripcion):
    """Sube el Reel como Short a YouTube. Devuelve el link o lanza un error.
    Si YouTube rechaza los datos (por ejemplo error 409), reintenta con datos minimos."""
    tok = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "client_id": YT_CLIENT_ID, "client_secret": YT_CLIENT_SECRET,
        "refresh_token": YT_REFRESH_TOKEN, "grant_type": "refresh_token"}).json()
    if "access_token" not in tok:
        raise RuntimeError(f"YouTube no dio acceso: {tok.get('error_description') or tok}")
    cab = {"Authorization": f"Bearer {tok['access_token']}"}
    limpio = lambda t: t.replace("<", "").replace(">", "")
    titulo_base = limpio(titulo[:88])
    etiquetas = list(dict.fromkeys(t.lstrip("#") for t in re.findall(r"#\w+", descripcion)))[:8]
    intentos = [
        {"snippet": {"title": f"{titulo_base} #Shorts", "description": limpio(descripcion[:4900]),
                     "categoryId": "25", "tags": etiquetas or ["QueloQueViral"]},
         "status": {"privacyStatus": YT_PRIVACIDAD, "selfDeclaredMadeForKids": False}},
        {"snippet": {"title": f"{titulo_base} | QLQ #Shorts", "description": limpio(descripcion[:4900]),
                     "categoryId": "25"},
         "status": {"privacyStatus": YT_PRIVACIDAD, "selfDeclaredMadeForKids": False}},
    ]
    tam = os.path.getsize(ruta_video)
    ultimo_error = ""
    for meta in intentos:
        ini = requests.post("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                            timeout=60, json=meta, headers={**cab, "X-Upload-Content-Type": "video/mp4",
                                                            "X-Upload-Content-Length": str(tam)})
        if ini.status_code != 200 or "Location" not in ini.headers:
            ultimo_error = f"YouTube rechazo la subida ({ini.status_code}): {ini.text[:200]}"
            print(ultimo_error + " — reintento con datos minimos.")
            continue
        with open(ruta_video, "rb") as f:
            r = requests.put(ini.headers["Location"], data=f, timeout=600,
                             headers={**cab, "Content-Type": "video/mp4", "Content-Length": str(tam)})
        if r.status_code in (200, 201):
            return f"https://youtube.com/shorts/{r.json()['id']}"
        ultimo_error = f"YouTube fallo al subir ({r.status_code}): {r.text[:200]}"
        print(ultimo_error + " — reintento.")
    raise RuntimeError(ultimo_error)


# ======================== PAGINAS WEB (las pide TikTok) ========================
def url_web():
    dueno, nombre = os.environ.get("GITHUB_REPOSITORY", "usuario/repo").split("/")
    return f"https://{dueno.lower()}.github.io/{nombre}"


_ESTILO = ("<meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
           "<style>body{font-family:system-ui,sans-serif;background:#0e111c;color:#f5f5f5;max-width:720px;"
           "margin:auto;padding:24px;line-height:1.6}h1{color:#ffc400}a{color:#ffc400}"
           "code{background:#222838;padding:10px;display:block;word-break:break-all;font-size:15px}</style>")


def preparar_web():
    """Crea las paginas publicas que pide TikTok (inicio, privacidad, terminos y la de autorizacion).
    Se publican en GitHub Pages junto con los videos."""
    os.makedirs("sitio", exist_ok=True)
    paginas = {
        "index.html": f"""<title>QueloQue Viral</title>{_ESTILO}<h1>QueloQue Viral</h1>
<p>Lo más viral del mundo, contado en español y en 30 segundos. Resúmenes de noticias con fuentes citadas,
publicados en Instagram, YouTube y TikTok como {NOMBRE_CUENTA}.</p>
<p><a href='privacidad.html'>Política de privacidad</a> · <a href='terminos.html'>Términos de servicio</a></p>""",
        "privacidad.html": f"""<title>Privacidad - QueloQue Viral</title>{_ESTILO}<h1>Política de privacidad</h1>
<p>QueloQue Viral es una herramienta de uso personal que publica videos en las cuentas propias de
{NOMBRE_CUENTA}. No recopila, vende ni comparte datos de otras personas.</p>
<p>Los permisos otorgados por Instagram, YouTube y TikTok se usan exclusivamente para publicar contenido
en las cuentas del propio titular. Los accesos se guardan de forma cifrada y pueden revocarse en cualquier
momento desde la configuración de cada plataforma.</p>
<p>Contacto: a través de {NOMBRE_CUENTA} en Instagram.</p>""",
        "terminos.html": f"""<title>Términos - QueloQue Viral</title>{_ESTILO}<h1>Términos de servicio</h1>
<p>QueloQue Viral es una herramienta privada de publicación de contenido propio para las cuentas de
{NOMBRE_CUENTA}. No ofrece servicios a terceros ni permite que otras personas conecten sus cuentas.</p>
<p>El contenido publicado resume noticias con sus fuentes citadas y usa imágenes y música libres de derechos.</p>""",
        "tiktok_callback.html": f"""<title>Autorización TikTok</title>{_ESTILO}<h1>Autorización de TikTok</h1>
<p id='m'>Buscando el código...</p><code id='c'></code>
<script>
const p = new URLSearchParams(location.search);
const c = p.get('code');
document.getElementById('m').textContent = c
  ? 'Listo. Copia este código completo y pégalo en GitHub (Run workflow → modo tiktok_token). Vence en pocos minutos.'
  : 'No llegó ningún código. Error: ' + (p.get('error_description') || p.get('error') || 'desconocido');
document.getElementById('c').textContent = c || '';
</script>""",
    }
    for nombre, contenido in paginas.items():
        with open(os.path.join("sitio", nombre), "w", encoding="utf-8") as f:
            f.write("<!doctype html><html lang='es'><head>" + contenido.replace("<h1>", "</head><body><h1>", 1)
                    + "</body></html>")
    # Archivos de verificacion (TikTok, Google, etc.): todo lo que este en la carpeta "verificacion"
    if os.path.isdir("verificacion"):
        for archivo in os.listdir("verificacion"):
            ruta = os.path.join("verificacion", archivo)
            if os.path.isfile(ruta):
                shutil.copy(ruta, "sitio")


# ======================== TIKTOK ========================
TIKTOK_API = "https://open.tiktokapis.com/v2"


def tiktok_redirect():
    return f"{url_web()}/tiktok_callback.html"


def tiktok_link_autorizacion():
    q = urllib.parse.urlencode({"client_key": TIKTOK_CLIENT_KEY, "response_type": "code",
                                "scope": "user.info.basic,video.upload", "redirect_uri": tiktok_redirect(),
                                "state": "qlq"})
    return f"https://www.tiktok.com/v2/auth/authorize/?{q}"


def tiktok_token(datos):
    r = requests.post(f"{TIKTOK_API}/oauth/token/", timeout=30, data={
        "client_key": TIKTOK_CLIENT_KEY, "client_secret": TIKTOK_CLIENT_SECRET, **datos},
        headers={"Content-Type": "application/x-www-form-urlencoded"}).json()
    if "access_token" not in r:
        raise RuntimeError(f"TikTok no dio acceso: {r.get('error_description') or r}")
    return r


def tiktok_canjear_codigo(codigo):
    """Una sola vez: cambia el codigo de autorizacion por el token de larga duracion y lo manda a Telegram."""
    r = tiktok_token({"code": codigo.strip(), "grant_type": "authorization_code",
                      "redirect_uri": tiktok_redirect()})
    guardar_token("tiktok", r["refresh_token"])
    subir_cambios("Token de TikTok")
    avisar("✅ TikTok conectado y guardado. No hace falta crear ningun secreto: el bot se encarga "
           "de renovarlo solo.")


def subir_a_tiktok(ruta_video):
    """Manda el video a la bandeja de TikTok como borrador (no requiere auditoria)."""
    vigente = leer_token("tiktok", TIKTOK_REFRESH_TOKEN)
    if not vigente:
        raise RuntimeError("TikTok no esta conectado. Corre el modo tiktok_link y despues tiktok_token.")
    tok = tiktok_token({"grant_type": "refresh_token", "refresh_token": vigente})
    if tok.get("refresh_token"):
        guardar_token("tiktok", tok["refresh_token"])       # TikTok lo puede cambiar: guardamos el nuevo
    tam = os.path.getsize(ruta_video)
    if tam > 64 * 1024 * 1024:
        raise RuntimeError("El video pesa mas de 64 MB.")
    ini = requests.post(f"{TIKTOK_API}/post/publish/inbox/video/init/", timeout=60,
                        headers={"Authorization": f"Bearer {tok['access_token']}",
                                 "Content-Type": "application/json; charset=UTF-8"},
                        json={"source_info": {"source": "FILE_UPLOAD", "video_size": tam,
                                              "chunk_size": tam, "total_chunk_count": 1}}).json()
    datos = ini.get("data") or {}
    if not datos.get("upload_url"):
        raise RuntimeError(f"TikTok rechazo la subida: {(ini.get('error') or {}).get('message') or ini}")
    with open(ruta_video, "rb") as f:
        r = requests.put(datos["upload_url"], data=f, timeout=600, headers={
            "Content-Type": "video/mp4", "Content-Length": str(tam), "Content-Range": f"bytes 0-{tam - 1}/{tam}"})
    if r.status_code not in (200, 201):
        raise RuntimeError(f"TikTok fallo al subir el video ({r.status_code}): {r.text[:200]}")
    return datos.get("publish_id", "")


MARCA_TOKEN = os.path.join(CARPETA, "token_instagram_renovado.txt")
DIAS_ENTRE_RENOVACIONES = 30


def renovar_token():
    """Renueva el token de Instagram (dura 60 dias) una vez por mes, no en cada publicacion.
    El token nuevo se guarda cifrado en el repositorio, asi que no hay que actualizar ningun secreto."""
    try:
        if os.path.exists(MARCA_TOKEN):
            with open(MARCA_TOKEN, encoding="utf-8") as f:
                ultima = datetime.fromisoformat(f.read().strip())
            if datetime.now() - ultima < timedelta(days=DIAS_ENTRE_RENOVACIONES):
                return
        r = requests.get("https://graph.instagram.com/refresh_access_token",
                         params={"grant_type": "ig_refresh_token", "access_token": IG_TOKEN}, timeout=30).json()
        nuevo, dias = r.get("access_token"), r.get("expires_in", 0) // 86400
        if not nuevo:
            print(f"No se pudo renovar el token: {r}")
            return
        os.makedirs(CARPETA, exist_ok=True)
        with open(MARCA_TOKEN, "w", encoding="utf-8") as f:
            f.write(datetime.now().isoformat(timespec="seconds"))
        guardar_token("instagram", nuevo)                  # se guarda cifrado; no hay que tocar nada
        print(f"Token de Instagram renovado y guardado: vence en {dias} dias.")
    except Exception as e:
        print(f"No se pudo renovar el token: {e}")


# ======================== PROGRAMA PRINCIPAL ========================
def main():
    modo_prueba = (len(sys.argv) > 1 and sys.argv[1] == "prueba") or not IG_TOKEN
    faltan = [n for n, v in [("ANTHROPIC_API_KEY", ANTHROPIC_API_KEY), ("TELEGRAM_TOKEN", TELEGRAM_TOKEN),
                             ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID)] if not v]
    if faltan:
        print("Faltan secretos: " + ", ".join(faltan))
        sys.exit(1)

    preparar_web()
    id_corrida = datetime.now(ARGENTINA).strftime("%Y%m%d-%H%M")
    historial = []
    if os.path.exists(HISTORIAL):
        with open(HISTORIAL, encoding="utf-8") as f:
            historial = json.load(f)

    contenido = (os.environ.get("CONTENIDO") or "auto").strip().lower()
    if contenido not in ("noticias", "interes", "radar"):
        contenido = "interes" if datetime.now(ARGENTINA).hour in HORAS_INTERES else "noticias"
    categoria, indice_cat, aviso = "", None, ""
    guion, fuentes = None, []
    if INTENTO["n"] == 0:
        try:
            leer_pedidos_telegram()
        except Exception as e:
            print(f"No pude leer los pedidos de Telegram: {e}")
    pedidos = _cargar_pedidos()

    oportunista = False
    if pedidos and INTENTO["n"] == 0:                  # los pedidos con /tema van primero, en cualquier corrida
        # Primero los temas que pediste con /tema
        pedido = pedidos.pop(0)
        _guardar_pedidos(pedidos)
        PEDIDO_ATENDIDO["si"] = True
        subir_cambios("Tema pedido en produccion")
        avisar(f"🎯 Armando el Reel que pediste: «{pedido}»")
        notas, fuentes = investigar_pedido(pedido)
        if sum(len(t) for _, t in notas) < 400:
            avisar(f"⚠️ No encontré información confiable suficiente sobre «{pedido}». Sigo con el contenido normal.")
        else:
            categoria = "tema pedido"
            try:
                guion = completar_guion(escribir_guion(pedido, notas, "interes", "tema pedido"))
                guion = revisar_datos(guion, notas)
            except Exception as e:
                print(f"No se pudo armar el pedido: {e}")
                guion = None
            if guion and any(p in pedido.lower() for p in ("salud", "dieta", "aliment", "nutri", "mental",
                                                             "ansiedad", "dormir", "sueño", "ejercicio")):
                aviso = AVISO_SALUD

    if contenido == "radar" and not guion and not pedidos_atendidos():
        estado = _estado_radar()
        if estado["publicados"] >= MAX_OPORTUNISTAS_DIA:
            print("Ya se publicaron los oportunistas del dia.")
            return
        elegido = elegir_oportunista(senales_tendencia(),
                                     "; ".join(historial[-30:] + estado.get("temas", []) + DESCARTADOS))
        if not elegido:
            print("Radar: nada lo bastante caliente por ahora.")
            return
        notas, fuentes = investigar_pedido(elegido["tema"], elegido.get("busqueda"))
        if sum(len(t) for _, t in notas) < 400:
            print(f"Radar: poca informacion confiable sobre {elegido['tema']}.")
            return
        try:
            guion = completar_guion(escribir_guion(elegido["tema"], notas))
            guion = revisar_datos(guion, notas)
            oportunista = True
            avisar(f"⚡ Oportunista: «{elegido['tema']}»\nPor qué ahora: {elegido.get('motivo', '')}")
        except Exception as e:
            print(f"Radar: no se pudo armar el guion: {e}")
            return

    if contenido == "interes" and not guion:
        indice_cat, categoria = proxima_categoria()
        items, fallidas = juntar_interes(categoria)
        print(f"Interes general: {categoria}. {len(items)} articulos. Fuentes con problemas: {fallidas or 'ninguna'}")
        for tema in elegir_tema_interes(categoria, items, "; ".join(historial[-30:] + DESCARTADOS)):
            ids = [i for i in tema.get("ids", []) if isinstance(i, int) and 0 <= i < len(items)]
            notas, fuentes = [], []
            for i in ids[:3]:
                n = items[i]
                texto = leer_nota(n["link"]) if es_directo(n) else ""
                notas.append((n["fuente"], texto if len(texto) >= 400 else f"{n['titulo']}. {n['descripcion']}"))
                if n["fuente"] not in fuentes:
                    fuentes.append(n["fuente"])
            if not ids:
                if not tema.get("fuente_texto"):
                    continue
                fuentes = [tema["fuente_texto"]]
            try:
                guion = completar_guion(escribir_guion(tema["tema"], notas, "interes", categoria))
                guion = revisar_datos(guion, notas)
                break
            except Exception as e:
                print(f"No se pudo armar '{tema.get('tema')}': {e}")
        if categoria in CATEGORIAS_SALUD:
            aviso = AVISO_SALUD
        if guion:
            guion["categoria"] = guion.get("categoria") or categoria.upper()
    elif contenido == "noticias" and not guion:
        noticias, tendencias, fallidas = juntar_noticias()
        print(f"{len(noticias)} noticias leidas. Fuentes con problemas: {fallidas or 'ninguna'}")
        if len(noticias) < 15:
            avisar(f"⚠️ Solo consegui {len(noticias)} noticias (fallaron: {', '.join(fallidas)}). No armo el Reel.")
            return

        # Elige el tema y lee las notas completas (si el primero no se puede leer, prueba el siguiente)
        guion = None
        for tema in elegir_temas(noticias, tendencias, "; ".join(historial[-20:] + DESCARTADOS)):
            ids = [i for i in tema.get("ids", []) if isinstance(i, int) and 0 <= i < len(noticias)]
            notas, fuentes = [], []
            for i in sorted(ids, key=lambda i: not es_directo(noticias[i])):
                n = noticias[i]
                if n["fuente"] in fuentes or n.get("youtube"):
                    continue
                texto = leer_nota(n["link"]) if es_directo(n) else ""
                if len(texto) < 400:
                    texto = f"{n['titulo']}. {n['descripcion']}"
                notas.append((n["fuente"], texto))
                fuentes.append(n["fuente"])
                if len(notas) == 3:
                    break
            for i in ids:                                     # material de YouTube, si el tema viene de ahi
                n = noticias[i]
                if n.get("youtube") and n["fuente"] not in fuentes and len(fuentes) < 5:
                    notas.append((n["fuente"], f"{n['titulo']}. {n.get('texto_largo', '')}"))
                    fuentes.append(n["fuente"])
            if sum(len(t) for _, t in notas) >= 800:
                guion = completar_guion(escribir_guion(tema["tema"], notas))
                break
            print(f"Poca informacion sobre '{tema['tema']}', pruebo el siguiente.")

    if not guion:
        avisar("⚠️ No consegui informacion suficiente para armar un Reel confiable. Salteo esta vuelta.")
        return

    texto_tema = (categoria + " " + guion["gancho"] + " " + " ".join(guion.get("palabras_clave") or [])).lower()
    NASA_ACTIVA["si"] = any(p in texto_tema for p in ("espacio", "astronom", "nasa", "planeta", "luna", "marte",
                                                        "estrella", "galaxia", "cohete", "satélite", "satelite",
                                                        "eclipse", "asteroide", "telescopio", "ciencia", "tierra"))
    carpeta = tempfile.mkdtemp()
    medios = [f for f in fuentes if not f.startswith("YouTube:")][:3]
    creadores = [f.replace("YouTube: ", "") + " (YouTube)" for f in fuentes if f.startswith("YouTube:")][:2]

    usados, fotos_usadas, reales_usados, autores = set(), set(), set(), []
    contexto = f"{guion['gancho']}. " + " ".join(p.get("pantalla", "") for p in guion["placas"])
    # Las 3 palabras clave mandan: todas las imagenes se buscan a partir de ellas
    claves = [c for c in (guion.get("palabras_clave") or []) if isinstance(c, str) and c.strip()][:3]
    claves = claves or [x for x in [guion.get("imagen_gancho")] + [p.get("imagen") for p in guion["placas"]] if x][:3]
    claves_en = [c for c in (guion.get("palabras_clave_en") or []) if isinstance(c, str) and c.strip()][:3]
    if not claves_en:                                   # respaldo si la IA no las devolvio
        claves_en = [c for c in claves if c][:3]
    aprobados = []                                   # fondos ya verificados, para reusar si falta alguno

    def _registrar(credito):
        if credito and credito not in autores:
            autores.append(credito)

    def _foto(clave, orden):
        ruta, credito = buscar_foto(clave, carpeta, fotos_usadas, contexto)
        if not ruta:
            return None
        _registrar(credito)
        fotos = [ruta]
        for clave2 in [clave] + [c for c in orden if c != clave]:
            ruta2, credito2 = buscar_foto(clave2, carpeta, fotos_usadas, contexto)
            if ruta2:
                fotos.append(ruta2)
                _registrar(credito2)
                break
        return {"fotos": fotos} if len(fotos) > 1 else {"foto": ruta}

    def _video_stock(indice):
        orden_en = claves_en[indice % len(claves_en):] + claves_en[:indice % len(claves_en)] if claves_en else []
        for busqueda in orden_en:
            ruta, autor = buscar_video(busqueda, carpeta, usados, contexto)
            if ruta:
                _registrar(autor)
                return {"fondo": ruta}
        return None

    ideas_ia = [x for x in (guion.get("ilustraciones") or []) if isinstance(x, str) and x.strip()]
    if len(ideas_ia) < 3:                               # respaldo: escenas a partir de las palabras clave
        ideas_ia += [f"{c}, atmospheric scene, wide shot" for c in claves_en if c][:3 - len(ideas_ia)]
    DIAG["ia_ideas"] = len(ideas_ia)

    ideas_usadas = set()

    def _ilustracion(indice):
        """Genera una ilustracion con una idea que todavia no se uso en este Reel."""
        for k in range(len(ideas_ia)):
            idea = ideas_ia[(indice + k) % len(ideas_ia)]
            if idea in ideas_usadas:
                continue
            ideas_usadas.add(idea)
            ruta, credito = generar_ilustracion(idea, carpeta, contexto)
            if ruta:
                _registrar(credito)
                return {"foto": ruta}
        return None

    def fondo(indice):
        """Gancho: imagen real del protagonista (para reconocerlo al instante).
        Desarrollo: PRIMERO VIDEO (real o de stock relacionado) para que el Reel tenga movimiento;
        foto solo si no hay video que pase el control de la IA."""
        orden = claves[indice % len(claves):] + claves[:indice % len(claves)] if claves else []
        media = None
        for clave in orden:                               # 1) video real del tema
            ruta, credito = buscar_video_real(clave, carpeta, reales_usados, contexto)
            if ruta:
                _registrar(credito)
                media = {"video_real": ruta}
                break
        if not media and indice == 0:                     # 2a) gancho: foto del protagonista
            for clave in orden:
                media = _foto(clave, orden)
                if media:
                    break
        if not media:                                     # 2b) desarrollo: video de stock del tema
            media = _video_stock(indice)
        if not media and indice > 0:                      # 3) ilustracion con IA (variedad en vez de repetir)
            media = _ilustracion(indice)
        if not media:                                     # 4) foto del tema
            for clave in orden:
                media = _foto(clave, orden)
                if media:
                    break
        if not media and indice == 0:                     # 5) gancho sin foto: ilustracion
            media = _ilustracion(indice)
        if not media:                                     # 6) ultimo intento: otra ilustracion distinta
            media = _ilustracion(indice + 1)
        if media:
            aprobados.append(media)
            return media
        return {"fondo": None}                            # fondo de marca: nunca se repite una imagen

    segmentos = [{**fondo(0), "capa": os.path.join(carpeta, "c0.png"),
                  }]                                       # el gancho se ve completo desde el primer cuadro
    capa_gancho(guion, segmentos[0]["capa"])
    for i, p in enumerate(guion["placas"][:3]):
        seg = {**fondo(i + 1), "capa": os.path.join(carpeta, f"c{i + 1}.png"),
               "render_sub": (lambda bloque, activa, ruta, p=p, i=i: capa_subtitulo(
                   p, i, len(guion["placas"]), guion["categoria"], ruta, bloque, activa)),
               "texto_voz": p["voz"]}
        capa_desarrollo(p, i, len(guion["placas"]), guion["categoria"], seg["capa"])
        segmentos.append(seg)
    cierre = {"fondo": None, "capa": os.path.join(carpeta, "cierre.png")}     # cierre con fondo de marca
    capa_cierre(medios or ["ver video citado"], creadores, autores, cierre["capa"], guion.get("pregunta", ""), aviso)
    segmentos.append(cierre)

    # Filtro de calidad: si no hay al menos 3 fondos distintos, no se manda un Reel pobre
    con_fondo = [sg for sg in segmentos[:-1] if sg.get("fondo") or sg.get("foto") or sg.get("fotos") or sg.get("video_real")]
    if len(con_fondo) < MIN_FONDOS:
        ia_txt = ("faltan las claves de Cloudflare" if not (CF_ACCOUNT_ID and CF_API_TOKEN)
                  else f"IA: {DIAG['ia_generadas']} generadas, {DIAG['ia_fallidas']} fallidas")
        avisar(f"⚠️ Descarté el Reel sobre «{guion['gancho']}»: solo {len(con_fondo)} de {len(segmentos) - 1} partes "
               f"con imagen. Fotos: {DIAG['aceptadas']} aceptadas de {DIAG['candidatas']}; videos de stock: "
               f"{DIAG['stock_busquedas']} búsquedas, {DIAG['stock_resultados']} resultados, "
               f"{DIAG['stock_encontrados']} aptos, {DIAG['stock_descarga_fallida']} sin poder bajar, "
               f"{DIAG['stock_aceptados']} aceptados y {DIAG['stock_rechazados']} rechazados por la IA; "
               f"{ia_txt}, {DIAG.get('ia_rechazadas', 0)} rechazadas por el control, {DIAG['ia_ideas']} ideas" + (f" (error: {DIAG['ia_error']})" if DIAG["ia_error"] else "")
               + (f"; sin respuesta: {', '.join(sorted(DIAG['fuentes_con_error']))}" if DIAG["fuentes_con_error"] else "")
               + ".")
        if INTENTO["n"] < 1:                             # prueba con otro tema (una vez)
            INTENTO["n"] += 1
            DESCARTADOS.append(guion["gancho"])
            for k in DIAG:
                DIAG[k] = set() if isinstance(DIAG[k], set) else ("" if isinstance(DIAG[k], str) else 0)
            IA_USADAS["cantidad"] = 0
            CONTROLES["n"] = 0
            avisar("🔁 Pruebo con otro tema...")
            return main()
        return

    textos_voz = [guion.get("voz_gancho") or guion["gancho"]] + [p["voz"] for p in guion["placas"][:3]]
    pregunta = (guion.get("pregunta") or "").strip()
    textos_voz.append((pregunta + " " if pregunta else "") + "Síguenos en QueloQue Viral.")
    reel = os.path.join(carpeta, f"reel-{id_corrida}.mp4")
    portada = os.path.join(carpeta, f"portada-{id_corrida}.jpg")
    total, con_voz, con_musica = armar_reel(segmentos, textos_voz, reel, portada,
                                            (guion.get("tono") or "").strip().lower())
    bancos = autores                                      # créditos completos (autor y licencia)
    caption = texto_publicacion(guion, medios, creadores, bancos, aviso)
    sin_fondo = sum(1 for sg in segmentos[:-1]
                    if not (sg.get("fondo") or sg.get("foto") or sg.get("fotos") or sg.get("video_real")))
    def _es_ia(sg):
        return "ia" in os.path.basename(str(sg.get("foto") or "")).split("_")[0][:3]
    reales = sum(1 for sg in segmentos[:-1] if (sg.get("foto") or sg.get("fotos") or sg.get("video_real"))
                 and not _es_ia(sg))
    stock = sum(1 for sg in segmentos[:-1] if sg.get("fondo"))
    ilustradas = sum(1 for sg in segmentos[:-1] if sg.get("foto") and _es_ia(sg))

    nota = []
    if not con_voz:
        nota.append("sin voz en off (el servicio de voz no respondio)")
    if not con_musica:
        nota.append("sin musica (no hay archivos en la carpeta 'musica')")
    if sin_fondo:
        nota.append(f"{sin_fondo} partes sin video de fondo (no se encontro video o falta la clave de Pixabay)")
    nota.append(f"Partes: {reales} con foto/video real del tema, {stock} con video de stock, "
                f"{ilustradas} con ilustración IA (de {len(segmentos) - 1})")
    distintos = len({str(sorted((k, str(v)) for k, v in sg.items() if k in ("foto", "fotos", "fondo", "video_real")))
                     for sg in segmentos[:-1]})
    ia_txt = ("SIN CLAVES (falta CF_ACCOUNT_ID / CF_API_TOKEN)" if not (CF_ACCOUNT_ID and CF_API_TOKEN)
              else f"{DIAG['ia_generadas']} generadas, {DIAG['ia_fallidas']} fallidas")
    nota.append(f"{distintos} fondos distintos | fotos: {DIAG['candidatas']} encontradas, "
                f"{DIAG['aceptadas']} aceptadas, {DIAG['rechazadas']} rechazadas | videos de stock: "
                f"{DIAG['stock_encontrados']} encontrados, {DIAG['stock_descarga_fallida']} sin poder bajar, "
                f"{DIAG['stock_aceptados']} aceptados, {DIAG['stock_rechazados']} rechazados | IA: {ia_txt}"
                + (f" | sin respuesta: {', '.join(sorted(DIAG['fuentes_con_error']))}" if DIAG["fuentes_con_error"] else ""))
    mandar_borrador(reel, caption, id_corrida, modo_prueba,
                    f"ℹ️ Reel de {total:.0f} segundos" + (" — " + "; ".join(nota) if nota else ""))
    if modo_prueba:
        return

    respuesta = esperar_respuesta(id_corrida)
    if respuesta is None:
        avisar("⌛ No hubo respuesta a tiempo. Descarte el Reel.")
        return
    if not respuesta:
        avisar("🗑 Reel descartado.")
        return
    preparar_sitio([reel, portada], caption, [guion["gancho"]], indice_cat, oportunista)
    print("Aprobado. El workflow sigue con la publicacion.")


def publicar():
    """Segunda etapa: los archivos ya estan en GitHub Pages; ahora se suben a Instagram."""
    with open("pendiente.json", encoding="utf-8") as f:
        p = json.load(f)
    base = os.environ["PAGES_URL"].rstrip("/") + "/"
    url_reel, url_portada = [base + a for a in p["archivos"]]
    esperar_urls([url_reel, url_portada])
    renovar_token()
    link, usuario, historia_ok = publicar_en_instagram(url_reel, url_portada, p["caption"])
    historial = []
    if os.path.exists(HISTORIAL):
        with open(HISTORIAL, encoding="utf-8") as f:
            historial = json.load(f)
    if p.get("indice_categoria") is not None:
        guardar_categoria(p["indice_categoria"])            # la proxima de interes general sera otra categoria
    if p.get("oportunista"):
        estado = _estado_radar()
        estado["publicados"] += 1
        estado["temas"].append(p["titulos"][0])
        _guardar_radar(estado)
    guardar_historial((historial + p["titulos"])[-40:])
    avisar(f"✅ Reel publicado en @{usuario}\n{link}" +
           ("\n📲 Historia publicada" if historia_ok else "\n⚠️ La historia no se pudo publicar"))

    # YouTube Shorts (si estan las claves). Un error aca no afecta a Instagram.
    if YT_CLIENT_ID and YT_CLIENT_SECRET and YT_REFRESH_TOKEN:
        try:
            reel = os.path.join("sitio", p["archivos"][0])
            link_yt = subir_a_youtube(reel, p["titulos"][0], p["caption"])
            extra = ("\n🔒 Quedo PRIVADO (YouTube exige auditoria para publicar por API). "
                     "Para publicarlo: YouTube Studio → Contenido → Visibilidad → Publico.") if YT_PRIVACIDAD != "public" else ""
            avisar(f"▶️ Subido a YouTube Shorts\n{link_yt}{extra}")
        except Exception as e:
            avisar(f"⚠️ No se pudo subir a YouTube: {e}")

    # TikTok: queda como borrador en tu bandeja para terminarlo desde la app
    if TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET and leer_token("tiktok", TIKTOK_REFRESH_TOKEN):
        try:
            subir_a_tiktok(os.path.join("sitio", p["archivos"][0]))
            avisar("🎵 Enviado a TikTok. Abrí la app: te llega una notificación con el borrador. "
                   "Agregale un sonido en tendencia (bajito), pegá el texto de arriba y publicalo.")
        except Exception as e:
            avisar(f"⚠️ No se pudo enviar a TikTok: {e}")
        subir_cambios("Token de TikTok")                     # guarda el token renovado

if __name__ == "__main__":
    try:
        modo = sys.argv[1] if len(sys.argv) > 1 else ""
        if modo == "publicar":
            publicar()
        elif modo == "web":
            preparar_web()
            print("Paginas listas.")
        elif modo == "tiktok_link":
            preparar_web()
            avisar("Abrí este link en el celular, entrá con @queloqueviral y autorizá:\n\n" + tiktok_link_autorizacion())
        elif modo == "tiktok_token":
            preparar_web()
            tiktok_canjear_codigo(os.environ.get("TIKTOK_CODIGO", ""))
        else:
            main()
    except Exception as e:
        avisar(f"⚠️ Error en el bot de noticias: {e}")
        raise
