from homeassistant_api import Client
import logging as log
from dotenv import load_dotenv
import os
load_dotenv()

HOMEASSISTANT_URL = os.getenv("HOMEASSISTANT_URL")
HOMEASSISTANT_TOKEN = os.getenv("HOMEASSISTANT_TOKEN")

client = Client(HOMEASSISTANT_URL, HOMEASSISTANT_TOKEN, cache_session=False)

def callService(service, **extra):
    domain, _ = service.split(".", 1)
    entity, action = service.rsplit(".", 1)
    kw = {"entity_id": entity, **extra}

    print("Calling Home Assistant service: %s", service)
    try:
        client.trigger_service(domain, action, **kw)
            # threading.Thread(
            #     target=client.trigger_service,
            #     args=(domain, action),
            #     kwargs=kw,
            #     daemon=True
            # ).start()
        return True
    except Exception:
        log.exception("Unexpected HA error calling %s", service)

    return False 

def getEntityState(entity):
    try:
        return client.get_state(entity_id=entity)
    except Exception:
        log.exception("Unexpected HA error getting state for %s", entity)
        return None
