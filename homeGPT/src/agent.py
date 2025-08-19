import os
from contextlib import ExitStack
from dotenv import load_dotenv
from strands import Agent
from strands.models.openai import OpenAIModel
from strands.tools.mcp import MCPClient
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client


load_dotenv()
HOMEASSISTANT_URL = os.getenv("HOMEASSISTANT_URL")
HOMEASSISTANT_TOKEN = os.getenv("HOMEASSISTANT_TOKEN")
CHATGPT_KEY = os.getenv("CHATGPT_KEY")
GPT_PROMPT = os.getenv("GPT_PROMPT", "You are a helpful assistant.")

gpt_prompt = """You are a Home Assistant operator for my house. 
Keep replies brief and action-focused (optimize for TTS). 
When I ask for something, do this policy:

1) Resolve intent:
   - Action (on/off/toggle/set/scene) + Targets (entities/areas) + Options (brightness, temp, %).
   - If the entity_id is unknown, search by friendly name/area; prefer best-effort resolution.
   - Avoid asking for clarification unless there is true ambiguinty in what the request is. 
   - Ask 1 short clarification if the action is risky (unlock/door/drain).

2) Grounding:
   - Never invent entity_ids. Use tools to find them:
     • `list_entities`
     • `get_entity` for exact state/attributes
     • When searching for devices only use one key word (e.g., “light” or "office").
   - Use your best judgment to resolve ambiguities (e.g., multiple “closet light”, "upstairs living room" is the "living room").

3) No-ops & batching:
   - If the device is already in the desired state, say so and don’t call a service.
   - If a request clearly affects multiple devices (“turn off office lights”), batch them.

4) Act & verify:
   - Use `entity_action` (on/off/toggle) or `call_service_tool` for custom services.

5) Safety & confirmations:
   - For doors/locks/garage/openers/alarms/critical HVAC changes: require explicit confirmation.
   - Do not execute destructive actions without confirmation.

6) Errors:
   - If Home Assistant is unreachable or returns an error, run a quick health check if available (e.g., `ha_ping`) and report a short actionable message.

Style:
- Be concise. Do not explain reasoning for how your arrived to an answer unless requested. Examples: 
  “Turned on office closet light… (100%).”
  “Already off.”
  “Multiple ‘closet light’ found: office, hallway. Which?”
  "12 inches by 12 inches by 12 inches equals 7.48 gallons."
"""


def gpt_init():
    """
    Initialize the GPT client.
    """
    model = OpenAIModel(
        client_args={"api_key": CHATGPT_KEY},
        model_id="gpt-4.1",
        params={"temperature": 0.7},
    )

    return model


def mcp_init():
    """Return a list of MCPClient *context managers* (factories inside)."""
    # hass_mcp = MCPClient(lambda: sse_client(
    #     url=HOMEASSISTANT_URL,
    #     headers={"Authorization": f"Bearer {HOMEASSISTANT_TOKEN}"}
    # ))

    # Home Assistant MCP via stdio
    hass_mcp = MCPClient(lambda: stdio_client(
        StdioServerParameters(
            command="uv",
            args=["run", "-m", "mcps.hass.main"],
            env=os.environ 
        )
    ))

    common_mcp = MCPClient(lambda: stdio_client(
        StdioServerParameters(
            command="uv",
            args=["run", "-m", "mcps.common.main"],
            env=os.environ 
        )
    ))

    return [hass_mcp, common_mcp]


def agent_request(request_text, mcp, model):
    with ExitStack() as stack:
        # Open all MCP contexts
        opened = [stack.enter_context(cm) for cm in mcp]

        # Merge tools from each open server
        tools = []
        for c in opened:
            ts = c.list_tools_sync()
            tools += ts
            if not ts:
                print("[MCP] no tools exposed by one server")
            else:
                print(f"[MCP] loaded {len(ts)} tools from a server")

        agent = Agent(model=model, tools=tools, system_prompt=gpt_prompt)
        result = agent(request_text).message

        return result["content"][0]["text"]
