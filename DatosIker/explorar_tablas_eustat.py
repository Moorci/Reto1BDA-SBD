import json
from pathlib import Path

import requests

BASE_URL = "https://www.eustat.eus/bankupx/api/v1/es/DB"

TABLAS = {
    "renta_por_edad": "PX_173402_crpf_rpf_rp03.px",
    "renta_por_municipio": "PX_173402_crpf_rpf_rp11s.px",
    "indicadores_municipales": "PX_173402_crpf_rpf_rp36.px",
    "percentiles_renta_municipales": "PX_173402_crpf_rpf_rp30.px",
    "distribucion_renta_municipal": "PX_173402_crpf_rpf_rp31.px",
    "distribucion_renta_por_edad": "PX_173402_crpf_rpf_rp33.px",
}

carpeta = Path("originales")
carpeta.mkdir(parents=True, exist_ok=True)

for nombre, identificador in TABLAS.items():
    url = f"{BASE_URL}/{identificador}"

    respuesta = requests.get(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0"
        },
        timeout=30
    )
    if not respuesta.ok:
        print(f"\nERROR al consultar: {nombre}")
        print(f"URL: {url}")
        print(f"Código HTTP: {respuesta.status_code}")
        print(f"Respuesta de Eustat: {respuesta.text[:2000]}")
        continue

    metadatos = respuesta.json()

    # Guardar los metadatos originales
    archivo = carpeta / f"metadatos_{nombre}.json"

    archivo.write_text(
        json.dumps(metadatos, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"\n{'=' * 60}")
    print(metadatos.get("title", identificador))
    print(f"Metadatos guardados en: {archivo}")

    # Mostrar las variables y algunas de sus categorías
    for variable in metadatos.get("variables", []):
        codigo = variable.get("code")
        titulo = variable.get("text", codigo)

        print(f"\nVariable: {titulo}")
        print(f"Código: {codigo}")

        codigos = variable.get("values", [])
        etiquetas = variable.get("valueTexts", [])

        for valor, etiqueta in list(zip(codigos, etiquetas))[:8]:
            print(f"  {valor}: {etiqueta}")

        if len(etiquetas) > 8:
            print(f"  ... Total de categorías: {len(etiquetas)}")

print("\nExploración finalizada.")