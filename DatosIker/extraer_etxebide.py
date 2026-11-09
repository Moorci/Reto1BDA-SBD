import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

url = (
    "https://www.etxebide.euskadi.eus/"
    "contenidos/ds_localizaciones/promociones_etxebide/"
    "es_vpo/index.shtml"
)

respuesta = requests.get(url, timeout=30)
respuesta.raise_for_status()

soup = BeautifulSoup(respuesta.text, "html.parser")

# Buscar enlaces a ficheros descargables
for enlace in soup.select("a[href]"):
    titulo = enlace.get_text(" ", strip=True)
    direccion = urljoin(url, enlace["href"])

    if "csv" in titulo.lower() or "xls" in titulo.lower():
        print(f"{titulo}\n{direccion}\n")