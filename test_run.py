import asyncio
from aiblueprint_mcp.backend import AIBlueprintBackend

async def main():
    b = AIBlueprintBackend()
    await b.initialize()
    print("Backend initialized.")
    await b.drawing_create("my_test_plan")
    
    # Draw a simple rectangle
    await b.create_rectangle(0, 0, 100, 80, layer="LOT")
    
    # Save it
    path = "/tmp/my_test_plan.dxf"
    await b.drawing_save(path)
    print(f"Saved to {path}")
    
    # Try preview
    try:
        result = await b.preview()
        print(f"Preview saved to: {result.payload['png_path']}")
    except Exception as e:
        print(f"Preview failed (LibreCAD might not be configured): {e}")

if __name__ == "__main__":
    asyncio.run(main())
