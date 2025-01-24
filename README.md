
# Grafos de Accesibilidad 🗺️⚙️
*Análisis de redes espaciales con métricas de centralidad y accesibilidad*

[![Licencia MIT](https://img.shields.io/badge/Licencia-MIT-green.svg)](LICENSE)
![Docker](https://img.shields.io/badge/Docker-Contenedor_Activo-blue)
![PostGIS](https://img.shields.io/badge/PostGIS-3.3-brightgreen)
![Python](https://img.shields.io/badge/Python-3.9+-blue)

## Tabla de Contenidos
1. [Versión 1.0 (Python)](#versión-10-python)
   - [Descripción](#descripción-del-proyecto)
   - [Características](#características-clave)
   - [Instalación](#instalación)
   - [Uso](#uso)
   - [Estructura](#estructura-del-proyecto)
2. [Versión 2.0 (Docker + PostGIS)](#versión-20-docker--postgis)
   - [Descripción](#descripción-del-proyecto-1)
   - [Características](#características-clave-1)
   - [Instalación](#instalación-1)
   - [Uso](#uso-1)
   - [Estructura](#estructura-del-proyecto-1)
3. [Contribución](#contribución)
4. [Licencia](#licencia)

---

## **Versión 1.0 (Python)**
---
<img src="https://github.com/user-attachments/assets/3228e688-66a0-4be7-b209-a1a9f19528b8" alt="Description of the image" width="600" height="auto">

*Metricas de la red**

### Descripción del Proyecto 📌
**Objetivo**: Análisis básico de redes de transporte usando grafos en memoria  
**Tecnologías**:
- Python 3.9+ con NetworkX 2.6 y Pandas 1.3
- Almacenamiento en CSV/GeoJSON

## Métricas Calculadas 📈
### Nodos y Aristas
1. **Centralidad de Grado** (`degree_centrality`)
2. **Centralidad de Intermediación** (`betweenness_centrality`)
3. **Centralidad de Cercanía** (`closeness_centrality`)

### Accesibilidad
1. **Accesibilidad ponderada por impedancia**
2. **Distancias mínimas (Dijkstra)**
3. **Conectividad por componentes**

### Espaciales
1. **Densidad de ciclovías por km²**
2. **Cobertura geográfica (buffers)**
3. **Superposición con red vial principal**

---

## Parámetros Principales 🌟
| Parámetro | Descripción | Valores Típicos |
|-----------|-------------|-----------------|
| `--osm_input` | Fuente de datos OSM (GeoJSON o "osm") | `data/red_vial.geojson` |
| `--ciclo_input` | Datos de ciclovías (GeoJSON) | `data/ciclovias.geojson` |
| `--location` | Ubicación geográfica | `"Santiago, Chile"` |
| `--buffer_inhibidores` | Radio de inhibición (metros) | `15` |
| `--buffer_desinhibicion` | Radio de desinhibición (metros) | `25` |
| `--srid` | Sistema de coordenadas | `32719` |

---

### Instalación ⚙️
markdown
Copy
```bash
git clone --branch py-ciclo https://github.com/Masciclo/grafos-accesibilidad.git
pip install -r requirements.txt
```
---

### Uso 🚀

**Importar libreria**:
```python
from grafo_basico import GrafoSimple
```


**Cargar datos**:
```python
red = GrafoSimple('datos/red_calles.geojson')
```


**Calcular métricas**:
red.calcular_centralidad()
red.generar_visualizacion()

**Exportar resultados**:
red.exportar_metricas('resultados/metricas_v1.csv')

### Estructura del Proyecto 📂

grafos-accesibilidad/
├── data/                # Datos de entrada
│   ├── ejemplos/        # Datos sample
│   └── resultados/      # Salidas generadas
├── src/
│   ├── grafo.py         # Clase principal
│   ├── metricas/        # Cálculos especializados
│   └── utils/           # Herramientas auxiliares
├── requirements.txt
└── LICENSE

---



## *Versión 2.0 (Docker + PostGIS)*
---
<img src="https://github.com/user-attachments/assets/ed1a4a59-55fa-440c-a3dd-a6ec0d871cfa" alt="Description of the image" width="600" height="auto">

* Impendancia y Analisis por componentes**
  
## Descripción del Proyecto 📌

### Objetivo
Este proyecto tiene como objetivo cortar la red con un buffer, para luego calcular en cada seccion y procesar redes de ciclovías a nivel global utilizando datos de **OpenStreetMap (OSM)**. A través de un entorno contenerizado con **Docker**, se integran tecnologías como **PostgreSQL**, **PostGIS**, y **pgRouting** para realizar análisis geoespaciales avanzados y calcular métricas clave como **accesibilidad**, **centralidad**, y **conectividad**.

### Tecnologías Utilizadas
- **Docker**: Para la creación y gestión de contenedores.
- **PostgreSQL + PostGIS + pgRouting**: Para el almacenamiento y análisis de datos geoespaciales.
- **Python**: Para la manipulación de datos y ejecución de pipelines.
- **GeoPandas**: Para el procesamiento de datos geoespaciales en Python.

### 🔄 Flujo Completo de Análisis

Entrada de Datos:
```bash
docker exec python-app python main.py \
  --osm_input=data/ciudad.geojson \
  --location="Paris, Francia" \
  --srid=2154
```
Procesamiento en PostGIS:

1. Conversión a geometrías proyectadas

- Generación de topología de red
- Aplicación de buffers de inhibición

2. Cálculos con pgRouting:

- Betweenness Centrality ponderada
- Rutas óptimas considerando impedancias
- Análisis de conectividad multimodal

3. Salida:

- Capas GeoJSON con métricas espacializadas
- Celdas H3 con indicadores agregados

Metadatos técnicos en formato JSON
### Métricas Calculadas
- **Componentes de la red (Node components)**
- **Accesibilidad isocrónica (buffers temporales)**
- **Conectividad multimodal**

📊 Ejemplo de Resultados Generados

| Capa GeoJSON                  | Campos                           | Descripción                                  |
|-------------------------------|----------------------------------|----------------------------------------------|
| `nodos_centralidad.geojson`   | `betweenness`, `closeness`       | Importancia estratégica de intersecciones    |
| `accesibilidad_h3.geojson`    | `tiempo_promedio`, `conteo_rutas`| Accesibilidad por celdas hexagonales         |
| `red_final.geojson`           | `impedancia`, `tipo_via`         | Red operativa después de inhibición          |
| `componentes_conexos.geojson` | `component_id`, `nodos_count`    | Sub-redes conectadas (islas de accesibilidad)|

---

## Características Clave 🌟

- **Entorno contenerizado**: Utiliza Docker para garantizar un entorno reproducible y aislado.
- **Integración con PostGIS**: Permite el manejo eficiente de datos geoespaciales y la ejecución de consultas avanzadas.
- **Pipeline automatizado**: Incluye procesos ETL para la carga, transformación y análisis de datos.
- **Escalabilidad**: Capaz de manejar grandes volúmenes de datos espaciales.
- **Interfaz flexible**: Permite la inhibición y desinhibición de redes mediante buffers espaciales.

---

## Instalación ⚙️

### Requisitos Previos
1. **Docker**: Instalado y configurado en tu sistema.
2. **Docker Compose**: Para la orquestación de contenedores.
3. **Conexión a Internet**: Para descargar imágenes de Docker y datos de OSM.
4. **Recursos de hardware**: Suficiente memoria RAM y espacio de almacenamiento para procesar grandes conjuntos de datos.

### Pasos de Instalación
1. Clona el repositorio:
   ```bash
   git clone --branch py-ciclo https://github.com/Masciclo/grafos-accesibilidad.git
   cd grafos-accesibilidad
    ```

2. Configura las variables de entorno:

Edita el archivo .env en la raíz del proyecto con las credenciales de la base de datos:

```bash
Copy
DATABASE_NAME='ciclo_dev'
HOST='stationdb'
PORT='5432'
DB_USER='ciclo'
DB_PASSWORD='ciclo']
```
3. Construye y levanta los contenedores:

```bash
docker-compose build
docker-compose up -d
```
---

### Uso 🚀
**Ejecución del Pipeline**:
1. Ingresa al contenedor de Python:

```bash
docker exec -it grafos-accessibilidad-ciclo-py-1 /bin/bash
Navega al directorio de la aplicación:
```

```bash
cd /app
Ejecuta el script principal con los parámetros deseados:
```

```bash
python main.py \
--osm_input='osm' \
--ciclo_input='data/ciclo.geojson' \
--location='Santiago, Chile' \
--srid=32719 \
--inhibit=1 \
--inhibitor_input='osm' \
--buffer_inhibidores=15 \
--disinhit=1 \
--disinhitor_input='osm' \
--buffer_disinhibitor=25
```

**Parámetros Principales**:
- osm_input: Fuente de datos de la red vial (GeoJSON o "osm" para descargar de OSM).
- ciclo_input: Fuente de datos de las ciclovías (GeoJSON o "osm").
- location: Ubicación geográfica a analizar (ej. "Santiago, Chile").
- srid: Sistema de referencia espacial (ej. EPSG:32719).
- inhibit: Activa la inhibición de la red (1 para activar, 0 para desactivar).
- inhibitor_input: Fuente de datos de los inhibidores (GeoJSON o "osm").
- buffer_inhibidores: Radio del buffer de inhibición en metros.
- disinhit: Activa la desinhibición de la red (1 para activar, 0 para desactivar).
- disinhitor_input: Fuente de datos de los desinhibidores (GeoJSON o "osm").
- buffer_disinhibitor: Radio del buffer de desinhibición en metros.

---

### Estructura del Proyecto 📂
Copy
grafos-accesibilidad/
├── docker-compose.yml    # Configuración de contenedores
├── postgis/              # Configuración de la base de datos PostGIS
├── app/                  # Aplicación Python
│   ├── main.py           # Script principal
│   ├── requirements.txt  # Dependencias de Python
│   └── queries/          # Consultas SQL optimizadas
├── data/                 # Datos de entrada (GeoJSON, Shapefiles)
├── .env                  # Variables de entorno
└── LICENSE               # Licencia del proyecto

---

## Contribución 🤝

```bash
# Para versión Python
pytest tests/ --cov=grafo_basico

# Para versión Docker
docker-compose run --rm test pytest /app/tests
```
## Licencia 📄
MIT License - Ver LICENSE para detalles
"""
