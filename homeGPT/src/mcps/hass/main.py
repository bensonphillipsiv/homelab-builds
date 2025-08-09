#!/usr/bin/env python
"""Entry point for running Hass-MCP as a module"""

from .server import mcp
import os


def main():
    """Run the MCP server with stdio communication"""
    print(os.environ.get("HOMEASSISTANT_URL"))
    mcp.run()


# if __name__ == "__main__":
#     main()

main()