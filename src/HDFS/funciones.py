import os
from pathlib import PurePosixPath

from hdfs import InsecureClient


def obtener_configuracion():
    usuario = os.getenv("HDFS_USER", "iabd-user11")
    return {
        "USUARIO": usuario,
        "KAFKA_BROKER": os.getenv("KAFKA_BROKER", "10.22.87.215:9092"),
        "HDFS_URL": os.getenv("HDFS_URL", "http://10.22.87.215:50070"),
        "HDFS_ROOT": PurePosixPath(
            os.getenv("HDFS_ROOT", f"/user/{usuario}/reto1")
        ),
        "KAFKA_TOPIC": os.getenv("KAFKA_TOPIC", f"reto1_archivos_{usuario}"),
    }


def conectar_hdfs(url, usuario):
    return InsecureClient(url, user=usuario)
