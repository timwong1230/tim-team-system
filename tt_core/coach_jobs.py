"""Background AI Tim jobs — keep answering after the user leaves the page.

Streamlit only keeps the UI thread; we run ``coach_tim.reply`` in a daemon
thread and park results in a process-level store. Every script run (any menu)
calls ``sync_job_into_session`` so the answer lands in ``coach_tim_messages``.
"""

from __future__ import annotations

import threading
import time
import uuid
from copy import deepcopy
from typing import Any

_LOCK = threading.Lock()
# username -> job dict
_JOBS: dict[str, dict[str, Any]] = {}


def _new_job_id() -> str:
    return uuid.uuid4().hex[:12]


def get_job(username: str) -> dict[str, Any] | None:
    u = str(username or "").strip()
    if not u:
        return None
    with _LOCK:
        job = _JOBS.get(u)
        return deepcopy(job) if job else None


def is_running(username: str) -> bool:
    job = get_job(username)
    return bool(job and job.get("status") == "running")


def start_reply_job(
    *,
    username: str,
    role: str,
    user_text: str,
    history: list[dict[str, str]],
    ctx: dict[str, Any],
) -> dict[str, Any]:
    """Start a background reply. Returns the job snapshot.

    If a job is already running for this user, returns that job without starting
    a second one (callers should tell the user to wait).
    """
    u = str(username or "").strip()
    if not u:
        raise ValueError("missing username")

    with _LOCK:
        existing = _JOBS.get(u)
        if existing and existing.get("status") == "running":
            return deepcopy(existing)

        job_id = _new_job_id()
        job: dict[str, Any] = {
            "id": job_id,
            "username": u,
            "role": str(role or "Member"),
            "question": str(user_text or ""),
            "status": "running",
            "answer": "",
            "mode": "",
            "meta": {},
            "error": "",
            "started_at": time.time(),
            "finished_at": None,
            "synced": False,
        }
        _JOBS[u] = job

    hist = [
        {"role": str(m.get("role") or ""), "content": str(m.get("content") or "")}
        for m in (history or [])
        if m.get("role") in ("user", "assistant")
    ]
    ctx_copy = deepcopy(ctx or {})
    ctx_copy["username"] = u
    ctx_copy["role"] = str(role or "Member")
    question = str(user_text or "")

    def _worker() -> None:
        answer = ""
        mode = "offline"
        meta: dict[str, Any] = {}
        err = ""
        try:
            from tt_core import coach_tim as ct

            result = ct.reply(question, hist, ctx_copy)
            if isinstance(result, tuple) and len(result) >= 2:
                answer = str(result[0] or "")
                mode = str(result[1] or "offline")
                meta = dict(result[2] or {}) if len(result) > 2 else {}
            else:
                answer = str(result or "")
        except Exception as e:
            err = str(e)[:400]
            try:
                from tt_core.coach_tim import offline_reply

                answer = f"（AI 背景回覆失敗）\n\n{offline_reply(question, ctx_copy)}"
            except Exception:
                answer = f"（AI 暫時連線唔到）\n\n{err}"
            mode = "offline"
            meta = {"ai_error": err}

        with _LOCK:
            cur = _JOBS.get(u)
            if not cur or cur.get("id") != job_id:
                return
            cur["status"] = "done" if not err else "done"
            cur["answer"] = answer
            cur["mode"] = mode
            cur["meta"] = meta
            cur["error"] = err
            cur["finished_at"] = time.time()

    threading.Thread(target=_worker, name=f"aitim-{u}-{job_id}", daemon=True).start()
    return deepcopy(job)


def sync_job_into_session(username: str) -> bool:
    """If a finished job is waiting, append the answer into session messages.

    Returns True when a new assistant message was applied (caller may toast/rerun).
    """
    import streamlit as st

    u = str(username or "").strip()
    if not u:
        return False

    with _LOCK:
        job = _JOBS.get(u)
        if not job or job.get("synced"):
            return False
        if job.get("status") not in ("done", "error"):
            return False
        snapshot = deepcopy(job)
        job["synced"] = True

    msgs = st.session_state.setdefault("coach_tim_messages", [])
    answer = str(snapshot.get("answer") or "").strip()
    if not answer:
        answer = "（冇收到回覆，請再問一次。）"

    meta = snapshot.get("meta") or {}
    tools_used = meta.get("tools_used") or []
    if tools_used and snapshot.get("mode") == "offline":
        try:
            from tt_core.coach_tim import TOOL_CATALOG

            labels = [TOOL_CATALOG.get(t, t) for t in tools_used]
            answer = answer + "\n\n—\n_已查：" + "、".join(labels) + "_"
        except Exception:
            pass

    if meta.get("pending"):
        st.session_state["coach_tim_write_pending"] = meta["pending"]
    if meta.get("ai_error"):
        st.session_state["_coach_tim_last_error"] = str(meta["ai_error"])[:400]
    else:
        st.session_state.pop("_coach_tim_last_error", None)

    # Avoid duplicating if the same answer was already appended
    if not (
        msgs
        and msgs[-1].get("role") == "assistant"
        and msgs[-1].get("content") == answer
        and msgs[-1].get("_job_id") == snapshot.get("id")
    ):
        msgs.append(
            {
                "role": "assistant",
                "content": answer,
                "_job_id": snapshot.get("id"),
                "_mode": snapshot.get("mode"),
            }
        )

    st.session_state.pop("coach_tim_job_running", None)
    st.session_state["coach_tim_job_ready"] = True
    return True


def clear_job(username: str) -> None:
    u = str(username or "").strip()
    if not u:
        return
    with _LOCK:
        _JOBS.pop(u, None)
