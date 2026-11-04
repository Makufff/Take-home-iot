"""One HTTP server on the Pi:
  /mcp   MCP server (Streamable HTTP) for the AI chat box
  /api/* REST API for the web dashboard
  /      web dashboard (static files from ../dashboard)
"""
import uvicorn
from starlette.routing import Mount

from app import config
from app.api import create_api
from app.mcp_tools import create_mcp
from app.service import IoTService


def main():
    service = IoTService()
    mcp = create_mcp(service)

    # host=0.0.0.0 so DNS rebinding protection doesn't reject LAN clients
    app = mcp.streamable_http_app(stateless_http=True, host=config.HTTP_HOST)
    app.router.routes.append(Mount("/", app=create_api(service)))

    service.start()
    try:
        uvicorn.run(app, host=config.HTTP_HOST, port=config.HTTP_PORT)
    finally:
        service.stop()


if __name__ == "__main__":
    main()
