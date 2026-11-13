
from pathlib import Path
import pandas as pd
import unicodedata
import re
import csv
from datetime import datetime


# ============================================================
# CONFIGURACIÓN
# ============================================================

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
# FUNCIONES
# ============================================================

def normalizar(texto):
    """Normaliza un texto para poder compararlo."""

    if pd.isna(texto):
        return ""

    texto = str(texto).strip().lower()

    texto = unicodedata.normalize("NFD", texto)

    texto = "".join(
        c for c in texto
        if unicodedata.category(c) != "Mn"
    )

    return re.sub(r"[^a-z0-9]", "", texto)


def obtener_tokens(texto):
    """
    Obtiene las palabras normalizadas y ordenadas.
    Permite comparar nombres bilingües en distinto orden.
    """

    texto = unicodedata.normalize(
        "NFD", str(texto).strip().lower()
    )

    texto = "".join(
        c for c in texto
        if unicodedata.category(c) != "Mn"
    )

    return tuple(sorted(re.findall(r"[a-z0-9]+", texto)))


def normalizar_provincia(provincia):

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
    Extrae el municipio de localidad_zona.

    Ejemplos:

    Centro (Barakaldo) -> Barakaldo

    Ametzola (Distrito Errekalde. Bilbao) -> Bilbao

    San Sebastián - Donostia -> San Sebastián - Donostia

    Si no hay paréntesis, conserva el nombre completo.
    """

    if pd.isna(localidad):
        return ""

    localidad = str(localidad).strip()

    coincidencia = re.search(
        r"\(([^()]*)\)\s*$",
        localidad
    )

    if not coincidencia:
        return localidad

    interior = coincidencia.group(1).strip()

    # Los distritos de Bilbao contienen el municipio
    # después del último punto.
    if interior.lower().startswith("distrito "):
        if "." in interior:
            return interior.rsplit(".", 1)[-1].strip()

    return interior


def crear_aliases(fila):
    """
    Crea nombres alternativos a partir del nombre oficial
    y del nombre utilizado por Fotocasa.

    Separa denominaciones bilingües mediante / y -.
    """

    aliases = set()

    nombres = [
        fila["municipio_oficial"],
        fila["nombre_fotocasa"]
    ]

    for nombre in nombres:

        nombre = str(nombre).strip()

        if not nombre:
            continue

        aliases.add(nombre)

        partes = re.split(r"\s*/\s*|\s*-\s*", nombre)

        for parte in partes:

            parte = parte.strip()

            if parte:
                aliases.add(parte)

    return aliases


def buscar_coincidencias(municipio, provincia, catalogo):

    nombre = normalizar(municipio)
    tokens = obtener_tokens(municipio)

    provincia_norm = normalizar_provincia(provincia)

    coincidencias = []

    for candidato in catalogo:

        if candidato["provincia_normalizada"] != provincia_norm:
            continue

        for alias in candidato["aliases"]:

            alias_norm = normalizar(alias)
            alias_tokens = obtener_tokens(alias)

            if (
                nombre == alias_norm
                or tokens == alias_tokens
            ):

                coincidencias.append(candidato)
                break

    return coincidencias


def leer_csv(ruta):

    with open(ruta, "r", encoding="utf-8-sig") as archivo:

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


# ============================================================
# PROCESO PRINCIPAL
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
                f"No se encuentra: {archivo}"
            )

    CARPETA_INFORMES.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # 2. Leer archivos
    # --------------------------------------------------------

    pisos = leer_csv(ARCHIVO_PISOS)
    catalogo_df = leer_csv(ARCHIVO_CATALOGO)

    print("\nARCHIVOS LEÍDOS")
    print("-" * 65)

    print(f"Anuncios: {len(pisos)}")
    print(f"Registros catálogo: {len(catalogo_df)}")

    print("\nColumnas Pisos.com:")
    print(list(pisos.columns))

    print("\nColumnas Fotocasa:")
    print(list(catalogo_df.columns))

    # --------------------------------------------------------
    # 3. Validar columnas
    # --------------------------------------------------------

    requeridas_pisos = {
        "provincia",
        "localidad_zona"
    }

    requeridas_catalogo = {
        "municipio_codigo",
        "municipio_oficial",
        "provincia",
        "nombre_fotocasa",
        "estado"
    }

    if not requeridas_pisos.issubset(pisos.columns):
        raise ValueError("Faltan columnas en Pisos.com.")

    if not requeridas_catalogo.issubset(catalogo_df.columns):
        raise ValueError("Faltan columnas en el catálogo.")

    # --------------------------------------------------------
    # 4. Preparar catálogo
    # --------------------------------------------------------

    candidatos = []

    for _, fila in catalogo_df.iterrows():

        estado_catalogo = normalizar(fila["estado"])

        candidato = {

            "codigo": str(fila["municipio_codigo"]),

            "municipio_oficial": fila["municipio_oficial"],

            "nombre_fotocasa": fila["nombre_fotocasa"],

            "provincia": fila["provincia"],

            "provincia_normalizada": normalizar_provincia(
                fila["provincia"]
            ),

            "estado_catalogo": estado_catalogo,

            "aliases": crear_aliases(fila)

        }

        candidatos.append(candidato)

    municipios_validados = sum(
        c["estado_catalogo"] == "validado"
        for c in candidatos
    )

    municipios_excluidos = sum(
        c["estado_catalogo"] != "validado"
        for c in candidatos
    )

    # --------------------------------------------------------
    # 5. Validar anuncios
    # --------------------------------------------------------

    resultados = []

    provincias_euskadi = {
        "alava",
        "bizkaia",
        "gipuzkoa"
    }

    for indice, fila in pisos.iterrows():

        provincia = fila["provincia"]
        localidad = fila["localidad_zona"]

        municipio = extraer_municipio(localidad)

        provincia_norm = normalizar_provincia(provincia)

        estado = ""
        codigo = ""
        municipio_oficial = ""
        provincia_catalogo = ""
        estado_catalogo = ""
        numero_candidatos = 0

        if not provincia.strip():

            estado = "provincia_vacia"

        elif not localidad.strip():

            estado = "localidad_vacia"

        elif provincia_norm not in provincias_euskadi:

            estado = "provincia_no_reconocida"

        elif not normalizar(municipio):

            estado = "municipio_no_identificable"

        else:

            coincidencias = buscar_coincidencias(
                municipio,
                provincia,
                candidatos
            )

            numero_candidatos = len(coincidencias)

            if numero_candidatos == 0:

                estado = "sin_correspondencia"

            elif numero_candidatos > 1:

                estado = "coincidencia_ambigua"

            else:

                candidato = coincidencias[0]

                estado_catalogo = candidato["estado_catalogo"]

                municipio_oficial = candidato["municipio_oficial"]

                provincia_catalogo = candidato["provincia"]

                if estado_catalogo != "validado":

                    estado = "municipio_excluido_catalogo"

                else:

                    codigo = candidato["codigo"]

                    # Comprobamos si la coincidencia es literal
                    # o requiere normalización.

                    aliases = candidato["aliases"]

                    if any(
                        normalizar(municipio) == normalizar(alias)
                        for alias in aliases
                    ):

                        estado = "coincidencia_exacta"

                    else:

                        estado = "coincidencia_normalizada"

        resultados.append({

            "fila_original": indice + 2,

            "provincia_pisos": provincia,

            "localidad_zona_original": localidad,

            "municipio_extraido": municipio,

            "provincia_normalizada": provincia_norm,

            "municipio_normalizado": normalizar(municipio),

            "estado_correspondencia": estado,

            "numero_candidatos": numero_candidatos,

            "municipio_oficial_fotocasa": municipio_oficial,

            "provincia_catalogo": provincia_catalogo,

            "estado_catalogo": estado_catalogo,

            "municipio_codigo": codigo

        })

    resultado = pd.DataFrame(resultados)

    # --------------------------------------------------------
    # 6. Crear CSV de pendientes
    # --------------------------------------------------------

    pendientes = resultado[
        ~resultado["estado_correspondencia"].isin([
            "coincidencia_exacta",
            "coincidencia_normalizada"
        ])
    ].copy()

    if not pendientes.empty:

        pendientes_resumen = (

            pendientes.groupby(
                [
                    "provincia_pisos",
                    "municipio_extraido",
                    "estado_correspondencia"
                ],
                dropna=False
            )
            .agg(

                numero_anuncios=(
                    "fila_original",
                    "count"
                ),

                localidades_zona_ejemplo=(
                    "localidad_zona_original",
                    lambda x: " | ".join(sorted(set(x)))
                )

            )
            .reset_index()
            .sort_values([
                "provincia_pisos",
                "municipio_extraido"
            ])

        )

    else:

        pendientes_resumen = pd.DataFrame(columns=[
            "provincia_pisos",
            "municipio_extraido",
            "estado_correspondencia",
            "numero_anuncios",
            "localidades_zona_ejemplo"
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
    # 8. Calcular estadísticas
    # --------------------------------------------------------

    estados = resultado[
        "estado_correspondencia"
    ].value_counts()

    exactas = int(
        (resultado["estado_correspondencia"]
         == "coincidencia_exacta").sum()
    )

    normalizadas = int(
        (resultado["estado_correspondencia"]
         == "coincidencia_normalizada").sum()
    )

    excluidos = int(
        (resultado["estado_correspondencia"]
         == "municipio_excluido_catalogo").sum()
    )

    ambiguos = int(
        (resultado["estado_correspondencia"]
         == "coincidencia_ambigua").sum()
    )

    sin_correspondencia = int(
        (resultado["estado_correspondencia"]
         == "sin_correspondencia").sum()
    )

    total_correspondencias = exactas + normalizadas

    # --------------------------------------------------------
    # 9. Generar informe TXT
    # --------------------------------------------------------

    lineas = [

        "=" * 65,

        "INFORME DE VALIDACIÓN GEOGRÁFICA - PISOS.COM",

        "=" * 65,

        f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",

        "",

        "ARCHIVOS ANALIZADOS",

        f"Anuncios Pisos.com: {len(pisos)}",

        f"Registros catálogo: {len(catalogo_df)}",

        f"Municipios validados en catálogo: {municipios_validados}",

        f"Registros excluidos del catálogo: {municipios_excluidos}",

        "",

        "RESULTADOS",

        f"Coincidencias exactas: {exactas}",

        f"Coincidencias normalizadas: {normalizadas}",

        f"Total con correspondencia única: {total_correspondencias}",

        f"Municipios excluidos: {excluidos}",

        f"Sin correspondencia: {sin_correspondencia}",

        f"Coincidencias ambiguas: {ambiguos}",

        "",

        "PROVINCIAS EN PISOS.COM"

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
        "LOCALIDADES PENDIENTES"
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

        "- Los nombres originales se conservan.",

        "- La normalización se utiliza únicamente para comparar.",

        "- Los códigos municipales se mantienen como texto.",

        "- Los municipios excluidos no reciben código validado.",

        "- Las coincidencias ambiguas no reciben código.",

        "- La validación definitiva requiere revisar las incidencias.",

        "",

        "=" * 65

    ])

    ARCHIVO_INFORME.write_text(
        "\n".join(lineas),
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # 10. Mostrar resultados
    # --------------------------------------------------------

    print("\n" + "=" * 65)
    print("RESUMEN DE VALIDACIÓN")
    print("=" * 65)

    print(f"Anuncios analizados: {len(resultado)}")

    print(f"Coincidencias exactas: {exactas}")

    print(f"Coincidencias normalizadas: {normalizadas}")

    print(f"Total con correspondencia única: {total_correspondencias}")

    print(f"Municipios excluidos: {excluidos}")

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

    print("\nValidación preliminar finalizada.")


if __name__ == "__main__":
    main()
