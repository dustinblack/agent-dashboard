"""Socket.IO event handlers for the Agent Dashboard.

Manages real-time communication between the frontend UI, the
backend hub, and remote host daemons over the /terminal namespace.

All database operations are offloaded to a thread pool via
asyncio.to_thread() so they never block the async event loop.
This is critical because the event loop also relays terminal
I/O — a blocked loop adds latency to every keystroke.
"""

import asyncio
import json
import os
from base64 import b64decode
from datetime import datetime, timezone
from http.cookies import SimpleCookie

import socketio
from itsdangerous import TimestampSigner, BadSignature

from . import database, models

# Initialize the AsyncServer with ASGI support and CORS
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")


def _validate_session_cookie(environ):
    """Validate the Starlette session cookie from the ASGI scope.

    Parses the Cookie header, extracts the 'session' cookie,
    and verifies its signature using the same SECRET_KEY that
    SessionMiddleware uses. Returns the decoded session dict
    on success, or None on failure.
    """
    secret_key = os.getenv("SECRET_KEY", "")
    if not secret_key:
        return None

    headers = dict(environ.get("asgi.scope", {}).get("headers", []))
    cookie_header = None
    for k, v in headers.items():
        if k == b"cookie":
            cookie_header = v.decode("utf-8")
            break
    if not cookie_header:
        return None

    cookies = SimpleCookie()
    cookies.load(cookie_header)
    session_morsel = cookies.get("session")
    if not session_morsel:
        return None

    signer = TimestampSigner(secret_key)
    try:
        data = signer.unsign(session_morsel.value.encode("utf-8"))
        return json.loads(b64decode(data))
    except (BadSignature, Exception):
        return None


# ── Synchronous DB helpers (run via asyncio.to_thread) ────


def _db_authenticate_host(host_token):
    """Look up host by token. Returns (host_id, host_name) or None."""
    db = database.SessionLocal()
    try:
        host = (
            db.query(models.Host).filter(models.Host.host_token == host_token).first()
        )
        if not host:
            return None
        host.status = "online"
        db.commit()
        return (host.id, host.name)
    finally:
        db.close()


def _db_mark_host_offline(host_id):
    """Mark a host as offline."""
    db = database.SessionLocal()
    try:
        host = db.query(models.Host).filter(models.Host.id == host_id).first()
        if host:
            host.status = "offline"
            db.commit()
            return host.name
        return None
    finally:
        db.close()


def _db_upsert_agent_telemetry(agent_id, telemetry, host_id=None):
    """Update agent telemetry, creating the record if needed.

    Returns the merged telemetry dict, or None if the agent
    could not be created (no host_id).
    """
    db = database.SessionLocal()
    try:
        db_agent = (
            db.query(models.Agent).filter(models.Agent.agent_id == agent_id).first()
        )
        if not db_agent:
            if not host_id:
                return None
            db_agent = models.Agent(
                host_id=host_id,
                agent_id=agent_id,
                tool_name=telemetry.get("tool_name"),
                status="active",
                telemetry_json=telemetry,
            )
            db.add(db_agent)
            db.commit()
            db.refresh(db_agent)
            print(f"Auto-created agent {agent_id}" f" for host {host_id}")

        current_tel = db_agent.telemetry_json or {}
        new_tel = dict(current_tel)
        new_tel.update(telemetry)
        db_agent.telemetry_json = new_tel
        db.commit()
        return new_tel
    finally:
        db.close()


def _db_update_host_telemetry(host_id, data):
    """Update host's cached project/tool list."""
    db = database.SessionLocal()
    try:
        host = db.query(models.Host).filter(models.Host.id == host_id).first()
        if host:
            host.last_projects_json = data
            db.commit()
    finally:
        db.close()


def _db_close_agent(agent_id):
    """Mark an agent as closed."""
    db = database.SessionLocal()
    try:
        db_agent = (
            db.query(models.Agent).filter(models.Agent.agent_id == agent_id).first()
        )
        if db_agent:
            db_agent.status = "closed"
            db_agent.ended_at = datetime.now(timezone.utc)
            db.commit()
            return True
        return False
    finally:
        db.close()


# ── Socket.IO event handlers ─────────────────────────────


@sio.on("connect", namespace="/terminal")
async def connect(sid, environ, auth):
    """
    Handles new Socket.IO connections on the /terminal namespace.
    Identifies if the connection is from a Host Daemon or a UI Client.

    Host daemons authenticate via X-Host-Token header or auth.token.
    UI clients are validated against the OIDC session cookie when
    authentication is enabled (BYPASS_AUTH is not set).
    """
    headers = dict(environ.get("asgi.scope", {}).get("headers", []))
    headers_str = {
        k.decode("utf-8").lower(): v.decode("utf-8") for k, v in headers.items()
    }

    host_token = headers_str.get("x-host-token") or (auth and auth.get("token"))

    if not host_token:
        # UI client — enforce auth unless bypassed
        bypass = os.getenv("BYPASS_AUTH", "false").lower() == "true"
        if not bypass:
            session = _validate_session_cookie(environ)
            if not session or "user" not in session:
                return False
        return True

    result = await asyncio.to_thread(_db_authenticate_host, host_token)
    if not result:
        return False

    host_id, host_name = result

    async with sio.session(sid, namespace="/terminal") as session:
        session["host_id"] = host_id
        session["is_host"] = True

    room_name = f"host_{host_id}"
    await sio.enter_room(sid, room_name, namespace="/terminal")
    print(
        f"Host Daemon connected: {host_name}" f" (SID: {sid}) joined room: {room_name}"
    )


@sio.on("disconnect", namespace="/terminal")
async def disconnect(sid):
    """
    Handles disconnection. If it was a host, mark it as offline.
    """
    async with sio.session(sid, namespace="/terminal") as session:
        if session.get("is_host"):
            host_id = session.get("host_id")
            host_name = await asyncio.to_thread(_db_mark_host_offline, host_id)
            if host_name:
                print(
                    f"Host Daemon {host_name}"
                    f" (ID: {host_id}) disconnected"
                    f" and marked offline."
                )


@sio.on("terminal_output", namespace="/terminal")
async def handle_terminal_output(sid, data):
    """
    Receives stdout/stderr from an agent (via the host daemon) and broadcasts it.
    data: {'sid': 'agent_id', 'output': '...'}
    """
    agent_id = data.get("sid")
    output = data.get("output", "")

    if agent_id and output:
        # skip_sid prevents echoing the output back to
        # the daemon that sent it. Without this, every
        # output frame is broadcast to the room (which
        # includes the daemon), deserialized, dispatched
        # through the catch-all handler, and discarded.
        # At ~7fps spinner output, this wastes ~2.5KB/s
        # of unnecessary WebSocket traffic per agent.
        await sio.emit(
            "terminal_output",
            {"sid": agent_id, "output": output},
            room=agent_id,
            namespace="/terminal",
            skip_sid=sid,
        )


@sio.on("join_room", namespace="/terminal")
async def handle_join_room(sid, data):
    """
    Adds a client to an agent's room. Used by both UI
    clients (to receive output) and host daemons (to
    receive room-targeted input and resize events).
    """
    agent_id = data.get("room")
    if agent_id:
        await sio.enter_room(sid, agent_id, namespace="/terminal")
        session = await sio.get_session(sid, namespace="/terminal")
        is_host = session.get("is_host", False) if session else False
        client_type = "Host Daemon" if is_host else "UI Client"
        print(f"{client_type} {sid} joined Agent room: {agent_id}")

        if not is_host:
            await sio.emit(
                "request_history",
                {"agent_id": agent_id},
                namespace="/terminal",
            )


@sio.on("request_projects", namespace="/terminal")
async def handle_request_projects(sid, data):
    """
    Relays a UI request for available projects to all host daemons.
    """
    print(f"UI Client {sid} requested project lists.")
    await sio.emit("request_projects", {}, namespace="/terminal")


@sio.on("history_complete", namespace="/terminal")
async def handle_history_complete(sid, data):
    """
    Relays the history completion signal to the UI.
    """
    agent_id = data.get("agent_id")
    if agent_id:
        await sio.emit(
            "history_complete",
            data,
            room=agent_id,
            namespace="/terminal",
        )


@sio.on("terminal_resize", namespace="/terminal")
async def handle_terminal_resize(sid, data):
    """
    Relays a terminal resize event to the agent's room.
    data: {'sid': 'agent_id', 'cols': 80, 'rows': 24}
    """
    agent_id = data.get("sid")
    if agent_id:
        await sio.emit(
            "terminal_resize",
            data,
            room=agent_id,
            namespace="/terminal",
            skip_sid=sid,
        )


@sio.on("agent_telemetry", namespace="/terminal")
async def handle_agent_telemetry(sid, data):
    """
    Receives live telemetry updates from host daemons and
    broadcasts them to UI clients. Persists the latest
    telemetry state in the database via a thread pool.
    data: {'agent_id': '...', 'telemetry': {...}}
    """
    agent_id = data.get("agent_id")
    telemetry = data.get("telemetry")
    if not agent_id or not telemetry:
        return

    session = await sio.get_session(sid, namespace="/terminal")
    host_id = session.get("host_id") if session else None

    new_tel = await asyncio.to_thread(
        _db_upsert_agent_telemetry, agent_id, telemetry, host_id
    )

    if new_tel is not None:
        await sio.emit(
            "agent_telemetry_update",
            {"agent_id": agent_id, "telemetry": new_tel},
            namespace="/terminal",
        )
    else:
        print(f"Cannot create agent {agent_id}" f" — no host_id in session")


@sio.on("host_telemetry", namespace="/terminal")
async def handle_host_telemetry(sid, data):
    """
    Receives host-wide configuration (like project list) and broadcasts it.
    data: {'projects_root': '...', 'available_projects': [...]}
    """
    async with sio.session(sid, namespace="/terminal") as session:
        host_id = session.get("host_id")
        n_projects = len(data.get("available_projects", []))
        n_tools = len(data.get("available_tools", []))
        print(
            f"Received host_telemetry from"
            f" Host ID: {host_id}"
            f" ({n_projects} projects,"
            f" {n_tools} tools)"
        )
        if host_id:
            await asyncio.to_thread(_db_update_host_telemetry, host_id, data)
            await sio.emit(
                "host_telemetry_update",
                {"host_id": host_id, "telemetry": data},
                namespace="/terminal",
            )


@sio.on("agent_exit", namespace="/terminal")
async def handle_agent_exit(sid, data):
    """
    Called by the Host Daemon when an agent process terminates.
    data: {'agent_id': '...'}
    """
    agent_id = data.get("agent_id")
    if agent_id:
        closed = await asyncio.to_thread(_db_close_agent, agent_id)
        if closed:
            print(f"Agent {agent_id} exited" f" and marked as closed in DB.")
            await sio.emit(
                "agent_status_update",
                {"agent_id": agent_id, "status": "closed"},
                namespace="/terminal",
            )


@sio.on("terminal_input", namespace="/terminal")
async def handle_terminal_input(sid, data):
    """
    Relays keystrokes to the agent's room where only
    the owning daemon receives them.
    data: {'target_sid': 'agent_id', 'input': '...'}
    """
    agent_id = data.get("target_sid")
    if agent_id:
        await sio.emit(
            "terminal_input",
            data,
            room=agent_id,
            namespace="/terminal",
            skip_sid=sid,
        )
