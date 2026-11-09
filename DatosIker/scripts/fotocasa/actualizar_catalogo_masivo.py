import csv
import shutil
from pathlib import Path
from datetime import datetime
from collections import Counter

BASE = Path(__file__).resolve().parents[2]

CATALOGO = BASE / "originales" / "fotocasa" / "catalogo_municipios_fotocasa.csv"
INFORME = BASE / "informes" / "fotocasa" / "localizacion_masiva_fotocasa.csv"

CODIGO_EXCLUIDO = "48916"
MUNICIPIOS_ESPERADOS = 241


def leer_csv(ruta):
    with ruta.open("r", encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f, delimiter=";")
        return lector.fieldnames, list(lector)


def guardar_csv(ruta, columnas, filas):
    with ruta.open("w", encoding="utf-8-sig", newline="") as f:
        escritor = csv.DictWriter(
            f,
            fieldnames=columnas,
            delimiter=";",
            extrasaction="ignore"
        )
        escritor.writeheader()
        escritor.writerows(filas)


def main():
    columnas_catalogo, catalogo = leer_csv(CATALOGO)
    _, informe = leer_csv(INFORME)

    # 1. Comprobar estructura.
    campos_necesarios = {
        "municipio_codigo",
        "estado",
        "fotocasa_id",
        "fotocasa_slug",
        "nombre_fotocasa",
        "url",
        "registros_alquiler",
        "registros_venta"
    }

    if not campos_necesarios.issubset(columnas_catalogo):
        raise ValueError("El catálogo no contiene todos los campos necesarios.")

    # 2. Comprobar códigos del catálogo.
    codigos_catalogo = [f["municipio_codigo"] for f in catalogo]

    if len(codigos_catalogo) != len(set(codigos_catalogo)):
        raise ValueError("Hay códigos municipales duplicados en el catálogo.")

    catalogo_por_codigo = {
        fila["municipio_codigo"]: fila for fila in catalogo
    }

    if CODIGO_EXCLUIDO not in catalogo_por_codigo:
        raise ValueError("Usansolo no aparece en el catálogo.")

    # 3. Seleccionar candidatos válidos.
    validos = [
        fila for fila in informe
        if fila["estado"] == "candidato_valido"
    ]

    print("Candidatos válidos en el informe:", len(validos))

    if len(validos) != MUNICIPIOS_ESPERADOS:
        raise ValueError(
            f"Se esperaban {MUNICIPIOS_ESPERADOS} candidatos válidos."
        )

    # 4. Comprobar códigos duplicados en el informe.
    codigos_informe = [f["municipio_codigo"] for f in validos]
    duplicados = [
        codigo for codigo, cantidad in Counter(codigos_informe).items()
        if cantidad > 1
    ]

    if duplicados:
        raise ValueError(f"Códigos duplicados en el informe: {duplicados}")

    # 5. Comprobar datos de cada candidato.
    for fila in validos:
        codigo = fila["municipio_codigo"]

        if codigo not in catalogo_por_codigo:
            raise ValueError(f"El código {codigo} no está en el catálogo.")

        if catalogo_por_codigo[codigo]["estado"] == "validado":
            raise ValueError(
                f"El municipio {codigo} ya estaba validado en el catálogo."
            )

        if not fila["fotocasa_id"]:
            raise ValueError(f"El municipio {codigo} no tiene ID Fotocasa.")

        if fila["http_status"] != "200":
            raise ValueError(f"El municipio {codigo} no tiene HTTP 200.")

        if fila["registros_alquiler"] != "82":
            raise ValueError(f"Alquiler incorrecto para {codigo}.")

        if fila["registros_venta"] != "82":
            raise ValueError(f"Venta incorrecta para {codigo}.")

    # 6. Comprobar IDs únicos entre los 10 anteriores y los 241 nuevos.
    ids_validos = [
        fila["fotocasa_id"]
        for fila in catalogo
        if fila["estado"] == "validado" and fila["fotocasa_id"]
    ]

    ids_nuevos = [fila["fotocasa_id"] for fila in validos]

    todos_ids = ids_validos + ids_nuevos

    duplicados_ids = [
        identificador
        for identificador, cantidad in Counter(todos_ids).items()
        if cantidad > 1
    ]

    if duplicados_ids:
        raise ValueError(
            f"IDs Fotocasa duplicados entre municipios: {duplicados_ids}"
        )

    # 7. Crear copia de seguridad.
    marca_tiempo = datetime.now().strftime("%Y%m%d_%H%M%S")

    backup = CATALOGO.with_name(
        f"catalogo_municipios_fotocasa_backup_{marca_tiempo}.csv"
    )

    shutil.copy2(CATALOGO, backup)

    # 8. Actualizar los 241 municipios.
    for fila in validos:
        codigo = fila["municipio_codigo"]
        destino = catalogo_por_codigo[codigo]

        destino.update({
            "fotocasa_id": fila["fotocasa_id"],
            "fotocasa_slug": fila["slug_probado"],
            "nombre_fotocasa": fila["nombre_fotocasa"],
            "url": fila["url"],
            "estado": "validado",
            "registros_alquiler": fila["registros_alquiler"],
            "registros_venta": fila["registros_venta"]
        })

    # 9. Marcar Usansolo como excluido.
    usansolo = catalogo_por_codigo[CODIGO_EXCLUIDO]

    usansolo.update({
        "fotocasa_id": "",
        "fotocasa_slug": "",
        "nombre_fotocasa": "",
        "url": "",
        "estado": "excluido",
        "registros_alquiler": "0",
        "registros_venta": "0"
    })

    # 10. Guardar catálogo.
    guardar_csv(CATALOGO, columnas_catalogo, catalogo)

    # 11. Comprobación final.
    estados = Counter(fila["estado"] for fila in catalogo)

    print("\n" + "=" * 55)
    print("ACTUALIZACIÓN DEL CATÁLOGO COMPLETADA")
    print("=" * 55)
    print("Municipios totales:", len(catalogo))
    print("Municipios validados:", estados["validado"])
    print("Municipios excluidos:", estados["excluido"])
    print("Municipios pendientes:", estados["pendiente"])
    print("IDs Fotocasa únicos:", len(set(todos_ids)))
    print("Copia de seguridad:", backup)


if __name__ == "__main__":
    main()