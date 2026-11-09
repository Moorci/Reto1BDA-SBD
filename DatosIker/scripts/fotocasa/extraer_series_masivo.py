
import csv
import json
import re
from pathlib import Path
from datetime import datetime
from collections import Counter

BASE = Path(__file__).resolve().parents[2]

CATALOGO = (
    BASE / "originales" / "fotocasa" /
    "catalogo_municipios_fotocasa.csv"
)

CARPETA_HTML = BASE / "originales" / "fotocasa" / "masiva"
CARPETA_PROCESADOS = BASE / "procesados" / "fotocasa"
CARPETA_INFORMES = BASE / "informes" / "fotocasa"

CSV_SALIDA = (
    CARPETA_PROCESADOS /
    "series_historicas_241_municipios.csv"
)

JSON_SALIDA = (
    CARPETA_PROCESADOS /
    "series_historicas_241_municipios.json"
)

INFORME = (
    CARPETA_INFORMES /
    "resultado_extraccion_241_municipios.csv"
)

MESES_ESPERADOS = [
    f"{anio}-{mes:02d}"
    for anio in range(2020, 2027)
    for mes in range(1, 13)
    if (anio, mes) <= (2026, 10)
]

TOTAL_ESPERADO = 241
REGISTROS_ESPERADOS = 82


def leer_csv(ruta):
    with ruta.open("r", encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f, delimiter=";")
        return list(lector)


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


def normalizar_fecha(valor):
    """
    Convierte los formatos de fecha de Fotocasa a AAAA-MM.
    """

    texto = str(valor).strip()

    # Formato AAAA-MM
    coincidencia = re.match(r"^(\d{4})-(\d{2})", texto)

    if coincidencia:
        anio, mes = map(int, coincidencia.groups())
        if 1 <= mes <= 12:
            return f"{anio}-{mes:02d}"

    # Formato AAAAMMDD o AAAAMM
    coincidencia = re.match(r"^(\d{4})(\d{2})(\d{2})?$", texto)

    if coincidencia:
        anio = int(coincidencia.group(1))
        mes = int(coincidencia.group(2))

        if 1 <= mes <= 12:
            return f"{anio}-{mes:02d}"

    # Otros formatos ISO
    try:
        fecha = datetime.fromisoformat(
            texto.replace("Z", "+00:00")
        )
        return fecha.strftime("%Y-%m")
    except ValueError:
        raise ValueError(f"Formato de fecha no reconocido: {valor}")


def convertir_precio(valor):
    if isinstance(valor, str):
        valor = valor.strip().replace(",", ".")

    precio = float(valor)

    if precio <= 0:
        raise ValueError(f"Precio no positivo: {valor}")

    return precio


def extraer_serie(datos, tipo, codigo):
    if not isinstance(datos, list):
        raise ValueError(
            f"La serie {tipo} de {codigo} no es una lista."
        )

    registros = []

    for punto in datos:
        if not isinstance(punto, dict):
            raise ValueError(
                f"Punto incorrecto en serie {tipo}, municipio {codigo}."
            )

        if "period" not in punto or "meanPriceSqm" not in punto:
            raise ValueError(
                f"Faltan period o meanPriceSqm en {codigo}, {tipo}."
            )

        fecha = normalizar_fecha(punto["period"])
        precio = convertir_precio(punto["meanPriceSqm"])

        registros.append({
            "fecha": fecha,
            "precio_eur_m2": precio
        })

    fechas = [r["fecha"] for r in registros]

    if len(registros) != REGISTROS_ESPERADOS:
        raise ValueError(
            f"{codigo}, {tipo}: {len(registros)} registros; "
            f"se esperaban {REGISTROS_ESPERADOS}."
        )

    if len(set(fechas)) != len(fechas):
        raise ValueError(
            f"Fechas duplicadas en {codigo}, {tipo}."
        )

    if fechas != MESES_ESPERADOS:
        raise ValueError(
            f"Fechas incorrectas en {codigo}, {tipo}. "
            f"Primera: {fechas[0]}, última: {fechas[-1]}."
        )

    return registros


def guardar_csv(ruta, registros):
    columnas = [
        "municipio_codigo",
        "municipio_oficial",
        "fotocasa_id",
        "nombre_fotocasa",
        "tipo",
        "fecha",
        "precio_eur_m2"
    ]

    with ruta.open("w", encoding="utf-8-sig", newline="") as f:
        escritor = csv.DictWriter(
            f,
            fieldnames=columnas,
            delimiter=";"
        )
        escritor.writeheader()
        escritor.writerows(registros)


def main():
    CARPETA_PROCESADOS.mkdir(parents=True, exist_ok=True)
    CARPETA_INFORMES.mkdir(parents=True, exist_ok=True)

    catalogo = leer_csv(CATALOGO)

    municipios = [
        fila for fila in catalogo
        if fila["estado"] == "validado"
        and fila["municipio_codigo"] not in {
            "48020", "01059", "48013", "20069", "01002",
            "48001", "20001", "48002", "20002", "01051"
        }
    ]

    print("=" * 65)
    print("EXTRACCIÓN HISTÓRICA MASIVA DE FOTOCASA")
    print("=" * 65)
    print("Municipios que se van a procesar:", len(municipios))

    if len(municipios) != TOTAL_ESPERADO:
        raise ValueError(
            f"Se esperaban {TOTAL_ESPERADO} municipios nuevos, "
            f"pero se han encontrado {len(municipios)}."
        )

    registros_totales = []
    resultados = []
    municipios_correctos = 0

    for numero, municipio in enumerate(municipios, start=1):
        codigo = municipio["municipio_codigo"]
        nombre = municipio["municipio_oficial"]
        fotocasa_id = municipio["fotocasa_id"]

        print(
            f"\n[{numero}/{len(municipios)}] "
            f"{nombre} ({codigo})"
        )

        try:
            archivos_preferidos = {
                "01017": "01017_campezo-kampezu.html",
                "20065": "20065_soraluze-plasencia-de-las-armas.html"
            }

            if codigo in archivos_preferidos:
                archivo = CARPETA_HTML / archivos_preferidos[codigo]

                if not archivo.exists():
                    raise FileNotFoundError(
                        f"No se encuentra el archivo seleccionado: {archivo.name}"
                    )
            else:
                archivos = list(CARPETA_HTML.glob(f"{codigo}_*.html"))

                if len(archivos) != 1:
                    raise ValueError(
                        f"Se esperaba un HTML y se encontraron "
                        f"{len(archivos)}."
                    )

                archivo = archivos[0]

            html = archivo.read_text(encoding="utf-8")

            patron = (
                r'<script[^>]*id="__initial_props__"[^>]*>'
                r'(.*?)</script>'
            )

            coincidencia = re.search(
                patron,
                html,
                re.DOTALL
            )

            if not coincidencia:
                raise ValueError("No se encuentra __initial_props__.")

            datos_json = json.loads(coincidencia.group(1))
            datos_municipio = buscar_municipio(datos_json)

            if not datos_municipio:
                raise ValueError("No se encuentra priceEvolution.")

            id_html = str(datos_municipio.get("id", ""))

            if id_html != fotocasa_id:
                raise ValueError(
                    f"ID diferente. Catálogo: {fotocasa_id}; "
                    f"HTML: {id_html}."
                )

            evolucion = datos_municipio["priceEvolution"]

            alquiler = extraer_serie(
                evolucion["rent"], "alquiler", codigo
            )

            venta = extraer_serie(
                evolucion["sale"], "venta", codigo
            )

            nombre_fotocasa = (
                datos_municipio.get("name")
                or datos_municipio.get("municipalityName")
                or municipio["nombre_fotocasa"]
            )

            registros_municipio = []

            for tipo, serie in [
                ("alquiler", alquiler),
                ("venta", venta)
            ]:
                for punto in serie:
                    anio, mes = punto["fecha"].split("-")

                    registros_municipio.append({
                        "municipio_codigo": codigo,
                        "municipio_oficial": nombre,
                        "fotocasa_id": fotocasa_id,
                        "nombre_fotocasa": nombre_fotocasa,
                        "tipo": tipo,
                        "fecha": punto["fecha"],
                        "precio_eur_m2": punto["precio_eur_m2"]
                    })

            registros_totales.extend(registros_municipio)
            municipios_correctos += 1

            resultados.append({
                "municipio_codigo": codigo,
                "municipio": nombre,
                "estado": "correcto",
                "registros_alquiler": len(alquiler),
                "registros_venta": len(venta),
                "observaciones": ""
            })

            print("  Alquiler:", len(alquiler))
            print("  Venta:", len(venta))
            print("  Estado: CORRECTO")

        except Exception as error:
            resultados.append({
                "municipio_codigo": codigo,
                "municipio": nombre,
                "estado": "error",
                "registros_alquiler": 0,
                "registros_venta": 0,
                "observaciones": str(error)
            })

            print("  ERROR:", error)

    # Guardar únicamente los municipios que han superado
    # todas las validaciones.
    guardar_csv(CSV_SALIDA, registros_totales)

    with JSON_SALIDA.open("w", encoding="utf-8") as f:
        json.dump(
            registros_totales,
            f,
            ensure_ascii=False,
            indent=2
        )

    with INFORME.open("w", encoding="utf-8-sig", newline="") as f:
        columnas = [
            "municipio_codigo",
            "municipio",
            "estado",
            "registros_alquiler",
            "registros_venta",
            "observaciones"
        ]

        escritor = csv.DictWriter(
            f,
            fieldnames=columnas,
            delimiter=";"
        )
        escritor.writeheader()
        escritor.writerows(resultados)

    # Comprobaciones finales.
    claves = [
        (
            r["municipio_codigo"],
            r["tipo"],
            r["fecha"]
        )
        for r in registros_totales
    ]

    duplicados = len(claves) - len(set(claves))

    print("\n" + "=" * 65)
    print("RESUMEN DE EXTRACCIÓN")
    print("=" * 65)
    print("Municipios procesados:", len(municipios))
    print("Municipios correctos:", municipios_correctos)
    print("Municipios con errores:", len(municipios) - municipios_correctos)
    print("Registros generados:", len(registros_totales))
    print("Duplicados:", duplicados)

    print("\nArchivos generados:")
    print(CSV_SALIDA)
    print(JSON_SALIDA)
    print(INFORME)


if __name__ == "__main__":
    main()
