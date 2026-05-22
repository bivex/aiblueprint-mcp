# AIBlueprint MCP

MCP server for headless DXF generation via ezdxf + LibreCAD preview — purpose-built for site plans and architectural drafting.

## Tools

| Tool | Description |
|------|-------------|
| `drawing` | File management: create, open, info, save |
| `entity` | Entity CRUD: lines, polylines, circles, rectangles, arcs, text, hatches. Modify: copy, move, rotate, scale, mirror, offset, fillet, array, erase |
| `layer` | Layer management: list, create, set current, set properties, freeze/thaw, lock/unlock |
| `block` | Block definition, insertion, attributes |
| `annotation` | Dimensions (aligned, linear, angular, radius with style overrides), leaders, text |
| `view` | Screenshot (matplotlib) and LibreCAD preview (dxf2png) |

## Key Features

- **entity_offset** — offset closed polylines inward/outward for deck bands, setbacks, concentric shapes
- **entity_fillet** — fillet two lines with a radius arc for rounded corners
- **Dimension overrides** — dimtxt, dimasz, dimlunit, dimclrd, dimclre, dimclrt, dimtxsty
- **Solid hatch fills** — pattern="SOLID" for water features, hardscape
- **LibreCAD preview** — dxf2png integration for instant visual feedback
- **0 software license cost** — ezdxf is MIT, LibreCAD is GPL

## Usage

```bash
# Install
git clone https://github.com/thebossnow/aiblueprint-mcp
cd aiblueprint-mcp
uv sync

# Run as MCP server (stdio)
uv run aiblueprint-mcp
```

Configure in your MCP client (Claude Desktop, Hermes, etc.):

```json
{
  "mcpServers": {
    "aiblueprint-mcp": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/aiblueprint-mcp", "aiblueprint-mcp"]
    }
  }
}
```
