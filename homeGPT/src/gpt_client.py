"""gpt_client.py – openAI chatGPT via Strands + Home‑Assistant MCP."""

import os, json, time, datetime as dt
from dotenv import load_dotenv
from strands import Agent
from strands.models.openai import OpenAIModel
from strands.tools.mcp import MCPClient
from mcp.client.sse import sse_client

load_dotenv()

HOMEASSISTANT_MCP_URL = os.getenv("HOMEASSISTANT_URL")
LOG_PATH = "agent_debug.log"

# OpenAI model
model = OpenAIModel(
    client_args={"api_key": os.getenv("CHATGPT_KEY")},
    model_id="gpt-4.1-mini",
    params={"temperature": 0.7},
)

# Home Assistant MCP SSE
homeassistant_mcp_client = lambda: sse_client(
    url=HOMEASSISTANT_MCP_URL,
    headers={"Authorization": f"Bearer {os.getenv('HOMEASSISTANT_TOKEN')}"}
)

def _debugger_callback(**evt):
    """Log each Strands callback event as JSONL."""
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": dt.datetime.now().isoformat(timespec="seconds"), **evt}) + "\n")

def chat_with_gpt(prompt: str) -> str:
    """Send `prompt` to the LLM, return reply text."""
    t0 = time.perf_counter()
    with MCPClient(homeassistant_mcp_client) as ha_mcp:
        tools = ha_mcp.list_tools_sync()
        agent = Agent(
            model=model,
            tools=tools,
            system_prompt=os.getenv("GPT_PROMPT"),
            # callback_handler=_debugger_callback,
        )
        reply = agent(prompt).message
    print(f"LLM round‑trip: {time.perf_counter() - t0:.2f}s")
    return reply
