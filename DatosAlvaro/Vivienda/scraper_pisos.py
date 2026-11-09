"""
Scraper de pisos.com -> CSV (venta y alquiler en Euskadi)

Uso:
    pip install requests beautifulsoup4
    python scraper_pisos.py                 # todo Euskadi, venta + alquiler
    python scraper_pisos.py --paginas 5     # limitar a 5 paginas por provincia/operacion
    python scraper_pisos.py --debug         # guarda el HTML de la 1a pagina para revisar selectores

IMPORTANTE: antes de ejecutarlo, abre en el navegador las URLs de BASE_URL
para comprobar que existen (los "slugs" de provincia pueden variar).
"""

import argparse
import csv
import random
import re
import time
from datetime import date

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.pisos.com"

# operacion -> {provincia: ruta}
RUTAS = {
    "venta": {
        "Araba": "/venta/pisos-alava_araba/",
        "Gipuzkoa": "/venta/pisos-guipuzcoa/",
        "Bizkaia": "/venta/pisos-vizcaya_bizkaia/",
    },
    "alquiler": {
        "Araba": "/alquiler/pisos-alava_araba/",
        "Gipuzkoa": "/alquiler/pisos-guipuzcoa/",
        "Bizkaia": "/alquiler/pisos-vizcaya_bizkaia/",
    },
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}

CAMPOS = [
    "fecha_extraccion", "operacion", "provincia", "titulo", "localidad_zona",
    "precio_eur", "habitaciones", "banos", "metros_m2", "precio_m2", "url",
]


def solo_numero(texto):
    """'1.250 €/mes' -> 1250 ; '85,5 m²' -> 85.5"""
    if not texto:
        return None
    m = re.search(r"\d[\d\.]*(?:,\d+)?", texto)
    if not m:
        return None
    limpio = m.group(0).replace(".", "").replace(",", ".")
    try:
        valor = float(limpio)
        return int(valor) if valor.is_integer() else valor
    except ValueError:
        return None


def parsear_anuncio(card, operacion, provincia):
    titulo_el = card.select_one("a.ad-preview__title")
    precio_el = card.select_one("span.ad-preview__price")
    zona_el = card.select_one("p.ad-preview__subtitle")

    habs = banos = metros = None
    for c in card.select("p.ad-preview__char"):
        t = c.get_text(" ", strip=True).lower()
        if "hab" in t:
            habs = solo_numero(t)
        elif "baño" in t:
            banos = solo_numero(t)
        elif "m" in t and "²" in t or "m2" in t:
            metros = solo_numero(t)

    precio = solo_numero(precio_el.get_text(strip=True)) if precio_el else None
    href = card.get("data-lnk-href") or (titulo_el.get("href") if titulo_el else None)
    url = BASE_URL + href if href and href.startswith("/") else href

    precio_m2 = round(precio / metros, 2) if precio and metros else None

    return {
        "fecha_extraccion": date.today().isoformat(),
        "operacion": operacion,
        "provincia": provincia,
        "titulo": titulo_el.get_text(" ", strip=True) if titulo_el else None,
        "localidad_zona": zona_el.get_text(" ", strip=True) if zona_el else None,
        "precio_eur": precio,
        "habitaciones": habs,
        "banos": banos,
        "metros_m2": metros,
        "precio_m2": precio_m2,
        "url": url,
    }


def scrapear(operacion, provincia, ruta, max_paginas, sesion, debug=False):
    resultados = []
    vistos = set()

    for pagina in range(1, max_paginas + 1):
        url = BASE_URL + ruta + (f"{pagina}/" if pagina > 1 else "")
        try:
            r = sesion.get(url, headers=HEADERS, timeout=20)
        except requests.RequestException as e:
            print(f"  [!] Error de red en {url}: {e}")
            break

        if r.status_code != 200:
            print(f"  [!] {r.status_code} en {url} (posible bloqueo o URL incorrecta)")
            break

        if debug and pagina == 1:
            nombre = f"debug_{operacion}_{provincia}.html"
            with open(nombre, "w", encoding="utf-8") as f:
                f.write(r.text)
            print(f"  [debug] HTML guardado en {nombre}")

        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select("div.ad-preview")
        if not cards:
            print(f"  Sin anuncios en pagina {pagina}; fin.")
            break

        nuevos = 0
        for card in cards:
            anuncio = parsear_anuncio(card, operacion, provincia)
            clave = anuncio["url"] or (anuncio["titulo"], anuncio["precio_eur"])
            if clave in vistos:
                continue
            vistos.add(clave)
            resultados.append(anuncio)
            nuevos += 1

        print(f"  {operacion}/{provincia} pag {pagina}: {nuevos} anuncios nuevos")
        if nuevos == 0:  # pisos.com repite la ultima pagina si te pasas
            break

        time.sleep(random.uniform(2, 4))  # ser amable con el servidor

    return resultados


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paginas", type=int, default=10, help="max paginas por provincia/operacion")
    ap.add_argument("--salida", default="pisos_euskadi.csv")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    todos = []
    with requests.Session() as sesion:
        for operacion, provincias in RUTAS.items():
            for provincia, ruta in provincias.items():
                print(f"-> {operacion} en {provincia}")
                todos += scrapear(operacion, provincia, ruta, args.paginas, sesion, args.debug)

    with open(args.salida, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        w.writeheader()
        w.writerows(todos)

    print(f"\nListo: {len(todos)} anuncios guardados en {args.salida}")


if __name__ == "__main__":
    main()