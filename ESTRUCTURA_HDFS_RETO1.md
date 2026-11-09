# Estructura de originales en HDFS — Reto 1

## Objetivo

Guardar en HDFS únicamente los archivos originales recopilados para el análisis. No crear carpetas `processed` ni `reports`. No subir scripts, backups, archivos temporales ni datos intermedios.

La raíz puede ser, por ejemplo, `/user/<usuario>/reto1`. Dentro de ella se crea:

```text
/user/<usuario>/reto1/
└── originales/
    ├── emal/
    ├── eustat/
    ├── etxebide/
    ├── fotocasa/
    ├── otras_fuentes/
    └── pisos/
```

## Archivos incluidos

### Fotocasa — `originales/fotocasa`

- `MunicipiosCAE_2025_19_02.xlsx`, catálogo oficial empleado para identificar municipios.
- HTML originales de municipios que se extrajeron correctamente.
- Se excluyen HTML que contienen `notFound`, backups y archivos de prueba.
- Se conserva la subcarpeta `masiva` cuando exista.

No subir las series históricas ni el catálogo CSV procesado.

### EMAL — `originales/emal`

- `EMAL.-Barrios-Municipios.-2016-2026_es.xlsx`, original utilizado para procesar los datos.

No subir los JSON procesados de alquiler anual o vigente.

### Eustat — `originales/eustat`

Originales JSON descargados y metadatos asociados:

- `eustat_distribucion_renta_municipal.json`
- `eustat_distribucion_renta_por_edad.json`
- `eustat_indicadores_municipales.json`
- `eustat_percentiles_renta_municipales.json`
- `eustat_renta_por_edad.json`
- `eustat_renta_por_municipio.json`
- Sus archivos `metadatos_*.json` disponibles.

### Etxebide — `originales/etxebide`

Guardar ambos archivos disponibles, sin sobrescribir una fecha con otra:

- `Demandantes-Etxebide-Municipio-2026-04-01_limpio.csv`
- `Demandantes-Etxebide-Municipio-2026-07-01_limpio.csv`

Aunque están procesados/limpios, para esta entrega se guardan bajo `originales`, según el criterio acordado para la carga.

### Otras fuentes — `originales/otras_fuentes`

- `iovj-empleo-economico.csv`

### Pisos — `originales/pisos`

- `pisos_euskadi.csv`

Se incluye en HDFS por decisión del proyecto aunque todavía se deban tener presentes las advertencias de calidad y asignación geográfica al analizarlo.

## Carga

El notebook [`src/HDFS/subir_archivos_kafka_hdfs.ipynb`](./src/HDFS/subir_archivos_kafka_hdfs.ipynb) valida y envía el manifiesto por Kafka en fragmentos; después reconstruye los archivos en HDFS. Ejecutar sus celdas en orden y configurar los endpoints, usuario y tópico del proyecto. El usuario requiere permisos de productor/consumidor en Kafka y escritura en la raíz HDFS configurada.

Antes de enviar archivos por Kafka, el notebook compara cada ruta existente con el tamaño del archivo local. Si el destino existe y el tamaño coincide, lo omite; los archivos nuevos o con tamaño diferente sí se envían y el destino se actualiza en la misma ruta. Así, una segunda ejecución normal no vuelve a transferir los archivos ya cargados. La comprobación se basa en tamaño, no en hash: si cambia el contenido pero conserva exactamente el mismo tamaño, se considera ya cargado.

La celda de carga crea solo las carpetas padre que necesita el manifiesto, bajo `originales/`. No elimina carpetas antiguas que pudieran existir en HDFS de ejecuciones anteriores; si ya se creó `processed` o `reports`, deben eliminarse aparte por una persona con permisos y únicamente si se confirma que no contienen datos que deban conservarse.
