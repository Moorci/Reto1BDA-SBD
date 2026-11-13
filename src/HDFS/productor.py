import base64
import csv
import json
import math
import socket
import time
import uuid
from pathlib import Path, PurePosixPath

try:
    from .funciones import conectar_hdfs, obtener_configuracion
except ImportError:  # pragma: no cover
    from funciones import conectar_hdfs, obtener_configuracion


CHUNK_SIZE = 128 * 1024
PROJECT_ROOT = None


def _html_exclusion_reason(path, fotocasa_originales):
    relative_path = path.relative_to(fotocasa_originales)
    if "pruebas" in {part.casefold() for part in relative_path.parts[:-1]}:
        return "pruebas"
    if "notfound" in path.name.casefold() or b"notfound" in path.read_bytes().lower():
        return "notFound"
    return None


def recolectar_archivos_locales():
    files = []

    def add_file(local_relative, hdfs_relative):
        files.append(
            {
                "local_path": PROJECT_ROOT / local_relative,
                "hdfs_relative": PurePosixPath(hdfs_relative).as_posix(),
            }
        )

    add_file(
        Path("DatosIker")
        / "originales"
        / "fotocasa"
        / "MunicipiosCAE_2025_19_02.xlsx",
        "originales/fotocasa/MunicipiosCAE_2025_19_02.xlsx",
    )
    add_file(
        Path("DatosIker")
        / "originales"
        / "EMAL.-Barrios-Municipios.-2016-2026_es.xlsx",
        "originales/emal/EMAL.-Barrios-Municipios.-2016-2026_es.xlsx",
    )

    eustat_originales = (
        "eustat_distribucion_renta_municipal.json",
        "eustat_distribucion_renta_por_edad.json",
        "eustat_indicadores_municipales.json",
        "eustat_percentiles_renta_municipales.json",
        "eustat_renta_por_edad.json",
        "eustat_renta_por_municipio.json",
        "metadatos_distribucion_renta_municipal.json",
        "metadatos_distribucion_renta_por_edad.json",
        "metadatos_indicadores_municipales.json",
        "metadatos_percentiles_renta_municipales.json",
        "metadatos_renta_por_edad.json",
        "metadatos_renta_por_municipio.json",
    )
    for filename in eustat_originales:
        add_file(
            Path("DatosIker") / "originales" / filename,
            f"originales/eustat/{filename}",
        )

    fotocasa_originales = PROJECT_ROOT / "DatosIker" / "originales" / "fotocasa"
    if not fotocasa_originales.is_dir():
        raise FileNotFoundError(
            f"No existe la carpeta de originales: {fotocasa_originales}"
        )

    html_files = sorted(fotocasa_originales.rglob("*.html"))
    excluded_html = []
    for path in html_files:
        if _html_exclusion_reason(path, fotocasa_originales):
            excluded_html.append(path)
            continue
        relative_html_path = path.relative_to(fotocasa_originales)
        add_file(
            path.relative_to(PROJECT_ROOT),
            f"originales/fotocasa/{relative_html_path.as_posix()}",
        )
    if not any(item["local_path"].suffix.lower() == ".html" for item in files):
        raise FileNotFoundError("No se encontraron HTML válidos de Fotocasa.")

    for filename in (
        "Demandantes-Etxebide-Municipio-2026-04-01_limpio.csv",
        "Demandantes-Etxebide-Municipio-2026-07-01_limpio.csv",
    ):
        add_file(
            Path("DatosAlvaro") / "Vivienda" / "VPO" / filename,
            f"originales/etxebide/{filename}",
        )

    add_file(
        Path("DatosAlvaro") / "Salario" / "iovj-empleo-economico.csv",
        "originales/otras_fuentes/iovj-empleo-economico.csv",
    )
    add_file(
        Path("DatosAlvaro") / "Vivienda" / "pisos_euskadi.csv",
        "originales/pisos/pisos_euskadi.csv",
    )

    missing_files = [
        str(item["local_path"])
        for item in files
        if not item["local_path"].is_file()
    ]
    if missing_files:
        raise FileNotFoundError(
            "Faltan archivos requeridos:\n  " + "\n  ".join(missing_files)
        )

    empty_files = [
        str(item["local_path"])
        for item in files
        if item["local_path"].stat().st_size == 0
    ]
    if empty_files:
        raise ValueError("Hay archivos vacíos:\n  " + "\n  ".join(empty_files))

    for item in files:
        path = item["local_path"]
        if path.suffix.lower() == ".json":
            with path.open("r", encoding="utf-8-sig") as source:
                json.load(source)
        elif path.suffix.lower() == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as source:
                header = next(
                    (
                        row
                        for row in csv.reader(source)
                        if any(cell.strip() for cell in row)
                    ),
                    None,
                )
            if not header:
                raise ValueError(f"El CSV no tiene encabezado: {path}")

    destinations = [item["hdfs_relative"] for item in files]
    if len(destinations) != len(set(destinations)):
        raise ValueError("El manifiesto contiene destinos HDFS duplicados.")

    return files, excluded_html


def enviar_evento_kafka(producer, topic, run_id, event, delivery_errors):
    payload = json.dumps(event, ensure_ascii=False).encode("utf-8")

    def delivery_report(error, message):
        if error is not None:
            delivery_errors.append(str(error))

    while True:
        try:
            producer.produce(
                topic,
                key=run_id.encode("utf-8"),
                value=payload,
                callback=delivery_report,
            )
            return
        except BufferError:
            producer.poll(0.5)


def procesar_y_enviar_archivos(
    producer, topic, run_id, files, hdfs_client, hdfs_root
):
    hdfs_directories = sorted(
        {str(PurePosixPath(item["hdfs_relative"]).parent) for item in files}
    )
    for relative_directory in hdfs_directories:
        hdfs_client.makedirs(str(hdfs_root / relative_directory))

    files_to_upload = []
    already_present = []
    for item in files:
        remote_path = hdfs_root / PurePosixPath(item["hdfs_relative"])
        remote_status = hdfs_client.status(str(remote_path), strict=False)
        if remote_status is not None and remote_status["type"] != "FILE":
            raise IsADirectoryError(
                f"El destino HDFS existe pero no es un archivo: {remote_path}"
            )
        local_size = item["local_path"].stat().st_size
        if remote_status is not None and remote_status["length"] == local_size:
            already_present.append(item)
        else:
            files_to_upload.append(item)

    print(f"Ya estaban en HDFS y se omiten: {len(already_present)}")
    print(f"Nuevos o de tamaño distinto para subir: {len(files_to_upload)}")

    file_specs = [
        {
            "path": item["hdfs_relative"],
            "chunks": math.ceil(item["local_path"].stat().st_size / CHUNK_SIZE),
        }
        for item in files_to_upload
    ]
    delivery_errors = []

    enviar_evento_kafka(
        producer,
        topic,
        run_id,
        {"run_id": run_id, "type": "start", "files": file_specs},
        delivery_errors,
    )

    chunks_sent = 0
    for item in files_to_upload:
        relative_path = item["hdfs_relative"]
        with item["local_path"].open("rb") as source:
            chunk_index = 0
            while True:
                chunk = source.read(CHUNK_SIZE)
                if not chunk:
                    break
                enviar_evento_kafka(
                    producer,
                    topic,
                    run_id,
                    {
                        "run_id": run_id,
                        "type": "chunk",
                        "path": relative_path,
                        "index": chunk_index,
                        "data": base64.b64encode(chunk).decode("ascii"),
                    },
                    delivery_errors,
                )
                chunk_index += 1
                chunks_sent += 1

    enviar_evento_kafka(
        producer,
        topic,
        run_id,
        {"run_id": run_id, "type": "done"},
        delivery_errors,
    )
    pending = producer.flush(120)
    if pending:
        raise TimeoutError(f"Quedaron {pending} mensajes sin confirmar en Kafka.")
    if delivery_errors:
        raise RuntimeError("Errores de entrega Kafka: " + "; ".join(delivery_errors))

    print(
        f"Kafka confirmó {chunks_sent} fragmentos para "
        f"{len(files_to_upload)} archivos."
    )


def main():
    global PROJECT_ROOT

    from confluent_kafka import KafkaError, KafkaException, Producer

    configuracion = obtener_configuracion()
    usuario = configuracion["USUARIO"]
    kafka_broker = configuracion["KAFKA_BROKER"]
    hdfs_url = configuracion["HDFS_URL"]
    hdfs_root = configuracion["HDFS_ROOT"]
    topic = configuracion["KAFKA_TOPIC"]
    run_id = uuid.uuid4().hex

    if not hdfs_root.is_absolute() or ".." in hdfs_root.parts:
        raise ValueError("HDFS_ROOT debe ser una ruta HDFS absoluta sin '..'.")

    project_candidates = (Path.cwd(), *Path.cwd().parents)
    PROJECT_ROOT = next(
        (
            path
            for path in project_candidates
            if (path / "DatosIker").is_dir() and (path / "DatosAlvaro").is_dir()
        ),
        None,
    )
    if PROJECT_ROOT is None:
        raise FileNotFoundError(
            "No se encuentra la raíz del proyecto. Ejecuta el script desde la "
            "carpeta Reto1 o ajusta PROJECT_ROOT manualmente."
        )

    print(f"Proyecto: {PROJECT_ROOT}")
    print(f"Kafka: {kafka_broker} | tópico: {topic}")
    print(f"WebHDFS: {hdfs_url} | destino: {hdfs_root}")
    print(f"Usuario HDFS: {usuario}")

    files, excluded_html = recolectar_archivos_locales()
    print(f"Archivos originales validados: {len(files)}")
    print(f"HTML excluidos por notFound/pruebas: {len(excluded_html)}")
    print(
        f"Tamaño total: "
        f"{sum(item['local_path'].stat().st_size for item in files):,} bytes"
    )

    hdfs_client = conectar_hdfs(hdfs_url, usuario)
    print("Conexión WebHDFS correcta; carpetas de la raíz:", hdfs_client.list("/"))

    producer = Producer(
        {
            "bootstrap.servers": kafka_broker,
            "client.id": socket.gethostname(),
        }
    )
    leader_deadline = time.monotonic() + 60
    leader_warning_shown = False
    while True:
        try:
            metadata = producer.list_topics(topic=topic, timeout=15)
        except KafkaException as error:
            raise RuntimeError(
                f"No se pudo consultar Kafka en {kafka_broker}; comprueba el "
                "broker y la conectividad de red."
            ) from error

        topic_metadata = metadata.topics.get(topic)
        if topic_metadata is None:
            raise RuntimeError(f"Kafka no devolvió metadatos para el tópico {topic}.")
        if topic_metadata.error is not None:
            topic_error = topic_metadata.error
            retry_leader = topic_error.code() == KafkaError.LEADER_NOT_AVAILABLE
            if not retry_leader:
                raise RuntimeError(
                    f"Kafka no puede acceder al tópico {topic}: {topic_error}. "
                    "Comprueba el nombre del tópico y los permisos del usuario."
                )
        else:
            if not topic_metadata.partitions:
                raise RuntimeError(f"El tópico Kafka {topic} no tiene particiones.")
            unavailable_partitions = [
                partition_id
                for partition_id, partition in topic_metadata.partitions.items()
                if partition.leader == -1 or partition.error is not None
            ]
            if not unavailable_partitions:
                break

        if time.monotonic() >= leader_deadline:
            raise TimeoutError(
                f"Kafka sigue sin asignar un líder disponible al tópico {topic} "
                "tras 60 segundos. No se enviaron archivos. Comprueba con el "
                "administrador que el tópico tenga particiones y sus brokers "
                "estén activos."
            )
        if not leader_warning_shown:
            print(f"El tópico {topic} aún no tiene líder disponible; reintentando...")
            leader_warning_shown = True
        time.sleep(5)

    print(f"Kafka listo: {topic}, {len(topic_metadata.partitions)} partición(es).")
    procesar_y_enviar_archivos(
        producer,
        topic,
        run_id,
        files,
        hdfs_client,
        hdfs_root,
    )


if __name__ == "__main__":
    main()
