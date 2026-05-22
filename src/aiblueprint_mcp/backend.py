"""AIBlueprint backend — enhanced ezdxf engine with offset, fillet, dim overrides, and solid fills.

Based on autocad-mcp's ezdxf_backend (MIT), extended for site-plan drafting:
  - entity_offset: parallel polyline offset
  - entity_fillet: fillet arc between two lines
  - dimension style overrides (dimtxt, dimasz, dimlunit)
  - solid-fill hatch support
  - LibreCAD preview via dxf2png

Configuration via environment variables:
  AIBLUEPRINT_LIBRECAD_BIN — path to librecad executable
  AIBLUEPRINT_WORKSPACE    — working directory for preview renders
  DISPLAY                  — X11 display for WSLg/Linux GUI (default: :0)
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

import ezdxf
import structlog

from aiblueprint_mcp.types import CommandResult

log = structlog.get_logger()

# ── Configurable paths ─────────────────────────────────────────────────
def _find_librecad() -> Path:
    """Resolve LibreCAD binary from env or common locations."""
    env = os.environ.get("AIBLUEPRINT_LIBRECAD_BIN", "")
    if env:
        return Path(env)

    # Common install locations
    candidates = [
        Path.home() / "workspace/LibreCAD/unix/librecad",
        Path("/usr/bin/librecad"),
        Path("/usr/local/bin/librecad"),
        Path.home() / "LibreCAD/unix/librecad",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]  # fallback — user will get a clear error if missing


LIBRECAD_BIN = _find_librecad()
WORKSPACE = Path(os.environ.get("AIBLUEPRINT_WORKSPACE", str(Path.home() / "workspace")))
DISPLAY = os.environ.get("DISPLAY", ":0")


class AIBlueprintBackend:
    """Pure-Python DXF generation via ezdxf — extended for site plans."""

    def __init__(self):
        self._doc: ezdxf.document.Drawing | None = None
        self._msp = None
        self._save_path: str | None = None
        self._entity_counter = 0

    @property
    def name(self) -> str:
        return "aiblueprint"

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def initialize(self) -> CommandResult:
        self._doc = ezdxf.new("R2013")
        self._msp = self._doc.modelspace()
        return CommandResult(ok=True, payload={"backend": "aiblueprint", "version": ezdxf.__version__})

    async def status(self) -> CommandResult:
        entity_count = len(self._msp) if self._msp else 0
        layers = [l.dxf.name for l in self._doc.layers] if self._doc else []
        return CommandResult(ok=True, payload={
            "backend": "aiblueprint",
            "version": ezdxf.__version__,
            "has_document": self._doc is not None,
            "entity_count": entity_count,
            "layers": layers,
            "save_path": self._save_path,
        })

    def _next_id(self) -> str:
        self._entity_counter += 1
        return f"ab_{self._entity_counter}"

    def _ensure_layer(self, layer: str | None):
        if layer and layer not in self._doc.layers:
            self._doc.layers.add(layer)

    # ── Color helpers ──────────────────────────────────────────────────

    @staticmethod
    def _color_to_int(color: str | int) -> int:
        if isinstance(color, int):
            return color
        color_map = {
            "red": 1, "yellow": 2, "green": 3, "cyan": 4,
            "blue": 5, "magenta": 6, "white": 7, "grey": 8, "gray": 8,
            "darkgrey": 8, "lightgrey": 9, "lightgray": 9,
        }
        return color_map.get(color.lower(), 7)

    # ── Drawing management ─────────────────────────────────────────────

    async def drawing_create(self, name: str | None = None) -> CommandResult:
        self._doc = ezdxf.new("R2013")
        self._msp = self._doc.modelspace()
        self._entity_counter = 0
        self._save_path = f"{name}.dxf" if name else None
        return CommandResult(ok=True, payload={"name": name or "untitled"})

    async def drawing_info(self) -> CommandResult:
        if not self._doc:
            return CommandResult(ok=False, error="No document open")
        layers = [l.dxf.name for l in self._doc.layers]
        entity_count = len(self._msp)
        blocks = [b.name for b in self._doc.blocks if not b.name.startswith("*")]
        return CommandResult(ok=True, payload={
            "entity_count": entity_count, "layers": layers, "blocks": blocks,
            "dxf_version": self._doc.dxfversion, "save_path": self._save_path,
        })

    async def drawing_save(self, path: str | None = None) -> CommandResult:
        if not self._doc:
            return CommandResult(ok=False, error="No document open")
        save_path = path or self._save_path
        if not save_path:
            return CommandResult(ok=False, error="No save path specified")
        self._doc.saveas(save_path)
        self._save_path = save_path
        return CommandResult(ok=True, payload={"path": save_path})

    async def drawing_open(self, path: str) -> CommandResult:
        try:
            self._doc = ezdxf.readfile(path)
            self._msp = self._doc.modelspace()
            self._save_path = path
            return CommandResult(ok=True, payload={"path": path})
        except Exception as ex:
            return CommandResult(ok=False, error=str(ex))

    # ── Entity creation ────────────────────────────────────────────────

    async def create_line(self, x1: float, y1: float, x2: float, y2: float,
                          layer: str | None = None) -> CommandResult:
        self._ensure_layer(layer)
        e = self._msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": layer or "0"})
        return CommandResult(ok=True, payload={"entity_type": "LINE", "handle": e.dxf.handle})

    async def create_circle(self, cx: float, cy: float, radius: float,
                            layer: str | None = None) -> CommandResult:
        self._ensure_layer(layer)
        e = self._msp.add_circle((cx, cy), radius, dxfattribs={"layer": layer or "0"})
        return CommandResult(ok=True, payload={"entity_type": "CIRCLE", "handle": e.dxf.handle})

    async def create_polyline(self, points: list[list[float]], closed: bool = False,
                              layer: str | None = None) -> CommandResult:
        self._ensure_layer(layer)
        pts = [(p[0], p[1]) for p in points]
        e = self._msp.add_lwpolyline(pts, close=closed, dxfattribs={"layer": layer or "0"})
        return CommandResult(ok=True, payload={"entity_type": "LWPOLYLINE", "handle": e.dxf.handle})

    async def create_rectangle(self, x1: float, y1: float, x2: float, y2: float,
                               layer: str | None = None) -> CommandResult:
        pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        return await self.create_polyline(pts, closed=True, layer=layer)

    async def create_arc(self, cx: float, cy: float, radius: float,
                         start_angle: float, end_angle: float,
                         layer: str | None = None) -> CommandResult:
        self._ensure_layer(layer)
        e = self._msp.add_arc((cx, cy), radius, start_angle, end_angle,
                              dxfattribs={"layer": layer or "0"})
        return CommandResult(ok=True, payload={"entity_type": "ARC", "handle": e.dxf.handle})

    async def create_text(self, x: float, y: float, text: str,
                          height: float = 2.5, rotation: float = 0.0,
                          layer: str | None = None) -> CommandResult:
        self._ensure_layer(layer)
        e = self._msp.add_text(text, dxfattribs={
            "insert": (x, y), "height": height, "rotation": rotation,
            "layer": layer or "0",
        })
        return CommandResult(ok=True, payload={"entity_type": "TEXT", "handle": e.dxf.handle})

    async def create_mtext(self, x: float, y: float, width: float, text: str,
                           height: float = 2.5, layer: str | None = None) -> CommandResult:
        self._ensure_layer(layer)
        e = self._msp.add_mtext(text, dxfattribs={
            "insert": (x, y), "char_height": height, "width": width,
            "layer": layer or "0",
        })
        return CommandResult(ok=True, payload={"entity_type": "MTEXT", "handle": e.dxf.handle})

    # ── Entity query ───────────────────────────────────────────────────

    async def entity_list(self, layer: str | None = None) -> CommandResult:
        entities = []
        for e in self._msp:
            if layer and e.dxf.get("layer", "0") != layer:
                continue
            entities.append({
                "type": e.dxftype(), "handle": e.dxf.handle,
                "layer": e.dxf.get("layer", "0"),
            })
        return CommandResult(ok=True, payload={"entities": entities, "count": len(entities)})

    async def entity_get(self, entity_id: str) -> CommandResult:
        try:
            e = self._doc.entitydb.get(entity_id)
            if e is None:
                return CommandResult(ok=False, error=f"Entity {entity_id} not found")
            info = {"type": e.dxftype(), "handle": e.dxf.handle, "layer": e.dxf.get("layer", "0")}
            if e.dxftype() == "LINE":
                info["start"] = list(e.dxf.start)[:2]
                info["end"] = list(e.dxf.end)[:2]
            elif e.dxftype() == "CIRCLE":
                info["center"] = list(e.dxf.center)[:2]
                info["radius"] = e.dxf.radius
            elif e.dxftype() == "LWPOLYLINE":
                pts = list(e.get_points(format="xy"))
                info["points"] = pts
            return CommandResult(ok=True, payload=info)
        except Exception as ex:
            return CommandResult(ok=False, error=str(ex))

    # ── Entity modification ────────────────────────────────────────────

    async def entity_erase(self, entity_id: str) -> CommandResult:
        try:
            e = self._doc.entitydb.get(entity_id)
            if e is None:
                if entity_id == "last" and len(self._msp) > 0:
                    e = list(self._msp)[-1]
                else:
                    return CommandResult(ok=False, error=f"Entity {entity_id} not found")
            self._msp.delete_entity(e)
            return CommandResult(ok=True, payload={"erased": entity_id})
        except Exception as ex:
            return CommandResult(ok=False, error=str(ex))

    async def entity_copy(self, entity_id: str, dx: float, dy: float) -> CommandResult:
        try:
            e = self._doc.entitydb.get(entity_id)
            if e is None:
                return CommandResult(ok=False, error=f"Entity {entity_id} not found")
            copy = e.copy()
            self._msp.add_entity(copy)
            copy.translate(dx, dy, 0)
            return CommandResult(ok=True, payload={"handle": copy.dxf.handle})
        except Exception as ex:
            return CommandResult(ok=False, error=str(ex))

    async def entity_move(self, entity_id: str, dx: float, dy: float) -> CommandResult:
        try:
            e = self._doc.entitydb.get(entity_id)
            if e is None:
                return CommandResult(ok=False, error=f"Entity {entity_id} not found")
            e.translate(dx, dy, 0)
            return CommandResult(ok=True, payload={"moved": entity_id})
        except Exception as ex:
            return CommandResult(ok=False, error=str(ex))

    async def entity_rotate(self, entity_id: str, cx: float, cy: float,
                            angle: float) -> CommandResult:
        try:
            e = self._doc.entitydb.get(entity_id)
            if e is None:
                return CommandResult(ok=False, error=f"Entity {entity_id} not found")
            from ezdxf.math import Matrix44
            m = Matrix44.z_rotate(math.radians(angle))
            e.translate(-cx, -cy, 0)
            e.transform(m)
            e.translate(cx, cy, 0)
            return CommandResult(ok=True, payload={"rotated": entity_id})
        except Exception as ex:
            return CommandResult(ok=False, error=str(ex))

    async def entity_scale(self, entity_id: str, cx: float, cy: float,
                           factor: float) -> CommandResult:
        try:
            e = self._doc.entitydb.get(entity_id)
            if e is None:
                return CommandResult(ok=False, error=f"Entity {entity_id} not found")
            from ezdxf.math import Matrix44
            m = Matrix44.scale(factor, factor, factor)
            e.translate(-cx, -cy, 0)
            e.transform(m)
            e.translate(cx, cy, 0)
            return CommandResult(ok=True, payload={"scaled": entity_id})
        except Exception as ex:
            return CommandResult(ok=False, error=str(ex))

    async def entity_mirror(self, entity_id: str, x1: float, y1: float,
                            x2: float, y2: float) -> CommandResult:
        try:
            e = self._doc.entitydb.get(entity_id)
            if e is None:
                return CommandResult(ok=False, error=f"Entity {entity_id} not found")
            copy = e.copy()
            self._msp.add_entity(copy)
            dx, dy = x2 - x1, y2 - y1
            length_sq = dx * dx + dy * dy
            if length_sq == 0:
                return CommandResult(ok=False, error="Mirror line has zero length")
            from ezdxf.math import Matrix44
            a = math.atan2(dy, dx)
            cos2a = math.cos(2 * a)
            sin2a = math.sin(2 * a)
            m = Matrix44([
                cos2a, sin2a, 0, 0,
                sin2a, -cos2a, 0, 0,
                0, 0, 1, 0,
                0, 0, 0, 1,
            ])
            copy.translate(-x1, -y1, 0)
            copy.transform(m)
            copy.translate(x1, y1, 0)
            return CommandResult(ok=True, payload={"handle": copy.dxf.handle})
        except Exception as ex:
            return CommandResult(ok=False, error=str(ex))

    async def entity_array(self, entity_id: str, rows: int, cols: int,
                           row_dist: float, col_dist: float) -> CommandResult:
        try:
            e = self._doc.entitydb.get(entity_id)
            if e is None:
                return CommandResult(ok=False, error=f"Entity {entity_id} not found")
            handles = []
            for r in range(rows):
                for c in range(cols):
                    if r == 0 and c == 0:
                        continue
                    copy = e.copy()
                    self._msp.add_entity(copy)
                    copy.translate(c * col_dist, r * row_dist, 0)
                    handles.append(copy.dxf.handle)
            return CommandResult(ok=True, payload={"copies": len(handles), "handles": handles})
        except Exception as ex:
            return CommandResult(ok=False, error=str(ex))

    # ── NEW: entity_offset ─────────────────────────────────────────────

    async def entity_offset(self, entity_id: str, distance: float) -> CommandResult:
        """Offset a closed LWPOLYLINE by a given distance.

        Computes a parallel polyline by offsetting each edge inward/outward
        and computing intersection points. Positive distance = outward
        (counter-clockwise), negative = inward.
        """
        try:
            e = self._doc.entitydb.get(entity_id)
            if e is None:
                return CommandResult(ok=False, error=f"Entity {entity_id} not found")

            if e.dxftype() != "LWPOLYLINE":
                return CommandResult(ok=False, error="Offset only supports LWPOLYLINE entities")

            points = list(e.get_points(format="xy"))
            if len(points) < 3:
                return CommandResult(ok=False, error="Need at least 3 points for offset")

            is_closed = e.closed
            if not is_closed:
                return CommandResult(ok=False, error="Offset only supports closed polylines")

            pts = points + [points[0]] if is_closed else points
            n = len(pts) - 1

            offset_pts = []
            for i in range(n):
                # Get the two edges meeting at vertex i
                p_prev = pts[(i - 1) % n]
                p_curr = pts[i]
                p_next = pts[(i + 1) % n]

                # Compute edge vectors
                v1 = (p_curr[0] - p_prev[0], p_curr[1] - p_prev[1])
                v2 = (p_next[0] - p_curr[0], p_next[1] - p_curr[1])

                # Edge normals (rotate 90° counter-clockwise: (-y, x))
                len1 = math.hypot(v1[0], v1[1])
                len2 = math.hypot(v2[0], v2[1])
                if len1 == 0 or len2 == 0:
                    offset_pts.append(p_curr)
                    continue

                n1 = (-v1[1] / len1, v1[0] / len1)
                n2 = (-v2[1] / len2, v2[0] / len2)

                # Offset the two edges
                e1_start = (p_prev[0] + n1[0] * distance, p_prev[1] + n1[1] * distance)
                e1_end = (p_curr[0] + n1[0] * distance, p_curr[1] + n1[1] * distance)
                e2_start = (p_curr[0] + n2[0] * distance, p_curr[1] + n2[1] * distance)
                e2_end = (p_next[0] + n2[0] * distance, p_next[1] + n2[1] * distance)

                # Compute intersection of the two offset edges
                inter = _line_intersection(e1_start, e1_end, e2_start, e2_end)
                if inter:
                    offset_pts.append(inter)
                else:
                    offset_pts.append(e1_end)

            new_pts = [(p[0], p[1]) for p in offset_pts]
            e_new = self._msp.add_lwpolyline(new_pts, close=True)
            return CommandResult(ok=True, payload={
                "entity_type": "LWPOLYLINE",
                "handle": e_new.dxf.handle,
                "offset": distance,
                "points": len(offset_pts),
            })
        except Exception as ex:
            return CommandResult(ok=False, error=str(ex))

    # ── NEW: entity_fillet ─────────────────────────────────────────────

    async def entity_fillet(self, entity_id1: str, entity_id2: str,
                            radius: float) -> CommandResult:
        """Fillet two LINE entities with an arc of given radius.

        Finds the tangent points and draws the fillet arc between them.
        Trims the original lines to the tangent points.
        """
        try:
            e1 = self._doc.entitydb.get(entity_id1)
            e2 = self._doc.entitydb.get(entity_id2)
            if e1 is None or e2 is None:
                return CommandResult(ok=False, error="Entity not found")
            if e1.dxftype() != "LINE" or e2.dxftype() != "LINE":
                return CommandResult(ok=False, error="Fillet requires two LINE entities")

            # Get line endpoints
            l1_start = (e1.dxf.start.x, e1.dxf.start.y)
            l1_end = (e1.dxf.end.x, e1.dxf.end.y)
            l2_start = (e2.dxf.start.x, e2.dxf.start.y)
            l2_end = (e2.dxf.end.x, e2.dxf.end.y)

            # Find intersection point of the two lines (extended)
            inter = _line_intersection(l1_start, l1_end, l2_start, l2_end)
            if not inter:
                return CommandResult(ok=False, error="Lines are parallel — cannot fillet")

            # Determine which endpoints are closest to intersection
            d1a = math.hypot(l1_start[0] - inter[0], l1_start[1] - inter[1])
            d1b = math.hypot(l1_end[0] - inter[0], l1_end[1] - inter[1])
            keep1 = l1_start if d1a > d1b else l1_end  # endpoint away from intersection
            near1 = l1_end if d1a > d1b else l1_start   # endpoint near intersection

            d2a = math.hypot(l2_start[0] - inter[0], l2_start[1] - inter[1])
            d2b = math.hypot(l2_end[0] - inter[0], l2_end[1] - inter[1])
            keep2 = l2_start if d2a > d2b else l2_end
            near2 = l2_end if d2a > d2b else l2_start

            # Direction vectors from intersection along each line.
            # Use direction toward FAR endpoint (keep), which always has nonzero length.
            # Then negate to get direction from keep toward intersection (where fillet cuts in).
            v1_far = (keep1[0] - inter[0], keep1[1] - inter[1])
            v2_far = (keep2[0] - inter[0], keep2[1] - inter[1])
            len1 = math.hypot(v1_far[0], v1_far[1])
            len2 = math.hypot(v2_far[0], v2_far[1])

            if len1 == 0 or len2 == 0:
                return CommandResult(ok=False, error="Zero-length line segment")

            # Unit vectors pointing AWAY from intersection (toward keep).
            u1_far = (v1_far[0] / len1, v1_far[1] / len1)
            u2_far = (v2_far[0] / len2, v2_far[1] / len2)

            # unit vectors from near toward inter (into the corner) — negate far dir
            u1 = (-u1_far[0], -u1_far[1])
            u2 = (-u2_far[0], -u2_far[1])

            # Angle between lines
            dot = u1[0] * u2[0] + u1[1] * u2[1]
            dot = max(-1, min(1, dot))  # clamp for floating point
            half_angle = math.acos(dot) / 2

            if abs(math.sin(half_angle)) < 1e-10:
                return CommandResult(ok=False, error="Lines are nearly parallel")

            # Tangent distance from intersection
            tan_dist = radius / math.tan(half_angle)

            # Tangent points
            t1 = (inter[0] + u1[0] * tan_dist, inter[1] + u1[1] * tan_dist)
            t2 = (inter[0] + u2[0] * tan_dist, inter[1] + u2[1] * tan_dist)

            # Arc center (perpendicular from tangent point, distance = radius)
            perp1 = (-u1[1], u1[0])  # rotate 90° CCW
            center = (t1[0] + perp1[0] * radius, t1[1] + perp1[1] * radius)

            # Verify center is on correct side (closer to intersection)
            if math.hypot(center[0] - inter[0], center[1] - inter[1]) > math.hypot(t1[0] - inter[0], t1[1] - inter[1]):
                center = (t1[0] - perp1[0] * radius, t1[1] - perp1[1] * radius)

            # Calculate arc angles
            start_angle = math.degrees(math.atan2(t1[1] - center[1], t1[0] - center[0]))
            end_angle = math.degrees(math.atan2(t2[1] - center[1], t2[0] - center[0]))

            # Draw the fillet arc
            arc = self._msp.add_arc(
                center, radius, start_angle, end_angle,
                dxfattribs={"layer": e1.dxf.get("layer", "0")},
            )

            # Trim lines to tangent points
            e1.dxf.start = keep1
            e1.dxf.end = t1
            e2.dxf.start = keep2
            e2.dxf.end = t2

            return CommandResult(ok=True, payload={
                "entity_type": "ARC",
                "handle": arc.dxf.handle,
                "radius": radius,
                "tangent_points": [list(t1), list(t2)],
            })
        except Exception as ex:
            return CommandResult(ok=False, error=str(ex))

    # ── Layer operations ───────────────────────────────────────────────

    async def layer_list(self) -> CommandResult:
        layers = []
        for l in self._doc.layers:
            layers.append({
                "name": l.dxf.name,
                "color": l.dxf.get("color", 7),
                "linetype": l.dxf.get("linetype", "Continuous"),
                "is_frozen": l.is_frozen(),
                "is_locked": l.is_locked(),
            })
        return CommandResult(ok=True, payload={"layers": layers})

    async def layer_create(self, name: str, color: str = "white",
                           linetype: str = "CONTINUOUS") -> CommandResult:
        if name in self._doc.layers:
            return CommandResult(ok=True, payload={"name": name, "existed": True})
        color_int = self._color_to_int(color)
        self._doc.layers.add(name, color=color_int, linetype=linetype)
        return CommandResult(ok=True, payload={"name": name, "color": color_int})

    async def layer_set_current(self, name: str) -> CommandResult:
        if name not in self._doc.layers:
            return CommandResult(ok=False, error=f"Layer '{name}' does not exist")
        self._doc.header["$CLAYER"] = name
        return CommandResult(ok=True, payload={"current_layer": name})

    async def layer_set_properties(self, name: str, color: str | None = None,
                                   linetype: str | None = None) -> CommandResult:
        if name not in self._doc.layers:
            return CommandResult(ok=False, error=f"Layer '{name}' does not exist")
        layer = self._doc.layers.get(name)
        if color is not None:
            layer.color = self._color_to_int(color)
        if linetype is not None:
            layer.dxf.linetype = linetype
        return CommandResult(ok=True, payload={"name": name})

    async def layer_freeze(self, name: str) -> CommandResult:
        if name not in self._doc.layers:
            return CommandResult(ok=False, error=f"Layer '{name}' does not exist")
        self._doc.layers.get(name).freeze()
        return CommandResult(ok=True, payload={"name": name, "frozen": True})

    async def layer_thaw(self, name: str) -> CommandResult:
        if name not in self._doc.layers:
            return CommandResult(ok=False, error=f"Layer '{name}' does not exist")
        self._doc.layers.get(name).thaw()
        return CommandResult(ok=True, payload={"name": name, "frozen": False})

    async def layer_lock(self, name: str) -> CommandResult:
        if name not in self._doc.layers:
            return CommandResult(ok=False, error=f"Layer '{name}' does not exist")
        self._doc.layers.get(name).lock()
        return CommandResult(ok=True, payload={"name": name, "locked": True})

    async def layer_unlock(self, name: str) -> CommandResult:
        if name not in self._doc.layers:
            return CommandResult(ok=False, error=f"Layer '{name}' does not exist")
        self._doc.layers.get(name).unlock()
        return CommandResult(ok=True, payload={"name": name, "locked": False})

    # ── Annotation (with dimension overrides) ──────────────────────────

    async def create_dimension_aligned(self, x1: float, y1: float, x2: float, y2: float,
                                       offset: float,
                                       dim_overrides: dict | None = None) -> CommandResult:
        """Aligned dimension with optional style overrides.

        dim_overrides: {dimtxt, dimasz, dimlunit, dimclrd, dimclre, dimclrt}
        """
        try:
            dim = self._msp.add_aligned_dim(p1=(x1, y1), p2=(x2, y2), distance=offset)
            override = self._apply_overrides(dim, dim_overrides)
            dim.render()
            return CommandResult(ok=True, payload={
                "entity_type": "DIMENSION",
                "overrides_applied": override,
            })
        except Exception as ex:
            return CommandResult(ok=False, error=str(ex))

    async def create_dimension_linear(self, x1: float, y1: float, x2: float, y2: float,
                                      dim_x: float, dim_y: float,
                                      dim_overrides: dict | None = None) -> CommandResult:
        """Linear dimension with optional style overrides."""
        try:
            dim = self._msp.add_linear_dim(base=(dim_x, dim_y), p1=(x1, y1), p2=(x2, y2))
            override = self._apply_overrides(dim, dim_overrides)
            dim.render()
            return CommandResult(ok=True, payload={
                "entity_type": "DIMENSION",
                "overrides_applied": override,
            })
        except Exception as ex:
            return CommandResult(ok=False, error=str(ex))

    async def create_dimension_angular(self, cx: float, cy: float,
                                       x1: float, y1: float, x2: float, y2: float,
                                       dim_overrides: dict | None = None) -> CommandResult:
        """Angular dimension with optional style overrides."""
        try:
            a1 = math.atan2(y1 - cy, x1 - cx)
            a2 = math.atan2(y2 - cy, x2 - cx)
            r = max(math.hypot(x1 - cx, y1 - cy), math.hypot(x2 - cx, y2 - cy)) * 0.7
            dim = self._msp.add_angular_dim_cra(
                center=(cx, cy), radius=r,
                start_angle=math.degrees(a1), end_angle=math.degrees(a2),
                distance=r * 1.2,
            )
            override = self._apply_overrides(dim, dim_overrides)
            dim.render()
            return CommandResult(ok=True, payload={
                "entity_type": "DIMENSION",
                "overrides_applied": override,
            })
        except Exception as ex:
            return CommandResult(ok=False, error=str(ex))

    async def create_dimension_radius(self, cx: float, cy: float, radius: float,
                                      angle: float,
                                      dim_overrides: dict | None = None) -> CommandResult:
        """Radius dimension with optional style overrides."""
        try:
            rad = math.radians(angle)
            px = cx + radius * math.cos(rad)
            py = cy + radius * math.sin(rad)
            dim = self._msp.add_radius_dim(center=(cx, cy), mpoint=(px, py))
            override = self._apply_overrides(dim, dim_overrides)
            dim.render()
            return CommandResult(ok=True, payload={
                "entity_type": "DIMENSION",
                "overrides_applied": override,
            })
        except Exception as ex:
            return CommandResult(ok=False, error=str(ex))

    async def create_leader(self, points: list[list[float]], text: str) -> CommandResult:
        """Create a leader line with text annotation."""
        try:
            pts = [(p[0], p[1]) for p in points]
            leader = self._msp.add_leader(pts)
            last = pts[-1]
            self._msp.add_mtext(text, dxfattribs={
                "insert": (last[0] + 2, last[1]),
                "char_height": 2.5, "width": 30,
            })
            return CommandResult(ok=True, payload={"entity_type": "LEADER"})
        except Exception as ex:
            return CommandResult(ok=False, error=str(ex))

    @staticmethod
    def _apply_overrides(dim, dim_overrides: dict | None) -> list[str]:
        """Apply dimension style overrides directly to dim.dimstyle.dxf."""
        if not dim_overrides:
            return []
        applied = []
        for attr in ["dimtxt", "dimasz", "dimlunit", "dimclrd", "dimclre", "dimclrt", "dimtxsty"]:
            if attr in dim_overrides:
                setattr(dim.dimstyle.dxf, attr, dim_overrides[attr])
                applied.append(attr)
        return applied

    # ── NEW: Hatch with solid fill support ─────────────────────────────

    async def create_hatch(self, entity_id: str, pattern: str = "ANSI31",
                           scale: float = 1.0) -> CommandResult:
        """Create a hatch from an entity boundary. pattern='SOLID' for solid fill."""
        try:
            e = self._doc.entitydb.get(entity_id)
            if e is None:
                return CommandResult(ok=False, error=f"Entity {entity_id} not found")

            # Get boundary points
            if e.dxftype() == "LWPOLYLINE":
                boundary_pts = [(p[0], p[1]) for p in e.get_points(format="xy")]
            elif e.dxftype() == "CIRCLE":
                # Approximate circle with polyline for hatch boundary
                cx, cy = e.dxf.center.x, e.dxf.center.y
                r = e.dxf.radius
                n = 36
                boundary_pts = [
                    (cx + r * math.cos(2 * math.pi * i / n),
                     cy + r * math.sin(2 * math.pi * i / n))
                    for i in range(n)
                ]
            else:
                return CommandResult(ok=False, error=f"Cannot hatch entity type {e.dxftype()}")

            hatch = self._msp.add_hatch()
            if pattern.upper() == "SOLID":
                hatch.set_solid_fill()
            else:
                hatch.set_pattern_fill(pattern, scale=scale)

            hatch.paths.add_polyline_path(boundary_pts, is_closed=True)
            return CommandResult(ok=True, payload={
                "entity_type": "HATCH",
                "handle": hatch.dxf.handle,
                "pattern": pattern,
                "is_solid": pattern.upper() == "SOLID",
            })
        except Exception as ex:
            return CommandResult(ok=False, error=str(ex))

    # ── Block operations ───────────────────────────────────────────────

    async def block_define(self, name: str, entities: list[dict]) -> CommandResult:
        block = self._doc.blocks.new(name=name)
        for ent_def in entities:
            etype = ent_def.get("type", "LINE")
            if etype == "LINE":
                block.add_line(
                    (ent_def.get("x1", 0), ent_def.get("y1", 0)),
                    (ent_def.get("x2", 0), ent_def.get("y2", 0)),
                )
            elif etype == "CIRCLE":
                block.add_circle(
                    (ent_def.get("cx", 0), ent_def.get("cy", 0)),
                    ent_def.get("radius", 1),
                )
            elif etype == "LWPOLYLINE":
                pts = [(p[0], p[1]) for p in ent_def.get("points", [])]
                block.add_lwpolyline(pts, close=ent_def.get("closed", False))
            elif etype == "ATTDEF":
                block.add_attdef(
                    ent_def.get("tag", "TAG"),
                    (ent_def.get("x", 0), ent_def.get("y", 0)),
                    dxfattribs={"height": ent_def.get("height", 2.5)},
                )
        return CommandResult(ok=True, payload={"block": name, "entity_count": len(entities)})

    async def block_list(self) -> CommandResult:
        blocks = [b.name for b in self._doc.blocks if not b.name.startswith("*")]
        return CommandResult(ok=True, payload={"blocks": blocks})

    async def block_insert(self, name: str, x: float, y: float,
                           scale: float = 1.0, rotation: float = 0.0) -> CommandResult:
        if name not in self._doc.blocks:
            return CommandResult(ok=False, error=f"Block '{name}' not defined")
        e = self._msp.add_blockref(name, (x, y), dxfattribs={
            "xscale": scale, "yscale": scale, "zscale": scale,
            "rotation": rotation,
        })
        return CommandResult(ok=True, payload={"entity_type": "INSERT", "handle": e.dxf.handle})

    async def block_insert_with_attributes(self, name: str, x: float, y: float,
                                           scale: float = 1.0, rotation: float = 0.0,
                                           attributes: dict[str, str] | None = None) -> CommandResult:
        if name not in self._doc.blocks:
            return CommandResult(ok=False, error=f"Block '{name}' not defined")
        e = self._msp.add_blockref(name, (x, y), dxfattribs={
            "xscale": scale, "yscale": scale, "zscale": scale,
            "rotation": rotation,
        })
        if attributes:
            try:
                e.add_auto_attribs(attributes)
            except Exception:
                for tag, value in attributes.items():
                    try:
                        e.add_attrib(tag, value, (x, y))
                    except Exception:
                        pass
        return CommandResult(ok=True, payload={"entity_type": "INSERT", "handle": e.dxf.handle})

    async def block_get_attributes(self, entity_id: str) -> CommandResult:
        try:
            e = self._doc.entitydb.get(entity_id)
            if e is None or e.dxftype() != "INSERT":
                return CommandResult(ok=False, error="Not an INSERT entity")
            attribs = {}
            for attrib in e.attribs:
                attribs[attrib.dxf.tag] = attrib.dxf.text
            return CommandResult(ok=True, payload={"attributes": attribs})
        except Exception as ex:
            return CommandResult(ok=False, error=str(ex))

    async def block_update_attribute(self, entity_id: str, tag: str, value: str) -> CommandResult:
        try:
            e = self._doc.entitydb.get(entity_id)
            if e is None or e.dxftype() != "INSERT":
                return CommandResult(ok=False, error="Not an INSERT entity")
            for attrib in e.attribs:
                if attrib.dxf.tag.upper() == tag.upper():
                    attrib.dxf.text = value
                    return CommandResult(ok=True, payload={"tag": tag, "value": value})
            return CommandResult(ok=False, error=f"Attribute '{tag}' not found")
        except Exception as ex:
            return CommandResult(ok=False, error=str(ex))

    # ── Screenshot ─────────────────────────────────────────────────────

    async def get_screenshot(self) -> CommandResult:
        """Render DXF to PNG via matplotlib (base64)."""
        if self._doc is None:
            return CommandResult(ok=False, error="No document open")
        try:
            import base64
            import io

            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            from ezdxf.addons.drawing import Frontend, RenderContext
            from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

            fig, ax = plt.subplots(figsize=(16, 10), dpi=150)
            ax.set_aspect("equal")
            ctx = RenderContext(self._doc)
            out = MatplotlibBackend(ax)
            Frontend(ctx, out).draw_layout(self._doc.modelspace())

            buf = io.BytesIO()
            fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.1)
            plt.close(fig)
            buf.seek(0)
            data = base64.b64encode(buf.read()).decode("ascii")
            return CommandResult(ok=True, payload=data)
        except Exception as e:
            return CommandResult(ok=False, error=str(e))

    # ── NEW: LibreCAD preview ──────────────────────────────────────────

    async def preview(self, save_first: bool = True) -> CommandResult:
        """Save DXF and render a PNG preview via LibreCAD dxf2png.

        Returns the PNG path for inline display.
        """
        import subprocess
        import tempfile

        if not self._doc:
            return CommandResult(ok=False, error="No document open")

        # Save DXF to temp file
        dxf_path = Path(tempfile.gettempdir()) / "aiblueprint_preview.dxf"
        png_path = Path(tempfile.gettempdir()) / "aiblueprint_preview.png"

        self._doc.saveas(str(dxf_path))

        # Render with LibreCAD
        librecad = LIBRECAD_BIN
        if not librecad.exists():
            return CommandResult(ok=False, error=(
                f"LibreCAD not found at {librecad}. "
                "Set AIBLUEPRINT_LIBRECAD_BIN to your librecad path, "
                "or build from source: https://docs.librecad.org/en/latest/appx/build.html"
            ))

        try:
            result = subprocess.run(
                [str(librecad), "dxf2png", "-o", str(png_path), str(dxf_path)],
                capture_output=True, text=True, timeout=15,
                env={**__import__("os").environ, "DISPLAY": DISPLAY},
                cwd=str(WORKSPACE) if WORKSPACE.exists() else None,
            )
            if result.returncode != 0:
                return CommandResult(ok=False, error=result.stderr.strip())
            return CommandResult(ok=True, payload={
                "dxf_path": str(dxf_path),
                "png_path": str(png_path),
                "entity_count": len(self._msp) if self._msp else 0,
            })
        except subprocess.TimeoutExpired:
            return CommandResult(ok=False, error="dxf2png timed out")
        except Exception as ex:
            return CommandResult(ok=False, error=str(ex))


# ── Geometry helpers ───────────────────────────────────────────────────


def _line_intersection(p1, p2, p3, p4):
    """Compute intersection of two line segments (p1-p2) and (p3-p4).

    Returns (x, y) or None if parallel.
    """
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-10:
        return None

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    x = x1 + t * (x2 - x1)
    y = y1 + t * (y2 - y1)
    return (x, y)
