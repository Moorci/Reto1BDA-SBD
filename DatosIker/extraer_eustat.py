import json
from pathlib import Path

import requests

# API oficial del banco de datos de Eustat
BASE_URL = "https://www.eustat.eus/bankupx/api/v1/es/DB"

# Carpeta para conservar los datos originales
carpeta = Path("DatosIker/originales")
carpeta.mkdir(parents=True, exist_ok=True)

# Consultar el catálogo de tablas estadísticas
respuesta = requests.get(
    BASE_URL,
    headers={
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
    },
    timeout=30
)

print("Código HTTP:", respuesta.status_code)
print("URL solicitada:", respuesta.url)
print("Respuesta del servidor:", respuesta.text[:1500])

respuesta.raise_for_status()

tablas = respuesta.json()

# Guardar la respuesta original
archivo = carpeta / "eustat_catalogo.json"
archivo.write_text(
    json.dumps(tablas, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

# Buscar únicamente tablas relacionadas con nuestro proyecto
palabras_clave = (
    "renta personal",
    "alquiler",
)

relevantes = []

for tabla in tablas:
    titulo = tabla.get("text", "")

    if any(palabra in titulo.lower() for palabra in palabras_clave):
        relevantes.append({
            "id": tabla.get("id"),
            "titulo": titulo,
            "actualizado": tabla.get("updated"),
        })

# Guardar los resultados filtrados
archivo_filtrado = carpeta / "eustat_tablas_relevantes.json"

archivo_filtrado.write_text(
    json.dumps(relevantes, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

# Mostrar los resultados en pantalla
print(f"\nTablas relevantes encontradas: {len(relevantes)}")

for tabla in relevantes:
    print(f"\nID: {tabla['id']}")
    print(f"Título: {tabla['titulo']}")
    print(f"Actualización: {tabla['actualizado']}")

print(f"\nResultados guardados en: {archivo_filtrado}")