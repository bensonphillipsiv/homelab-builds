import queue

from asr import asr_init, asr_process
from agent import gpt_init, mcp_init, agent_request


def orchestrator_thread(q_utterance: queue.Queue, q_tts: queue.Queue):
    """
    Orchestrates the flow of data:
        - receives utterances from the listener
        - processes them with ASR
        - sends text to the LLM
        - queues the response for TTS
    """

    asr = asr_init()
    model = gpt_init()
    mcp = mcp_init()

    print("[Orchestrator started]")
    while True:
        request_audio = q_utterance.get()
        if not request_audio:
            continue
        
        request_text = asr_process(asr, request_audio)
        print(f"🗣️  {request_text}")

        reply = agent_request(request_text, mcp, model)
        print(f"\n🤖  {reply}")

        # q_tts.put(reply)
