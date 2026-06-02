"""Monitor zdrowia systemu dla Jarvisa v3.

UDOO X86 Ultra: CPU Intel, RAM, dysk, temperatura rdzeni.
Alertuje gdy wartości przekraczają progi.

pip install psutil   (zwykle już jest)
"""
from __future__ import annotations

import datetime
import os
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, List, Optional
from core.logging_setup import get_logger

log = get_logger(__name__)

try:
    import psutil
    _PSUTIL_OK = True
except ImportError:
    _PSUTIL_OK = False
    log.warning("psutil niedostępny: pip install psutil")


@dataclass
class HealthSnapshot:
    ts: float                       # time.time()
    cpu_pct: float
    ram_pct: float
    ram_used_mb: float
    ram_total_mb: float
    disk_pct: float
    disk_free_gb: float
    temps: Dict[str, float]         # {"core0": 65.0, ...}
    net_sent_mb: float
    net_recv_mb: float
    load_avg: tuple                 # (1min, 5min, 15min)
    processes: int

    def max_temp(self) -> float:
        return max(self.temps.values(), default=0.0)

    def format_short(self) -> str:
        temp_str = f"  🌡 {self.max_temp():.0f}°C" if self.temps else ""
        return (
            f"🖥  CPU: {self.cpu_pct:.0f}%"
            f"  💾 RAM: {self.ram_pct:.0f}% ({self.ram_used_mb:.0f}/{self.ram_total_mb:.0f} MB)"
            f"  💿 Dysk: {self.disk_pct:.0f}% (wolne {self.disk_free_gb:.1f} GB)"
            f"{temp_str}"
        )

    def format_full(self) -> str:
        lines = [
            "📊 STAN SYSTEMU (UDOO X86)",
            f"  🖥  CPU:    {self.cpu_pct:.1f}%  (load: {self.load_avg[0]:.2f} / {self.load_avg[1]:.2f} / {self.load_avg[2]:.2f})",
            f"  💾 RAM:    {self.ram_pct:.1f}%  ({self.ram_used_mb:.0f} MB / {self.ram_total_mb:.0f} MB)",
            f"  💿 Dysk:   {self.disk_pct:.1f}%  (wolne {self.disk_free_gb:.1f} GB)",
            f"  🔢 Procesy: {self.processes}",
            f"  🌐 Sieć:   ↑ {self.net_sent_mb:.1f} MB  ↓ {self.net_recv_mb:.1f} MB",
        ]
        if self.temps:
            temp_items = "  ".join(f"{k}: {v:.0f}°C" for k, v in sorted(self.temps.items()))
            lines.append(f"  🌡 Temp:   {temp_items}")
        return "\n".join(lines)


@dataclass
class HealthConfig:
    enabled: bool = True
    interval_s: int = 30            # jak często zbiera dane
    history_count: int = 120        # ile snapshottów trzyma (60 min przy 30s)
    alert_cpu_pct: float = 90.0
    alert_ram_pct: float = 90.0
    alert_disk_pct: float = 90.0
    alert_temp_c: float = 85.0
    monitor_path: str = "/"         # dysk do monitorowania


class HealthMonitor:
    """Zbiera metryki systemu w tle i alertuje przy przekroczeniu progów."""

    def __init__(self, cfg: HealthConfig, alert_fn: Optional[Callable] = None):
        self.cfg = cfg
        self.alert_fn = alert_fn    # callable(title, body, source)
        self._history: Deque[HealthSnapshot] = deque(maxlen=cfg.history_count)
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._net_base = None       # baseline dla liczników sieci

    def start(self) -> None:
        if not _PSUTIL_OK or not self.cfg.enabled:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="jarvis-health",
        )
        self._thread.start()
        log.info("HealthMonitor uruchomiony (interwał %ds)", self.cfg.interval_s)

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            try:
                snap = self._collect()
                with self._lock:
                    self._history.append(snap)
                self._check_alerts(snap)
            except Exception as e:
                log.debug("HealthMonitor błąd: %s", e)
            time.sleep(self.cfg.interval_s)

    def _collect(self) -> HealthSnapshot:
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(self.cfg.monitor_path)

        # Temperatura
        temps: Dict[str, float] = {}
        try:
            raw = psutil.sensors_temperatures()
            for sensor_name, entries in raw.items():
                if sensor_name.lower() in ("coretemp", "k10temp", "cpu_thermal", "acpitz"):
                    for i, e in enumerate(entries):
                        label = e.label or f"{sensor_name}{i}"
                        temps[label] = e.current
        except (AttributeError, NotImplementedError):
            pass

        # Sieć (delta od baseline)
        net_io = psutil.net_io_counters()
        if self._net_base is None:
            self._net_base = net_io
        net_sent = (net_io.bytes_sent - self._net_base.bytes_sent) / 1024 / 1024
        net_recv = (net_io.bytes_recv - self._net_base.bytes_recv) / 1024 / 1024

        load = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)

        return HealthSnapshot(
            ts=time.time(),
            cpu_pct=cpu,
            ram_pct=mem.percent,
            ram_used_mb=mem.used / 1024 / 1024,
            ram_total_mb=mem.total / 1024 / 1024,
            disk_pct=disk.percent,
            disk_free_gb=disk.free / 1024 / 1024 / 1024,
            temps=temps,
            net_sent_mb=net_sent,
            net_recv_mb=net_recv,
            load_avg=load,
            processes=len(psutil.pids()),
        )

    def _check_alerts(self, snap: HealthSnapshot) -> None:
        if not self.alert_fn:
            return
        alerts = []
        if snap.cpu_pct >= self.cfg.alert_cpu_pct:
            alerts.append(f"🔴 CPU: {snap.cpu_pct:.0f}%")
        if snap.ram_pct >= self.cfg.alert_ram_pct:
            alerts.append(f"🔴 RAM: {snap.ram_pct:.0f}%")
        if snap.disk_pct >= self.cfg.alert_disk_pct:
            alerts.append(f"🔴 Dysk: {snap.disk_pct:.0f}% (wolne {snap.disk_free_gb:.1f} GB)")
        if snap.max_temp() >= self.cfg.alert_temp_c:
            alerts.append(f"🌡 Temperatura: {snap.max_temp():.0f}°C")

        if alerts:
            self.alert_fn(
                title="⚠ Ostrzeżenie systemu",
                body="\n".join(alerts),
                source="system",
            )

    def current(self) -> Optional[HealthSnapshot]:
        if not _PSUTIL_OK:
            return None
        try:
            return self._collect()
        except Exception:
            with self._lock:
                return self._history[-1] if self._history else None

    def history_json(self) -> List[dict]:
        """Dane historyczne do wykresu w GUI."""
        with self._lock:
            result = []
            for s in self._history:
                result.append({
                    "ts": datetime.datetime.fromtimestamp(s.ts).strftime("%H:%M:%S"),
                    "cpu": round(s.cpu_pct, 1),
                    "ram": round(s.ram_pct, 1),
                    "temp": round(s.max_temp(), 1),
                    "disk": round(s.disk_pct, 1),
                })
            return result
