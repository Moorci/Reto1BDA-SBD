import base64
import json
import tempfile
import time
import uuid
from pathlib import Path, PurePosixPath

from confluent_kafka import Consumer
from funciones import conectar_hdfs, obtener_configuracion


IDLE_TIMEOUT_SECONDS = 600


def esperar_asignacion_topic(consumer, topic):
    assignment_deadline = time.monotonic() + 30
    while not consumer.assignment():
        consumer.poll(0.5)
        if time.monotonic() >= assignment_deadline:
            consumer.close()
            raise TimeoutError(
                f"El tópico {topic} existe, pero Kafka no asignó particiones al "
                "consumidor. Comprueba ACL y errores de grupo del broker."
            )

    print("Consumidor Kafka preparado:", consumer.assignment())


def procesar_chunk_y_subir(
    event,
    temporary_root,
    hdfs_client,
    hdfs_root,
    expected_chunks,
    next_chunk,
    completed_files,
):
    relative_path = PurePosixPath(event["path"])
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError(f"Ruta de archivo no permitida: {relative_path}")
    path_key = relative_path.as_posix()
    if path_key not in expected_chunks:
        raise ValueError(f"Archivo no incluido en el manifiesto: {path_key}")

    index = event["index"]
    if index < next_chunk[path_key]:
        return
    if index != next_chunk[path_key]:
        raise ValueError(f"Fragmento fuera de orden para {path_key}: {index}")

    decoded_chunk = base64.b64decode(event["data"], validate=True)
    local_path = temporary_root.joinpath(*relative_path.parts)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with local_path.open("ab") as target:
        target.write(decoded_chunk)
    next_chunk[path_key] += 1

    if next_chunk[path_key] == expected_chunks[path_key]:
        remote_path = hdfs_root / relative_path
        hdfs_client.makedirs(str(remote_path.parent))
        hdfs_client.upload(str(remote_path), str(local_path), overwrite=True)
        if hdfs_client.status(str(remote_path), strict=False) is None:
            raise IOError(f"No se encontró el archivo en HDFS: {remote_path}")
        completed_files.add(path_key)
        print(f"Subido: {remote_path}")


def consumir_mensajes(consumer, hdfs_client, hdfs_root):
    run_id = None
    expected_chunks = {}
    next_chunk = {}
    completed_files = set()
    start_received = False
    done_received = False
    last_message_at = time.monotonic()

    try:
        with tempfile.TemporaryDirectory(prefix="reto1_hdfs_") as temporary_directory:
            temporary_root = Path(temporary_directory)
            while not (done_received and completed_files == set(expected_chunks)):
                message = consumer.poll(2.0)
                if message is None:
                    if time.monotonic() - last_message_at > IDLE_TIMEOUT_SECONDS:
                        raise TimeoutError(
                            "Kafka dejó de entregar mensajes antes de completar "
                            "la carga. Inicia primero consumidor.py y después "
                            "productor.py; revisa también el tópico y los logs."
                        )
                    continue
                if message.error():
                    raise RuntimeError(f"Error del consumidor Kafka: {message.error()}")

                event = json.loads(message.value().decode("utf-8"))
                if run_id is None:
                    if event.get("type") != "start":
                        continue
                    run_id = event.get("run_id")
                    if not isinstance(run_id, str) or not run_id:
                        raise ValueError("El manifiesto de Kafka no incluye un run_id.")
                if event.get("run_id") != run_id:
                    continue
                last_message_at = time.monotonic()

                if event["type"] == "start":
                    if start_received:
                        raise ValueError(
                            "Se recibió más de un manifiesto para la ejecución."
                        )
                    declared_files = event.get("files")
                    if not isinstance(declared_files, list):
                        raise ValueError(
                            "El manifiesto recibido por Kafka no es válido."
                        )

                    for entry in declared_files:
                        relative_path = PurePosixPath(entry["path"])
                        chunks = entry["chunks"]
                        if (
                            relative_path.is_absolute()
                            or ".." in relative_path.parts
                            or not relative_path.parts
                        ):
                            raise ValueError(
                                f"Ruta de archivo no permitida: {relative_path}"
                            )
                        if not isinstance(chunks, int) or chunks < 0:
                            raise ValueError(
                                f"Número de fragmentos no válido para {relative_path}."
                            )
                        path_key = relative_path.as_posix()
                        if path_key in expected_chunks:
                            raise ValueError(
                                f"Archivo duplicado en el manifiesto: {path_key}"
                            )
                        expected_chunks[path_key] = chunks
                        next_chunk[path_key] = 0
                    start_received = True

                elif event["type"] == "chunk":
                    if not start_received:
                        raise ValueError("Se recibió un fragmento antes del manifiesto.")
                    procesar_chunk_y_subir(
                        event,
                        temporary_root,
                        hdfs_client,
                        hdfs_root,
                        expected_chunks,
                        next_chunk,
                        completed_files,
                    )

                elif event["type"] == "done":
                    done_received = True
                    missing = sorted(set(expected_chunks) - completed_files)
                    if missing:
                        raise RuntimeError(
                            "Archivos no completados: " + ", ".join(missing)
                        )
                else:
                    raise ValueError(f"Tipo de evento Kafka desconocido: {event['type']}")
    finally:
        consumer.close()

    if not start_received:
        raise RuntimeError("No se recibió el manifiesto de esta ejecución.")

    return expected_chunks


def main():
    configuracion = obtener_configuracion()
    usuario = configuracion["USUARIO"]
    kafka_broker = configuracion["KAFKA_BROKER"]
    hdfs_url = configuracion["HDFS_URL"]
    hdfs_root = configuracion["HDFS_ROOT"]
    topic = configuracion["KAFKA_TOPIC"]
    group_id = f"grupo_reto1_{usuario}_{uuid.uuid4().hex}"

    if not hdfs_root.is_absolute() or ".." in hdfs_root.parts:
        raise ValueError("HDFS_ROOT debe ser una ruta HDFS absoluta sin '..'.")

    hdfs_client = conectar_hdfs(hdfs_url, usuario)
    print("Conexión WebHDFS correcta; carpetas de la raíz:", hdfs_client.list("/"))

    consumer = Consumer(
        {
            "bootstrap.servers": kafka_broker,
            "group.id": group_id,
            "auto.offset.reset": "latest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([topic])
    esperar_asignacion_topic(consumer, topic)
    print("Esperando el manifiesto del productor. Inicia ahora productor.py.")

    expected_chunks = consumir_mensajes(consumer, hdfs_client, hdfs_root)
    missing_in_hdfs = []
    for relative_path in expected_chunks:
        remote_path = hdfs_root / PurePosixPath(relative_path)
        if hdfs_client.status(str(remote_path), strict=False) is None:
            missing_in_hdfs.append(str(remote_path))

    if missing_in_hdfs:
        raise FileNotFoundError(
            "No aparecen en HDFS los siguientes archivos:\n  "
            + "\n  ".join(missing_in_hdfs)
        )

    print(
        f"Verificación correcta: {len(expected_chunks)} archivos comprobados "
        f"en {hdfs_root}."
    )
    print("Contenido de la raíz HDFS:", hdfs_client.list(str(hdfs_root)))


if __name__ == "__main__":
    main()
