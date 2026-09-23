# Copyright (C) 2026 J. Israel Villarreal B.
# SPDX-License-Identifier: GPL-2.0-or-later

import csv
import html
import math
import os

from qgis.PyQt.QtCore import QDir, QFileInfo, QSettings, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QAction,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsMapLayerType,
    QgsPointXY,
    QgsProject,
    QgsWkbTypes,
)


class ConstructionTableDialog(QDialog):
    """Diálogo para generar un cuadro de construcción desde un polígono."""

    VERTEX_TOLERANCE_METERS = 0.020

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.generated = False
        self.settings = QSettings("CuadroDeConstruccion", "CuadroDeConstruccion")
        self.setWindowTitle("Cuadro de Construcción")
        self.resize(1100, 700)

        self.layer_combo = QComboBox()
        self.crs_combo = QComboBox()
        self.vertical_datum_combo = QComboBox()
        self.surface_combo = QComboBox()
        self.title_field_combo = QComboBox()
        self.output_path_edit = QLineEdit()
        self.html_output_path_edit = QLineEdit()
        self.control_name_edit = QLineEdit()
        self.control_type_edit = QComboBox()
        self.control_desc_edit = QLineEdit()
        self.control_state_edit = QComboBox()
        self.control_access_edit = QPlainTextEdit()
        self.control_east_edit = QLineEdit()
        self.control_north_edit = QLineEdit()

        self.layer_combo.currentIndexChanged.connect(self._on_layer_changed)
        self._populate_layers()
        self._populate_defaults()
        self.output_path_edit.setText(self._get_last_output_path("cuadro_construccion.csv"))
        self.html_output_path_edit.setText(self._get_last_output_path("cuadro_construccion.html"))

        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels(
            [
                "Polígono", "Est", "PV", "Lado", "Azimut", "Rumbo",
                "Distancia (m)", "X (Este)", "Y (Norte)", "Z (msnmm)",
            ]
        )
        self.table.horizontalHeader().setStretchLastSection(True)

        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)

        form_layout = QGridLayout()
        form_layout.addWidget(QLabel("Capa de polígono:"), 0, 0)
        form_layout.addWidget(self.layer_combo, 0, 1)
        form_layout.addWidget(QLabel("Atributo para título del cuadro:"), 1, 0)
        form_layout.addWidget(self.title_field_combo, 1, 1)
        form_layout.addWidget(QLabel("CRS de cálculo:"), 2, 0)
        form_layout.addWidget(self.crs_combo, 2, 1)
        form_layout.addWidget(QLabel("Datum vertical:"), 3, 0)
        form_layout.addWidget(self.vertical_datum_combo, 3, 1)
        form_layout.addWidget(QLabel("Superficie:"), 4, 0)
        form_layout.addWidget(self.surface_combo, 4, 1)
        form_layout.addWidget(QLabel("Archivo salida CSV:"), 5, 0)
        output_layout = QHBoxLayout()
        output_layout.addWidget(self.output_path_edit)
        browse_btn = QPushButton("Buscar...")
        browse_btn.clicked.connect(self._select_output_path)
        output_layout.addWidget(browse_btn)
        form_layout.addLayout(output_layout, 5, 1)
        form_layout.addWidget(QLabel("Archivo salida HTML:"), 6, 0)
        html_output_layout = QHBoxLayout()
        html_output_layout.addWidget(self.html_output_path_edit)
        html_browse_btn = QPushButton("Buscar...")
        html_browse_btn.clicked.connect(self._select_html_output_path)
        html_output_layout.addWidget(html_browse_btn)
        form_layout.addLayout(html_output_layout, 6, 1)

        self.metadata_toggle = QPushButton("▶ Vinculación a la red geodésica y monumentación")
        self.metadata_toggle.setCheckable(True)
        self.metadata_toggle.setChecked(False)
        self.metadata_toggle.toggled.connect(self._toggle_metadata)
        metadata_widget = QWidget()
        metadata_layout = QFormLayout()
        metadata_layout.addRow("Clave / Nombre de la Estación:", self.control_name_edit)
        metadata_layout.addRow("Tipo de Estación:", self.control_type_edit)
        metadata_layout.addRow("Descripción del Monumento / Mojonera:", self.control_desc_edit)
        metadata_layout.addRow("Estado de Conservación:", self.control_state_edit)
        metadata_layout.addRow("Coordenada Este (X):", self.control_east_edit)
        metadata_layout.addRow("Coordenada Norte (Y):", self.control_north_edit)
        metadata_layout.addRow("Localización y Acceso:", self.control_access_edit)
        metadata_widget.setLayout(metadata_layout)
        self.metadata_widget = metadata_widget
        self._toggle_metadata(False)

        button_layout = QHBoxLayout()
        generate_btn = QPushButton("Generar cuadro")
        close_btn = QPushButton("Cerrar")
        button_layout.addWidget(generate_btn)
        button_layout.addWidget(close_btn)

        generate_btn.clicked.connect(self._generate_table)
        close_btn.clicked.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form_layout)
        layout.addWidget(self.metadata_toggle)
        layout.addWidget(self.metadata_widget)
        layout.addWidget(self.table)
        layout.addWidget(QLabel("Resumen:"))
        layout.addWidget(self.log_box)
        layout.addLayout(button_layout)

    def showEvent(self, event):
        self._populate_layers()
        super().showEvent(event)

    def _toggle_metadata(self, expanded):
        self.metadata_widget.setVisible(expanded)
        prefix = "▼" if expanded else "▶"
        self.metadata_toggle.setText(f"{prefix} Vinculación a la red geodésica y monumentación")

    def _populate_layers(self):
        self.layer_combo.clear()
        self.layer_combo.addItem("Seleccione una capa", None)
        active_layer = self.iface.activeLayer()
        active_layer_id = active_layer.id() if active_layer is not None else None
        for layer in QgsProject.instance().mapLayers().values():
            if self._is_polygon_layer(layer):
                self.layer_combo.addItem(layer.name(), layer.id())
        if active_layer_id:
            active_index = self.layer_combo.findData(active_layer_id)
            if active_index >= 0:
                self.layer_combo.setCurrentIndex(active_index)
        self._on_layer_changed()

    def _on_layer_changed(self):
        self._populate_title_fields()
        self._populate_crs()

    def _populate_title_fields(self):
        self.title_field_combo.clear()
        self.title_field_combo.addItem("Seleccione un atributo", None)
        layer = self._get_selected_layer()
        if layer is None:
            return
        for field_name in layer.fields().names():
            self.title_field_combo.addItem(field_name, field_name)

    def _populate_crs(self):
        self.crs_combo.blockSignals(True)
        self.crs_combo.clear()
        self.crs_combo.addItem("Seleccione un CRS", None)
        layer = self._get_selected_layer()
        layer_crs = layer.crs() if layer is not None else None
        layer_entry = None
        crs_entries = []
        seen = set()

        def add_crs(crs, label=None):
            if crs is None or not crs.isValid():
                return
            key = crs.authid() or crs.toWkt()
            if key in seen:
                return
            seen.add(key)
            display = label or f"{crs.authid() or 'CRS personalizado'} - {crs.description()}"
            crs_entries.append((display, crs))

        if layer_crs is not None and layer_crs.isValid():
            layer_entry = (
                "CRS de la capa - " + (layer_crs.authid() or layer_crs.description()),
                layer_crs,
            )
            seen.add(layer_crs.authid() or layer_crs.toWkt())

        for project_layer in QgsProject.instance().mapLayers().values():
            if layer is not None and project_layer.id() == layer.id():
                continue
            project_layer_crs = project_layer.crs()
            if self._is_metric_projected_crs(project_layer_crs):
                add_crs(
                    project_layer_crs,
                    f"CRS de capa: {project_layer.name()} - "
                    f"{project_layer_crs.authid() or project_layer_crs.description()}",
                )

        project_crs = QgsProject.instance().crs()
        if self._is_metric_projected_crs(project_crs):
            add_crs(project_crs, f"CRS del proyecto - {project_crs.authid() or project_crs.description()}")
        if layer_entry is not None:
            self.crs_combo.addItem(layer_entry[0], layer_entry[1])
        for display, crs in sorted(crs_entries, key=lambda entry: entry[0].upper()):
            self.crs_combo.addItem(display, crs)
        if layer_crs is not None and layer_crs.isValid():
            for index in range(1, self.crs_combo.count()):
                candidate = self.crs_combo.itemData(index)
                if candidate is not None and (
                    candidate.authid() == layer_crs.authid()
                    or candidate.toWkt() == layer_crs.toWkt()
                ):
                    self.crs_combo.setCurrentIndex(index)
                    break
        self.crs_combo.blockSignals(False)

    def _is_metric_projected_crs(self, crs):
        return (
            crs is not None
            and crs.isValid()
            and not crs.isGeographic()
            and crs.mapUnits() == Qgis.DistanceUnit.Meters
        )

    def _is_polygon_layer(self, layer):
        vector_type = getattr(getattr(Qgis, "LayerType", None), "Vector", QgsMapLayerType.VectorLayer)
        polygon_type = getattr(getattr(Qgis, "GeometryType", None), "Polygon", QgsWkbTypes.Polygon)
        return layer.type() == vector_type and layer.geometryType() == polygon_type

    def _populate_defaults(self):
        self.vertical_datum_combo.addItems(["NAVD88", "INEGI Datum Vertical", "Otros"])
        self.vertical_datum_combo.setCurrentText("NAVD88")

        self.surface_combo.addItems([
            "m² con tres decimales",
            "ha, áreas y centiáreas",
        ])
        self.surface_combo.setCurrentText("m² con tres decimales")

        self.control_type_edit.addItems([
            "Base propia de control",
            "Estación Pasiva RGNA",
            "Estación Activa / CORS",
            "No especificado",
        ])
        self.control_type_edit.setCurrentText("Base propia de control")

        self.control_state_edit.addItems(["Bueno", "Dañado", "Removido", "Inestable", "No especificado"])
        self.control_state_edit.setCurrentText("Bueno")

    def _select_output_path(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar CSV",
            self._get_last_output_path("cuadro_construccion.csv"),
            "CSV (*.csv)",
        )
        if path:
            if not path.lower().endswith(".csv"):
                path += ".csv"
            self.output_path_edit.setText(path)
            self._remember_output_directory(path)

    def _select_html_output_path(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar HTML",
            self._get_last_output_path("cuadro_construccion.html"),
            "HTML (*.html)",
        )
        if path:
            if not path.lower().endswith(".html"):
                path += ".html"
            self.html_output_path_edit.setText(path)
            self._remember_output_directory(path)

    def _get_last_output_path(self, filename):
        directory = self.settings.value("last_output_directory", "", type=str)
        if not directory or not QFileInfo(directory).isDir():
            downloads_directory = QDir(QDir.homePath()).filePath("Downloads")
            directory = downloads_directory if QFileInfo(downloads_directory).isDir() else QDir.homePath()
        return QDir(directory).filePath(filename)

    def _remember_output_directory(self, path):
        directory = QFileInfo(path).absolutePath()
        if directory:
            self.settings.setValue("last_output_directory", directory)

    def _get_selected_layer(self):
        layer_id = self.layer_combo.currentData()
        if not layer_id:
            return None
        return QgsProject.instance().mapLayers().get(layer_id)

    def _extract_polygon_points(self, layer, feature):
        geometry = feature.geometry()
        if geometry.isNull() or geometry.isEmpty():
            return []
        native_geometry = geometry.constGet()
        if geometry.isMultipart():
            native_geometry = native_geometry.geometryN(0)
        if native_geometry is not None and hasattr(native_geometry, "exteriorRing"):
            exterior_ring = native_geometry.exteriorRing()
            if exterior_ring is not None and hasattr(exterior_ring, "vertices"):
                points = list(exterior_ring.vertices())
                if points:
                    return points

        if geometry.isMultipart():
            polygons = geometry.asMultiPolygon()
            if polygons:
                return list(polygons[0][0])
        polygons = geometry.asPolygon()
        if polygons:
            return list(polygons[0])
        return []

    def _get_vertex_elevation(self, point, fallback):
        point_z = getattr(point, "z", None)
        if point_z is not None:
            try:
                elevation = float(point_z() if callable(point_z) else point_z)
                if not math.isnan(elevation) and elevation != 0:
                    return elevation
            except (TypeError, ValueError):
                pass
        try:
            elevation = float(fallback)
            return "" if math.isnan(elevation) else elevation
        except (TypeError, ValueError):
            return ""

    def _get_elevation_field(self, layer):
        field_names = layer.fields().names()
        normalized_names = {
            name.lower().replace("á", "a").replace("é", "e"): name
            for name in field_names
        }
        preferred_names = ["z", "elevacion", "elevación", "cota", "altura"]
        for preferred_name in preferred_names:
            normalized_name = preferred_name.lower().replace("á", "a").replace("é", "e")
            if normalized_name in normalized_names:
                return normalized_names[normalized_name]
        for normalized_name, original_name in normalized_names.items():
            if any(token in normalized_name for token in ("elev", "cota", "altura")):
                return original_name
        return None

    def _order_ring_points(self, layer, ring):
        points = list(ring)
        if len(points) > 1 and points[0] == points[-1]:
            points.pop()

        projected_points = [
            self._coordinate_transform(layer, point)
            for point in points
        ]
        if not projected_points:
            return points, projected_points

        max_northing = max(point[1] for point in projected_points)
        northern_indices = [
            index
            for index, point in enumerate(projected_points)
            if max_northing - point[1] <= self.VERTEX_TOLERANCE_METERS
        ]
        start_index = min(northern_indices, key=lambda index: projected_points[index][0])

        signed_area = sum(
            projected_points[index][0] * projected_points[(index + 1) % len(projected_points)][1]
            - projected_points[(index + 1) % len(projected_points)][0] * projected_points[index][1]
            for index in range(len(projected_points))
        ) / 2

        if signed_area > 0:
            points.reverse()
            projected_points.reverse()

        max_northing = max(point[1] for point in projected_points)
        northern_indices = [
            index
            for index, point in enumerate(projected_points)
            if max_northing - point[1] <= self.VERTEX_TOLERANCE_METERS
        ]
        start_index = min(northern_indices, key=lambda index: projected_points[index][0])
        points = points[start_index:] + points[:start_index]
        projected_points = projected_points[start_index:] + projected_points[:start_index]
        return points, projected_points

    def _get_vertex_name(self, vertex_registry, projected_point):
        for registered_point, name in vertex_registry:
            if math.hypot(
                projected_point[0] - registered_point[0],
                projected_point[1] - registered_point[1],
            ) <= self.VERTEX_TOLERANCE_METERS:
                return name

        if len(vertex_registry) >= 9999:
            raise ValueError("La capa tiene más de 9,999 vértices únicos.")

        name = f"V{len(vertex_registry) + 1:03d}"
        vertex_registry.append((projected_point, name))
        return name

    def _coordinate_transform(self, layer, point):
        source_crs = layer.crs()
        target_crs = self.crs_combo.currentData()
        if target_crs is None or not target_crs.isValid():
            raise ValueError("Debe seleccionar un CRS de cálculo válido.")
        transform = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())
        transformed = transform.transform(QgsPointXY(point.x(), point.y()))
        return transformed.x(), transformed.y()

    def _get_calculation_crs(self):
        crs = self.crs_combo.currentData()
        if crs is None or not crs.isValid():
            return None
        if crs.isGeographic():
            return None
        if crs.mapUnits() != Qgis.DistanceUnit.Meters:
            return None
        return crs

    def _decimal_to_dms(self, decimal_degrees):
        if decimal_degrees < 0:
            decimal_degrees += 360
        degrees = int(decimal_degrees)
        minutes_float = (decimal_degrees - degrees) * 60
        minutes = int(minutes_float)
        seconds = (minutes_float - minutes) * 60
        return degrees, minutes, seconds

    def _format_dms(self, decimal_degrees):
        degrees, minutes, seconds = self._decimal_to_dms(decimal_degrees)
        return f"{degrees}° {minutes:02d}' {seconds:05.2f}\""

    def _format_rumbo(self, decimal_degrees):
        if decimal_degrees < 0:
            decimal_degrees += 360
        quadrant = (int(decimal_degrees / 90) + 1) if decimal_degrees >= 0 else 0
        if decimal_degrees >= 0 and decimal_degrees < 90:
            reference = "N"
            angle = decimal_degrees
            suffix = "E"
        elif decimal_degrees >= 90 and decimal_degrees < 180:
            reference = "S"
            angle = 180 - decimal_degrees
            suffix = "E"
        elif decimal_degrees >= 180 and decimal_degrees < 270:
            reference = "S"
            angle = decimal_degrees - 180
            suffix = "W"
        else:
            reference = "N"
            angle = 360 - decimal_degrees
            suffix = "W"
        deg, minutes, seconds = self._decimal_to_dms(angle)
        return f"{reference} {deg:02d}°{minutes:02d}'{seconds:05.2f}\" {suffix}"

    def _azimuth_to_rumbo(self, decimal_degrees):
        if decimal_degrees < 0:
            decimal_degrees += 360
        return self._format_rumbo(decimal_degrees)

    def _calculate_azimuth(self, x1, y1, x2, y2):
        dx = x2 - x1
        dy = y2 - y1
        azimuth = math.degrees(math.atan2(dx, dy))
        if azimuth < 0:
            azimuth += 360
        return azimuth

    def _format_surface(self, area_m2):
        if self.surface_combo.currentText() == "ha, áreas y centiáreas":
            hectares = int(area_m2 // 10000)
            remaining = area_m2 - hectares * 10000
            areas = int(remaining // 100)
            centiareas = remaining - areas * 100
            return f"{hectares} ha, {areas} áreas y {centiareas:.2f} centiáreas"
        return f"{area_m2:.3f} m²"

    def _build_report(self, area_m2, has_elevation):
        title_field = self.title_field_combo.currentText()
        calculation_crs = self.crs_combo.currentData()
        crs_text = f"{calculation_crs.authid()} - {calculation_crs.description()}"
        vertical_text = self.vertical_datum_combo.currentText()
        surface_text = self._format_surface(area_m2)
        control_name = self.control_name_edit.text().strip() or "No especificado"
        control_type = self.control_type_edit.currentText()
        control_desc = self.control_desc_edit.text().strip() or "No especificado"
        control_state = self.control_state_edit.currentText()
        control_access = self.control_access_edit.toPlainText().strip() or "No especificado"

        control_text = (
            "Vinculación a la red geodésica: No especificado."
            if control_name == "No especificado"
            else (
                f"Vinculación a la red geodésica: {control_name} | Tipo: {control_type} | "
                f"Monumento: {control_desc} | Estado: {control_state}.\n"
                f"Localización y Acceso: {control_access}."
            )
        )
        text = (
            f"Atributo de título: {title_field}.\n"
            f"Sistema de Proyección: UTM (Universal Transverse Mercator).\n"
            f"CRS de cálculo: {crs_text}.\n"
            f"{f'Datum Vertical: {vertical_text}.' if has_elevation else ''}\n"
            f"Superficie: {surface_text}.\n"
            f"{control_text}\n"
        )
        return text

    def _build_html(self, records, area_m2, has_elevation, html_path):
        calculation_crs = self.crs_combo.currentData()
        footer_datum = f"{calculation_crs.authid()} - {calculation_crs.description()}"
        headers = ["Est", "PV", "Lado", "Azimut", "Rumbo", "Distancia (m)", "X (Este)", "Y (Norte)"]
        if has_elevation:
            headers.append("Z (msnmm)")
        grouped_records = {}
        for record in records:
            grouped_records.setdefault(record["polygon_title"], []).append(record)
        tables = []
        for polygon_title, polygon_records in grouped_records.items():
            table_rows = []
            polygon_title_row = f'<tr class="polygon-title"><th colspan="{len(headers)}">{html.escape(polygon_title)}</th></tr>'
            title_row = f'<tr class="title-row"><th colspan="{len(headers)}">CUADRO DE CONSTRUCCIÓN</th></tr>'
            for record in polygon_records:
                table_rows.append(
                    "<tr>" + "".join(
                        f"<td>{html.escape(str(record[key]))}</td>"
                        for key in ["est", "pv", "lado", "azimut", "rumbo", "distancia", "x", "y"]
                        + (["z"] if has_elevation else [])
                    ) + "</tr>"
                )
            tables.append(
                f'<table><thead>{polygon_title_row}{title_row}<tr>'
                f'{"".join(f"<th>{header}</th>" for header in headers)}</tr></thead>'
                f'<tbody>{"".join(table_rows)}</tbody>'
                f'<tfoot><tr><td class="area" colspan="{len(headers)}">'
                f'<strong>Área o superficie:</strong> {html.escape(self._format_surface(polygon_records[0]["polygon_area"]))}'
                f'</td></tr></tfoot></table>'
            )
        vertical_note = f"<p><strong>Datum vertical:</strong> {html.escape(self.vertical_datum_combo.currentText())}</p>" if has_elevation else ""
        control_name = self.control_name_edit.text().strip()
        if control_name:
            control_note = (
                "<p class=\"note\"><strong>Vinculación a la red geodésica y monumentación:</strong> "
                f"La estación de control <strong>{html.escape(control_name)}</strong> "
                f"corresponde a {html.escape(self.control_type_edit.currentText())}. "
                f"Descripción del monumento o mojonera: {html.escape(self.control_desc_edit.text().strip() or 'No especificado')}. "
                f"Estado de conservación: {html.escape(self.control_state_edit.currentText())}. "
                f"Coordenada Este (X): {html.escape(self.control_east_edit.text().strip() or 'No especificada')}; "
                f"Coordenada Norte (Y): {html.escape(self.control_north_edit.text().strip() or 'No especificada')}. "
                f"Localización y acceso: {html.escape(self.control_access_edit.toPlainText().strip() or 'No especificado')}."
                "</p>"
            )
        else:
            control_note = ""
        document = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Cuadro de Construcción</title>
<style>
body {{ font-family: Arial, sans-serif; color: #111; margin: 24px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 10px; }}
th, td {{ border: 1px solid #555; padding: 5px; text-align: center; }}
th {{ background: #e5e5e5; }}
.title-row th {{ background: #000; color: #fff; font-weight: bold; font-size: 15px; }}
.polygon-title th {{ background: #f0f0f0; font-weight: bold; font-size: 18px; }}
.area {{ border: 0; text-align: left; padding: 9px 0 16px; }}
.footer {{ margin-top: 16px; font-size: 12px; }}
.note {{ font-size: 11px; font-style: italic; }}
@media print {{ body {{ margin: 10mm; }} }}
</style>
</head>
<body>
{''.join(tables)}
<div class="footer">
<p><strong>Referencia:</strong> {html.escape(footer_datum)}</p>
{vertical_note}
{control_note}
</div>
</body>
</html>
"""
        with open(html_path, "w", encoding="utf-8") as html_file:
            html_file.write(document)

    def _generate_table(self):
        layer = self._get_selected_layer()
        if layer is None:
            self.log_box.setPlainText("Debe seleccionar una capa de polígono válida.")
            return
        calculation_crs = self._get_calculation_crs()
        if calculation_crs is None:
            self.log_box.setPlainText(
                "El CRS de cálculo debe ser un CRS proyectado con unidades métricas."
            )
            return

        layer_features = list(layer.getFeatures())
        if not layer_features:
            self.log_box.setPlainText("La capa seleccionada no tiene entidades.")
            return

        records = []
        vertex_registry = []
        area_m2 = 0.0
        has_elevation = False
        title_field = self.title_field_combo.currentData()
        for feature_index, feature in enumerate(layer_features):
            ring = self._extract_polygon_points(layer, feature)
            if len(ring) < 3:
                continue
            ring, projected_points = self._order_ring_points(layer, ring)
            vertex_count = len(ring)
            if vertex_count > 9999:
                self.log_box.setPlainText(
                    "El polígono tiene más de 9,999 vértices; "
                    "los nombres no pueden superar 5 caracteres."
                )
                return

            polygon_area_m2 = abs(
                sum(
                    projected_points[index][0] * projected_points[(index + 1) % vertex_count][1]
                    - projected_points[(index + 1) % vertex_count][0] * projected_points[index][1]
                    for index in range(vertex_count)
                )
            ) / 2
            area_m2 += polygon_area_m2

            elevation_field = self._get_elevation_field(layer)
            raw_z_value = feature.attribute(elevation_field) if elevation_field else None
            vertex_elevations = [
                self._get_vertex_elevation(point, raw_z_value)
                for point in ring
            ]
            has_feature_elevation = any(elevation not in (None, "", 0) for elevation in vertex_elevations)
            has_elevation = has_elevation or has_feature_elevation
            polygon_title = feature.attribute(title_field) if title_field else None
            if polygon_title in (None, ""):
                polygon_title = f"Polígono {feature_index + 1}"
            polygon_title = str(polygon_title)

            for idx in range(vertex_count):
                x1, y1 = projected_points[idx]
                x2, y2 = projected_points[(idx + 1) % vertex_count]

                distance = math.hypot(x2 - x1, y2 - y1)
                azimuth_degrees = self._calculate_azimuth(x1, y1, x2, y2)
                rumbo = self._azimuth_to_rumbo(azimuth_degrees)

                try:
                    station_name = self._get_vertex_name(vertex_registry, projected_points[idx])
                    next_vertex_index = (idx + 1) % vertex_count
                    pv_name = self._get_vertex_name(vertex_registry, projected_points[next_vertex_index])
                except ValueError as exc:
                    self.log_box.setPlainText(str(exc))
                    return
                z_value = vertex_elevations[idx] if has_feature_elevation else ""

                records.append(
                    {
                        "est": station_name,
                        "pv": pv_name,
                        "lado": f"{station_name}-{pv_name}",
                        "azimut": self._format_dms(azimuth_degrees),
                        "rumbo": rumbo,
                        "distancia": f"{distance:.3f}",
                        "x": f"{x1:.3f}",
                        "y": f"{y1:.3f}",
                        "z": z_value,
                        "polygon_title": polygon_title,
                        "polygon_area": polygon_area_m2,
                    }
                )

        if not records:
            self.log_box.setPlainText("No se pudieron leer vértices válidos del polígono.")
            return

        visible_headers = [
            "Polígono", "Est", "PV", "Lado", "Azimut", "Rumbo",
            "Distancia (m)", "X (Este)", "Y (Norte)",
        ]
        if has_elevation:
            visible_headers.append("Z (msnmm)")
        self.table.setColumnCount(len(visible_headers))
        self.table.setHorizontalHeaderLabels(visible_headers)
        self.table.setRowCount(len(records))
        for row_idx, record in enumerate(records):
            values = [
                record["polygon_title"],
                record["est"],
                record["pv"],
                record["lado"],
                record["azimut"],
                record["rumbo"],
                record["distancia"],
                record["x"],
                record["y"],
            ]
            if has_elevation:
                values.append(str(record["z"]))
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_idx, col_idx, item)

        self.log_box.setPlainText(self._build_report(area_m2, has_elevation))

        output_path = self.output_path_edit.text().strip()
        if not output_path:
            output_path = self._get_last_output_path("cuadro_construccion.csv")
        if not output_path.lower().endswith(".csv"):
            output_path += ".csv"
        html_path = self.html_output_path_edit.text().strip()
        if not html_path:
            html_path = self._get_last_output_path("cuadro_construccion.html")
        if not html_path.lower().endswith(".html"):
            html_path += ".html"

        try:
            with open(output_path, "w", newline="", encoding="utf-8-sig") as csv_file:
                writer = csv.writer(csv_file)
                csv_headers = ["Polígono", "Est", "PV", "Lado", "Azimut", "Rumbo", "Distancia (m)", "X", "Y"]
                if has_elevation:
                    csv_headers.append("Z (msnmm)")
                writer.writerow(csv_headers)
                for row in records:
                    csv_values = [row["polygon_title"]] + [row[key] for key in ["est", "pv", "lado", "azimut", "rumbo", "distancia", "x", "y"]]
                    if has_elevation:
                        csv_values.append(row["z"])
                    writer.writerow(csv_values)
            self.log_box.appendPlainText(f"\nArchivo CSV exportado en: {output_path}")
            self._build_html(records, area_m2, has_elevation, html_path)
            self.log_box.appendPlainText(f"Archivo HTML exportado en: {html_path}")
            self.generated = True
        except Exception as exc:  # pragma: no cover
            self.log_box.appendPlainText(f"\nNo se pudo exportar CSV: {exc}")


class CuadroDeConstruccionPlugin:
    """Plugin para generar un cuadro de construcción a partir de un polígono."""

    def __init__(self, iface):
        self.iface = iface
        self.action = None

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        self.action = QAction(QIcon(icon_path), "Cuadro de Construcción", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToVectorMenu("Cuadro de Construcción", self.action)

    def unload(self):
        if self.action is not None:
            self.iface.removePluginVectorMenu("Cuadro de Construcción", self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None

    def run(self):
        dialog = ConstructionTableDialog(self.iface, self.iface.mainWindow())
        dialog.exec()
        if dialog.generated:
            self.iface.messageBar().pushMessage(
                "Cuadro de Construcción",
                "Cuadro de construcción generado o actualizado.",
                level=Qgis.Info,
                duration=3,
            )
