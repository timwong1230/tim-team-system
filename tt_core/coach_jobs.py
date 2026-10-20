"""Background AI Tim jobs — keep answering after the user leaves the page.

Streamlit only keeps the UI thread; we run ``coach_tim.reply`` in a worker
and park results in a process-level store. Every script run (any menu) calls
``sync_job_into_session`` so the answer lands in ``coach_tim_messages``.

Jobs have a **hard timeout** so a hung Gemini/Sheets call cannot lock chat
forever (the screenshot bug: input disabled while status stuck on running).
"""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from copy import deepcopy
from typing import Any

_LOCK = threading.Lock()
# username -> job dict
_JOBS: dict[str, dict[str, Any]] = {}

# Whole turn (tools + LLM) must finish within this window
JOB_TIMEOUT_SEC = 45
# UI treats anything older as stuck even if the thread is still spinning
STALE_RUNNING_SEC = 55


def _new_job_id() -> str:
    return uuid.uuid4().hex[:12]


def _offline_fallback(question: str, ctx: dict[str, Any], *, reason: str) -> str:
    try:
        from tt_core.coach_tim import offline_reply

        body = offline_reply(question, ctx)
    except Exception:
        body = "暫時答唔到，請稍後再問一次，或者問今日優先／本週活動／個案名。"
    tip = reason.strip() or "AI 回應逾時"
    return f"（{tip}）\n\n{body}"


def _finalize_stuck(job: dict[str, Any], *, reason: str) -> None:
    """Mark a running job done with offline text (caller holds _LOCK)."""
    if job.get("status") != "running":
        return
    q = str(job.get("question") or "")
    ctx = job.get("_ctx") or {"username": job.get("username"), "role": job.get("role")}
    job["status"] = "done"
    job["answer"] = _offline_fallback(q, ctx, reason=reason)
    job["mode"] = "offline"
    job["meta"] = {"ai_error": reason, "tools_used": []}
    job["error"] = reason
    job["finished_at"] = time.time()
    job["synced"] = False


def _sweep_stale_locked(now: float | None = None) -> None:
    """Expire hung running jobs so chat unlocks (must hold _LOCK)."""
    now = time.time() if now is None else now
    for job in _JOBS.values():
        if job.get("status") != "running":
            continue
        started = float(job.get("started_at") or 0)
        if started and (now - started) >= STALE_RUNNING_SEC:
            _finalize_stuck(job, reason="AI 回應逾時，已改用即時教練資料")


def get_job(username: str) -> dict[str, Any] | None:
    u = str(username or "").strip()
    if not u:
        return None
    with _LOCK:
        _sweep_stale_locked()
        job = _JOBS.get(u)
        if not job:
            return None
        out = deepcopy(job)
        out.pop("_ctx", None)
        return out


def is_running(username: str) -> bool:
    job = get_job(username)
    return bool(job and job.get("status") == "running")


def cancel_job(username: str, *, reason: str = "已取消等待") -> bool:
    """User-cancel a stuck/running job; unlocks chat on next sync."""
    u = str(username or "").strip()
    if not u:
        return False
    with _LOCK:
        job = _JOBS.get(u)
        if not job:
            return False
        if job.get("status") == "running":
            _finalize_stuck(job, reason=reason)
            return True
        if not job.get("synced"):
            # Allow re-sync after cancel of a done-but-unsynced job
            return False
        _JOBS.pop(u, None)
        return True


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
    a second one (callers should tell the user to wait or cancel).
    """
    u = str(username or "").strip()
    if not u:
        raise ValueError("missing username")

    with _LOCK:
        _sweep_stale_locked()
        existing = _JOBS.get(u)
        if existing and existing.get("status") == "running":
            out = deepcopy(existing)
            out.pop("_ctx", None)
            return out

        job_id = _new_job_id()
        ctx_copy = deepcopy(ctx or {})
        ctx_copy["username"] = u
        ctx_copy["role"] = str(role or "Member")
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
            "_ctx": ctx_copy,
        }
        _JOBS[u] = job

    hist = [
        {"role": str(m.get("role") or ""), "content": str(m.get("content") or "")}
        for m in (history or [])
        if m.get("role") in ("user", "assistant")
    ]
    question = str(user_text or "")

    def _worker() -> None:
        answer = ""
        mode = "offline"
        meta: dict[str, Any] = {}
        err = ""
        try:
            from tt_core import coach_tim as ct

            # Hard ceiling — never leave UI locked on a hung HTTP/Sheets call
            with ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(ct.reply, question, hist, ctx_copy)
                try:
                    result = fut.result(timeout=JOB_TIMEOUT_SEC)
                except FuturesTimeout:
                    err = f"超過 {JOB_TIMEOUT_SEC} 秒未完成"
                    answer = _offline_fallback(
                        question, ctx_copy, reason="AI 回應逾時，已改用即時教練資料"
                    )
                    result = None
            if result is not None:
                if isinstance(result, tuple) and len(result) >= 2:
                    answer = str(result[0] or "")
                    mode = str(result[1] or "offline")
                    meta = dict(result[2] or {}) if len(result) > 2 else {}
                else:
                    answer = str(result or "")
        except Exception as e:
            err = str(e)[:400]
            answer = _offline_fallback(
                question, ctx_copy, reason="AI 暫時連線唔到，已改用即時教練資料"
            )
            mode = "offline"
            meta = {"ai_error": err}

        with _LOCK:
            cur = _JOBS.get(u)
            if not cur or cur.get("id") != job_id:
                return
            # If UI already expired/cancelled this job, don't overwrite
            if cur.get("status") != "running":
                return
            cur["status"] = "done"
            cur["answer"] = answer
            cur["mode"] = mode
            cur["meta"] = meta
            cur["error"] = err
            cur["finished_at"] = time.time()
            cur["synced"] = False

    threading.Thread(target=_worker, name=f"aitim-{u}-{job_id}", daemon=True).start()
    with _LOCK:
        out = deepcopy(_JOBS[u])
        out.pop("_ctx", None)
        return out


def sync_job_into_session(username: str) -> bool:
    """If a finished job is waiting, append the answer into session messages.

    Returns True when a new assistant message was applied (caller may toast/rerun).
    """
    import streamlit as st

    u = str(username or "").strip()
    if not u:
        return False

    with _LOCK:
        _sweep_stale_locked()
        job = _JOBS.get(u)
        if not job or job.get("synced"):
            return False
        if job.get("status") not in ("done", "error"):
            return False
        snapshot = deepcopy(job)
        snapshot.pop("_ctx", None)
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
