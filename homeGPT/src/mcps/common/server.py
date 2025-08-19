import functools
import logging
import json
from typing import List, Dict, Any, Optional, Callable, Awaitable, TypeVar, cast

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Type variable for generic functions
T = TypeVar('T')

# Create an MCP server
from mcp.server.fastmcp import FastMCP
from mcp.server.stdio import stdio_server
import mcp.types as types
mcp = FastMCP("common_mcp")

from .functions import (
    get_time, set_timer
)

def async_handler(command_type: str):
    """
    Simple decorator that logs the command
    
    Args:
        command_type: The type of command (for logging)
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            logger.info(f"Executing command: {command_type}")
            return await func(*args, **kwargs)
        return cast(Callable[..., Awaitable[T]], wrapper)
    return decorator

@mcp.tool()
@async_handler("get_time")
async def get_time_tool(timezone_name: Optional[str] = None) -> dict:
    """
    Get the time in the local or specified timezone
    
    Args:
        timezone: Optional timezone name (e.g., "America/New_York"). If None, uses local timezone.

    Returns:
        A dictionary with the current time in the specified timezone.
    
    Examples:
        timezone="America/New_York" - returns current time in New York
        timezone=None - returns current local time

    Best Practices:
        - Default to local time if no location is specified
        - Use IANA timezone identifiers
    """
    if timezone_name is None:
        logger.info("Getting local time")
        return await get_time()
    else:
        logger.info(f"Getting time for timezone: {timezone_name}")
        return await get_time(timezone_name=timezone_name)

@mcp.tool()
@async_handler("set_timer")
async def set_timer_tool(
    seconds: Optional[int] = None,
    minutes: Optional[int] = None, 
    hours: Optional[int] = None,
) -> dict:
    """
    Set a timer for a specified duration. Use this for all time related tasks such as setting a reminder or to set intervals between actions.
    
    Args:
        seconds: Number of seconds (0-59)
        minutes: Number of minutes (0-59)
        hours: Number of hours (0-23) 
    
    Returns:
        Timer result with completion status and timing information
    
    Examples:
        seconds=30 - 30 second timer
        hours=1, minutes=30 - 1 hour 30 minute timer

    Best Practices:
        - Use the time units as specified (e.g., if given minutes=90, use 90 minutes rather than converting to 1 hour 30 minutes)
    """
    logger.info(f"Setting timer: {hours or 0}h {minutes or 0}m {seconds or 0}s")
    
    return await set_timer(
        seconds=seconds,
        minutes=minutes, 
        hours=hours,
    )

