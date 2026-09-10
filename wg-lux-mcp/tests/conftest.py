from __future__ import annotations

import os

# In-process tests exercise tool behavior without an HTTP authorization flow.
os.environ["WG_LUX_MCP_OAUTH_ENABLED"] = "false"
