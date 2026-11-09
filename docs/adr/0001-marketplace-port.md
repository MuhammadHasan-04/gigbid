# ADR 0001: One marketplace port behind the Marketplace MCP server
**Status:** accepted. **Context:** R1 needs GigSim and live Upwork to be switchable by config, and agents must only see MCP tools.
**Decision:** the port (`agent/marketplace_port.py`) lives *inside* our Marketplace MCP server. Adapters are GigSim (HTTP) and Upwork (official MCP over Streamable HTTP + OAuth). Agents call our server's tools only.
**Consequences:** the graph cannot tell which marketplace it uses, and approval tokens and idempotency apply in both modes. The cost is one extra hop in live mode, and Upwork tool names must be mapped (config-overridable).
