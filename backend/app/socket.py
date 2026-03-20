"""Socket.IO event handlers for the Agent Dashboard.

Manages real-time communication between the frontend UI, the
backend hub, and remote host daemons over the /terminal namespace.
"""

import socketio

from . import database, models

# Initialize the AsyncServer with ASGI support and CORS
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")


@sio.on("connect", namespace="/terminal")
async def connect(sid, environ, auth):
    """
    Handles new Socket.IO connections on the /terminal namespace.
    Identifies if the connection is from a Host Daemon or a UI Client.
    """
    headers = dict(environ.get("asgi.scope", {}).get("headers", []))
    headers_str = {
        k.decode("utf-8").lower(): v.decode("utf-8") for k, v in headers.items()
    }

    host_token = headers_str.get("x-host-token") or (auth and auth.get("token"))

    if not host_token:
        # UI client connected
        return True

    db = next(database.get_db())
    try:
        host = (
            db.query(models.Host).filter(models.Host.host_token == host_token).first()
        )
        if not host:
            return False

        # Store host info in the session
        async with sio.session(sid, namespace="/terminal") as session:
            session["host_id"] = host.id
            session["is_host"] = True

        # Update host status in database
        host.status = "online"
        db.commit()

        # Join a room specific to this host's ID so we can send spawn commands to it
        room_name = f"host_{host.id}"
        await sio.enter_room(sid, room_name, namespace="/terminal")
        print(
            f"Host Daemon connected: {host.name} (SID: {sid}) joined room: {room_name}"
        )

    finally:
        db.close()


@sio.on("disconnect", namespace="/terminal")
async def disconnect(sid):
    """
    Handles disconnection. If it was a host, mark it as offline.
    """
    async with sio.session(sid, namespace="/terminal") as session:
        if session.get("is_host"):
            host_id = session.get("host_id")
            db = next(database.get_db())
            try:
                host = db.query(models.Host).filter(models.Host.id == host_id).first()
                if host:
                    host.status = "offline"
                    db.commit()
                    print(
                        f"Host Daemon {host.name}"
                        f" (ID: {host_id}) disconnected"
                        f" and marked offline."
                    )
            finally:
                db.close()


@sio.on("terminal_output", namespace="/terminal")
async def handle_terminal_output(sid, data):
    """
    Receives stdout/stderr from an agent (via the host daemon) and broadcasts it.
    data: {'sid': 'agent_id', 'output': '...'}
    """
    agent_id = data.get("sid")
    output = data.get("output", "")

    if agent_id and output:
        # Broadcast to the room dedicated to this agent's ID
        await sio.emit(
            "terminal_output",
            {"sid": agent_id, "output": output},
            room=agent_id,
            namespace="/terminal",
        )


@sio.on("join_room", namespace="/terminal")
async def handle_join_room(sid, data):
    """
    Allows the UI to join a specific agent's room to receive its output.
    """
    agent_id = data.get("room")
    if agent_id:
        await sio.enter_room(sid, agent_id, namespace="/terminal")
        print(f"UI Client {sid} joined Agent room: {agent_id}")

        # Request history replay from the host daemon
        await sio.emit("request_history", {"agent_id": agent_id}, namespace="/terminal")


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
        await sio.emit("history_complete", data, room=agent_id, namespace="/terminal")


@sio.on("terminal_resize", namespace="/terminal")
async def handle_terminal_resize(sid, data):
    """
    Relays a terminal resize event from UI to all host daemons.
    data: {'sid': 'agent_id', 'cols': 80, 'rows': 24}
    """
    await sio.emit("terminal_resize", data, namespace="/terminal")


@sio.on("agent_telemetry", namespace="/terminal")
async def handle_agent_telemetry(sid, data):
    """
    Receives live telemetry updates from host daemons and broadcasts them to UI clients.
    Also persists the latest telemetry state in the database.
    data: {'agent_id': '...', 'telemetry': {...}}
    """
    agent_id = data.get("agent_id")
    telemetry = data.get("telemetry")
    print(
        f"DEBUG: handle_agent_telemetry received for agent_id {agent_id}: {telemetry}"
    )
    if agent_id and telemetry:
        db = next(database.get_db())
        try:
            db_agent = (
                db.query(models.Agent).filter(models.Agent.agent_id == agent_id).first()
            )
            if db_agent:
                # Merge new telemetry into existing
                current_tel = db_agent.telemetry_json or {}
                # Create a new dict to trigger SQLAlchemy's
                # change detection on JSON columns
                new_tel = dict(current_tel)
                new_tel.update(telemetry)
                db_agent.telemetry_json = new_tel
                db.commit()
                msg = f"DEBUG: successfully updated DB for agent {agent_id}"
                print(msg)

                # Broadcast update to all UI clients for real-time card refresh
                await sio.emit(
                    "agent_telemetry_update",
                    {"agent_id": agent_id, "telemetry": new_tel},
                    namespace="/terminal",
                )
            else:
                print(f"DEBUG: agent_id {agent_id} not found in DB")
        finally:
            db.close()


@sio.on("host_telemetry", namespace="/terminal")
async def handle_host_telemetry(sid, data):
    """
    Receives host-wide configuration (like project list) and broadcasts it.
    data: {'projects_root': '...', 'available_projects': [...]}
    """
    async with sio.session(sid, namespace="/terminal") as session:
        host_id = session.get("host_id")
        print(f"Received host_telemetry from SID {sid} (Host ID: {host_id}): {data}")
        if host_id:
            db = next(database.get_db())
            try:
                host = db.query(models.Host).filter(models.Host.id == host_id).first()
                if host:
                    host.last_projects_json = data
                    db.commit()
            finally:
                db.close()

            # Broadcast to UI clients so they can update pickers
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
        db = next(database.get_db())
        try:
            db_agent = (
                db.query(models.Agent).filter(models.Agent.agent_id == agent_id).first()
            )
            if db_agent:
                db_agent.status = "closed"
                from datetime import datetime, timezone

                db_agent.ended_at = datetime.now(timezone.utc)
                db.commit()
                print(f"Agent {agent_id} exited and marked as closed in DB.")

                # Notify UI clients that the agent is gone
                await sio.emit(
                    "agent_status_update",
                    {"agent_id": agent_id, "status": "closed"},
                    namespace="/terminal",
                )
        finally:
            db.close()


@sio.on("terminal_input", namespace="/terminal")
async def handle_terminal_input(sid, data):
    """
    Receives keystrokes from the UI and relays them to the Host Daemon.
    data: {'target_sid': 'agent_id', 'input': '...'}
    """
    # Relay directly to all connected clients on this namespace.
    # The Host Daemon will filter by agent_id.
    await sio.emit("terminal_input", data, namespace="/terminal")
