"""System info action."""
from core.registry import registry
from actions.base import BaseAction, ActionResult


@registry.register("health_status")
class SysInfoAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        if ctx.has("health_monitor"):
            snap = ctx.health_monitor.current()
            if snap:
                return ActionResult(snap.format_full(), data=snap.__dict__)
        try:
            import psutil, os
            cpu  = psutil.cpu_percent(interval=0.5)
            mem  = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            temps = {}
            try:
                for sn, entries in psutil.sensors_temperatures().items():
                    if sn.lower() in ("coretemp","k10temp","cpu_thermal","acpitz"):
                        for i,e in enumerate(entries):
                            temps[e.label or f"{sn}{i}"] = e.current
            except Exception:
                pass
            max_temp = max(temps.values(), default=0)
            temp_str = f"\n🌡 Temp: {max_temp:.0f}°C" if temps else ""
            text = (f"🖥  CPU: {cpu:.0f}%\n"
                    f"💾 RAM: {mem.percent:.0f}% ({mem.used//1024//1024}/{mem.total//1024//1024} MB)\n"
                    f"💿 Dysk: {disk.percent:.0f}% (wolne {disk.free//1024//1024//1024:.1f} GB)"
                    f"{temp_str}")
            return ActionResult(text, data={"cpu":cpu,"ram":mem.percent,"disk":disk.percent})
        except ImportError:
            return ActionResult("Zainstaluj psutil: pip install psutil", success=False)


@registry.register("backup_now")
class BackupNowAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        try:
            from ai.backup import export_to_file, auto_export_path
            from pathlib import Path
            base = Path("~/.jarvis").expanduser()
            path = auto_export_path(base)
            r = export_to_file(ctx.memory, path)
            return ActionResult(f"Backup zapisany: {path.name} ({r['main']} wpisów).")
        except Exception as e:
            return ActionResult(f"Backup nie powiódł się: {e}", success=False)


@registry.register("backup_status")
class BackupStatusAction(BaseAction):
    def run(self, intent, ctx) -> ActionResult:
        return ActionResult(f"Pamięć: {ctx.memory.count()} wpisów, archiwum: {ctx.memory.archive_count()}.")
