"""
Bro — Generatore di Disegni
Genera planimetrie SVG e DXF, Excel, PDF programmaticamente.
"""

from __future__ import annotations

import io
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Room:
    name: str
    width: float   # in metri
    depth: float   # in metri
    x: float = 0   # posizione
    y: float = 0

    @property
    def area(self) -> float:
        return round(self.width * self.depth, 1)


class FloorPlanGenerator:
    """Genera planimetrie SVG e DXF."""

    def __init__(self, total_sqm: float = 100):
        self.total_sqm = total_sqm
        self.rooms: list[Room] = []

    def generate_layout(self, bedrooms: int = 2, bathrooms: int = 1, has_study: bool = True) -> None:
        """Calcola un layout ragionevole in base ai mq e al numero di stanze."""
        # Distribuzione approssimativa
        area_salotto = self.total_sqm * 0.30
        area_cucina = self.total_sqm * 0.12
        area_bagno = self.total_sqm * 0.08 * bathrooms
        area_corridoio = self.total_sqm * 0.05
        area_studio = self.total_sqm * 0.15 if has_study else 0
        area_camere = self.total_sqm - (area_salotto + area_cucina + area_bagno + area_corridoio + area_studio)

        self.rooms = []
        # Corridoio (rettangolare stretto)
        self.rooms.append(Room("Corridoio", 5, area_corridoio / 5, 0, 0))
        # Salotto (grande)
        self.rooms.append(Room("Salotto", 6, area_salotto / 6, 5, 0))
        # Cucina
        self.rooms.append(Room("Cucina", 4, area_cucina / 4, 11, 0))
        # Bagni (a destra)
        for i in range(bathrooms):
            self.rooms.append(Room(f"Bagno {i+1}", 3, area_bagno / (3 * bathrooms), 0, 5 + i * (area_bagno / (3 * bathrooms))))
        # Camere
        camera_area = area_camere / bedrooms
        for i in range(bedrooms):
            self.rooms.append(Room(f"Camera {i+1}", 4.5, camera_area / 4.5, 5 + i * 4.5, 5))
        # Studio
        if has_study:
            self.rooms.append(Room("Studio", 4, area_studio / 4, 5 + bedrooms * 4.5, 5))

    def to_svg(self) -> str:
        """Genera SVG della planimetria."""
        scale = 40  # pixel per metro
        margin = 60

        # Calcola bounding box
        max_x = max(r.x + r.width for r in self.rooms)
        max_y = max(r.y + r.depth for r in self.rooms)
        width_px = int(max_x * scale + 2 * margin)
        height_px = int(max_y * scale + 2 * margin)

        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_px}" height="{height_px}" viewBox="0 0 {width_px} {height_px}">',
            f'<rect width="{width_px}" height="{height_px}" fill="#0a0a0a"/>',
            f'<text x="{width_px/2}" y="30" fill="#ffcc00" font-family="monospace" font-size="16" text-anchor="middle">Planimetria {self.total_sqm} m²</text>',
        ]

        colors = ["#ffcc00", "#ffaa00", "#ff8800", "#eebb00", "#dd9900", "#cc8800"]

        for i, room in enumerate(self.rooms):
            x = margin + room.x * scale
            y = margin + 50 + room.y * scale
            w = room.width * scale
            h = room.depth * scale
            color = colors[i % len(colors)]

            # Rettangolo
            svg_parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="{color}" stroke-width="2"/>')
            # Riempimento semi-trasparente
            svg_parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{color}" opacity="0.08"/>')
            # Nome stanza
            svg_parts.append(f'<text x="{x + w/2}" y="{y + h/2}" fill="{color}" font-family="monospace" font-size="12" text-anchor="middle" dominant-baseline="middle">{room.name}</text>')
            # Area
            svg_parts.append(f'<text x="{x + w/2}" y="{y + h/2 + 16}" fill="{color}" font-family="monospace" font-size="10" text-anchor="middle" opacity="0.7">{room.area} m²</text>')

        # Scala
        svg_parts.append(f'<text x="{margin}" y="{height_px - 20}" fill="#ffcc00" font-family="monospace" font-size="10">1 metro = {scale}px</text>')
        svg_parts.append('</svg>')
        return "\n".join(svg_parts)

    def to_dxf(self, path: Path) -> Path:
        """Genera file DXF (AutoCAD)."""
        import ezdxf
        doc = ezdxf.new("R2010")
        msp = doc.modelspace()

        for room in self.rooms:
            # Rettangolo della stanza
            points = [
                (room.x, room.y),
                (room.x + room.width, room.y),
                (room.x + room.width, room.y + room.depth),
                (room.x, room.y + room.depth),
                (room.x, room.y),
            ]
            msp.add_lwpolyline(points)

            # Testo con nome stanza
            msp.add_text(
                room.name,
                dxfattribs={"height": 0.3},
            ).set_placement((room.x + room.width / 2, room.y + room.depth / 2))

            # Testo con area
            msp.add_text(
                f"{room.area} m2",
                dxfattribs={"height": 0.2},
            ).set_placement((room.x + room.width / 2, room.y + room.depth / 2 - 0.4))

        doc.saveas(str(path))
        return path


class ExcelGenerator:
    """Genera file Excel."""

    @staticmethod
    def from_data(title: str, headers: list[str], rows: list[list[Any]], path: Path) -> Path:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = title[:31]  # max 31 caratteri

        # Header
        header_fill = PatternFill(start_color="FFCC00", end_color="FFCC00", fill_type="solid")
        header_font = Font(bold=True, color="000000")

        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

        # Righe
        for r, row in enumerate(rows, 2):
            for c, val in enumerate(row, 1):
                ws.cell(row=r, column=c, value=val)

        # Larghezza automatica
        for col in range(1, len(headers) + 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = 20

        wb.save(str(path))
        return path


# === API per Bro ===

def create_floor_plan(
    sqm: float = 100,
    bedrooms: int = 2,
    bathrooms: int = 1,
    has_study: bool = True,
) -> dict[str, Any]:
    """Genera una planimetria e ritorna i percorsi dei file."""
    gen = FloorPlanGenerator(total_sqm=sqm)
    gen.generate_layout(bedrooms=bedrooms, bathrooms=bathrooms, has_study=has_study)

    timestamp = int(__import__("time").time())
    svg_path = OUTPUT_DIR / f"planimetria_{timestamp}.svg"
    dxf_path = OUTPUT_DIR / f"planimetria_{timestamp}.dxf"

    svg_content = gen.to_svg()
    svg_path.write_text(svg_content, encoding="utf-8")
    gen.to_dxf(dxf_path)

    log.info("drawings.floor_plan_created", svg=str(svg_path), dxf=str(dxf_path))

    return {
        "type": "floor_plan",
        "svg_path": str(svg_path),
        "svg_url": f"/v1/files/{svg_path.name}",
        "dxf_path": str(dxf_path),
        "dxf_url": f"/v1/files/{dxf_path.name}",
        "svg_inline": svg_content,
        "rooms": [{"name": r.name, "area": r.area} for r in gen.rooms],
        "total_sqm": sum(r.area for r in gen.rooms),
    }


def create_excel(
    title: str,
    headers: list[str],
    rows: list[list[Any]],
) -> dict[str, Any]:
    """Genera un file Excel e ritorna il percorso."""
    timestamp = int(__import__("time").time())
    xlsx_path = OUTPUT_DIR / f"{title.replace(' ', '_')}_{timestamp}.xlsx"
    ExcelGenerator.from_data(title, headers, rows, xlsx_path)
    return {
        "type": "excel",
        "path": str(xlsx_path),
        "url": f"/v1/files/{xlsx_path.name}",
        "filename": xlsx_path.name,
    }


if __name__ == "__main__":
    # Test
    result = create_floor_plan(sqm=100, bedrooms=2, bathrooms=1, has_study=True)
    print(f"SVG: {result['svg_path']}")
    print(f"DXF: {result['dxf_path']}")
    print(f"Stanze: {len(result['rooms'])}")
    for r in result["rooms"]:
        print(f"  - {r['name']}: {r['area']} m²")
    print(f"Totale: {result['total_sqm']} m²")
