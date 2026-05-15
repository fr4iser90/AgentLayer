# Domain tools

Shipped layout (one tool module per file, each exports `TOOLS` + `HANDLERS`):

```text
domains/
  fishing/
    bite_index.py
    spot_recommendation.py
    bait_selector.py
  hunting/
    wind_analysis.py
    tracking.py
  survival/
    water_calc.py
    shelter_guide.py
    risk_assessment.py
```

Set **`TOOL_DOMAIN`** (category id for routing; lowercased in the registry) and **`TOOL_TRIGGERS`**. Optional **`TOOL_TAGS`** land in `tools_meta` for operators / filters.

**`TOOL_REQUIRES`** lists **context / argument hints** for routing and documentation (what the tool expects in the user message or tool arguments). It is **not** the same as user-stored API keys. Those are declared with **`TOOL_SECRETS_REQUIRED`** (per-user `service_key` names in encrypted secrets) — see **`gmail.py`** / **`github.py`**.

HTTP: **`X-Agent-Tool-Domain`** or JSON body **`TOOL_DOMAIN`** (stripped before Ollama) narrows `tools[]` after category routing.
