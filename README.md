# Cuadro de Construcción

Complemento de QGIS 4.2 para generar cuadros de construcción a partir de polígonos.

## Licencia

Copyright © 2026 J. Israel Villarreal B.

Cuadro de Construcción se distribuye bajo los términos de la Licencia Pública General de GNU, versión 2 o, a elección de quien lo reciba, cualquier versión posterior. El texto completo se encuentra en el archivo LICENSE.

## Estructura

- `__init__.py`: punto de entrada del plugin
- `plugin.py`: lógica principal del complemento
- `metadata.txt`: metadatos del plugin para QGIS
- `.gitignore`: archivos de entorno y caché

## Requisitos

- QGIS 4.2+
- Python compatible con la versión de QGIS
- VS Code o entorno similar

## Instalación

1. Copia esta carpeta al directorio de plugins de QGIS.
2. Reinicia QGIS.
3. Activa el plugin desde el gestor de complementos.

## Desarrollo

Puedes ampliar `plugin.py` con nuevas acciones, menús, cuadros de diálogo o procesamiento geoespacial.
