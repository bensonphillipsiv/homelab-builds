import os

# Home Assistant configuration
HOMEASSISTANT_URL: str = os.environ.get("HOMEASSISTANT_URL")
HOMEASSISTANT_TOKEN: str = os.environ.get("HOMEASSISTANT_TOKEN", "")

def get_ha_headers() -> dict:
    """Return the headers needed for Home Assistant API requests"""
    headers = {
        "Content-Type": "application/json",
    }
    
    # Only add Authorization header if token is provided
    if HOMEASSISTANT_TOKEN:
        headers["Authorization"] = f"Bearer {HOMEASSISTANT_TOKEN}"
    
    return headers
