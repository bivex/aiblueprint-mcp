"""AIBlueprint MCP Server — 6 consolidated tools for site-plan drafting.

Tools: drawing, entity, layer, block, annotation, view

Each tool dispatches to operation-specific backend methods.
"""

from __future__ import annotations

import structlog
from mcp.server.fastmcp import FastMCP

from aiblueprint_mcp.backend import AIBlueprintBackend

log = structlog.get_logger()
mcp = FastMCP("aiblueprint-mcp")

_backend: AIBlueprintBackend | None = None


async def _get_backend() -> AIBlueprintBackend:
    """Lazy-initialize the backend singleton."""
    global _backend
    if _backend is None:
        _backend = AIBlueprintBackend()
        result = await _backend.initialize()
        if not result.ok:
            raise RuntimeError(f"Backend init failed: {result.error}")
        log.info("backend_initialized", backend=_backend.name)
    return _backend


def _ok(data: dict) -> str:
    """Serialize a result dict to JSON."""
    import json
    return json.dumps({"ok": True, **data}, default=str)


def _err(msg: str) -> str:
    """Serialize an error to JSON."""
    import json
    return json.dumps({"ok": False, "error": msg})


# ═══════════════════════════════════════════════════════════════════════
# 1. drawing — File/drawing management
# ═══════════════════════════════════════════════════════════════════════

@mcp.tool()
async def drawing(operation: str, data: dict | None = None) -> str:
    """Drawing file management.

    Operations:
      create — New empty drawing. data: {name?}
      open   — Open existing DXF. data: {path}
      info   — Get layers, entity count, blocks.
      save   — Save to path. data: {path}
    """
    data = data or {}
    b = await _get_backend()

    if operation == "create":
        r = await b.drawing_create(data.get("name"))
    elif operation == "open":
        r = await b.drawing_open(data["path"])
    elif operation == "info":
        r = await b.drawing_info()
    elif operation == "save":
        r = await b.drawing_save(data.get("path"))
    else:
        return _err(f"Unknown drawing operation: {operation}")

    return _ok(r.payload) if r.ok else _err(r.error or "Unknown error")


# ═══════════════════════════════════════════════════════════════════════
# 2. entity — Entity CRUD + modification
# ═══════════════════════════════════════════════════════════════════════

@mcp.tool()
async def entity(
    operation: str,
    x1: float | None = None, y1: float | None = None,
    x2: float | None = None, y2: float | None = None,
    points: list[list[float]] | None = None,
    layer: str | None = None,
    entity_id: str | None = None,
    data: dict | None = None,
) -> str:
    """Entity creation, querying, and modification.

    Create operations:
      create_line       — x1, y1, x2, y2, layer?
      create_circle     — data: {cx, cy, radius}, layer?
      create_polyline   — points: [[x,y],...], data: {closed?}, layer?
      create_rectangle  — x1, y1, x2, y2, layer?
      create_arc        — data: {cx, cy, radius, start_angle, end_angle}, layer?
      create_text       — data: {x, y, text, height?, rotation?}, layer?
      create_mtext      — data: {x, y, width, text, height?}, layer?
      create_hatch      — entity_id, data: {pattern?, scale?}

    Read operations:
      list              — layer? → list entities
      get               — entity_id → entity details

    Modify operations:
      copy    — entity_id, data: {dx, dy}
      move    — entity_id, data: {dx, dy}
      rotate  — entity_id, data: {cx, cy, angle}
      scale   — entity_id, data: {cx, cy, factor}
      mirror  — entity_id, x1, y1, x2, y2
      offset  — entity_id, data: {distance}
      array   — entity_id, data: {rows, cols, row_dist, col_dist}
      fillet  — data: {id1, id2, radius}
      erase   — entity_id
    """
    data = data or {}
    b = await _get_backend()

    # Create
    if operation == "create_line":
        r = await b.create_line(x1, y1, x2, y2, layer)
    elif operation == "create_circle":
        r = await b.create_circle(data["cx"], data["cy"], data["radius"], layer)
    elif operation == "create_polyline":
        r = await b.create_polyline(points or [], data.get("closed", False), layer)
    elif operation == "create_rectangle":
        r = await b.create_rectangle(x1, y1, x2, y2, layer)
    elif operation == "create_arc":
        r = await b.create_arc(data["cx"], data["cy"], data["radius"],
                               data["start_angle"], data["end_angle"], layer)
    elif operation == "create_text":
        r = await b.create_text(data["x"], data["y"], data["text"],
                                data.get("height", 2.5), data.get("rotation", 0.0), layer)
    elif operation == "create_mtext":
        r = await b.create_mtext(data["x"], data["y"], data["width"], data["text"],
                                 data.get("height", 2.5), layer)
    elif operation == "create_hatch":
        r = await b.create_hatch(entity_id, data.get("pattern", "ANSI31"),
                                 data.get("scale", 1.0))
    # Read
    elif operation == "list":
        r = await b.entity_list(layer)
    elif operation == "get":
        r = await b.entity_get(entity_id)
    # Modify
    elif operation == "copy":
        r = await b.entity_copy(entity_id, data["dx"], data["dy"])
    elif operation == "move":
        r = await b.entity_move(entity_id, data["dx"], data["dy"])
    elif operation == "rotate":
        r = await b.entity_rotate(entity_id, data["cx"], data["cy"], data["angle"])
    elif operation == "scale":
        r = await b.entity_scale(entity_id, data["cx"], data["cy"], data["factor"])
    elif operation == "mirror":
        r = await b.entity_mirror(entity_id, x1, y1, x2, y2)
    elif operation == "offset":
        r = await b.entity_offset(entity_id, data["distance"])
    elif operation == "array":
        r = await b.entity_array(entity_id, data["rows"], data["cols"],
                                 data["row_dist"], data["col_dist"])
    elif operation == "fillet":
        r = await b.entity_fillet(data["id1"], data["id2"], data["radius"])
    elif operation == "erase":
        r = await b.entity_erase(entity_id)
    else:
        return _err(f"Unknown entity operation: {operation}")

    return _ok(r.payload) if r.ok else _err(r.error or "Unknown error")


# ═══════════════════════════════════════════════════════════════════════
# 3. layer — Layer management
# ═══════════════════════════════════════════════════════════════════════

@mcp.tool()
async def layer(operation: str, data: dict | None = None) -> str:
    """Layer creation and management.

    Operations:
      list            — List all layers.
      create          — data: {name, color?, linetype?}
      set_current     — data: {name}
      set_properties  — data: {name, color?, linetype?}
      freeze / thaw   — data: {name}
      lock / unlock   — data: {name}
    """
    data = data or {}
    b = await _get_backend()

    if operation == "list":
        r = await b.layer_list()
    elif operation == "create":
        r = await b.layer_create(data["name"], data.get("color", "white"),
                                 data.get("linetype", "CONTINUOUS"))
    elif operation == "set_current":
        r = await b.layer_set_current(data["name"])
    elif operation == "set_properties":
        r = await b.layer_set_properties(data["name"], data.get("color"),
                                         data.get("linetype"))
    elif operation == "freeze":
        r = await b.layer_freeze(data["name"])
    elif operation == "thaw":
        r = await b.layer_thaw(data["name"])
    elif operation == "lock":
        r = await b.layer_lock(data["name"])
    elif operation == "unlock":
        r = await b.layer_unlock(data["name"])
    else:
        return _err(f"Unknown layer operation: {operation}")

    return _ok(r.payload) if r.ok else _err(r.error or "Unknown error")


# ═══════════════════════════════════════════════════════════════════════
# 4. block — Block operations
# ═══════════════════════════════════════════════════════════════════════

@mcp.tool()
async def block(operation: str, data: dict | None = None) -> str:
    """Block definition, insertion, and attribute management.

    Operations:
      list                    — List all block definitions.
      insert                  — data: {name, x, y, scale?, rotation?}
      insert_with_attributes  — data: {name, x, y, scale?, rotation?, attributes: {tag: value}}
      get_attributes          — data: {entity_id}
      update_attribute        — data: {entity_id, tag, value}
      define                  — data: {name, entities: [{type, ...}]}
    """
    data = data or {}
    b = await _get_backend()

    if operation == "list":
        r = await b.block_list()
    elif operation == "insert":
        r = await b.block_insert(data["name"], data["x"], data["y"],
                                 data.get("scale", 1.0), data.get("rotation", 0.0))
    elif operation == "insert_with_attributes":
        r = await b.block_insert_with_attributes(
            data["name"], data["x"], data["y"],
            data.get("scale", 1.0), data.get("rotation", 0.0),
            data.get("attributes"),
        )
    elif operation == "get_attributes":
        r = await b.block_get_attributes(data["entity_id"])
    elif operation == "update_attribute":
        r = await b.block_update_attribute(data["entity_id"], data["tag"], data["value"])
    elif operation == "define":
        r = await b.block_define(data["name"], data.get("entities", []))
    else:
        return _err(f"Unknown block operation: {operation}")

    return _ok(r.payload) if r.ok else _err(r.error or "Unknown error")


# ═══════════════════════════════════════════════════════════════════════
# 5. annotation — Text, dimensions, leaders
# ═══════════════════════════════════════════════════════════════════════

@mcp.tool()
async def annotation(operation: str, data: dict | None = None) -> str:
    """Annotation: text, dimensions, and leaders.

    Operations:
      create_text               — data: {x, y, text, height?, rotation?, layer?}
      create_dimension_aligned  — data: {x1, y1, x2, y2, offset, dim_overrides?}
      create_dimension_linear   — data: {x1, y1, x2, y2, dim_x, dim_y, dim_overrides?}
      create_dimension_angular  — data: {cx, cy, x1, y1, x2, y2, dim_overrides?}
      create_dimension_radius   — data: {cx, cy, radius, angle, dim_overrides?}
      create_leader             — data: {points: [[x,y],...], text}

    dim_overrides: {dimtxt, dimasz, dimlunit, dimclrd, dimclre, dimclrt, dimtxsty}
    """
    data = data or {}
    b = await _get_backend()

    if operation == "create_text":
        r = await b.create_text(
            data["x"], data["y"], data["text"],
            data.get("height", 2.5), data.get("rotation", 0.0), data.get("layer"),
        )
    elif operation == "create_dimension_aligned":
        r = await b.create_dimension_aligned(
            data["x1"], data["y1"], data["x2"], data["y2"], data["offset"],
            data.get("dim_overrides"),
        )
    elif operation == "create_dimension_linear":
        r = await b.create_dimension_linear(
            data["x1"], data["y1"], data["x2"], data["y2"],
            data["dim_x"], data["dim_y"], data.get("dim_overrides"),
        )
    elif operation == "create_dimension_angular":
        r = await b.create_dimension_angular(
            data["cx"], data["cy"], data["x1"], data["y1"],
            data["x2"], data["y2"], data.get("dim_overrides"),
        )
    elif operation == "create_dimension_radius":
        r = await b.create_dimension_radius(
            data["cx"], data["cy"], data["radius"], data["angle"],
            data.get("dim_overrides"),
        )
    elif operation == "create_leader":
        r = await b.create_leader(data["points"], data["text"])
    else:
        return _err(f"Unknown annotation operation: {operation}")

    return _ok(r.payload) if r.ok else _err(r.error or "Unknown error")


# ═══════════════════════════════════════════════════════════════════════
# 6. view — Preview and screenshot
# ═══════════════════════════════════════════════════════════════════════

@mcp.tool()
async def view(operation: str) -> str:
    """Preview and screenshot.

    Operations:
      screenshot   — Render DXF as base64 PNG (matplotlib).
      preview      — Save DXF + render PNG via LibreCAD dxf2png. Returns file paths.
    """
    b = await _get_backend()

    if operation == "screenshot":
        r = await b.get_screenshot()
    elif operation == "preview":
        r = await b.preview()
    else:
        return _err(f"Unknown view operation: {operation}")

    return _ok(r.payload) if r.ok else _err(r.error or "Unknown error")


async def main():
    """Run the MCP server over stdio."""
    await mcp.run_stdio_async()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
