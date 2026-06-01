# AIBlueprint MCP Project Instructions

## Environment Setup
- **LibreCAD Path**: `/Applications/LibreCAD.app/Contents/MacOS/LibreCAD`
- **Workspace**: `/Volumes/External/Code/aiblueprint-mcp`

## Configuration
The server is configured in Gemini CLI with:
- **Command**: `uv run --directory /Volumes/External/Code/aiblueprint-mcp aiblueprint-mcp`
- **Environment**: `AIBLUEPRINT_LIBRECAD_BIN=/Applications/LibreCAD.app/Contents/MacOS/LibreCAD`

## Drafting Workflow
- Units are consistently in **meters**.
- Use layers: `WALLS_EXTERIOR`, `WALLS_INTERIOR`, `HATCH_CONCRETE`, `ANNOTATIONS`.
- Previews are generated via the `view -> preview` tool which uses LibreCAD's `dxf2png`.
- When using LibreCAD GUI for viewing, use `File -> Revert` to see updates from the AI.
