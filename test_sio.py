"""Test Socket.IO from remote host."""
import asyncio
import sys
import socketio

URL = sys.argv[1] if len(sys.argv) > 1 else "http://172.16.5.2:8000"
AGENT = sys.argv[2] if len(sys.argv) > 2 else "b8f53162-1cbd-4e53-a23e-b70a28b31e43"


async def test():
    sio = socketio.AsyncClient()

    @sio.on("connect", namespace="/terminal")
    async def on_connect():
        print("Connected")
        await sio.emit("join_room", {"room": AGENT}, namespace="/terminal")

    @sio.on("history_complete", namespace="/terminal")
    async def on_hc(data):
        if data.get("agent_id") == AGENT:
            print("HISTORY COMPLETE")

    @sio.on("terminal_output", namespace="/terminal")
    async def on_out(data):
        if data.get("sid") == AGENT:
            print(f"OUTPUT: {len(data.get('output', ''))} bytes")

    await sio.connect(URL, namespaces=["/terminal"], socketio_path="socket.io")
    print(f"Waiting 15s for events from {AGENT}...")
    await asyncio.sleep(15)
    print("Done")
    try:
        await sio.disconnect()
    except Exception:
        pass


asyncio.run(test())
