from homeassistant_api import Client
import logging as log
from dotenv import load_dotenv
import os
import threading
import queue

load_dotenv()

HOMEASSISTANT_URL = os.getenv("HOMEASSISTANT_URL")
HOMEASSISTANT_TOKEN = os.getenv("HOMEASSISTANT_TOKEN")

client = Client(HOMEASSISTANT_URL, HOMEASSISTANT_TOKEN, cache_session=False)

_queue = queue.Queue()
_worker = None

def _run_worker():
    while True:
        task = _queue.get()
        if task is None:
            break
        service, extra = task
        domain, _ = service.split(".", 1)
        entity, action = service.rsplit(".", 1)
        kw = {"entity_id": entity, **extra}
        try:
            client.trigger_service(domain, action, **kw)
        except Exception:
            log.exception("HA error calling %s", service)
        _queue.task_done()

def start():
    global _worker
    if _worker is None:
        _worker = threading.Thread(target=_run_worker, daemon=True)
        _worker.start()

def callService(service, **extra):
    """Non-blocking: queues the call and returns immediately."""
    _queue.put((service, extra))

def getEntityState(entity):
    """Blocking: must wait for result."""
    try:
        return client.get_state(entity_id=entity)
    except Exception:
        log.exception("HA error getting state for %s", entity)
        return None