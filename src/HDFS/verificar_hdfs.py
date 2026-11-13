from __future__ import annotations

import csv
from pathlib import PurePosixPath
from typing import Any

from .funciones import conectar_hdfs, obtener_configuracion
from .subir_procesados import (
    PROCESSED_ROOT,
    _sha256_file,
    _sha256_hdfs,
    collect_processed_files,
)
from ..fase5_streaming import REQUIRED_COLUMNS


def _remote_file_statuses(
    client: Any,
    root: PurePosixPath,
) -> dict[PurePosixPath, dict[str, Any]]:
    files: dict[PurePosixPath, dict[str, Any]] = {}
    for (directory, _), _, entries in client.walk(str(root), status=True):
        for filename, status in entries:
            path = PurePosixPath(directory) / filename
            relative_path = path.relative_to(root)
            files[relative_path] = status
    return files


def verify_hdfs() -> None:
    configuration = obtener_configuracion()
    client = conectar_hdfs(
        configuration["HDFS_URL"],
        configuration["USUARIO"],
    )
    hdfs_root = configuration["HDFS_ROOT"]
    original_root = hdfs_root / "originales"
    processed_root = hdfs_root / "procesados"
    original_files = _remote_file_statuses(client, original_root)
    remote_processed_files = _remote_file_statuses(client, processed_root)
    local_processed_files = {
        PurePosixPath(path.relative_to(PROCESSED_ROOT).as_posix()): path
        for path in collect_processed_files()
    }

    if not original_files:
        raise RuntimeError(f"No hay archivos originales en HDFS: {original_root}")
    if remote_processed_files.keys() != local_processed_files.keys():
        raise RuntimeError(
            "La lista de archivos procesados local y remota no coincide."
        )

    for relative_path, local_path in local_processed_files.items():
        hdfs_path = str(processed_root / relative_path)
        local_hash, local_size = _sha256_file(local_path)
        remote_hash, remote_size = _sha256_hdfs(client, hdfs_path)
        if remote_hash != local_hash or remote_size != local_size:
            raise IOError(
                f"El archivo procesado no coincide con HDFS: {relative_path}."
            )

    source_path = str(original_root / "pisos" / "pisos_euskadi.csv")
    with client.read(source_path, encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        missing_columns = sorted(REQUIRED_COLUMNS - set(reader.fieldnames or []))
        if missing_columns:
            raise ValueError(
                f"Faltan columnas en {source_path}: "
                f"{', '.join(missing_columns)}"
            )
        announcement_count = sum(1 for _ in reader)
    if announcement_count != 1041:
        raise RuntimeError(
            f"Se esperaban 1041 anuncios en el CSV de HDFS; "
            f"se encontraron {announcement_count}."
        )

    original_bytes = sum(status["length"] for status in original_files.values())
    processed_bytes = sum(
        status["length"] for status in remote_processed_files.values()
    )
    print(
        f"HDFS solo lectura: originales={len(original_files)} archivos, "
        f"{original_bytes} bytes; procesados={len(remote_processed_files)} "
        f"archivos, {processed_bytes} bytes, SHA-256 verificado; "
        f"CSV Pisos.com={announcement_count} anuncios recuperados."
    )


if __name__ == "__main__":
    verify_hdfs()
