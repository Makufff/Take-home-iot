"""Check that the MCP server on the Raspberry Pi is reachable, without Claude.

    python check_connection.py                      # http://raspberrypi.local:8000/mcp
    PI_HOST=192.168.1.50 python check_connection.py
"""
import asyncio
import os
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

URL = f"http://{os.getenv('PI_HOST', 'raspberrypi.local')}:{os.getenv('PI_PORT', '8000')}/mcp"


async def main():
    print(f"Connecting to {URL}")
    async with streamable_http_client(URL) as (read, write, *_):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("Tools:", ", ".join(t.name for t in tools.tools))
            result = await session.call_tool("read_pi_sensors", {})
            print("read_pi_sensors:", result.content[0].text)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Failed: {e!r}", file=sys.stderr)
        sys.exit(1)
