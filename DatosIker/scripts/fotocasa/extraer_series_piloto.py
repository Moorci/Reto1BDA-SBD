
import csv
import json
import re
from pathlib import Path
from datetime import datetime

# ============================================================
# CONFIGURACION
# ============================================================

CARPETA_HTML = Path("originales/fotocasa/pruebas")
CARPETA_SALIDA = Path("procesados/fotocasa")

ARCHIVO_INFORME = Path(
    "informes/fotocasa/prueba_localizacion_municipios.csv"
)

ARCHIVO_CSV = CARPETA_SALIDA / "series_historicas_piloto.csv"
ARCHIVO_JSON = CARPETA_SALIDA / "series_historicas_piloto.json"

REGISTROS_ESPERADOS = 82

# Posibles nombres de los campos dentro del JSON de Fotocasa.
CLAVES_FECHA = [
    "period", "date", "month", "yearMonth",
    "dateLabel", "monthDate", "fecha"
]

CLAVES_PRECIO = [
    "meanPriceSqm", "value", "price", "amount",
    "averagePrice", "pricePerSquareMeter", "precio"
]


# ============================================================
# FUNCIONES
# ============================================================

def extraer_json(html):
    patron = (
        r'<script\b(?=[^>]*\bid=["\']__initial_props__["\'])'
        r'[^>]*>(.*?)</script>'
    )

    coincidencia = re.search(
        patron,
        html,
        flags=re.IGNORECASE | re.DOTALL
    )

    if not coincidencia:
        raise ValueError("No se encuentra __initial_props__")

    return json.loads(coincidencia.group(1))


def buscar_municipio(objeto):
    if isinstance(objeto, dict):

        if "priceEvolution" in objeto and "id" in objeto:
            return objeto

        for valor in objeto.values():
            resultado = buscar_municipio(valor)

            if resultado is not None:
                return resultado

    elif isinstance(objeto, list):

        for elemento in objeto:
            resultado = buscar_municipio(elemento)

            if resultado is not None:
                return resultado

    return None


def normalizar_fecha(valor):
    """Convierte fechas de Fotocasa al formato YYYY-MM."""

    texto = str(valor).strip()

    # Formato AAAAMMDD, por ejemplo 20200101
    if re.fullmatch(r"\d{8}", texto):
        fecha = datetime.strptime(texto, "%Y%m%d")
        return fecha.strftime("%Y-%m")

    # Formato AAAA-MM o AAAA/MM
    coincidencia = re.fullmatch(
        r"(20\d{2})[-/](\d{1,2})",
        texto
    )

    if coincidencia:
        anio = int(coincidencia.group(1))
        mes = int(coincidencia.group(2))

        if 1 <= mes <= 12:
            return f"{anio:04d}-{mes:02d}"

    # Formato ISO
    try:
        fecha = datetime.fromisoformat(
            texto.replace("Z", "+00:00")
        )
        return fecha.strftime("%Y-%m")
    except ValueError:
        pass

    raise ValueError(
        f"Formato de fecha no reconocido: {valor}"
    )


def convertir_precio(valor):
    if isinstance(valor, bool) or valor is None:
        raise ValueError(f"Precio no válido: {valor}")

    if isinstance(valor, (int, float)):
        precio = float(valor)
    else:
        texto = str(valor).strip().replace(" ", "")

        # Admitir coma decimal si el valor viene como texto.
        if "," in texto and "." not in texto:
            texto = texto.replace(",", ".")

        precio = float(texto)

    if precio <= 0:
        raise ValueError(f"Precio no positivo: {valor}")

    return precio


def extraer_campos(registro):
    if not isinstance(registro, dict):
        raise ValueError(
            f"Registro con formato inesperado: {registro}"
        )

    fecha = next(
        (
            registro[k]
            for k in CLAVES_FECHA
            if k in registro and registro[k] is not None
        ),
        None
    )

    precio = next(
        (
            registro[k]
            for k in CLAVES_PRECIO
            if k in registro and registro[k] is not None
        ),
        None
    )

    if fecha is None or precio is None:
        raise ValueError(
            "No se reconocen los campos de fecha y precio. "
            f"Claves encontradas: {list(registro.keys())}. "
            f"Registro: {registro}"
        )

    return normalizar_fecha(fecha), convertir_precio(precio)


# ============================================================
# LEER INFORME DE LOS CINCO MUNICIPIOS
# ============================================================

CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)

with open(
    ARCHIVO_INFORME,
    encoding="utf-8-sig",
    newline=""
) as archivo:

    municipios = list(
        csv.DictReader(archivo, delimiter=";")
    )

if len(municipios) != 5:
    raise ValueError(
        f"Se esperaban 5 municipios y hay {len(municipios)}"
    )


# ============================================================
# EXTRAER SERIES
# ============================================================

todos_los_registros = []
resumen = []

print("=" * 65)
print("EXTRACCION DE SERIES HISTORICAS FOTOCASA")
print("=" * 65)

for municipio in municipios:

    codigo = municipio["municipio_codigo"]
    nombre = municipio["municipio_oficial"]
    slug = municipio["slug_probado"]

    archivo_html = CARPETA_HTML / f"{codigo}_{slug}.html"

    print(f"\nMunicipio: {nombre}")
    print("Archivo:", archivo_html)

    if not archivo_html.exists():
        raise FileNotFoundError(
            f"No existe el HTML: {archivo_html}"
        )

    html = archivo_html.read_text(encoding="utf-8")

    datos = extraer_json(html)
    objeto_municipio = buscar_municipio(datos)

    if objeto_municipio is None:
        raise ValueError(
            f"No se encuentra municipality para {nombre}"
        )

    id_fotocasa = str(objeto_municipio.get("id", ""))
    nombre_fotocasa = str(objeto_municipio.get("name", ""))

    # Comprobar que el HTML corresponde al municipio del informe.
    if id_fotocasa != municipio["fotocasa_id"]:
        raise ValueError(
            f"ID diferente para {nombre}: "
            f"{id_fotocasa} != {municipio['fotocasa_id']}"
        )

    evolucion = objeto_municipio.get("priceEvolution", {})

    for tipo, clave in [
        ("alquiler", "rent"),
        ("venta", "sale")
    ]:

        serie = evolucion.get(clave)

        if not isinstance(serie, list):
            raise ValueError(
                f"Serie {clave} no válida para {nombre}"
            )

        if len(serie) != REGISTROS_ESPERADOS:
            raise ValueError(
                f"{nombre}, {tipo}: se esperaban "
                f"{REGISTROS_ESPERADOS} registros y hay {len(serie)}"
            )

        registros_municipio = []

        for elemento in serie:

            fecha, precio = extraer_campos(elemento)

            registro = {
                "municipio_codigo": codigo,
                "municipio_oficial": nombre,
                "fotocasa_id": id_fotocasa,
                "nombre_fotocasa": nombre_fotocasa,
                "tipo": tipo,
                "fecha": fecha,
                "precio_eur_m2": precio
            }

            registros_municipio.append(registro)

        fechas = [
            registro["fecha"]
            for registro in registros_municipio
        ]

        if len(fechas) != len(set(fechas)):
            raise ValueError(
                f"Hay fechas duplicadas en {nombre}, {tipo}"
            )

        registros_municipio.sort(
            key=lambda x: x["fecha"]
        )

        todos_los_registros.extend(registros_municipio)

        resumen.append({
            "municipio_codigo": codigo,
            "municipio": nombre,
            "tipo": tipo,
            "registros": len(registros_municipio),
            "primera_fecha": registros_municipio[0]["fecha"],
            "ultima_fecha": registros_municipio[-1]["fecha"],
            "precio_ultimo": registros_municipio[-1]["precio_eur_m2"]
        })

        print(
            f"{tipo.capitalize()}: {len(registros_municipio)} registros | "
            f"{fechas[0]} a {fechas[-1]}"
        )


# ============================================================
# COMPROBACIONES GENERALES
# ============================================================

claves = [
    (
        r["municipio_codigo"],
        r["tipo"],
        r["fecha"]
    )
    for r in todos_los_registros
]

duplicados = len(claves) - len(set(claves))

if duplicados != 0:
    raise ValueError(
        f"Se han encontrado {duplicados} registros duplicados"
    )

if len(todos_los_registros) != 5 * 2 * REGISTROS_ESPERADOS:
    raise ValueError(
        f"Total inesperado: {len(todos_los_registros)}"
    )

# Comprobar que todos los precios son positivos.
if not all(
    r["precio_eur_m2"] > 0
    for r in todos_los_registros
):
    raise ValueError("Hay precios no positivos")


# ============================================================
# GUARDAR CSV Y JSON
# ============================================================

campos = [
    "municipio_codigo",
    "municipio_oficial",
    "fotocasa_id",
    "nombre_fotocasa",
    "tipo",
    "fecha",
    "precio_eur_m2"
]

with open(
    ARCHIVO_CSV,
    "w",
    encoding="utf-8-sig",
    newline=""
) as archivo:

    escritor = csv.DictWriter(
        archivo,
        fieldnames=campos,
        delimiter=";"
    )

    escritor.writeheader()
    escritor.writerows(todos_los_registros)


resultado_json = {
    "fuente": "Indice Inmobiliario Fotocasa",
    "municipios": 5,
    "registros_totales": len(todos_los_registros),
    "unidad": "euros por metro cuadrado",
    "datos": todos_los_registros
}

with open(
    ARCHIVO_JSON,
    "w",
    encoding="utf-8"
) as archivo:

    json.dump(
        resultado_json,
        archivo,
        ensure_ascii=False,
        indent=2
    )


# ============================================================
# RESUMEN FINAL
# ============================================================

print("\n" + "=" * 65)
print("RESUMEN DE EXTRACCION")
print("=" * 65)

print("Municipios:", len(municipios))
print("Series extraídas:", len(resumen))
print("Registros totales:", len(todos_los_registros))
print("Registros duplicados:", duplicados)

print("\nDETALLE POR MUNICIPIO Y TIPO:")

for fila in resumen:
    print(
        f"{fila['municipio']} | "
        f"{fila['tipo']} | "
        f"{fila['registros']} registros | "
        f"{fila['primera_fecha']} - {fila['ultima_fecha']} | "
        f"Último precio: {fila['precio_ultimo']}"
    )

print("\nARCHIVOS GENERADOS:")
print(ARCHIVO_CSV)
print(ARCHIVO_JSON)

print("\nExtracción terminada.")
