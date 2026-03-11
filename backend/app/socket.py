import socketio
from fastapi import HTTPException
from . import database, models

# Initialize the AsyncServer with ASGI support and CORS
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')

@sio.on('connect', namespace='/terminal')
async def connect(sid, environ, auth):
    """
    Handles new Socket.IO connections on the /terminal namespace.
    Authenticates the agent using the X-Machine-Token header.
    """
    headers = dict(environ.get('asgi.scope', {}).get('headers', []))
    # headers are byte strings, need to decode
    headers_str = {k.decode('utf-8').lower(): v.decode('utf-8') for k, v in headers.items()}
    
    machine_token = headers_str.get('x-machine-token') or (auth and auth.get('token'))

    if not machine_token:
        # Reject connection
        return False
        
    db = next(database.get_db())
    try:
        machine = db.query(models.Machine).filter(models.Machine.machine_token == machine_token).first()
        if not machine:
            return False
            
        # Create a new session for this connection
        new_session = models.Session(machine_id=machine.id, session_id=sid, status="active")
        db.add(new_session)
        db.commit()
        
        # Save machine info in the session environment for later use
        async with sio.session(sid, namespace='/terminal') as session:
            session['machine_id'] = machine.id
            session['db_session_id'] = new_session.id
            
        # Join a room specific to this session ID so the UI can subscribe to it
        sio.enter_room(sid, sid, namespace='/terminal')
        print(f"Agent connected: {machine.name} (SID: {sid})")
        
    finally:
        db.close()

@sio.on('disconnect', namespace='/terminal')
async def disconnect(sid):
    """
    Handles agent disconnection. Marks the session as closed.
    """
    async with sio.session(sid, namespace='/terminal') as session:
        db_session_id = session.get('db_session_id')
        if db_session_id:
            db = next(database.get_db())
            try:
                db_session = db.query(models.Session).filter(models.Session.id == db_session_id).first()
                if db_session:
                    db_session.status = "closed"
                    from datetime import datetime, timezone
                    db_session.ended_at = datetime.now(timezone.utc)
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
        # Broadcast to anyone listening to this specific session's room (e.g., the UI)
        await sio.emit('terminal_output', {'sid': sid, 'output': output}, room=sid, namespace='/terminal')
        
        # Optional: Save to Log table for historical purposes
        async with sio.session(sid, namespace='/terminal') as session:
            db_session_id = session.get('db_session_id')
            if db_session_id:
                db = next(database.get_db())
                try:
                    new_log = models.Log(session_id=db_session_id, content=output)
                    db.add(new_log)
                    db.commit()
                finally:
                    db.close()

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
        # Emit 'terminal_input' back to the specific agent wrapper
        await sio.emit('terminal_input', {'input': user_input}, room=target_sid, namespace='/terminal')
