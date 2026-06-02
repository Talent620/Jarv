"""Panel webowy Jarvisa — FastAPI + WebSocket."""
from __future__ import annotations
import asyncio
import json
import threading
from pathlib import Path
from typing import Optional, Set

from core.events import E
from core.logging_setup import get_logger
log = get_logger(__name__)

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse, JSONResponse
    import uvicorn
    _OK = True
except ImportError:
    _OK = False


class JarvisWebServer:
    def __init__(self, ctx, host: str = "0.0.0.0", port: int = 8080):
        self.ctx = ctx
        self.host = host
        self.port = port
        self._clients: Set[WebSocket] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

        if not _OK:
            log.warning("Web: pip install fastapi uvicorn")
            return

        self.app = FastAPI(title="Jarvis V2")
        self._routes()
        self._subscribe()

    def start_background(self):
        if not _OK: return
        self._thread = threading.Thread(target=self._run, daemon=True, name="jarvis-web")
        self._thread.start()
        log.info("Panel webowy: http://%s:%d", self.host, self.port)

    def _run(self):
        uvicorn.run(self.app, host=self.host, port=self.port, log_level="warning")

    def _subscribe(self):
        self.ctx.bus.subscribe(E.WEB_PUSH,     self._push)
        self.ctx.bus.subscribe(E.SYSTEM_ALERT, self._alert)
        self.ctx.bus.subscribe(E.ACTION_DONE,  self._action_done)

    def _push(self, event="update", data=None, **_):
        self._broadcast({"event": event, "data": data or {}})

    def _alert(self, title="", body="", source="", **_):
        self._broadcast({"event": "alert", "data": {"title": title, "body": body, "source": source}})

    def _action_done(self, result=None, **_):
        if result:
            self._broadcast({"event": "response", "data": {"text": result.text, "success": result.success}})

    def _broadcast(self, payload: dict):
        if not self._clients or not self._loop: return
        msg = json.dumps(payload, ensure_ascii=False)
        dead = set()
        for ws in list(self._clients):
            try:
                asyncio.run_coroutine_threadsafe(ws.send_text(msg), self._loop)
            except Exception:
                dead.add(ws)
        self._clients -= dead

    def _routes(self):
        app = self.app
        ctx = self.ctx

        @app.websocket("/ws")
        async def ws_endpoint(ws: WebSocket):
            await ws.accept()
            self._clients.add(ws)
            self._loop = asyncio.get_event_loop()
            try:
                while True:
                    data = await ws.receive_text()
                    try:
                        msg = json.loads(data)
                        if msg.get("type") == "command":
                            ctx.bus.emit(E.TEXT_INPUT, text=msg["text"], source="web")
                    except Exception:
                        pass
            except WebSocketDisconnect:
                self._clients.discard(ws)

        @app.get("/api/status")
        async def status():
            timers = 0
            if ctx.has("timer_manager"):
                try: timers = len(ctx.timer_manager.list_active())
                except Exception: pass
            devices = []
            if ctx.has("esp32"):
                try: devices = [d.name for d in ctx.esp32.cfg.devices]
                except Exception: pass
            return {
                "ollama":  ctx.ollama.is_running(),
                "model":   ctx.ollama.has_model() if ctx.ollama.is_running() else False,
                "memory":  ctx.memory.count(),
                "esp32":   ctx.has("esp32") and ctx.esp32.cfg.enabled,
                "timers":  timers,
                "version": "2.0",
                "devices": devices,
            }

        @app.get("/api/health")
        async def health():
            try:
                import psutil
                mem  = psutil.virtual_memory()
                disk = psutil.disk_usage("/")
                cpu  = psutil.cpu_percent(interval=0.3)
                max_temp = 0
                try:
                    for sn, entries in psutil.sensors_temperatures().items():
                        for e in entries:
                            if e.current > max_temp: max_temp = e.current
                except Exception: pass
                return {"cpu_pct": cpu, "ram_pct": mem.percent,
                        "ram_used_mb": mem.used//1024//1024,
                        "ram_total_mb": mem.total//1024//1024,
                        "disk_pct": disk.percent,
                        "disk_free_gb": disk.free//1024//1024//1024,
                        "max_temp": max_temp}
            except ImportError:
                return JSONResponse({"error": "pip install psutil"}, 503)

        @app.post("/api/chat")
        async def chat(body: dict):
            text = (body.get("text") or "").strip()
            if not text: return JSONResponse({"error": "Brak tekstu"}, 400)
            ctx.bus.emit(E.TEXT_INPUT, text=text, source="web")
            return {"ok": True}

        @app.get("/api/memory")
        async def mem_list():
            try:
                entries = ctx.memory.all_entries()[-50:]
            except Exception:
                entries = []
            return {
                "count": ctx.memory.count(),
                "entries": [{"id": e.id, "tresc": e.tresc[:200],
                             "kategoria": e.kategoria, "data": e.data,
                             "tagi": e.tagi} for e in entries]
            }

        @app.get("/api/timers")
        async def timers():
            if not ctx.has("timer_manager"): return {"timers": []}
            try:
                return {"timers": [
                    {"id": e.id, "label": e.label,
                     "remaining": e.format_remaining(),
                     "fired": e.fired}
                    for e in ctx.timer_manager.list_active()
                ]}
            except Exception:
                return {"timers": []}

        @app.get("/api/todo")
        async def todo():
            if not ctx.has("todo_tool"): return {"items": []}
            try:
                items = ctx.todo_tool.list_all()
                return {"items": [
                    {"id": i.id, "text": i.text,
                     "priority": i.priority, "done": i.done}
                    for i in items
                ]}
            except Exception:
                return {"items": []}

        @app.post("/api/todo")
        async def todo_add(body: dict):
            if not ctx.has("todo_tool"): return JSONResponse({"error": "TodoTool niedostępny"}, 503)
            text = (body.get("text") or "").strip()
            if not text: return JSONResponse({"error": "Brak tekstu"}, 400)
            item = ctx.todo_tool.add(text, priority=int(body.get("priority", 2)))
            return {"ok": True, "id": item.id}

        @app.post("/api/todo/{item_id}/done")
        async def todo_done(item_id: int):
            if not ctx.has("todo_tool"): return JSONResponse({"error": "niedostępny"}, 503)
            return {"ok": ctx.todo_tool.done(item_id)}

        @app.post("/api/esp32/command")
        async def esp32_cmd(body: dict):
            if not ctx.has("esp32"): return JSONResponse({"error": "ESP32 nieaktywny"}, 503)
            cmd    = body.get("cmd", "")
            params = body.get("params", {})
            if cmd == "relay_on":
                r = ctx.esp32.turn_on(params.get("device", ""))
            elif cmd == "relay_off":
                r = ctx.esp32.turn_off(params.get("device", ""))
            elif cmd == "set_voltage":
                r = ctx.esp32.set_voltage(float(params.get("volts", 0)))
            elif cmd == "set_pwm":
                r = ctx.esp32.set_value(params.get("device", ""), int(params.get("value", 0)))
            elif cmd == "status":
                r = ctx.esp32.get_status()
            else:
                r = ctx.esp32.http.command(cmd, params)
            return {"ok": r.success, "message": r.message, "raw": r.raw}

        @app.get("/api/esp32/status")
        async def esp32_status():
            if not ctx.has("esp32"): return JSONResponse({"error": "nieaktywny"}, 503)
            r = ctx.esp32.get_status()
            return {"ok": r.success, "data": r.raw}

        @app.get("/api/esp32/devices")
        async def esp32_devices():
            if not ctx.has("esp32"): return {"devices": []}
            return {"devices": [
                {"name": d.name, "pin": d.pin, "type": d.type, "aliases": d.aliases}
                for d in ctx.esp32.cfg.devices
            ]}

        @app.get("/")
        async def index():
            import pathlib
            static = pathlib.Path(__file__).parent / "static" / "index.html"
            if static.exists():
                return HTMLResponse(static.read_text(encoding="utf-8"))
            return HTMLResponse(_FALLBACK_HTML)


_FALLBACK_HTML = "<!-- Jarvis V2 Panel — brak pliku static/index.html -->"