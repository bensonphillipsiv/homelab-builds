import queue
import asyncio
import threading
from listener import listener_thread
from orchestrator import orchestrator_thread
from speaker import speaker_thread

def main():
    # Create queues for communication between threads
    q_utterance=queue.Queue(maxsize=3)
    q_tts=queue.Queue(maxsize=3)
    
    # Start worker threads
    t_listener = threading.Thread(target=listener_thread, args=(q_utterance,), daemon=True)
    t_speaker = threading.Thread(target=speaker_thread, args=(q_tts,), daemon=True)

    t_listener.start()
    t_speaker.start()

    # Start orchestrator
    asyncio.run(orchestrator_thread(q_utterance, q_tts))
    # orchestrator_thread(q_utterance, q_tts)


if __name__ == "__main__":
    main()
