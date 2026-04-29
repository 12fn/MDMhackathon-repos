"""Real-data ingestion stub for OMNI-AGENT.

OMNI-AGENT does not ingest a single primary dataset — it federates across
the other 53 sibling apps. To plug in a *real* deployment:

  1. Each sibling app's load_real.py already documents how to ingest its
     own real dataset (DHA Medical Supply Network, NOAA NDFD, GCSS-MC,
     NASA Pred-Mx, IMB pirate-attack feed, etc).

  2. OMNI-AGENT's tools.py functions wrap each sibling's primary entrypoint
     (write_brief / score_spokes / run_pipeline / etc.). Once a sibling's
     real-data path is wired, OMNI-AGENT inherits it for free — no change
     to OMNI-AGENT itself.

  3. To add a NEW sibling app to the catalog:
       a) drop a tool definition into data/tool_registry.json
       b) add a wrapper function in src/tools.py
       c) add the OpenAI tool schema in TOOL_SCHEMAS

  4. To swap the orchestrator's LLM endpoint to Kamiwaza on-prem:
       export KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1
       export KAMIWAZA_API_KEY=...
     The shared client (shared/kamiwaza_client.py) routes everything
     through that endpoint. Zero code change in OMNI-AGENT.

  5. To wire a real Kamiwaza Tool Garden (MCP) catalog as the source of
     OMNI-AGENT's tools, replace data/tool_registry.json's loader with
     a fetch against {KAMIWAZA_BASE_URL}/tools and translate each MCP
     tool spec into an OpenAI function schema. The loop in src/agent.py
     stays identical.
"""
import os


def load_real_tool_registry() -> list[dict]:
    """Pull the live tool catalog from Kamiwaza Tool Garden.

    Not implemented in the demo — see the docstring above for the
    one-day-of-work path to wire it.
    """
    base = os.getenv("KAMIWAZA_BASE_URL")
    if not base:
        raise NotImplementedError(
            "KAMIWAZA_BASE_URL not set. See data/load_real.py docstring "
            "for the recipe to swap the synthetic registry for the live "
            "Kamiwaza Tool Garden."
        )
    raise NotImplementedError(
        "Live Tool-Garden fetch not yet implemented. The pattern is:\n"
        "  resp = httpx.get(f'{base}/tools', headers={'Authorization': f'Bearer {KEY}'})\n"
        "  for mcp_tool in resp.json()['tools']:\n"
        "      yield mcp_to_openai_schema(mcp_tool)\n"
    )
