
import json
from pathlib import Path
from collections import Counter

ARCHIVOS = [
    Path("procesados/emal_alquiler_anual_municipios.json"),
    Path("procesados/emal_alquiler_vigente_municipios.json"),
]

for ruta in ARCHIVOS:
    print(f"\n{'=' * 60}")
    print(f"Archivo: {ruta}")

    with ruta.open("r", encoding="utf-8") as archivo:
        datos = json.load(archivo)

    print(f"Registros: {len(datos)}")

    # Comprobar campos obligatorios
    campos = (
        {"municipio_codigo", "municipio", "anio",
         "renta_mensual_media_eur", "fuente"}
        if "anual" in ruta.name
        else {"municipio_codigo", "municipio", "fecha_referencia",
              "renta_mensual_media_eur", "fuente"}
    )

    errores = [
        i for i, registro in enumerate(datos)
        if not campos.issubset(registro.keys())
    ]

    print(f"Registros sin campos obligatorios: {len(errores)}")

    if "vigente" in ruta.name:
        print("Registros por fecha:", dict(Counter(
            r["fecha_referencia"] for r in datos
        )))

    # Comprobar duplicados según la clave lógica
    clave = (
        ("municipio_codigo", "anio")
        if "anual" in ruta.name
        else ("municipio_codigo", "fecha_referencia")
    )

    claves = [tuple(r[c] for c in clave) for r in datos]
    duplicados = len(claves) - len(set(claves))

    print(f"Claves duplicadas: {duplicados}")

    if datos:
        print("Primer registro:", json.dumps(
            datos[0], ensure_ascii=False
        ))

print("\nValidación terminada.")