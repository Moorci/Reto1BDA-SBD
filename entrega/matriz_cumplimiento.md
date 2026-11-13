# Matriz de cumplimiento del PDF

Estados: **Cumple** = hay implementación y evidencia de ejecución;
**Parcial** = hay trabajo realizado, pero falta un requisito del nivel máximo o
la evidencia completa; **Pendiente** = no hay evidencia suficiente.

Criterios revisados según el [PDF de evaluación](<../RETO 1Evaluacion SBD-BDA.pdf>).

## BDA — RA1

| Criterio del PDF | Estado | Evidencia y brecha |
|---|---|---|
| Extracción mediante Python | **Parcial** | Hay scraping automatizado de [Pisos.com](../DatosAlvaro/Vivienda/scraper_pisos.py) con `requests`/BeautifulSoup y consulta de páginas Fotocasa en [localizar_municipios_masivo.py](../DatosIker/scripts/fotocasa/localizar_municipios_masivo.py); las series se consolidan desde HTML guardado mediante [extraer_series_masivo.py](../DatosIker/scripts/fotocasa/extraer_series_masivo.py). No se implementa un cliente API; el usuario acepta esta brecha del criterio. |
| Almacenamiento HDFS | **Cumple** | Se verificaron 269 originales y 21 archivos procesados en carpetas separadas. Los procesados suman 205.376.874 bytes y cada archivo se comprobó por SHA-256; también se verificó la recuperación del CSV Pisos.com desde originales. |
| Kafka | **Cumple** | Productor y consumidor Python procesaron 1.041 eventos JSON en el tópico `reto1_anuncios_iabd-user11`. |
| Integración | **Cumple** | Se ejecutó el replay de anuncios HDFS → productor → Kafka → consumidor → `reto_vivienda_fase3.anuncios_stream_fase5`. Es un snapshot histórico, no una captación en tiempo real. |

## SBD — RA3

| Criterio del PDF | Estado | Evidencia |
|---|---|---|
| Modelado MongoDB | **Cumple** | Seis colecciones canónicas, referencias por código municipal y embedding limitado al catálogo; decisiones documentadas en el [informe de Fase 3](../DatosIker/informes/diseno_carga_mongodb_fase3.txt). |
| Operaciones PyMongo | **Cumple** | Insert, Find, Update y Delete se automatizan y verifican en un documento temporal que se elimina al finalizar. Cargas idempotentes mediante upsert. |
| Consultas | **Cumple** | Cinco consultas; incluyen filtros compuestos y campos anidados, con proyección y ordenación. |
| Aggregation Pipeline | **Cumple** | Tres pipelines ejecutados; combinan etapas y generan ranking, evolución y cruce de fuentes. |

## RA4 — Visualización y presentación

| Criterio del PDF | Estado | Evidencia y límites |
|---|---|---|
| Gráficos | **Cumple** | Siete SVG de tres tipos: líneas, barras comparativas y dispersión; se generan desde resultados PyMongo. |
| Datos utilizados | **Cumple** | Los conjuntos visuales se calculan consultando MongoDB; se exportan como CSV/JSON y se representan en SVG/HTML. |
| Presentación | **Cumple** | Gráficos con títulos, unidades y etiquetas/leyendas cuando procede; comparaciones municipales y fechas de referencia explícitas. |
| Interpretación | **Parcial** | Se calcula un escenario de alquiler municipal frente a remuneración juvenil regional y un cruce EMAL-Eustat municipal de 2024 para 71 municipios. La categoría Eustat «Renta del trabajo» no tiene desglose por edad ni equivale a salario neto; ninguno de los cocientes es una tasa individual observada. Las series Fotocasa repetidas limitan otros rankings. |

## Entregables

| Entregable | Estado | Evidencia |
|---|---|---|
| Código fuente | **Cumple** | Scripts Python en `src/` y scripts de extracción/procesado en `DatosIker/scripts/` y `DatosAlvaro/`. |
| Datos originales en HDFS y datos en MongoDB | **Cumple** | HDFS contiene originales y procesados en zonas separadas; MongoDB conserva las colecciones canónicas y la colección de replay. |
| Arquitectura | **Cumple** | [Diagrama de arquitectura](./arquitectura_reto1.svg). |
| Informe con gráficos, tablas y conclusiones | **Cumple** | [Informe final](./informe_final.md) y [análisis HTML de Fase 6](../resultados/fase6/informe_fase6.html). |
| Demostración | **Cumple** | [Guion reproducible](./guion_demo.md); los comandos de las fases 3, 4 y 6 se ejecutan localmente y Kafka requiere acceso a HDFS/Kafka. |

## Brechas prioritarias

1. La extracción API automatizada queda como brecha aceptada por decisión del
   usuario; no se presenta una descarga manual ni una API ajena al tema como si
   cumpliera el requisito.
2. No hay un salario juvenil municipal verificado. El cruce Eustat-EMAL utiliza
   renta personal media del trabajo de todos los grupos de edad; para
   conclusiones específicas sobre juventud haría falta una fuente municipal
   desglosada por edad. También deben tenerse en cuenta las series Fotocasa
   repetidas.
