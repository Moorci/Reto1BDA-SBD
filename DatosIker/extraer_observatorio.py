
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# Página oficial con las tablas estadísticas EMAL
URL = (
    "https://observatoriovivienda.euskadi.eus/"
    "estadistica/tablas-estadisticas-de-la-estadistica-del-"
    "mercado-de-alquiler-emal-2016-2020-hasta-el-2-trimestre-"
    "de-2020/webovv00-content/es/"
)

CARPETA = Path("originales")
CARPETA.mkdir(parents=True, exist_ok=True)

CABECERAS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml",
}

# 1. Descargar la página web para analizar sus enlaces
respuesta = requests.get(URL, headers=CABECERAS, timeout=30)
respuesta.raise_for_status()

# Guardar el HTML original como evidencia de la extracción
(CARPETA / "observatorio_emal_pagina.html").write_bytes(
    respuesta.content
)

soup = BeautifulSoup(respuesta.text, "html.parser")

# 2. Localizar el Excel de viviendas habituales y municipios
enlace_excel = None

for enlace in soup.find_all("a", href=True):
    texto = enlace.get_text(" ", strip=True).lower()
    href = enlace["href"]
    ruta = urlparse(href).path.lower()

    if (
        ruta.endswith(".xlsx")
        and "municipios" in texto
        and "viviendas habituales colectivas" in texto
    ):
        enlace_excel = urljoin(URL, href)
        print("Archivo encontrado:")
        print(texto)
        break

if enlace_excel is None:
    raise RuntimeError(
        "No se encontró el Excel de municipios. "
        "Revisa los enlaces disponibles en la página."
    )

# 3. Descargar el fichero Excel
respuesta_excel = requests.get(
    enlace_excel,
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=60,
)
respuesta_excel.raise_for_status()

# Comprobar que la respuesta parece un archivo Excel XLSX
if not respuesta_excel.content.startswith(b"PK"):
    raise RuntimeError(
        "La respuesta no parece un Excel válido. "
        f"Content-Type: {respuesta_excel.headers.get('Content-Type')}"
    )

# 4. Guardar el original con el nombre publicado
nombre = Path(urlparse(enlace_excel).path).name

if not nombre:
    nombre = "observatorio_emal_municipios.xlsx"

destino = CARPETA / nombre
destino.write_bytes(respuesta_excel.content)

print("\nDescarga completada.")
print(f"Archivo: {destino}")
print(f"Tamaño: {destino.stat().st_size:,} bytes")
