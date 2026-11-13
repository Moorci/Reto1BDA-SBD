from __future__ import annotations

import argparse
import hashlib
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from .funciones import conectar_hdfs, obtener_configuracion
except ImportError:  # pragma: no cover
    from funciones import conectar_hdfs, obtener_configuracion


CHUNK_SIZE = 1024 * 1024
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_ROOT = PROJECT_ROOT / "DatosIker" / "procesados"


def collect_processed_files(source_root: Path = PROCESSED_ROOT) -> list[Path]:
    if not source_root.is_dir():
        raise FileNotFoundError(f"No existe la carpeta procesada: {source_root}")

    files = sorted(source_root.rglob("*"))
    files = [path for path in files if path.is_file()]
    if not files:
        raise FileNotFoundError(f"No hay archivos procesados en {source_root}")

    for path in files:
        if path.is_symlink():
            raise ValueError(f"No se admiten enlaces simbólicos: {path}")
        if path.stat().st_size == 0:
            raise ValueError(f"El archivo procesado está vacío: {path}")
        path.relative_to(source_root)
    return files


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while True:
            chunk = source.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _sha256_hdfs(client: Any, hdfs_path: str) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with client.read(hdfs_path, chunk_size=CHUNK_SIZE) as source:
        for chunk in source:
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def upload_processed_files(
    client: Any,
    source_root: Path = PROCESSED_ROOT,
    hdfs_root: PurePosixPath | None = None,
) -> list[dict[str, Any]]:
    if hdfs_root is None:
        hdfs_root = obtener_configuracion()["HDFS_ROOT"]
    if not hdfs_root.is_absolute() or ".." in hdfs_root.parts:
        raise ValueError("HDFS_ROOT debe ser una ruta absoluta sin '..'.")

    destination_root = hdfs_root / "procesados"
    results = []
    for local_path in collect_processed_files(source_root):
        relative_path = PurePosixPath(local_path.relative_to(source_root).as_posix())
        remote_path = destination_root / relative_path
        remote_name = str(remote_path)
        local_hash, local_size = _sha256_file(local_path)

        client.makedirs(str(remote_path.parent))
        existing = client.status(remote_name, strict=False)
        if existing is not None and existing["type"] != "FILE":
            raise IsADirectoryError(
                f"El destino HDFS no es un archivo: {remote_name}"
            )

        if existing is not None:
            remote_hash, remote_size = _sha256_hdfs(client, remote_name)
            if remote_size == local_size and remote_hash == local_hash:
                results.append(
                    {
                        "archivo": str(relative_path),
                        "bytes": local_size,
                        "estado": "sin_cambios",
                    }
                )
                continue

        client.upload(
            remote_name,
            str(local_path),
            overwrite=True,
            n_threads=1,
            chunk_size=CHUNK_SIZE,
        )
        remote_hash, remote_size = _sha256_hdfs(client, remote_name)
        if remote_size != local_size or remote_hash != local_hash:
            raise IOError(
                f"Falló la verificación SHA-256 tras subir {remote_name}: "
                f"local={local_size}/{local_hash}, "
                f"HDFS={remote_size}/{remote_hash}."
            )
        results.append(
            {
                "archivo": str(relative_path),
                "bytes": local_size,
                "estado": "subido",
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Copia DatosIker/procesados a HDFS/procesados y verifica "
            "cada archivo mediante SHA-256."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra el manifiesto sin conectarse ni escribir en HDFS.",
    )
    args = parser.parse_args()

    files = collect_processed_files()
    configuration = obtener_configuracion()
    hdfs_root = configuration["HDFS_ROOT"]
    print(f"Origen local: {PROCESSED_ROOT}")
    print(f"Destino HDFS: {hdfs_root / 'procesados'}")
    print(f"Archivos procesados: {len(files)}")
    print(f"Tamaño local total: {sum(path.stat().st_size for path in files):,} bytes")
    if args.dry_run:
        for path in files:
            print(f"  {path.relative_to(PROCESSED_ROOT)}")
        print("Dry-run completado; no se escribió en HDFS.")
        return

    client = conectar_hdfs(configuration["HDFS_URL"], configuration["USUARIO"])
    results = upload_processed_files(client, hdfs_root=hdfs_root)
    uploaded = sum(result["estado"] == "subido" for result in results)
    unchanged = sum(result["estado"] == "sin_cambios" for result in results)
    print(
        f"Verificados por SHA-256: {len(results)}; "
        f"subidos: {uploaded}; sin cambios: {unchanged}."
    )


if __name__ == "__main__":
    main()
