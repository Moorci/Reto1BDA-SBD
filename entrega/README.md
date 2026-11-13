# Entrega — ¿Dónde pueden vivir los jóvenes en Euskadi?

Paquete de documentación para presentar el Reto 1 de BDA y SBD. El estado de
la evaluación corresponde al PDF del reto y a las ejecuciones registradas en
los informes de las fases anteriores.

## Contenido

- [Informe final](./informe_final.md): datos, resultados, interpretación y límites.
- [Arquitectura](./arquitectura_reto1.svg): recorrido real de los datos.
- [Matriz de cumplimiento](./matriz_cumplimiento.md): estado por criterio del PDF.
- [Guion de demostración](./guion_demo.md): pasos y comandos para Windows.
- [Informe interactivo de Fase 6](../resultados/fase6/informe_fase6.html).

## Ejecución breve

Desde PowerShell, en la raíz del proyecto:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
.\.venv\Scripts\python.exe -B .\src\cargar_mongodb_fase3.py --dry-run
.\.venv\Scripts\python.exe -B .\src\cargar_mongodb_fase3.py
.\.venv\Scripts\python.exe -B .\src\crud_demostracion_fase3.py
.\.venv\Scripts\python.exe -B .\src\consultas_fase4.py
.\.venv\Scripts\python.exe -B .\src\cargar_salarios_regionales.py --dry-run
.\.venv\Scripts\python.exe -B .\src\cargar_salarios_regionales.py
.\.venv\Scripts\python.exe -B .\src\analisis_fase6.py
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Se recomienda Python 3.12; `requirements.txt` recoge las dependencias de los
scripts, Excel, scraping, HDFS, Kafka y MongoDB. Los gráficos SVG se generan
con código propio y no requieren una biblioteca de gráficos. Las pruebas usan
`unittest` de la biblioteca estándar. `requirements-fase5.txt` contiene el
subconjunto para el flujo principal de esa fase; la extensión nativa
`confluent-kafka` solo es necesaria para la utilidad histórica
`src/HDFS/consumidor.py` y está separada en
`requirements-optional-legacy.txt`.

MongoDB debe instalarse y arrancarse por separado. Por defecto, el código
utiliza `mongodb://localhost:27017`; `MONGO_URI` permite cambiar el endpoint,
y `MONGO_DB` selecciona la base auxiliar de referencias salariales (por defecto
`reto_vivienda`). La base canónica de vivienda se fija en
`reto_vivienda_fase3`. No guardes credenciales en el código ni en el paquete.

HDFS y Kafka son servicios externos opcionales para ejecutar la Fase 5. Deben
estar accesibles desde la red del equipo; el proyecto admite `HDFS_URL`,
`HDFS_USER`, `HDFS_ROOT`, `KAFKA_BROKER` y `KAFKA_TOPIC`. No se da por hecho
que estén instalados o arrancados. La descarga de datos o el scraping no forma
parte de la demostración reproducible y no se debe repetir innecesariamente.
El procedimiento por fases está en el [guion PowerShell](./guion_demo.md).

## Decisiones para la entrega

- Los datos canónicos de vivienda están en `reto_vivienda_fase3`. Fase 6
  consulta además las dos fuentes salariales regionales en `reto_vivienda`
  (o en la base indicada por `MONGO_DB`); el cargador focalizado no recarga las
  demás fuentes.
- Los códigos municipales se mantienen como texto de cinco caracteres.
- Fotocasa es oferta histórica; Pisos.com contiene anuncios; EMAL representa
  alquiler registrado; Eustat aporta renta personal, incluida la categoría
  municipal «Renta del trabajo»; Etxebide mide demanda de vivienda protegida.
- Para resultados Fotocasa, citar la fuente como «Índice Inmobiliario
  Fotocasa» y respetar los límites de frecuencia comunicados para el uso
  académico. La evidencia privada de autorización no se incorpora al paquete.
- El replay Kafka procede de un CSV histórico de Pisos.com. No representa
  anuncios nuevos ni sustituye la colección canónica geolocalizada.
- El esfuerzo de alquiler se presenta como escenario: precio Fotocasa
  municipal de 2024 frente a remuneración neta regional 16-29 de Euskadi, no
  como salario municipal ni como esfuerzo observado de cada persona.
- Se investigaron el catálogo y las tablas candidatas de Eustat. RP03 ofrece
  renta personal anual por edad para Euskadi, sin municipios; RP11S ofrece
  municipios, sin edad. No se combinan ambas tablas ni se estima renta juvenil
  municipal. Véase el [informe de investigación](../DatosIker/informes/investigacion_ingresos_juveniles_eustat.txt).
- Como complemento, Fase 6 cruza el alquiler mensual medio EMAL de contratos
  iniciados en 2024 con la renta personal media Eustat procedente del trabajo
  en 71 municipios. Eustat no desglosa este indicador por edad ni es salario
  neto; el cociente es contextual, no una tasa juvenil observada.
- Hay series Fotocasa idénticas entre códigos municipales. Se marcan en los
  resultados y el ranking solo considera series no compartidas; las tres
  capitales tienen trayectorias distintas.
- `salAnual.json` es nacional y no se usa como ingreso de Euskadi.
- La renta personal Eustat no equivale a salario juvenil. El nuevo cruce usa
  «Renta del trabajo» por municipio, pero no dispone de desglose por edad; se
  mantiene esa distinción en los análisis.

## Límites aún abiertos

La matriz de cumplimiento identifica dos límites: los precios inmobiliarios
se obtuvieron mediante scraping/series archivadas, sin una API inmobiliaria
implementada; y no se ha localizado una fuente verificada de ingresos juveniles
municipales. Sí hay llamadas automatizadas a la API estadística de Eustat, que
no ofrece precios inmobiliarios. El cruce Eustat-EMAL aporta contexto municipal
de renta del trabajo, sin desglose por edad. HDFS ya contiene
los originales y los 21 archivos de `DatosIker/procesados` en zonas separadas.
No se repite la carga de originales HDFS ni se ejecutan scraping o descargas
durante la demostración.
