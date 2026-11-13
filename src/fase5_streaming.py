from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from kafka import KafkaConsumer, KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic
from pymongo import MongoClient
from pymongo.database import Database

try:
    from .HDFS.funciones import conectar_hdfs, obtener_configuracion
    from .config import MONGO_URI, PHASE3_DATABASE_NAME
    from .transformar import normalize_string, to_float
except ImportError:  # pragma: no cover
    from HDFS.funciones import conectar_hdfs, obtener_configuracion
    from config import MONGO_URI, PHASE3_DATABASE_NAME
    from transformar import normalize_string, to_float


COLLECTION_NAME = "anuncios_stream_fase5"
REQUIRED_COLUMNS = {
    "fecha_extraccion",
    "operacion",
    "provincia",
    "titulo",
    "localidad_zona",
    "precio_eur",
    "habitaciones",
    "banos",
    "metros_m2",
    "precio_m2",
    "url",
}
NUMERIC_FIELDS = ("precio_eur", "habitaciones", "banos", "metros_m2", "precio_m2")
IDLE_TIMEOUT_SECONDS = 180


def _topic_name() -> str:
    return os.getenv("KAFKA_TOPIC_ANUNCIOS", "reto1_anuncios_iabd-user11")


def _serialize_event(event: dict[str, Any]) -> bytes:
    return json.dumps(event, ensure_ascii=False, allow_nan=False).encode("utf-8")


def _source_path(configuration: dict[str, Any]) -> str:
    return str(configuration["HDFS_ROOT"] / "originales/pisos/pisos_euskadi.csv")


def _number(value: Any, field: str) -> int | float | None:
    text = normalize_string(value)
    if text is None:
        return None
    parsed = to_float(text)
    if parsed is None or parsed < 0:
        raise ValueError(f"{field}: valor numérico inválido: {value!r}")
    if parsed.is_integer():
        return int(parsed)
    return parsed


def _announcement(
    row: dict[str, str], row_number: int, source_path: str
) -> dict[str, Any]:
    url = normalize_string(row.get("url"))
    if not url:
        raise ValueError(f"Anuncio sin URL en la fila {row_number}.")
    data: dict[str, Any] = {
        "event_id": hashlib.sha256(url.encode("utf-8")).hexdigest(),
        "fuente": "Pisos.com",
        "tipo_evento": "reproduccion_historica",
        "archivo_origen": source_path,
        "fila_origen": row_number,
        "fecha_extraccion": normalize_string(row.get("fecha_extraccion")),
        "operacion": normalize_string(row.get("operacion")),
        "provincia": normalize_string(row.get("provincia")),
        "titulo": normalize_string(row.get("titulo")),
        "localidad_zona": normalize_string(row.get("localidad_zona")),
        "url": url,
    }
    data.update(
        {field: _number(row.get(field), field) for field in NUMERIC_FIELDS}
    )
    return data


def _prepare_announcements(
    rows: Iterable[dict[str, str]], source_path: str
) -> list[dict[str, Any]]:
    announcements = []
    seen_ids = set()
    for row_number, row in enumerate(rows, start=2):
        data = _announcement(row, row_number, source_path)
        if data["event_id"] in seen_ids:
            raise ValueError(f"URL duplicada en la fila {row_number}.")
        seen_ids.add(data["event_id"])
        announcements.append(data)
    if not announcements:
        raise ValueError("El CSV de anuncios no contiene registros.")
    return announcements


def _read_hdfs_announcements(configuration: dict[str, Any]) -> list[dict[str, Any]]:
    hdfs_path = _source_path(configuration)
    client = conectar_hdfs(configuration["HDFS_URL"], configuration["USUARIO"])
    with client.read(hdfs_path, encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        columns = set(reader.fieldnames or [])
        missing_columns = sorted(REQUIRED_COLUMNS - columns)
        if missing_columns:
            raise ValueError(
                f"Faltan columnas en {hdfs_path}: {', '.join(missing_columns)}"
            )
        announcements = _prepare_announcements(reader, hdfs_path)
    print(f"HDFS: leídos {len(announcements)} anuncios de {hdfs_path}.")
    return announcements


def _topic_exists(broker: str, topic: str) -> bool:
    consumer = KafkaConsumer(
        bootstrap_servers=[broker],
        request_timeout_ms=10000,
    )
    try:
        return topic in consumer.topics()
    finally:
        consumer.close()


def ensure_topic(broker: str, topic: str) -> None:
    if _topic_exists(broker, topic):
        print(f"Kafka: el tópico {topic} ya existe.")
        return

    admin = KafkaAdminClient(
        bootstrap_servers=[broker],
        client_id="reto1-fase5-admin",
        request_timeout_ms=10000,
    )
    try:
        result = admin.create_topics(
            [NewTopic(topic, num_partitions=1, replication_factor=1)],
            timeout_ms=15000,
            wait_for_metadata=True,
        )
    finally:
        admin.close()

    topic_result = result["topics"][0]
    if topic_result["error_code"] != 0 and not _topic_exists(broker, topic):
        raise RuntimeError(
            f"No se pudo crear el tópico {topic}: "
            f"{topic_result['error_message'] or topic_result['error_code']}"
        )
    print(f"Kafka: tópico {topic} disponible.")


def produce_batch(configuration: dict[str, Any]) -> None:
    broker = configuration["KAFKA_BROKER"]
    topic = _topic_name()
    ensure_topic(broker, topic)
    announcements = _read_hdfs_announcements(configuration)
    run_id = uuid.uuid4().hex

    producer = KafkaProducer(
        bootstrap_servers=[broker],
        client_id="reto1-fase5-productor",
        acks="all",
        retries=5,
    )
    futures = []
    try:
        futures.append(
            producer.send(
                topic,
                key=run_id.encode("utf-8"),
                value=_serialize_event({
                    "tipo": "inicio_lote",
                    "run_id": run_id,
                    "esperados": len(announcements),
                    "archivo_origen": _source_path(configuration),
                }),
            )
        )
        for announcement in announcements:
            futures.append(
                producer.send(
                    topic,
                    key=run_id.encode("utf-8"),
                    value=_serialize_event({
                        "tipo": "anuncio",
                        "run_id": run_id,
                        "datos": announcement,
                    }),
                )
            )
        futures.append(
            producer.send(
                topic,
                key=run_id.encode("utf-8"),
                value=_serialize_event({"tipo": "fin_lote", "run_id": run_id}),
            )
        )
        producer.flush(timeout=30)
        for future in futures:
            future.get(timeout=30)
    finally:
        producer.close(timeout=30)

    print(
        f"Kafka: enviados y confirmados {len(announcements)} anuncios; "
        f"run_id={run_id}, tópico={topic}."
    )


def _validate_event(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("El mensaje de anuncio no contiene un objeto JSON.")
    url = normalize_string(data.get("url"))
    event_id = data.get("event_id")
    expected_id = hashlib.sha256(url.encode("utf-8")).hexdigest() if url else None
    if not isinstance(event_id, str) or event_id != expected_id:
        raise ValueError("El event_id no corresponde a la URL del anuncio.")
    if data.get("fuente") != "Pisos.com":
        raise ValueError("Fuente no reconocida en el anuncio.")
    if data.get("tipo_evento") != "reproduccion_historica":
        raise ValueError("El anuncio no está marcado como reproducción histórica.")
    for field in NUMERIC_FIELDS:
        value = data.get(field)
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError(f"{field}: tipo o valor no válido.")
    return data


def _upsert_announcement(
    database: Database, data: dict[str, Any]
) -> bool:
    document = {
        **data,
        "_id": data["event_id"],
        "fecha_ingesta": datetime.now(timezone.utc),
    }
    result = database[COLLECTION_NAME].update_one(
        {"_id": data["event_id"]},
        {"$setOnInsert": document},
        upsert=True,
    )
    return result.upserted_id is not None


def consume_batch(
    configuration: dict[str, Any], timeout_seconds: int = IDLE_TIMEOUT_SECONDS
) -> None:
    broker = configuration["KAFKA_BROKER"]
    topic = _topic_name()
    if not _topic_exists(broker, topic):
        raise RuntimeError(
            f"No existe el tópico {topic}; ejecuta primero la acción crear-topic."
        )

    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=[broker],
        client_id="reto1-fase5-consumidor",
        group_id=f"reto1-fase5-{uuid.uuid4().hex}",
        auto_offset_reset="latest",
        enable_auto_commit=False,
        request_timeout_ms=10000,
    )
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
        database = client[PHASE3_DATABASE_NAME]
        deadline = time.monotonic() + 30
        while not consumer.assignment():
            consumer.poll(timeout_ms=500)
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Kafka no asignó particiones para {topic}.")
        print(f"Kafka: consumidor listo en {topic}; esperando el lote.")

        run_id = None
        expected_count = None
        seen_ids = set()
        inserted_count = 0
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            records = consumer.poll(timeout_ms=1000)
            for partition_records in records.values():
                for message in partition_records:
                    event = json.loads(message.value.decode("utf-8"))
                    if not isinstance(event, dict):
                        raise ValueError("Kafka entregó un evento JSON no válido.")
                    if run_id is None:
                        if event.get("tipo") != "inicio_lote":
                            continue
                        run_id = event.get("run_id")
                        expected_count = event.get("esperados")
                        if (
                            not isinstance(run_id, str)
                            or not run_id
                            or isinstance(expected_count, bool)
                            or not isinstance(expected_count, int)
                            or expected_count <= 0
                        ):
                            raise ValueError("El manifiesto del lote no es válido.")
                        deadline = time.monotonic() + timeout_seconds
                        continue

                    if event.get("run_id") != run_id:
                        continue
                    deadline = time.monotonic() + timeout_seconds
                    if event.get("tipo") == "anuncio":
                        data = _validate_event(event.get("datos"))
                        if data["event_id"] in seen_ids:
                            continue
                        seen_ids.add(data["event_id"])
                        inserted_count += int(_upsert_announcement(database, data))
                    elif event.get("tipo") == "fin_lote":
                        if len(seen_ids) != expected_count:
                            raise RuntimeError(
                                f"Lote incompleto: recibidos {len(seen_ids)} de "
                                f"{expected_count} anuncios."
                            )
                        consumer.commit()
                        print(
                            f"MongoDB: recibidos={len(seen_ids)}, "
                            f"insertados={inserted_count}, "
                            f"ya_existentes={len(seen_ids) - inserted_count}; "
                            f"colección={PHASE3_DATABASE_NAME}.{COLLECTION_NAME}."
                        )
                        return
                    else:
                        raise ValueError(
                            f"Tipo de evento desconocido: {event.get('tipo')!r}"
                        )
        raise TimeoutError(
            f"No se completó el lote Kafka en {timeout_seconds} segundos."
        )
    finally:
        consumer.close()
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Flujo de reproducción Pisos.com desde HDFS por Kafka a MongoDB."
    )
    parser.add_argument(
        "accion",
        choices=("crear-topic", "productor", "consumidor"),
        help="Crear el tópico o ejecutar un extremo del flujo.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=IDLE_TIMEOUT_SECONDS,
        help="Segundos máximos que espera el consumidor (por defecto: 180).",
    )
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout debe ser mayor que cero.")

    configuration = obtener_configuracion()
    topic = _topic_name()
    if args.accion == "crear-topic":
        ensure_topic(configuration["KAFKA_BROKER"], topic)
    elif args.accion == "productor":
        produce_batch(configuration)
    else:
        consume_batch(configuration, timeout_seconds=args.timeout)


if __name__ == "__main__":
    main()
