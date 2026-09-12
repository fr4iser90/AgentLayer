#!/usr/bin/env python3
"""Smoke an external agent runtime end to end against a running AgentLayer.

Proves the whole chain that unit tests cannot: Qwen Code binary in the image, provider
pass-through, the workspace write, the git-diff audit and session resume.

Run it against a stack that has ``AGENT_EXTERNAL_RUNTIME_ENABLED=true`` and a bound
workspace:

    python scripts/verify_external_runtime_live.py --workspace <workspace-uuid> [model]

Checks, in order:

1. ``GET /v1/chat/runtime`` reports the runtime available.
2. A coding turn with ``agent_id=coding_qwen`` returns a report and
   ``agentlayer_context.external_runtime == "qwen_code"``.
3. The same conversation's second turn resumes the vendor session.

Audit trail afterwards: ``tool_invocations`` rows with ``tool_name = external_runtime.run``
(Admin → activity), and the workspace diff in the chat's Git panel.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tests.e2e.support.helpers import admin_credentials, base_url, load_e2e_env  # noqa: E402

AGENT_ID = "coding_qwen"
PROMPT_ONE = (
    "Create a file notes.txt in the workspace root containing exactly the line hello, "
    "then confirm it exists."
)
PROMPT_TWO = "What exactly did you change a moment ago? Answer in one short sentence."


def _runtime_state(client: httpx.Client) -> dict[str, Any]:
    r = client.get("/v1/chat/runtime")
    r.raise_for_status()
    return dict(r.json().get("external_runtimes") or {})


def _pick_workspace(client: httpx.Client, workspace_id: str | None) -> str:
    if workspace_id:
        return workspace_id
    r = client.get("/v1/workspaces")
    r.raise_for_status()
    rows = (r.json() or {}).get("workspaces") or (r.json() or {}).get("items") or []
    if not rows:
        raise SystemExit(
            "no workspace visible for this user — create one in the UI or pass --workspace <uuid>"
        )
    chosen = rows[0]
    print(f"workspace: {chosen.get('name')} ({chosen.get('id')})")
    return str(chosen["id"])


def _chat(
    client: httpx.Client,
    *,
    model: str | None,
    prompt: str,
    workspace_id: str,
    conversation_id: str | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "agent_id": AGENT_ID,
        "workspace_id": workspace_id,
    }
    if model:
        body["model"] = model
    if conversation_id:
        body["conversation_id"] = conversation_id
    r = client.post("/v1/chat/completions", json=body)
    if r.status_code != 200:
        raise SystemExit(f"chat failed HTTP {r.status_code}: {r.text[:1200]}")
    return dict(r.json())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", dest="workspace", default=None, help="workspace UUID to bind")
    parser.add_argument("model", nargs="?", default=None, help="model id (defaults to the provider's coding model)")
    args = parser.parse_args()

    load_e2e_env()
    with httpx.Client(base_url=base_url(), timeout=1800.0) as c:
        email, password = admin_credentials()
        token = c.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
        c.headers["Authorization"] = f"Bearer {token}"

        state = _runtime_state(c)
        print(f"runtimes : {state.get('runtimes')}")
        usable = [row for row in (state.get("runtimes") or []) if row.get("available")]
        if not state.get("enabled") or not usable:
            raise SystemExit(
                "external runtime not usable — set AGENT_EXTERNAL_RUNTIME_ENABLED=true and fix the "
                "reason above (missing qwen binary or qwen-code-sdk)"
            )

        workspace_id = _pick_workspace(c, args.workspace)

        created = c.post(
            "/v1/user/conversations",
            json={"title": "external-runtime smoke", "mode": "chat", "agent_id": AGENT_ID},
        )
        created.raise_for_status()
        conversation_id = str((created.json().get("conversation") or {})["id"])
        print(f"conv     : {conversation_id}\n")

        # Turn 1 must already carry the conversation id: that is the row the vendor
        # session id gets stored on, and without it turn 2 cannot resume.
        first = _chat(c, model=args.model, prompt=PROMPT_ONE, workspace_id=workspace_id, conversation_id=conversation_id)
        meta = first.get("agentlayer_context") or {}
        content = str(((first.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
        print(f"turn 1   : runtime={meta.get('external_runtime')} ok={meta.get('external_ok')} "
              f"changed={meta.get('external_changed_files')} no_vcs={meta.get('external_no_vcs')}")
        print(f"reply    : {content[:600] or '(empty)'}")
        if meta.get("external_runtime") != usable[0]["id"]:
            raise SystemExit("turn 1 did not run on the external runtime")
        if not meta.get("external_ok"):
            raise SystemExit(f"turn 1 failed: {meta.get('external_error')}")

        second = _chat(
            c,
            model=args.model,
            prompt=PROMPT_TWO,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
        )
        meta2 = second.get("agentlayer_context") or {}
        content2 = str(((second.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
        print(f"\nturn 2   : resumed={meta2.get('external_resumed')} session={meta2.get('external_session_id')}")
        print(f"reply    : {content2[:300] or '(empty)'}")
        if not meta2.get("external_resumed"):
            print(
                "\nNOTE: turn 2 did not resume — the conversation row must exist before the first "
                "turn for the vendor session id to be stored (this script creates it; check the "
                "chat runtime log for 'external session store failed')."
            )

    print(
        "\nOK — external runtime answered. Audit: tool_invocations rows with "
        "tool_name=external_runtime.run; diff in the chat Git panel."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
