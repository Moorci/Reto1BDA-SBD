import requests
import json
import re
import csv
import time
import shutil
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[2]

CARPETA_HTML = BASE / "originales" / "fotocasa" / "masiva"
INFORME = BASE / "informes" / "fotocasa" / "localizacion_masiva_fotocasa.csv"

CARPETA_HTML.mkdir(parents=True, exist_ok=True)

municipios = [
    {
        "codigo": "01017",
        "nombre": "Campezo/Kanpezu",
        "slug": "campezo-kampezu",
        "url": "https://www.fotocasa.es/es/indice-precio-vivienda/alquiler/campezo-kampezu/todas-las-zonas"
    },
    {
        "codigo": "20065",
        "nombre": "Soraluze-Placencia de las Armas",
        "slug": "soraluze-plasencia-de-las-armas",
        "url": "https://www.fotocasa.es/es/indice-precio-vivienda/alquiler/soraluze-plasencia-de-las-armas/todas-las-zonas"
    }
]

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    )
}


def buscar_municipio(objeto):
    if isinstance(objeto, dict):
        evolucion = objeto.get("priceEvolution")

        if isinstance(evolucion, dict):
            if "rent" in evolucion and "sale" in evolucion:
                return objeto

        for valor in objeto.values():
            resultado = buscar_municipio(valor)
            if resultado:
                return resultado

    elif isinstance(objeto, list):
        for elemento in objeto:
            resultado = buscar_municipio(elemento)
            if resultado:
                return resultado

    return None


def extraer_datos(html):
    patron = (
        r'<script[^>]*id="__initial_props__"[^>]*>'
        r'(.*?)</script>'
    )

    coincidencia = re.search(patron, html, re.DOTALL)

    if not coincidencia:
        raise ValueError("No se encuentra __initial_props__")

    datos = json.loads(coincidencia.group(1))
    municipio = buscar_municipio(datos)

    if not municipio:
        raise ValueError("No se encuentra priceEvolution")

    evolucion = municipio["priceEvolution"]

    return {
        "id": str(municipio.get("id", "")),
        "nombre": (
            municipio.get("name")
            or municipio.get("municipalityName")
            or ""
        ),
        "alquiler": evolucion["rent"],
        "venta": evolucion["sale"]
    }


def main():
    with INFORME.open("r", encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f, delimiter=";")
        columnas = lector.fieldnames
        filas = list(lector)

    if not columnas:
        raise ValueError("El informe no tiene encabezados.")

    # Backup del informe antes de modificarlo.
    marca_tiempo = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = INFORME.with_name(
        f"localizacion_masiva_fotocasa_backup_{marca_tiempo}.csv"
    )
    shutil.copy2(INFORME, backup)

    for municipio in municipios:
        codigo = municipio["codigo"]

        indices = [
            i for i, fila in enumerate(filas)
            if fila["municipio_codigo"] == codigo
        ]

        if len(indices) != 1:
            print(
                f"{codigo}: se esperaban una fila y se encontraron "
                f"{len(indices)}. No se modifica."
            )
            continue

        print(f"\nConsultando {municipio['nombre']}...")

        try:
            respuesta = requests.get(
                municipio["url"],
                headers=headers,
                timeout=30
            )

            print("HTTP:", respuesta.status_code)

            if respuesta.status_code != 200:
                print("No se modifica: respuesta HTTP incorrecta.")
                continue

            ruta_html = (
                CARPETA_HTML /
                f"{codigo}_{municipio['slug']}.html"
            )

            respuesta.encoding = respuesta.apparent_encoding
            html = respuesta.text

            datos = extraer_datos(html)

            alquiler = len(datos["alquiler"])
            venta = len(datos["venta"])

            valido = (
                bool(datos["id"])
                and alquiler == 82
                and venta == 82
            )

            print("ID Fotocasa:", datos["id"])
            print("Nombre Fotocasa:", datos["nombre"])
            print("Registros alquiler:", alquiler)
            print("Registros venta:", venta)

            if not valido:
                print("No se modifica: datos incompletos o no válidos.")
                continue

            # Comprobar que el ID no esté asignado a otro municipio.
            otros_ids = {
                fila["fotocasa_id"]
                for i, fila in enumerate(filas)
                if i != indices[0]
                and fila.get("estado") == "candidato_valido"
                and fila.get("fotocasa_id")
            }

            if datos["id"] in otros_ids:
                print("No se modifica: ID Fotocasa duplicado.")
                continue

            # Guardar HTML únicamente después de validar.
            ruta_html.write_text(html, encoding="utf-8")

            fila = filas[indices[0]]

            fila.update({
                "slug_probado": municipio["slug"],
                "url": municipio["url"],
                "http_status": "200",
                "fotocasa_id": datos["id"],
                "nombre_fotocasa": datos["nombre"],
                "registros_alquiler": alquiler,
                "registros_venta": venta,
                "estado": "candidato_valido",
                "observaciones": "URL alternativa comprobada"
            })

            print("Municipio actualizado correctamente.")

        except Exception as error:
            print("ERROR:", error)

        time.sleep(5)

    # Escribir el informe actualizado.
    with INFORME.open("w", encoding="utf-8-sig", newline="") as f:
        escritor = csv.DictWriter(
            f,
            fieldnames=columnas,
            delimiter=";",
            extrasaction="ignore"
        )
        escritor.writeheader()
        escritor.writerows(filas)

    print("\nInforme actualizado.")
    print("Backup:", backup)


if __name__ == "__main__":
    main()