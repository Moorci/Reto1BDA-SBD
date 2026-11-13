# Estructura de datos en HDFS — Reto 1

## Objetivo

Mantener separados los archivos originales y los conjuntos procesados. No subir scripts, backups, archivos temporales ni informes/gráficos a estas zonas de datos.

Los comandos de este documento asumen un entorno local `.venv` creado desde
PowerShell con `py -3.12 -m venv .venv` e instalado mediante
`python -m pip install -r requirements.txt`; no es necesario entregar `.conda`.

La raíz puede ser, por ejemplo, `/user/<usuario>/reto1`. Dentro de ella se crea:

```text
/user/<usuario>/reto1/
├── originales/
│   ├── emal/
│   ├── eustat/
│   ├── etxebide/
│   ├── fotocasa/
│   ├── otras_fuentes/
│   └── pisos/
└── procesados/
    ├── etxebide/
    ├── eustat/
    ├── fotocasa/
    └── pisoscom/
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

## Archivos procesados — `procesados`

La carpeta `DatosIker/procesados` se conserva en HDFS con su estructura
relativa. La carga verificada contiene **21 archivos (205.376.874 bytes)**:

- EMAL: `emal_alquiler_anual_municipios.json` y
  `emal_alquiler_vigente_municipios.json`.
- Etxebide: las dos fotografías con código municipal, abril y julio de 2026.
- Eustat: cuatro conjuntos de renta personal municipal.
- Fotocasa: doce CSV/JSON; se conservan piloto, complemento y versiones de
  10, 241 y 251 municipios, sin sustituir unos por otros.
- Pisos.com: `pisos_euskadi_geolocalizado.csv`.

Los originales permanecen en `originales/`; esta carga no los modifica.

## Carga

El notebook [`src/HDFS/subir_archivos_kafka_hdfs.ipynb`](./src/HDFS/subir_archivos_kafka_hdfs.ipynb) valida y envía el manifiesto por Kafka en fragmentos; después reconstruye los archivos en HDFS. Ejecutar sus celdas en orden y configurar los endpoints, usuario y tópico del proyecto. El usuario requiere permisos de productor/consumidor en Kafka y escritura en la raíz HDFS configurada.

Antes de enviar archivos por Kafka, el notebook compara cada ruta existente con el tamaño del archivo local. Si el destino existe y el tamaño coincide, lo omite; los archivos nuevos o con tamaño diferente sí se envían y el destino se actualiza en la misma ruta. Así, una segunda ejecución normal no vuelve a transferir los archivos ya cargados. La comprobación se basa en tamaño, no en hash: si cambia el contenido pero conserva exactamente el mismo tamaño, se considera ya cargado.

La celda de carga de originales crea solo las carpetas padre que necesita el
manifiesto, bajo `originales/`.

Los conjuntos procesados se cargan por WebHDFS con
[`src/HDFS/subir_procesados.py`](./src/HDFS/subir_procesados.py):

```powershell
.\.venv\Scripts\python.exe -B .\src\HDFS\subir_procesados.py --dry-run
.\.venv\Scripts\python.exe -B .\src\HDFS\subir_procesados.py
```

El script escribe bajo `procesados/`, conserva los subdirectorios locales y
compara SHA-256 antes de omitir archivos existentes. Tras cada carga verifica
tamaño y SHA-256 del archivo remoto. En la ejecución confirmada, los 21
archivos sumaron 205.376.874 bytes; 20 se subieron y uno ya estaba idéntico.
La verificación recursiva posterior encontró 21 archivos bajo HDFS
`procesados/`.

La carga indicada es para preparar una instalación nueva. En el entorno de
este proyecto ya existen los originales y procesados verificados; no se deben
volver a subir durante la demostración. Para inspección de solo lectura,
usar `.\.venv\Scripts\python.exe -B -m src.HDFS.verificar_hdfs` o consultar el
paso HDFS del [guion de defensa](./entrega/guion_demo.md).

## Fase 5 — flujo Kafka a MongoDB

La carga de originales y procesados ya se ejecutó y verificó; no se debe
repetir la carga de originales para ejecutar el flujo de anuncios. El productor de
[`src/fase5_streaming.py`](./src/fase5_streaming.py) lee el CSV original de
Pisos.com desde HDFS, publica el lote JSON en Kafka y el consumidor lo guarda
en `reto_vivienda_fase3.anuncios_stream_fase5`. La colección canónica
`anuncios_pisoscom` no se modifica.

Crear o verificar el tópico desde la raíz del proyecto:

```powershell
.\.venv\Scripts\python.exe -B .\src\fase5_streaming.py crear-topic
```

En una primera terminal, iniciar el consumidor:

```powershell
.\.venv\Scripts\python.exe -u -B .\src\fase5_streaming.py consumidor
```

Cuando indique que está listo, ejecutar en una segunda terminal:

```powershell
.\.venv\Scripts\python.exe -u -B .\src\fase5_streaming.py productor
```

La verificación del flujo y sus recuentos están en
[`DatosIker/informes/flujo_hdfs_kafka_mongodb_fase5.txt`](./DatosIker/informes/flujo_hdfs_kafka_mongodb_fase5.txt).
