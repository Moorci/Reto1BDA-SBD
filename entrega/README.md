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

Desde PowerShell, en la raíz `C:\Users\Alvaro.Morcillo\Desktop\Reto1`:

```powershell
.\.conda\python.exe -B .\src\cargar_mongodb_fase3.py --dry-run
.\.conda\python.exe -B .\src\crud_demostracion_fase3.py
.\.conda\python.exe -B .\src\consultas_fase4.py
.\.conda\python.exe -B .\src\cargar_salarios_regionales.py --dry-run
.\.conda\python.exe -B .\src\cargar_salarios_regionales.py
.\.conda\python.exe -B .\src\analisis_fase6.py
.\.conda\python.exe -B -m unittest discover -s tests -v
```

La demostración Kafka requiere dos terminales y acceso a los servicios HDFS y
Kafka del entorno del proyecto. Los pasos están en el [guion](./guion_demo.md).

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

La matriz de cumplimiento identifica dos brechas concretas respecto al nivel
máximo del PDF: no se implementará extracción API automatizada, decisión
aceptada por el usuario, y no se ha localizado una fuente de salario juvenil
municipal verificado. El cruce Eustat-EMAL aporta contexto municipal de renta
del trabajo, sin desglose por edad. HDFS ya contiene
los originales y los 21 archivos de `DatosIker/procesados` en zonas separadas.
No se repite la carga de originales HDFS ni se ejecutan scraping o descargas
durante la demostración.
