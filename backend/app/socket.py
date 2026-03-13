import socketio
from . import database, models

# Initialize the AsyncServer with ASGI support and CORS
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')

@sio.on('connect', namespace='/terminal')
async def connect(sid, environ, auth):
    """
    Handles new Socket.IO connections on the /terminal namespace.
    Identifies if the connection is from a Host Daemon or a UI Client.
    """
    headers = dict(environ.get('asgi.scope', {}).get('headers', []))
    headers_str = {k.decode('utf-8').lower(): v.decode('utf-8') for k, v in headers.items()}
    
    host_token = headers_str.get('x-host-token') or (auth and auth.get('token'))

    if not host_token:
        # UI client connected
        return True
        
    db = next(database.get_db())
    try:
        host = db.query(models.Host).filter(models.Host.host_token == host_token).first()
        if not host:
            return False
            
        # Store host info in the session
        async with sio.session(sid, namespace='/terminal') as session:
            session['host_id'] = host.id
            session['is_host'] = True
            
        # Join a room specific to this host's ID so we can send spawn commands to it
        await sio.enter_room(sid, f"host_{host.id}", namespace='/terminal')
        print(f"Host Daemon connected: {host.name} (SID: {sid})")
        
    finally:
        db.close()

@sio.on('disconnect', namespace='/terminal')
async def disconnect(sid):
    """
    Handles disconnection. If it was a host, we could mark all its agents as closed.
    """
    async with sio.session(sid, namespace='/terminal') as session:
        if session.get('is_host'):
            host_id = session.get('host_id')
            print(f"Host Daemon {host_id} disconnected (SID: {sid})")
            # In a production app, we'd mark all agents for this host as 'closed' here.

@sio.on('terminal_output', namespace='/terminal')
async def handle_terminal_output(sid, data):
    """
    Receives stdout/stderr from an agent (via the host daemon) and broadcasts it.
    data: {'sid': 'agent_id', 'output': '...'}
    """
    agent_id = data.get('sid')
    output = data.get('output', '')
    
    if agent_id and output:
        # Broadcast to the room dedicated to this agent's ID
        await sio.emit('terminal_output', {'sid': agent_id, 'output': output}, room=agent_id, namespace='/terminal')
        
        # We could also save logs to the database here if needed.

@sio.on('join_room', namespace='/terminal')
async def handle_join_room(sid, data):
    """
    Allows the UI to join a specific agent's room to receive its output.
    """
    agent_id = data.get('room')
    if agent_id:
        await sio.enter_room(sid, agent_id, namespace='/terminal')
        print(f"UI Client {sid} joined Agent room: {agent_id}")
        # Signal the host daemon to force a prompt redraw for this agent
        # We need to find which host SID is responsible for this agent_id.
        # For simplicity in this refactor, we'll broadcast the redraw request
        # to all hosts, or ideally the specific host if we had a mapping.
        await sio.emit('terminal_input', {'target_sid': agent_id, 'input': '\r'}, namespace='/terminal')

@sio.on('terminal_input', namespace='/terminal')
async def handle_terminal_input(sid, data):
    """
    Receives keystrokes from the UI and relays them to the Host Daemon.
    data: {'target_sid': 'agent_id', 'input': '...'}
    """
    # Relay directly to all connected clients on this namespace. 
    # The Host Daemon will filter by agent_id.
    await sio.emit('terminal_input', data, namespace='/terminal')
