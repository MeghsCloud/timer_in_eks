import asyncio
import json
import secrets
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse

security = HTTPBasic()

# Change these credentials and share with your team
USERNAME = "meghs-team"
PASSWORD = "timer2024"

def verify(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, USERNAME)
    correct_password = secrets.compare_digest(credentials.password, PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

app = FastAPI()

# All connected clients
clients: list[WebSocket] = []

# Shared timer state
timer_state = {
    "running": False,
    "elapsed": 0.0,
    "started_at": None,
}


def get_current_elapsed() -> float:
    if timer_state["running"] and timer_state["started_at"]:
        delta = datetime.utcnow().timestamp() - timer_state["started_at"]
        return timer_state["elapsed"] + delta
    return timer_state["elapsed"]


async def broadcast(message: dict):
    disconnected = []
    for client in clients:
        try:
            await client.send_text(json.dumps(message))
        except Exception:
            disconnected.append(client)
    for c in disconnected:
        clients.remove(c)


@app.get("/", response_class=HTMLResponse)
async def index():
    return """
<!DOCTYPE html>
<html>
<head>
  <title>Shared Timer</title>
  <style>
    body { font-family: Arial, sans-serif; display: flex; flex-direction: column;
           align-items: center; justify-content: center; height: 100vh;
           margin: 0; background: #1a1a2e; color: #eee; }
    #timer { font-size: 6rem; font-weight: bold; letter-spacing: 4px;
             color: #00d4ff; margin-bottom: 2rem; }
    button { font-size: 1.2rem; padding: 0.8rem 2rem; margin: 0.5rem;
             border: none; border-radius: 8px; cursor: pointer; }
    #startBtn { background: #00b894; color: white; }
    #stopBtn  { background: #d63031; color: white; }
    #resetBtn { background: #636e72; color: white; }
    #status   { margin-top: 1rem; font-size: 0.9rem; color: #aaa; }
  </style>
</head>
<body>
  <div id="timer">00:00:00.0</div>
  <div>
    <button id="startBtn" onclick="send('start')">Start</button>
    <button id="stopBtn"  onclick="send('stop')">Stop</button>
    <button id="resetBtn" onclick="send('reset')">Reset</button>
  </div>
  <div id="status">Connecting...</div>

  <script>
    const ws = new WebSocket(`ws://${location.host}/ws`);
    const status = document.getElementById('status');
    const timerEl = document.getElementById('timer');
    let elapsed = 0;
    let running = false;
    let localInterval = null;

    ws.onopen = () => status.textContent = 'Connected — synced with server';
    ws.onclose = () => status.textContent = 'Disconnected';

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      elapsed = data.elapsed;
      running = data.running;
      clearInterval(localInterval);
      if (running) {
        localInterval = setInterval(() => {
          elapsed += 0.1;
          render(elapsed);
        }, 100);
      }
      render(elapsed);
    };

    function send(action) { ws.send(JSON.stringify({ action })); }

    function render(s) {
      const h = Math.floor(s / 3600);
      const m = Math.floor((s % 3600) / 60);
      const sec = Math.floor(s % 60);
      const tenth = Math.floor((s * 10) % 10);
      timerEl.textContent =
        String(h).padStart(2,'0') + ':' +
        String(m).padStart(2,'0') + ':' +
        String(sec).padStart(2,'0') + '.' + tenth;
    }
  </script>
</body>
</html>
"""


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.append(websocket)

    # Send current state to new client
    await websocket.send_text(json.dumps({
        "running": timer_state["running"],
        "elapsed": get_current_elapsed(),
    }))

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            action = msg.get("action")

            if action == "start" and not timer_state["running"]:
                timer_state["running"] = True
                timer_state["started_at"] = datetime.utcnow().timestamp()

            elif action == "stop" and timer_state["running"]:
                timer_state["elapsed"] = get_current_elapsed()
                timer_state["running"] = False
                timer_state["started_at"] = None

            elif action == "reset":
                timer_state["running"] = False
                timer_state["elapsed"] = 0.0
                timer_state["started_at"] = None

            await broadcast({
                "running": timer_state["running"],
                "elapsed": get_current_elapsed(),
            })

    except WebSocketDisconnect:
        clients.remove(websocket)
