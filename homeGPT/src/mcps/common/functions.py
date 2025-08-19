from typing import Dict, Any, Optional, TypeVar, Callable, Awaitable, cast
import os
import functools
import inspect
import logging
import asyncio
from datetime import datetime, timedelta, timezone
import pytz

# Set up logging
logger = logging.getLogger(__name__)

# Define a generic type for our API function return values
T = TypeVar('T')
F = TypeVar('F', bound=Callable[..., Awaitable[Any]])

def handle_errors(func: F) -> F:
    """
    Decorator to handle common error cases for any function
    
    Args:
        func: The async function to decorate
        
    Returns:
        Wrapped function that handles errors
    """
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Determine return type from function annotation
        return_type = inspect.signature(func).return_annotation
        is_dict_return = 'Dict' in str(return_type)
        is_list_return = 'List' in str(return_type)
        
        # Prepare error formatters based on return type
        def format_error(msg: str) -> Any:
            if is_dict_return:
                return {"error": msg}
            elif is_list_return:
                return [{"error": msg}]
            else:
                return msg
        
        try:
            # Call the original function
            return await func(*args, **kwargs)
        except ValueError as e:
            logger.error(f"Invalid input in {func.__name__}: {str(e)}")
            return format_error(f"Invalid input: {str(e)}")
        except ImportError as e:
            logger.error(f"Missing dependency in {func.__name__}: {str(e)}")
            return format_error(f"Missing dependency: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}")
            return format_error(f"Unexpected error: {str(e)}")
    
    return cast(F, wrapper)


@handle_errors
async def get_time(
    timezone_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get the current time for the device's local timezone or a specified timezone
    
    Args:
        timezone_name: Optional timezone name (e.g., 'US/Eastern', 'Europe/London', 'UTC').
                      If None, returns the device's local time.
    
    Returns:
        Dictionary with current time information
    """
    if timezone_name is None:
        timezone_name = os.getenv("TIMEZONE", "America/Chicago")
    
    tz = pytz.timezone(timezone_name)
    now = datetime.now(tz)
    tz_info = timezone_name
    
    return {
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": tz_info,
        "iso_format": now.isoformat(),
        "unix_timestamp": int(now.timestamp())
    }


@handle_errors
async def set_timer(
    seconds: Optional[int] = None,
    minutes: Optional[int] = None,
    hours: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Set a timer for a specified duration
    
    Args:
        seconds: Number of seconds (0-59)
        minutes: Number of minutes (0-59) 
        hours: Number of hours (0-23)
    
    Returns:
        Dictionary with timer information and result
    """
    # Validate inputs
    if all(param is None for param in [seconds, minutes, hours]):
        raise ValueError("At least one time parameter (seconds, minutes, hours) must be provided")
    
    # Set defaults and validate ranges
    seconds = seconds or 0
    minutes = minutes or 0
    hours = hours or 0
    
    # Calculate total duration
    total_seconds = hours * 3600 + minutes * 60 + seconds
    
    if total_seconds <= 0:
        raise ValueError("Timer duration must be greater than 0")
    
    # Get start time
    start_time = datetime.now()
    end_time = start_time + timedelta(seconds=total_seconds)
    
    # Format duration for display
    duration_parts = []
    if hours > 0:
        duration_parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        duration_parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if seconds > 0:
        duration_parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
    
    duration_str = ", ".join(duration_parts)
    
    # Start the timer
    logger.info(f"Timer started for {duration_str}")
    
    # Wait for the specified duration
    await asyncio.sleep(total_seconds)
    
    # Timer completed
    completion_time = datetime.now()
    
    result = {
        "duration": duration_str,
        "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
        "actual_completion": completion_time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    logger.info(f"Timer completed: {duration_str}")
    return result
