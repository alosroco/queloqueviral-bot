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
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests
from PIL import Image, ImageDraw, ImageFont

# ======================== CONFIGURACION ========================
NOMBRE_CUENTA = "@queloqueviral"            # Cambialo por tu usuario de Instagram
HORAS_ATRAS = 8                           # Solo noticias de las ultimas X horas
ESPERA_APROBACION_MIN = 25                # Si no respondes en este tiempo, se descarta
MODELO_IA = "claude-sonnet-5-5"
VOZ = "es-US-AlonsoNeural"               # Voz neutra. Femenina: "es-US-PalomaNeural"
VELOCIDAD_VOZ = "+15%"
VOLUMEN_MUSICA = 0.10                     # 0.10 = bajito, debajo de la voz
CARPETA_MUSICA = "musica"                 # Pone ahi archivos .mp3 libres de derechos
HASHTAGS_FIJOS = ["#QLQ", "#QueloQueViral", "#noticias", "#viral", "#noticiasdehoy"]

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
PAISES_YOUTUBE = ["US", "GB", "MX", "ES", "AR", "CO"]
TENDENCIAS_RSS = {p: f"https://trends.google.com/trending/rss?geo={p}" for p in ["US", "GB", "MX", "ES", "AR"]}
# ==============================================================

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
IG_TOKEN = os.environ.get("IG_TOKEN", "")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
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
def preguntar_ia(texto, max_tokens=2000):
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=120, headers={
        "x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
        "content-type": "application/json"},
        json={"model": MODELO_IA, "max_tokens": max_tokens,
              "messages": [{"role": "user", "content": texto}]})
    r.raise_for_status()
    t = "".join(b.get("text", "") for b in r.json()["content"])
    t = t.replace("```json", "").replace("```", "").strip()
    return json.loads(t[t.find("{"):t.rfind("}") + 1])


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
- En politica, solo si es un hecho de alcance internacional; tono neutral.
- NO repitas estos temas ya publicados: {ya_publicadas or 'ninguno'}

Responde SOLO con JSON valido: {{"temas": [{{"tema": "descripcion corta", "ids": [numeros de TODOS los titulares de ese tema]}}]}}

TENDENCIAS EN GOOGLE (pais entre parentesis): {", ".join(tendencias) or "no disponibles"}

TITULARES (* = nota completa disponible, ▶ = video en tendencia de YouTube):
{lista}""")["temas"]


def escribir_guion(tema, notas):
    material = "\n\n".join(f"--- {fuente} ---\n{texto}" for fuente, texto in notas)
    return preguntar_ia(f"""Eres guionista de "QueloQue Viral", cuenta de Instagram de noticias para todo el publico hispanohablante.
Escribe el guion de UN Reel de 30 a 40 segundos sobre este tema: {tema}

REGLAS ESTRICTAS:
- Usa SOLO hechos que esten en las notas de abajo. Si un dato no esta, NO lo pongas. No inventes cifras,
  nombres, fechas ni declaraciones.
- Si las notas se contradicen, menciona solo lo que coincide.
- Escribe TODO con tus propias palabras, en espanol neutro (usa "tu"). No copies frases de las notas
  y no uses citas textuales. Si las notas estan en ingles, traduce los hechos con cuidado.
- Tono: claro, atrapante, sin exagerar ni dramatizar.

ESTRUCTURA:
- gancho: la frase que atrapa en los primeros 2 segundos (en pantalla, maximo 60 caracteres).
- 3 placas de desarrollo: 1) que paso, 2) el contexto o dato mas llamativo, 3) por que importa o que sigue.
  Para cada placa: "titulo" (2 a 4 palabras, ej: "Que paso", "El dato clave", "Que sigue"),
  "pantalla" (texto para leer, maximo 120 caracteres) y "voz" (lo que dice la voz en off,
  1 o 2 oraciones cortas, MAXIMO 20 palabras).
- El Reel completo debe durar unos 30 segundos: se breve y directo.
- pregunta: una pregunta corta para invitar a comentar (maximo 60 caracteres), ej: "¿Tu que harias?", "¿Lo sabias?".
- Para el gancho y cada placa, "video": 1 a 3 palabras EN INGLES para buscar un video de stock que
  ilustre esa parte (ej: "dog walking road", "football stadium crowd", "smartphone hands").
  * Escenas genericas y CONCRETAS (objetos, lugares, acciones). Nada de personas famosas ni marcas.
  * NUNCA pidas banderas, mapas, textos, numeros, anos, elecciones ni simbolos politicos.
  * Si la noticia ocurre en un lugar, usa una escena de ESE lugar (ej: "madrid street", "tokyo night"),
    nunca de otro pais.
- Si alguna informacion viene de un video de YouTube, nombra al canal como fuente en "pantalla" o "voz".

Responde SOLO con JSON valido:
{{"categoria": "UNA PALABRA EN MAYUSCULAS",
"gancho": "...", "voz_gancho": "version hablada del gancho, maximo 12 palabras", "video_gancho": "...",
"placas": [{{"titulo": "...", "pantalla": "...", "voz": "...", "video": "..."}}, (3 placas en total)],
"pregunta": "...",
"tono": "alegre" si es curiosidad, entretenimiento, tecnologia o deporte; "seria" si es una noticia importante, triste o delicada,
"descripcion": "texto para la publicacion de Instagram: 3 parrafos cortos que cuentan la noticia",
"hashtags": ["#hasta", "#seis", "#hashtags"]}}

NOTAS DE LOS MEDIOS:
{material}""", 2500)


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


def texto_con_sombra(d, texto, font, color, y, interlineado=1.3):
    for linea in partir(texto, font, ANCHO - 2 * MARGEN):
        d.text((MARGEN, y), linea, font=font, fill=color, stroke_width=3, stroke_fill=(0, 0, 0, 230))
        y += int(font.size * interlineado)
    return y


def titulo_en_recuadro(d, texto, font, y_base):
    """Dibuja el titulo dentro del recuadro oscuro. y_base = donde termina el recuadro."""
    lineas = partir(texto, font, ANCHO - 2 * MARGEN)
    alto = len(lineas) * int(font.size * 1.18)
    y0 = y_base - alto - 40
    d.rounded_rectangle([MARGEN - 36, y0 - 60, ANCHO - MARGEN + 36, y_base + 10], radius=34, fill=(10, 12, 20, 210))
    d.rectangle([MARGEN, y0 - 28, MARGEN + 110, y0 - 20], fill=ACENTO)
    for linea in lineas:
        d.text((MARGEN, y0), linea, font=font, fill=TEXTO)
        y0 += int(font.size * 1.18)


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


def capa_gancho(g, ruta):
    img, d = capa_nueva()
    etiqueta(d, g["categoria"], ARRIBA)
    titulo_en_recuadro(d, g["gancho"], fuente(True, 84), 1180)
    texto_con_sombra(d, "Te lo contamos en 30 segundos", fuente(False, 42), TEXTO, 1250)
    insignia(d, ANCHO - MARGEN - 50, ARRIBA + 29, 50)
    firma(d)
    img.save(ruta)


def capa_desarrollo(p, numero, total, categoria, ruta):
    img, d = capa_nueva()
    etiqueta(d, categoria, ARRIBA)
    puntos(d, numero, total)
    titulo_en_recuadro(d, p.get("titulo") or "", fuente(True, 66), 1000)
    texto_con_sombra(d, p["pantalla"], fuente(True, 50), TEXTO, 1080)
    firma(d)
    img.save(ruta)


def capa_cierre(medios, creadores, autores_video, ruta, pregunta=""):
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
    img.save(ruta)


# Palabras que delatan un video que puede confundir (banderas, fechas, politica, textos)
PROHIBIDAS_VIDEO = {"flag", "flags", "usa", "america", "american", "united states", "election", "elections",
                    "vote", "voting", "politics", "president", "trump", "biden", "text", "typography",
                    "logo", "brand", "map", "countdown", "calendar", "independence", "patriotic",
                    "4th of july", "july 4", "us flag"}


def video_apto(etiquetas, busqueda):
    """Descarta videos con banderas, anos, mapas o politica, salvo que se hayan pedido."""
    etiquetas = (etiquetas or "").lower()
    pedido = busqueda.lower()
    if re.search(r"\b(19|20)\d{2}\b", etiquetas) and not re.search(r"\b(19|20)\d{2}\b", pedido):
        return False
    return not any(p in etiquetas and p not in pedido for p in PROHIBIDAS_VIDEO)


def _bajar_video(url, carpeta, usados, clave):
    ruta = os.path.join(carpeta, f"fondo{len(usados)}.mp4")
    with open(ruta, "wb") as f:
        f.write(requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"}).content)
    usados.add(clave)
    return ruta


def buscar_video(busqueda, carpeta, usados):
    """Busca un video libre de derechos (Pixabay o Pexels).
    Devuelve (archivo, credito) o (None, None)."""
    if not busqueda:
        return None, None
    if PIXABAY_API_KEY:
        try:
            r = requests.get("https://pixabay.com/api/videos/", timeout=20, params={
                "key": PIXABAY_API_KEY, "q": busqueda[:100], "safesearch": "true",
                "per_page": 20, "video_type": "film"}).json()
            for v in r.get("hits", []):
                clave = f"pb{v['id']}"
                if clave in usados or v.get("duration", 0) < 4 or not video_apto(v.get("tags"), busqueda):
                    continue
                opciones = [o for o in (v.get("videos") or {}).values()
                            if o.get("url") and 720 <= (o.get("height") or 0) <= 2200]
                if not opciones:
                    continue
                elegido = max(opciones, key=lambda o: o["height"])
                return _bajar_video(elegido["url"], carpeta, usados, clave), f"Pixabay ({v.get('user', '')})"
        except Exception as e:
            print(f"Pixabay no respondio para '{busqueda}': {e}")
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
                return (_bajar_video(elegido["link"], carpeta, usados, clave),
                        f"Pexels ({v.get('user', {}).get('name', '')})")
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


def generar_voces(textos, carpeta):
    """Devuelve la lista de archivos de voz, o None si el servicio de voz no responde."""
    try:
        import edge_tts

        async def todas():
            rutas = []
            for i, t in enumerate(textos):
                ruta = os.path.join(carpeta, f"voz{i}.mp3")
                await edge_tts.Communicate(t, VOZ, rate=VELOCIDAD_VOZ).save(ruta)
                rutas.append(ruta)
            return rutas
        return asyncio.run(todas())
    except Exception as e:
        print(f"Sin voz en off ({e}). Sigo sin voz.")
        return None


def elegir_musica(tono):
    """Busca en musica/<tono>/ y, si no hay, en musica/. Devuelve la lista de temas posibles."""
    def temas_en(carpeta):
        if not os.path.isdir(carpeta):
            return []
        return [os.path.join(carpeta, m) for m in os.listdir(carpeta)
                if m.lower().endswith((".mp3", ".wav", ".m4a"))]
    return temas_en(os.path.join(CARPETA_MUSICA, tono or "")) or temas_en(CARPETA_MUSICA)


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
        if seg.get("fondo"):
            entrada = ["-stream_loop", "-1", "-i", seg["fondo"]]
            base = (f"[0:v]scale={ANCHO}:{ALTO}:force_original_aspect_ratio=increase,crop={ANCHO}:{ALTO},"
                    f"fps={fps},setsar=1,eq=brightness=-0.10:saturation=0.95[f]")
        else:
            entrada = ["-f", "lavfi", "-i", f"color=c=0x{FONDO[0]:02x}{FONDO[1]:02x}{FONDO[2]:02x}:s={ANCHO}x{ALTO}:r={fps}"]
            base = "[0:v]setsar=1[f]"
        filtro = (f"{base};[f][1:v]overlay=0:0,fade=t=in:st=0:d=0.25,"
                  f"fade=t=out:st={dur - 0.25:.2f}:d=0.25,format=yuv420p")
        correr(["ffmpeg", "-y", *entrada, "-i", seg["capa"], "-filter_complex", filtro, "-t", f"{dur:.3f}",
                "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-r", str(fps), clip])
        clips.append(clip)
    # La portada (para la historia) es un cuadro del gancho
    correr(["ffmpeg", "-y", "-ss", "1", "-i", clips[0], "-frames:v", "1", "-q:v", "2", portada_salida])

    lista = os.path.join(tmp, "lista.txt")
    with open(lista, "w") as f:
        f.writelines(f"file '{c}'\n" for c in clips)
    video = os.path.join(tmp, "video.mp4")
    correr(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lista, "-c", "copy", video])
    total = sum(duraciones)

    partes = []
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
                f"[0:a][m]amix=inputs=2:duration=first:normalize=0[a]",
                "-map", "[a]", "-t", f"{total:.3f}", "-ar", "48000", audio])

    correr(["ffmpeg", "-y", "-i", video, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-shortest", "-movflags", "+faststart", salida])
    shutil.rmtree(tmp, ignore_errors=True)
    return total, bool(voces), bool(temas)


def texto_publicacion(g, medios, creadores, bancos):
    etiquetas = list(dict.fromkeys(HASHTAGS_FIJOS + [h if h.startswith("#") else "#" + h
                                                      for h in g.get("hashtags", [])]))[:12]
    lineas = [f"🔥 {g['gancho']}", "", g["descripcion"], ""]
    if g.get("pregunta"):
        lineas += [f"💬 {g['pregunta']} Cuéntanos en los comentarios 👇", ""]
    lineas += [
              f"📌 Fuentes: {', '.join(medios) or 'ver video citado'}"]
    if creadores:
        lineas.append(f"🎥 Video viral: {', '.join(creadores)}")
    if bancos:
        lineas.append(f"🎞 Imágenes: {', '.join(bancos)}")
    lineas += ["Resumen elaborado a partir de lo publicado por los medios citados.", "",
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


def esperar_respuesta(id_corrida):
    r = tg("getUpdates", data={"offset": -1, "timeout": 0})
    offset = (r.get("result") or [{"update_id": 0}])[-1]["update_id"]
    fin = time.time() + ESPERA_APROBACION_MIN * 60
    while time.time() < fin:
        r = tg("getUpdates", data={"offset": offset + 1, "timeout": 30,
                                   "allowed_updates": json.dumps(["callback_query"])})
        for u in r.get("result", []):
            offset = u["update_id"]
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
def ig(metodo, ruta, **datos):
    datos["access_token"] = IG_TOKEN
    url = f"{IG_API}/{ruta}"
    r = requests.post(url, data=datos, timeout=60) if metodo == "POST" else requests.get(url, params=datos, timeout=60)
    js = r.json()
    if "error" in js:
        raise RuntimeError(f"Instagram: {js['error'].get('message')}")
    return js


def guardar_historial(historial_nuevo):
    os.makedirs(CARPETA, exist_ok=True)
    with open(HISTORIAL, "w", encoding="utf-8") as f:
        json.dump(historial_nuevo, f, ensure_ascii=False, indent=1)
    for c in (["git", "config", "user.name", "bot-noticias"],
              ["git", "config", "user.email", "bot@users.noreply.github.com"],
              ["git", "add", HISTORIAL], ["git", "commit", "-m", "Historial"], ["git", "push"]):
        subprocess.run(c, check=False)


def preparar_sitio(archivos, caption, titulos):
    """Deja los archivos en la carpeta 'sitio' para que GitHub Pages los publique
    (lo hace el paso siguiente del workflow) y guarda lo pendiente de publicar."""
    os.makedirs("sitio", exist_ok=True)
    for a in archivos:
        shutil.copy(a, "sitio")
    with open("pendiente.json", "w", encoding="utf-8") as f:
        json.dump({"archivos": [os.path.basename(a) for a in archivos], "caption": caption,
                   "titulos": titulos}, f, ensure_ascii=False)


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
              caption=caption, share_to_feed="true")["id"]
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


def renovar_token():
    """Extiende la vida del token (dura 60 dias). Si cambia, te avisa para actualizarlo."""
    try:
        r = requests.get("https://graph.instagram.com/refresh_access_token",
                         params={"grant_type": "ig_refresh_token", "access_token": IG_TOKEN}, timeout=30).json()
        nuevo, dias = r.get("access_token"), r.get("expires_in", 0) // 86400
        if nuevo and nuevo != IG_TOKEN:
            avisar("🔑 Instagram genero un token nuevo. Copialo y reemplaza el secreto IG_TOKEN en GitHub "
                   "(Settings > Secrets > Actions):\n\n" + nuevo)
        elif dias:
            print(f"Token de Instagram renovado: vence en {dias} dias.")
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

    id_corrida = datetime.now(ARGENTINA).strftime("%Y%m%d-%H%M")
    historial = []
    if os.path.exists(HISTORIAL):
        with open(HISTORIAL, encoding="utf-8") as f:
            historial = json.load(f)

    noticias, tendencias, fallidas = juntar_noticias()
    print(f"{len(noticias)} noticias leidas. Fuentes con problemas: {fallidas or 'ninguna'}")
    if len(noticias) < 15:
        avisar(f"⚠️ Solo consegui {len(noticias)} noticias (fallaron: {', '.join(fallidas)}). No armo el Reel.")
        return

    # Elige el tema y lee las notas completas (si el primero no se puede leer, prueba el siguiente)
    guion = None
    for tema in elegir_temas(noticias, tendencias, "; ".join(historial[-20:])):
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
            guion = escribir_guion(tema["tema"], notas)
            break
        print(f"Poca informacion sobre '{tema['tema']}', pruebo el siguiente.")
    if not guion:
        avisar("⚠️ No consegui informacion suficiente para armar un Reel confiable. Salteo esta vuelta.")
        return

    carpeta = tempfile.mkdtemp()
    medios = [f for f in fuentes if not f.startswith("YouTube:")][:3]
    creadores = [f.replace("YouTube: ", "") + " (YouTube)" for f in fuentes if f.startswith("YouTube:")][:2]

    usados, autores = set(), []
    def fondo(busqueda):
        ruta, autor = buscar_video(busqueda, carpeta, usados)
        if autor and autor not in autores:
            autores.append(autor)
        return ruta

    segmentos = [{"fondo": fondo(guion.get("video_gancho")), "capa": os.path.join(carpeta, "c0.png")}]
    capa_gancho(guion, segmentos[0]["capa"])
    for i, p in enumerate(guion["placas"][:3]):
        seg = {"fondo": fondo(p.get("video")), "capa": os.path.join(carpeta, f"c{i + 1}.png")}
        capa_desarrollo(p, i, 3, guion["categoria"], seg["capa"])
        segmentos.append(seg)
    cierre = {"fondo": segmentos[0]["fondo"], "capa": os.path.join(carpeta, "cierre.png")}
    capa_cierre(medios or ["ver video citado"], creadores, autores, cierre["capa"], guion.get("pregunta", ""))
    segmentos.append(cierre)

    textos_voz = [guion.get("voz_gancho") or guion["gancho"]] + [p["voz"] for p in guion["placas"][:3]]
    pregunta = (guion.get("pregunta") or "").strip()
    textos_voz.append((pregunta + " " if pregunta else "") + "Síguenos en QueloQue Viral.")
    reel = os.path.join(carpeta, f"reel-{id_corrida}.mp4")
    portada = os.path.join(carpeta, f"portada-{id_corrida}.jpg")
    total, con_voz, con_musica = armar_reel(segmentos, textos_voz, reel, portada,
                                            (guion.get("tono") or "").strip().lower())
    bancos = sorted({a.split(' (')[0] for a in autores})
    caption = texto_publicacion(guion, medios, creadores, bancos)
    sin_fondo = sum(1 for sg in segmentos[:-1] if not sg["fondo"])

    nota = []
    if not con_voz:
        nota.append("sin voz en off (el servicio de voz no respondio)")
    if not con_musica:
        nota.append("sin musica (no hay archivos en la carpeta 'musica')")
    if sin_fondo:
        nota.append(f"{sin_fondo} partes sin video de fondo (no se encontro video o falta la clave de Pixabay)")
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
    preparar_sitio([reel, portada], caption, [guion["gancho"]])
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
    guardar_historial((historial + p["titulos"])[-40:])
    avisar(f"✅ Reel publicado en @{usuario}\n{link}" +
           ("\n📲 Historia publicada" if historia_ok else "\n⚠️ La historia no se pudo publicar"))

if __name__ == "__main__":
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "publicar":
            publicar()
        else:
            main()
    except Exception as e:
        avisar(f"⚠️ Error en el bot de noticias: {e}")
        raise
