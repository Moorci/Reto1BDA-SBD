
from pathlib import Path
import pandas as pd
import unicodedata
import re
import csv
from datetime import datetime


# ============================================================
# CONFIGURACIÓN
# ============================================================

# El script está dentro de DatosIker/scripts/pisoscom/
# Subimos tres niveles para llegar a DatosIker.
RAIZ = Path(__file__).resolve().parents[2]

ARCHIVO_PISOS = (
    RAIZ / "../DatosAlvaro" / "Vivienda" / "pisos_euskadi.csv"
)

ARCHIVO_CATALOGO = (
    RAIZ / "originales" / "fotocasa"
    / "catalogo_municipios_fotocasa.csv"
)

CARPETA_INFORMES = RAIZ / "informes" / "pisoscom"

ARCHIVO_RESULTADOS = (
    CARPETA_INFORMES / "validacion_geografica_pisoscom.csv"
)

ARCHIVO_PENDIENTES = (
    CARPETA_INFORMES / "municipios_sin_correspondencia.csv"
)

ARCHIVO_INFORME = (
    CARPETA_INFORMES / "informe_validacion_geografica.txt"
)


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def normalizar(texto):
    """
    Normaliza nombres únicamente para compararlos.
    No modifica los datos originales.
    """

    if pd.isna(texto):
        return ""

    texto = str(texto).strip().lower()

    texto = unicodedata.normalize("NFD", texto)

    texto = "".join(
        caracter
        for caracter in texto
        if unicodedata.category(caracter) != "Mn"
    )

    texto = re.sub(r"[^a-z0-9]", "", texto)

    return texto


def normalizar_provincia(provincia):
    """
    Unifica las variantes de nombre de las provincias.
    """

    valor = normalizar(provincia)

    equivalencias = {
        "araba": "alava",
        "alava": "alava",
        "gipuzkoa": "gipuzkoa",
        "guipuzcoa": "gipuzkoa",
        "bizkaia": "bizkaia",
        "vizcaya": "bizkaia"
    }

    return equivalencias.get(valor, valor)


def extraer_municipio(localidad):
    """
    Si localidad_zona contiene un municipio entre paréntesis,
    extrae ese municipio.

    Ejemplo:
    Centro (Vitoria - Gasteiz)
    -> Vitoria - Gasteiz

    Si no hay paréntesis, conserva el texto completo.
    """

    if pd.isna(localidad):
        return ""

    localidad = str(localidad).strip()

    coincidencia = re.search(r"\(([^()]*)\)\s*$", localidad)

    if coincidencia:
        return coincidencia.group(1).strip()

    return localidad


def leer_csv(ruta):
    """
    Detecta automáticamente el separador del CSV.
    Lee todos los campos como texto para preservar códigos.
    """

    with open(ruta, "r", encoding="utf-8-sig", newline="") as archivo:
        muestra = archivo.read(10000)

    separador = csv.Sniffer().sniff(
        muestra,
        delimiters=",;\t|"
    ).delimiter

    return pd.read_csv(
        ruta,
        sep=separador,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig"
    )


def coincidencia_nombre(municipio, candidatos):
    """
    Busca coincidencias por nombre.
    Devuelve los registros candidatos sin asignar códigos
    cuando existen varias posibilidades.
    """

    clave = normalizar(municipio)

    if not clave:
        return []

    return [
        candidato
        for candidato in candidatos
        if clave in candidato["nombres_normalizados"]
    ]


# ============================================================
# VALIDACIÓN PRINCIPAL
# ============================================================

def main():

    print("=" * 65)
    print("VALIDACIÓN GEOGRÁFICA DE PISOS.COM")
    print("=" * 65)

    # --------------------------------------------------------
    # 1. Comprobar archivos
    # --------------------------------------------------------

    for archivo in [ARCHIVO_PISOS, ARCHIVO_CATALOGO]:

        if not archivo.exists():
            raise FileNotFoundError(
                f"No se encuentra el archivo: {archivo}"
            )

    CARPETA_INFORMES.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------------
    # 2. Leer archivos
    # --------------------------------------------------------

    pisos = leer_csv(ARCHIVO_PISOS)
    catalogo = leer_csv(ARCHIVO_CATALOGO)

    print("\n1. ARCHIVOS LEÍDOS")
    print("-" * 65)

    print(f"Anuncios Pisos.com: {len(pisos)}")
    print(f"Registros catálogo Fotocasa: {len(catalogo)}")

    print("\nColumnas Pisos.com:")
    print(list(pisos.columns))

    print("\nColumnas Fotocasa:")
    print(list(catalogo.columns))

    # --------------------------------------------------------
    # 3. Comprobar columnas necesarias
    # --------------------------------------------------------

    columnas_pisos = {
        "provincia",
        "localidad_zona"
    }

    columnas_catalogo = {
        "municipio_codigo",
        "municipio_oficial",
        "provincia",
        "nombre_fotocasa",
        "estado"
    }

    faltan_pisos = columnas_pisos - set(pisos.columns)
    faltan_catalogo = columnas_catalogo - set(catalogo.columns)

    if faltan_pisos or faltan_catalogo:
        raise ValueError(
            f"Faltan columnas. Pisos.com: {faltan_pisos}. "
            f"Catálogo: {faltan_catalogo}"
        )

    # --------------------------------------------------------
    # 4. Preparar catálogo de municipios
    # --------------------------------------------------------

    catalogo["provincia_normalizada"] = (
        catalogo["provincia"].apply(normalizar_provincia)
    )

    catalogo["codigo_original"] = (
        catalogo["municipio_codigo"].astype(str)
    )

    candidatos = []

    for _, fila in catalogo.iterrows():

        # Solo utilizamos municipios validados.
        if normalizar(fila["estado"]) != "validado":
            continue

        nombres = {
            normalizar(fila["municipio_oficial"]),
            normalizar(fila["nombre_fotocasa"])
        }

        nombres.discard("")

        candidatos.append({
            "codigo": fila["codigo_original"],
            "municipio_oficial": fila["municipio_oficial"],
            "nombre_fotocasa": fila["nombre_fotocasa"],
            "provincia": fila["provincia"],
            "provincia_normalizada": fila["provincia_normalizada"],
            "nombres_normalizados": nombres
        })

    # --------------------------------------------------------
    # 5. Preparar anuncios
    # --------------------------------------------------------

    resultados = []

    for indice, fila in pisos.iterrows():

        provincia_original = fila["provincia"]
        localidad_original = fila["localidad_zona"]

        municipio_extraido = extraer_municipio(
            localidad_original
        )

        provincia_norm = normalizar_provincia(
            provincia_original
        )

        municipio_norm = normalizar(
            municipio_extraido
        )

        estado = ""
        codigo = ""
        municipio_oficial = ""
        provincia_catalogo = ""
        numero_candidatos = 0

        # Comprobación de valores vacíos.
        if not str(provincia_original).strip():
            estado = "provincia_vacia"

        elif not str(localidad_original).strip():
            estado = "localidad_vacia"

        elif not municipio_norm:
            estado = "municipio_no_identificable"

        else:

            # Buscar únicamente dentro de la misma provincia.
            candidatos_provincia = [
                candidato
                for candidato in candidatos
                if candidato["provincia_normalizada"] == provincia_norm
            ]

            coincidencias = coincidencia_nombre(
                municipio_extraido,
                candidatos_provincia
            )

            numero_candidatos = len(coincidencias)

            if numero_candidatos == 0:

                estado = "sin_correspondencia"

            elif numero_candidatos > 1:

                estado = "coincidencia_ambigua"

            else:

                candidato = coincidencias[0]

                codigo = candidato["codigo"]
                municipio_oficial = candidato["municipio_oficial"]
                provincia_catalogo = candidato["provincia"]

                # Coincidencia literal o normalizada.
                nombres_originales = {
                    candidato["municipio_oficial"].strip().casefold(),
                    candidato["nombre_fotocasa"].strip().casefold()
                }

                if municipio_extraido.strip().casefold() in nombres_originales:
                    estado = "coincidencia_exacta"
                else:
                    estado = "coincidencia_normalizada"

        resultados.append({

            "fila_original": indice + 2,

            "provincia_pisos": provincia_original,

            "localidad_zona_original": localidad_original,

            "municipio_extraido": municipio_extraido,

            "provincia_normalizada": provincia_norm,

            "municipio_normalizado": municipio_norm,

            "estado_correspondencia": estado,

            "numero_candidatos": numero_candidatos,

            "municipio_oficial_fotocasa": municipio_oficial,

            "provincia_catalogo": provincia_catalogo,

            "municipio_codigo": codigo

        })

    resultado = pd.DataFrame(resultados)

    # --------------------------------------------------------
    # 6. Generar CSV de pendientes
    # --------------------------------------------------------

    pendientes = resultado[
        ~resultado["estado_correspondencia"].isin([
            "coincidencia_exacta",
            "coincidencia_normalizada"
        ])
    ].copy()

    if not pendientes.empty:

        pendientes_resumen = (
            pendientes
            .groupby(
                [
                    "provincia_pisos",
                    "localidad_zona_original",
                    "municipio_extraido",
                    "estado_correspondencia"
                ],
                dropna=False
            )
            .size()
            .reset_index(name="numero_anuncios")
            .sort_values(
                ["provincia_pisos", "municipio_extraido"]
            )
        )

    else:

        pendientes_resumen = pd.DataFrame(columns=[
            "provincia_pisos",
            "localidad_zona_original",
            "municipio_extraido",
            "estado_correspondencia",
            "numero_anuncios"
        ])

    # --------------------------------------------------------
    # 7. Guardar CSV
    # --------------------------------------------------------

    resultado.to_csv(
        ARCHIVO_RESULTADOS,
        index=False,
        encoding="utf-8-sig"
    )

    pendientes_resumen.to_csv(
        ARCHIVO_PENDIENTES,
        index=False,
        encoding="utf-8-sig"
    )

    # --------------------------------------------------------
    # 8. Estadísticas
    # --------------------------------------------------------

    estados = resultado["estado_correspondencia"].value_counts()

    coincidencias_exactas = int(
        (resultado["estado_correspondencia"] == "coincidencia_exacta").sum()
    )

    coincidencias_normalizadas = int(
        (resultado["estado_correspondencia"] == "coincidencia_normalizada").sum()
    )

    sin_correspondencia = int(
        (resultado["estado_correspondencia"] == "sin_correspondencia").sum()
    )

    ambiguos = int(
        (resultado["estado_correspondencia"] == "coincidencia_ambigua").sum()
    )

    validos = coincidencias_exactas + coincidencias_normalizadas

    # --------------------------------------------------------
    # 9. Crear informe TXT
    # --------------------------------------------------------

    lineas = [

        "=" * 65,
        "INFORME DE VALIDACIÓN GEOGRÁFICA - PISOS.COM",
        "=" * 65,

        f"Fecha de ejecución: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",

        "",

        "ARCHIVOS ANALIZADOS",

        f"Anuncios Pisos.com: {len(pisos)}",
        f"Registros catálogo Fotocasa: {len(catalogo)}",
        f"Municipios validados en catálogo: {len(candidatos)}",

        "",

        "RESULTADOS DE CORRESPONDENCIA",

        f"Coincidencias exactas: {coincidencias_exactas}",
        f"Coincidencias normalizadas: {coincidencias_normalizadas}",
        f"Total con correspondencia única: {validos}",
        f"Sin correspondencia: {sin_correspondencia}",
        f"Coincidencias ambiguas: {ambiguos}",

        "",

        "PROVINCIAS EN PISOS.COM",

    ]

    for provincia, cantidad in pisos["provincia"].value_counts().items():
        lineas.append(f"{provincia}: {cantidad}")

    lineas.extend([
        "",
        "ESTADOS DE VALIDACIÓN"
    ])

    for estado, cantidad in estados.items():
        lineas.append(f"{estado}: {cantidad}")

    lineas.extend([

        "",

        "LOCALIDADES PENDIENTES",

    ])

    if pendientes_resumen.empty:

        lineas.append("No hay localidades pendientes.")

    else:

        for _, fila in pendientes_resumen.iterrows():

            lineas.append(
                f"{fila['provincia_pisos']} | "
                f"{fila['municipio_extraido']} | "
                f"{fila['estado_correspondencia']} | "
                f"{fila['numero_anuncios']} anuncios"
            )

    lineas.extend([

        "",

        "OBSERVACIONES",

        "- Los archivos originales no se han modificado.",

        "- Los nombres se han normalizado solo para comparar.",

        "- Los códigos municipales se han conservado como texto.",

        "- No se han asignado códigos en coincidencias ambiguas "
        "o sin correspondencia.",

        "- Una coincidencia normalizada no demuestra por sí sola "
        "que la localidad sea correcta.",

        "- La validación definitiva requiere revisar las "
        "localidades pendientes.",

        "",

        "=" * 65

    ])

    ARCHIVO_INFORME.write_text(
        "\n".join(lineas),
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # 10. Mostrar resumen por terminal
    # --------------------------------------------------------

    print("\n" + "=" * 65)
    print("RESUMEN DE VALIDACIÓN")
    print("=" * 65)

    print(f"Anuncios analizados: {len(resultado)}")

    print(f"Coincidencias exactas: {coincidencias_exactas}")

    print(f"Coincidencias normalizadas: {coincidencias_normalizadas}")

    print(f"Con correspondencia única: {validos}")

    print(f"Sin correspondencia: {sin_correspondencia}")

    print(f"Coincidencias ambiguas: {ambiguos}")

    print("\nEstados encontrados:")

    print(estados.to_string())

    print("\n" + "=" * 65)
    print("ARCHIVOS GENERADOS")
    print("=" * 65)

    print(ARCHIVO_RESULTADOS)
    print(ARCHIVO_PENDIENTES)
    print(ARCHIVO_INFORME)

    print("\nValidación geográfica preliminar finalizada.")
    print("Es necesario revisar las localidades pendientes.")


if __name__ == "__main__":
    main()
