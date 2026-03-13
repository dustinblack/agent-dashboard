import socketio
from fastapi import HTTPException
from . import database, models

# Initialize the AsyncServer with ASGI support and CORS
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')

@sio.on('connect', namespace='/terminal')
async def connect(sid, environ, auth):
    """
    Handles new Socket.IO connections on the /terminal namespace.
    Authenticates the host or agent using the X-Host-Token header.
    """
    headers = dict(environ.get('asgi.scope', {}).get('headers', []))
    # headers are byte strings, need to decode
    headers_str = {k.decode('utf-8').lower(): v.decode('utf-8') for k, v in headers.items()}
    
    host_token = headers_str.get('x-host-token') or (auth and auth.get('token'))

    if not host_token:
        # Allow UI clients to connect without a host token
        print(f"UI client connected: (SID: {sid})")
        return True
        
    db = next(database.get_db())
    try:
        host = db.query(models.Host).filter(models.Host.host_token == host_token).first()
        if not host:
            return False
            
        # Create a new agent session for this connection (Temporary logic until Phase 3)
        new_agent = models.Agent(host_id=host.id, agent_id=sid, status="active", tool_name="gemini")
        db.add(new_agent)
        db.commit()
        
        # Save host info in the session environment for later use
        async with sio.session(sid, namespace='/terminal') as session:
            session['host_id'] = host.id
            session['db_agent_id'] = new_agent.id
            
        # Join a room specific to this agent ID so the UI can subscribe to it
        await sio.enter_room(sid, sid, namespace='/terminal')
        print(f"Agent connected from host: {host.name} (SID: {sid})")
        
    finally:
        db.close()

@sio.on('disconnect', namespace='/terminal')
async def disconnect(sid):
    """
    Handles agent or UI disconnection. Marks the agent as closed if it was an agent.
    """
    async with sio.session(sid, namespace='/terminal') as session:
        db_agent_id = session.get('db_agent_id')
        if db_agent_id:
            db = next(database.get_db())
            try:
                db_agent = db.query(models.Agent).filter(models.Agent.id == db_agent_id).first()
                if db_agent:
                    db_agent.status = "closed"
                    from datetime import datetime, timezone
                    db_agent.ended_at = datetime.now(timezone.utc)
                    db.commit()
                    print(f"Agent disconnected: SID {sid} marked as closed.")
            finally:
                db.close()

@sio.on('terminal_output', namespace='/terminal')
async def handle_terminal_output(sid, data):
    """
    Receives stdout/stderr from the agent and broadcasts it to the UI room.
    """
    # data is expected to be a dict: {'output': '...text...'}
    output = data.get('output', '')
    if output:
        # Broadcast to anyone listening to this specific agent's room (e.g., the UI)
        await sio.emit('terminal_output', {'sid': sid, 'output': output}, room=sid, namespace='/terminal')
        
        # Optional: Save to Log table for historical purposes
        async with sio.session(sid, namespace='/terminal') as session:
            db_agent_id = session.get('db_agent_id')
            if db_agent_id:
                db = next(database.get_db())
                try:
                    new_log = models.Log(agent_id=db_agent_id, content=output)
                    db.add(new_log)
                    db.commit()
                finally:
                    db.close()

@sio.on('join_room', namespace='/terminal')
async def handle_join_room(sid, data):
    """
    Allows the UI to join a specific agent's room to receive its output.
    """
    room = data.get('room')
    if room:
        await sio.enter_room(sid, room, namespace='/terminal')
        print(f"User SID {sid} joined room: {room}")
        # Send a carriage return to the agent so it redraws its prompt for the newly attached UI
        await sio.emit('terminal_input', {'input': '\r'}, room=room, namespace='/terminal')

@sio.on('terminal_input', namespace='/terminal')
async def handle_terminal_input(sid, data):
    """
    Receives keystrokes from the UI and sends them back to the specific agent.
    The UI emits this event to the server, and the server relays it to the agent.
    """
    # data is expected to be a dict: {'target_sid': '...', 'input': '...chars...'}
    target_sid = data.get('target_sid')
    user_input = data.get('input')
    
    if target_sid and user_input:
        # Emit 'terminal_input' back to the specific agent daemon
        await sio.emit('terminal_input', {'input': user_input}, room=target_sid, namespace='/terminal')
