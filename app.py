# 🐝 Swarm — Deterministic Multi-Agent Coordination Layer
# --------------------------------------------------------
# Flask-based coordination hub for agent registration, task assignment,
# and human-gated synchronization. Designed to integrate with Foxhunter's
# audit and ethics framework.
#
# Run:
#   pip install -r requirements.txt
#   python app.py
# Visit:
#   http://127.0.0.1:5000/

from flask import Flask, jsonify, request, Response
import sqlite3, json, hashlib, threading, time
from datetime import datetime
from pathlib import Path

APP = Flask(__name__)

DB = Path("swarm_audit.db")
AGENTS = {}
STATE_LOCK = threading.Lock()

# ---------- Audit ----------

def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT,
        type TEXT,
        payload TEXT,
        operator TEXT,
        hash TEXT
    )""")
    conn.commit()
    conn.close()

def audit(evt_type, payload, operator="swarm-core"):
    ts = datetime.utcnow().isoformat() + "Z"
    rec = {"ts": ts, "type": evt_type, "payload": payload, "operator": operator}
    h = hashlib.sha256(json.dumps(rec, sort_keys=True).encode()).hexdigest()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO events(ts,type,payload,operator,hash) VALUES(?,?,?,?,?)",
        (ts, evt_type, json.dumps(payload), operator, h),
    )
    conn.commit()
    conn.close()
    return h

# ---------- Agent Registry ----------

def register_agent(agent_id, meta):
    with STATE_LOCK:
        AGENTS[agent_id] = {
            "meta": meta,
            "last_seen": time.time(),
            "status": "idle",
            "task": None,
        }
    audit("register_agent", {"id": agent_id, "meta": meta})

def update_heartbeat(agent_id):
    with STATE_LOCK:
        if agent_id in AGENTS:
            AGENTS[agent_id]["last_seen"] = time.time()

def assign_task(agent_id, task):
    with STATE_LOCK:
        if agent_id not in AGENTS:
            return False
        AGENTS[agent_id]["task"] = task
        AGENTS[agent_id]["status"] = "assigned"
    audit("task_assigned", {"id": agent_id, "task": task})
    return True

def list_agents():
    with STATE_LOCK:
        now = time.time()
        return {
            aid: {
                **meta,
                "last_seen_delta": round(now - meta["last_seen"], 1)
            }
            for aid, meta in AGENTS.items()
        }

# ---------- Flask Routes ----------

@APP.route("/")
def home():
    return Response(HTML, mimetype="text/html")

@APP.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json(force=True)
    agent_id = data.get("agent_id")
    meta = data.get("meta", {})
    if not agent_id:
        return jsonify({"ok": False, "error": "missing agent_id"}), 400
    register_agent(agent_id, meta)
    return jsonify({"ok": True})

@APP.route("/api/heartbeat", methods=["POST"])
def api_heartbeat():
    data = request.get_json(force=True)
    agent_id = data.get("agent_id")
    if not agent_id:
        return jsonify({"ok": False, "error": "missing agent_id"}), 400
    update_heartbeat(agent_id)
    return jsonify({"ok": True})

@APP.route("/api/assign", methods=["POST"])
def api_assign():
    data = request.get_json(force=True)
    agent_id = data.get("agent_id")
    task = data.get("task")
    if not agent_id or not task:
        return jsonify({"ok": False, "error": "missing params"}), 400
    success = assign_task(agent_id, task)
    return jsonify({"ok": success})

@APP.route("/api/agents")
def api_agents():
    return jsonify(list_agents())

@APP.route("/api/audit")
def api_audit():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM events ORDER BY id DESC LIMIT 50")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)

# ---------- HTML UI ----------

HTML = """
<!doctype html><html><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Swarm Coordination Hub</title>
<style>
:root{--bg:#0e1014;--fg:#e0e2ea;--line:#252a36;--card:#151820;--accent:#2e8b57;}
body{margin:0;font-family:system-ui,Inter,Segoe UI;background:var(--bg);color:var(--fg);}
header{padding:12px 16px;border-bottom:1px solid var(--line);}
main{padding:16px;display:grid;gap:14px;}
.card{background:var(--card);padding:14px;border-radius:10px;border:1px solid var(--line);}
table{width:100%;border-collapse:collapse;}
th,td{padding:6px 10px;border-bottom:1px solid var(--line);font-size:13px;}
.btn{background:var(--accent);color:#fff;border:none;padding:6px 10px;border-radius:6px;cursor:pointer;}
</style></head>
<body>
<header><h2>🐝 Swarm Coordination Hub</h2><div>Human-Gated Multi-Agent Synchronization</div></header>
<main>
  <section class="card">
    <h3>Active Agents</h3>
    <table><thead><tr><th>ID</th><th>Status</th><th>Last Seen (s)</th><th>Task</th></tr></thead>
    <tbody id="agents"></tbody></table>
  </section>
  <section class="card">
    <h3>Audit Log</h3>
    <table><thead><tr><th>Type</th><th>Operator</th><th>Timestamp</th><th>Hash</th></tr></thead>
    <tbody id="audit"></tbody></table>
  </section>
</main>
<script>
async function loadAgents(){
  const data=await (await fetch('/api/agents')).json();
  const el=document.querySelector('#agents'); el.innerHTML='';
  Object.entries(data).forEach(([id,a])=>{
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${id}</td><td>${a.status}</td><td>${a.last_seen_delta}</td><td>${a.task||'—'}</td>`;
    el.appendChild(tr);
  });
}
async function loadAudit(){
  const rows=await (await fetch('/api/audit')).json();
  const el=document.querySelector('#audit'); el.innerHTML='';
  rows.forEach(r=>{
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${r.type}</td><td>${r.operator}</td><td>${r.ts}</td><td>${r.hash.slice(0,10)}…</td>`;
    el.appendChild(tr);
  });
}
setInterval(()=>{loadAgents();loadAudit();},1500);
loadAgents();loadAudit();
</script>
</body></html>
"""

# ---------- Main ----------

if __name__ == "__main__":
    init_db()
    print("🐝 Swarm Coordination Hub running on http://127.0.0.1:5000")
    APP.run(host="0.0.0.0", port=5000)
