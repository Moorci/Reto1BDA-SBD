import json
import math
import re
from pathlib import Path

import pandas as pd


# --------------------------------------------------
# CONFIGURACIÓN
# --------------------------------------------------

ARCHIVO = Path(
    "originales/EMAL.-Barrios-Municipios.-2016-2026_es.xlsx"
)

CARPETA_SALIDA = Path("procesados")
CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)

ANIOS = list(range(2016, 2026))

FECHAS_VIGENTES = [
    "2025-12-31",
    "2026-03-31"
]


print("Fechas configuradas:", FECHAS_VIGENTES)

FUENTE = "Observatorio Vasco de la Vivienda - EMAL"


# --------------------------------------------------
# FUNCIONES AUXILIARES
# --------------------------------------------------

def esta_vacio(valor):
    """Detecta valores vacíos o marcados como no disponibles."""

    if valor is None:
        return True

    if isinstance(valor, str):
        return valor.strip() in {"", "-", "—", "–"}

    try:
        return bool(pd.isna(valor))
    except (TypeError, ValueError):
        return False


def normalizar_codigo(valor):
    """Conserva los códigos municipales como texto."""

    if esta_vacio(valor):
        return None

    if isinstance(valor, (int, float)):
        if not math.isfinite(float(valor)):
            return None

        if not float(valor).is_integer():
            return None

        texto = str(int(valor))
    else:
        texto = str(valor).strip()

        if texto.endswith(".0"):
            texto = texto[:-2]

    if re.fullmatch(r"\d{1,5}", texto):
        return texto.zfill(5)

    return None


def convertir_numero(valor, decimales=2):
    """Convierte números y transforma guiones o vacíos en None."""

    if esta_vacio(valor):
        return None

    try:
        if isinstance(valor, str):
            valor = valor.strip().replace(",", ".")

        numero = float(valor)

        if not math.isfinite(numero):
            return None

        if decimales == 0:
            return int(round(numero))

        return round(numero, decimales)

    except (TypeError, ValueError):
        return None


# --------------------------------------------------
# LECTURA Y NORMALIZACIÓN DE LAS HOJAS
# --------------------------------------------------

def leer_hoja(nombre_hoja, decimales):
    """
    Lee una hoja del Excel y devuelve sus datos por municipio.

    Las columnas C-L contienen los años 2016-2025.
    Las columnas M-N contienen las dos fechas de referencia.
    """

    tabla = pd.read_excel(
        ARCHIVO,
        sheet_name=nombre_hoja,
        header=None,
        dtype=object,
        engine="openpyxl"
    )

    municipios = {}

    for _, fila in tabla.iterrows():

        if len(fila) < 15:
            continue

        codigo = normalizar_codigo(fila.iloc[0])

        # Saltar títulos, encabezados y filas agregadas
        if codigo is None:
            continue

        if esta_vacio(fila.iloc[1]):
            continue

        nombre = str(fila.iloc[1]).strip()

        datos_anuales = {}

        for posicion, anio in enumerate(ANIOS):
            datos_anuales[anio] = convertir_numero(
                fila.iloc[2 + posicion],
                decimales
            )

        # Columnas M y N del Excel:
        # M = alquileres vigentes a 31/12/2025
        # N = alquileres vigentes a 31/03/2026

        datos_vigentes = {
            FECHAS_VIGENTES[0]: convertir_numero(
                fila.iloc[13],
                decimales
            ),
            FECHAS_VIGENTES[1]: convertir_numero(
                fila.iloc[14],
                decimales
            )
        }

        municipios[codigo] = {
            "municipio_codigo": codigo,
            "municipio": nombre,
            "anual": datos_anuales,
            "vigente": datos_vigentes
        }

    return municipios


def guardar_json(ruta, datos):
    """Guarda los datos en JSON UTF-8."""

    with ruta.open("w", encoding="utf-8") as archivo:
        json.dump(
            datos,
            archivo,
            ensure_ascii=False,
            indent=2,
            allow_nan=False
        )


# --------------------------------------------------
# PROCESO PRINCIPAL
# --------------------------------------------------

if not ARCHIVO.exists():
    raise FileNotFoundError(
        f"No se encuentra el Excel: {ARCHIVO.resolve()}"
    )


print("Leyendo las hojas del Observatorio...")

fianzas = leer_hoja("T2.1", 0)
rentas = leer_hoja("T2.2", 2)
precios_m2 = leer_hoja("T2.3", 4)

print("\nCOMPROBACIÓN DE AMURRIO")

print("Fianzas:", fianzas["01002"]["vigente"])
print("Rentas:", rentas["01002"]["vigente"])
print("Precio por m2:", precios_m2["01002"]["vigente"])

codigos = sorted(
    set(fianzas) | set(rentas) | set(precios_m2)
)

datos_anuales = []
datos_vigentes = []


# --------------------------------------------------
# 1. DATOS ANUALES
# --------------------------------------------------

for codigo in codigos:

    nombre = (
        rentas.get(codigo, {}).get("municipio")
        or precios_m2.get(codigo, {}).get("municipio")
        or f"Municipio {codigo}"
    )

    for anio in ANIOS:

        numero_fianzas = fianzas.get(
            codigo, {}
        ).get("anual", {}).get(anio)

        renta = rentas.get(
            codigo, {}
        ).get("anual", {}).get(anio)

        precio_m2 = precios_m2.get(
            codigo, {}
        ).get("anual", {}).get(anio)

        # No guardar registros sin ningún dato útil
        if all(
            valor is None
            for valor in (numero_fianzas, renta, precio_m2)
        ):
            continue

        datos_anuales.append({
            "municipio_codigo": codigo,
            "municipio": nombre,
            "anio": anio,
            "numero_fianzas_depositadas": numero_fianzas,
            "renta_mensual_media_eur": renta,
            "renta_mensual_media_eur_m2": precio_m2,
            "tipo_dato": "alquiler_libre_vivienda_habitual",
            "periodicidad": "anual",
            "fuente": FUENTE,
            "archivo_origen": ARCHIVO.name
        })


# --------------------------------------------------
# 2. ALQUILERES VIGENTES A FECHAS DE REFERENCIA
# --------------------------------------------------

for codigo in codigos:

    nombre = (
        rentas.get(codigo, {}).get("municipio")
        or precios_m2.get(codigo, {}).get("municipio")
        or f"Municipio {codigo}"
    )

    for fecha in FECHAS_VIGENTES:

        numero_vigentes = fianzas.get(
            codigo, {}
        ).get("vigente", {}).get(fecha)

        renta = rentas.get(
            codigo, {}
        ).get("vigente", {}).get(fecha)

        precio_m2 = precios_m2.get(
            codigo, {}
        ).get("vigente", {}).get(fecha)

        if all(
            valor is None
            for valor in (numero_vigentes, renta, precio_m2)
        ):
            continue

        datos_vigentes.append({
            "municipio_codigo": codigo,
            "municipio": nombre,
            "fecha_referencia": fecha,
            "numero_alquileres_vigentes": numero_vigentes,
            "renta_mensual_media_eur": renta,
            "renta_mensual_media_eur_m2": precio_m2,
            "tipo_dato": "alquileres_vigentes",
            "fuente": FUENTE,
            "archivo_origen": ARCHIVO.name
        })

from collections import Counter

print("\nRegistros por fecha:")
print(Counter(
    registro["fecha_referencia"]
    for registro in datos_vigentes
))

print("\nDatos de Amurrio:")
for registro in datos_vigentes:
    if registro["municipio"] == "Amurrio":
        print(json.dumps(
            registro,
            ensure_ascii=False,
            indent=2
        ))

# --------------------------------------------------
# GUARDAR LOS RESULTADOS
# --------------------------------------------------

archivo_anual = (
    CARPETA_SALIDA / "emal_alquiler_anual_municipios.json"
)

archivo_vigente = (
    CARPETA_SALIDA / "emal_alquiler_vigente_municipios.json"
)

guardar_json(archivo_anual, datos_anuales)
guardar_json(archivo_vigente, datos_vigentes)

print("\nTransformación completada.")
print(f"Municipios identificados: {len(codigos)}")
print(f"Registros anuales: {len(datos_anuales)}")
print(f"Registros de alquiler vigente: {len(datos_vigentes)}")

print(f"\nArchivo anual: {archivo_anual}")
print(f"Archivo de alquiler vigente: {archivo_vigente}")

if datos_anuales:
    print("\nEjemplo de registro anual:")
    print(json.dumps(datos_anuales[0], ensure_ascii=False, indent=2))

if datos_vigentes:
    print("\nEjemplo de registro vigente:")
    print(json.dumps(datos_vigentes[0], ensure_ascii=False, indent=2))