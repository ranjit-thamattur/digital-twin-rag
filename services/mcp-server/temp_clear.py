
import asyncio
import os
import sys

# Add the directory to path so we can import main
sys.path.append('/Users/ranjitt/Ranjit/digital-twin-rag/services/mcp-server')

from main import clear_tenant_knowledge, qdrant

async def run_clear():
    print("🧹 Running direct clear for tenant 'apexenergy'...")
    try:
        result = await clear_tenant_knowledge("apexenergy")
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_clear())
