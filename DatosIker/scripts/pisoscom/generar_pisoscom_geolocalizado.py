from pathlib import Path
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]

ARCHIVO_PISOS = RAIZ / "../DatosAlvaro" / "Vivienda" / "pisos_euskadi.csv"
ARCHIVO_VALIDACION = (
    RAIZ / "informes" / "pisoscom" / "validacion_geografica_pisoscom.csv"
)

SALIDA = RAIZ / "procesados" / "pisoscom" / "pisos_euskadi_geolocalizado.csv"
INFORME = RAIZ / "informes" / "pisoscom" / "resumen_geolocalizacion_pisoscom.txt"

COLUMNAS_VALIDACION = [
    "fila_original",
    "municipio_extraido",
    "municipio_oficial_fotocasa",
    "municipio_codigo",
    "estado_correspondencia",
]


def detener(mensaje):
    raise SystemExit(f"\nERROR: {mensaje}")


def main():
    print("=" * 65)
    print("GENERACIÓN DEL CSV DE PISOS.COM CON CÓDIGO MUNICIPAL")
    print("=" * 65)

    for archivo in (ARCHIVO_PISOS, ARCHIVO_VALIDACION):
        if not archivo.exists():
            detener(f"No se encuentra el archivo:\n{archivo}")

    pisos = pd.read_csv(
        ARCHIVO_PISOS,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    validacion = pd.read_csv(
        ARCHIVO_VALIDACION,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )

    faltan = [c for c in COLUMNAS_VALIDACION if c not in validacion.columns]
    if faltan:
        detener("Al CSV de validación le faltan columnas: " + ", ".join(faltan))

    # En el informe de validación, fila_original es el número de línea
    # del CSV de origen, contando la cabecera como línea 1.
    # Por eso, la primera fila de datos tiene fila_original = 2.
    pisos = pisos.copy()
    pisos["fila_original"] = (pisos.index + 2).astype(str)
    validacion = validacion[COLUMNAS_VALIDACION].copy()
    validacion["fila_original"] = validacion["fila_original"].str.strip()

    if validacion["fila_original"].duplicated().any():
        duplicadas = validacion.loc[
            validacion["fila_original"].duplicated(keep=False),
            "fila_original"
        ].tolist()
        detener("Hay valores fila_original duplicados: " + ", ".join(duplicadas[:10]))

    if (validacion["fila_original"] == "").any():
        detener("Hay registros de validación sin fila_original.")

    resultado = pisos.merge(
        validacion,
        on="fila_original",
        how="left",
        validate="one_to_one",
        indicator=True,
    )

    sin_validacion = resultado[resultado["_merge"] != "both"]
    if not sin_validacion.empty:
        ejemplos = sin_validacion["fila_original"].head(10).tolist()
        detener(
            f"{len(sin_validacion)} anuncios no tienen validación. "
            f"Filas de origen de ejemplo: {', '.join(ejemplos)}"
        )

    resultado = resultado.drop(columns=["_merge"])

    estados_permitidos = {
        "coincidencia_exacta",
        "coincidencia_normalizada",
        "municipio_excluido_catalogo",
    }
    estados_desconocidos = sorted(
        set(resultado["estado_correspondencia"]) - estados_permitidos
    )
    if estados_desconocidos:
        detener("Estados no esperados: " + ", ".join(estados_desconocidos))

    asignados = resultado["estado_correspondencia"].isin({
        "coincidencia_exacta",
        "coincidencia_normalizada",
    })
    excluidos = (
        resultado["estado_correspondencia"] == "municipio_excluido_catalogo"
    )

    if (resultado.loc[asignados, "municipio_codigo"].str.strip() == "").any():
        detener("Hay anuncios validados sin código municipal.")
    if (resultado.loc[excluidos, "municipio_codigo"].str.strip() != "").any():
        detener("Un municipio excluido tiene un código asignado.")
    if (resultado.loc[~excluidos, "municipio_codigo"].str.strip() == "").any():
        detener("Hay registros sin código que no están marcados como excluidos.")

    # Mantener las columnas originales y añadir las geográficas al final.
    resultado.to_csv(SALIDA, index=False, encoding="utf-8-sig")

    conteo_estados = resultado["estado_correspondencia"].value_counts()
    codigos = resultado.loc[asignados, "municipio_codigo"].nunique()

    lineas = [
        "RESUMEN DE GEOLOCALIZACIÓN DE PISOS.COM",
        "=" * 55,
        f"Anuncios de entrada: {len(pisos)}",
        f"Registros de validación: {len(validacion)}",
        f"Anuncios en archivo final: {len(resultado)}",
        f"Anuncios con código municipal: {int(asignados.sum())}",
        f"Anuncios de municipio excluido: {int(excluidos.sum())}",
        f"Códigos municipales diferentes: {codigos}",
        "",
        "ESTADOS DE CORRESPONDENCIA",
        "-" * 55,
    ]
    for estado, cantidad in conteo_estados.items():
        lineas.append(f"{estado}: {cantidad}")

    lineas.extend([
        "",
        "COMPROBACIONES",
        "-" * 55,
        "Correspondencia por fila_original: correcta",
        "Cruce uno a uno: correcto",
        "Anuncios sin validación: 0",
        "Anuncios validados sin código: 0",
        "Municipios excluidos con código: 0",
        "",
        f"Archivo generado: {SALIDA}",
    ])

    INFORME.parent.mkdir(parents=True, exist_ok=True)
    INFORME.write_text("\n".join(lineas) + "\n", encoding="utf-8")

    print("\nRESUMEN")
    print("-" * 65)
    print(f"Anuncios de entrada: {len(pisos)}")
    print(f"Registros de validación: {len(validacion)}")
    print(f"Anuncios finales: {len(resultado)}")
    print(f"Con código municipal: {int(asignados.sum())}")
    print(f"Municipios excluidos: {int(excluidos.sum())}")
    print(f"Códigos municipales diferentes: {codigos}")
    print("\nEstados:")
    for estado, cantidad in conteo_estados.items():
        print(f"  {estado}: {cantidad}")

    print("\nCOMPROBACIONES")
    print("-" * 65)
    print("Cruce uno a uno por fila_original: correcto")
    print("Anuncios sin validación: 0")
    print("Anuncios validados sin código: 0")
    print("Municipios excluidos con código: 0")

    print("\nARCHIVOS GENERADOS")
    print(SALIDA)
    print(INFORME)
    print("\nProceso finalizado correctamente.")


if __name__ == "__main__":
    main()
