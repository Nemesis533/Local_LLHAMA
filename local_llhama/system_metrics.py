"""
System Metrics Collection Module
Collects CPU, RAM, and GPU metrics for backend health monitoring.
"""

import json
import subprocess
from typing import Dict, List, Optional

import psutil


class SystemMetrics:
    """Collects system health metrics including CPU, RAM, and GPU statistics."""

    @staticmethod
    def get_cpu_metrics() -> Dict:
        """Get CPU temperature and usage statistics."""
        metrics = {
            "usage_percent": psutil.cpu_percent(interval=1, percpu=False),
            "usage_per_core": psutil.cpu_percent(interval=1, percpu=True),
            "temperature": None,
        }

        # Try to get CPU temperature using sensors
        try:
            # First try psutil's sensors_temperatures (Linux only)
            temps = psutil.sensors_temperatures()
            if temps:
                # Try coretemp first (Intel), then k10temp (AMD), then others
                for sensor_name in [
                    "coretemp",
                    "k10temp",
                    "cpu_thermal",
                    "soc_thermal",
                ]:
                    if sensor_name in temps:
                        entries = temps[sensor_name]
                        if entries:
                            # Average all core temperatures
                            avg_temp = sum(entry.current for entry in entries) / len(
                                entries
                            )
                            metrics["temperature"] = round(avg_temp, 1)
                            break

                # If still no temp, use first available sensor
                if metrics["temperature"] is None and temps:
                    first_sensor = list(temps.values())[0]
                    if first_sensor:
                        metrics["temperature"] = round(first_sensor[0].current, 1)
        except (AttributeError, Exception):
            # sensors_temperatures not available or failed
            pass

        # Fallback: try sensors command
        if metrics["temperature"] is None:
            try:
                result = subprocess.run(
                    ["sensors", "-A", "-u"], capture_output=True, text=True, timeout=2
                )
                if result.returncode == 0:
                    # Parse output for CPU temp
                    for line in result.stdout.split("\n"):
                        if "temp1_input" in line or "Package id 0" in line:
                            parts = line.split(":")
                            if len(parts) > 1:
                                try:
                                    temp_str = parts[1].strip().split()[0]
                                    metrics["temperature"] = round(float(temp_str), 1)
                                    break
                                except (ValueError, IndexError):
                                    pass
            except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
                pass

        return metrics

    @staticmethod
    def get_ram_metrics() -> Dict:
        """Get RAM usage statistics."""
        mem = psutil.virtual_memory()
        return {
            "total_gb": round(mem.total / (1024**3), 2),
            "used_gb": round(mem.used / (1024**3), 2),
            "available_gb": round(mem.available / (1024**3), 2),
            "percent": round(mem.percent, 1),
        }

    @staticmethod
    def get_gpu_metrics() -> List[Dict]:
        """Get GPU metrics using nvidia-smi."""
        gpus = []

        try:
            # Use nvidia-smi to get GPU metrics in JSON format
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=index,name,temperature.gpu,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )

            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                for line in lines:
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 9:
                        try:
                            gpu_info = {
                                "index": int(parts[0]),
                                "name": parts[1],
                                "temperature": (
                                    float(parts[2])
                                    if parts[2] not in ["[N/A]", "N/A", ""]
                                    else None
                                ),
                                "utilization_percent": (
                                    float(parts[3])
                                    if parts[3] not in ["[N/A]", "N/A", ""]
                                    else None
                                ),
                                "memory_utilization_percent": (
                                    float(parts[4])
                                    if parts[4] not in ["[N/A]", "N/A", ""]
                                    else None
                                ),
                                "memory_used_mb": (
                                    float(parts[5])
                                    if parts[5] not in ["[N/A]", "N/A", ""]
                                    else None
                                ),
                                "memory_total_mb": (
                                    float(parts[6])
                                    if parts[6] not in ["[N/A]", "N/A", ""]
                                    else None
                                ),
                                "power_draw_w": (
                                    float(parts[7])
                                    if parts[7] not in ["[N/A]", "N/A", ""]
                                    else None
                                ),
                                "power_limit_w": (
                                    float(parts[8])
                                    if parts[8] not in ["[N/A]", "N/A", ""]
                                    else None
                                ),
                            }
                            gpus.append(gpu_info)
                        except (ValueError, IndexError):
                            continue
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            # nvidia-smi not available or failed
            pass

        return gpus

    @staticmethod
    def get_all_metrics() -> Dict:
        """Get all system metrics."""
        return {
            "cpu": SystemMetrics.get_cpu_metrics(),
            "ram": SystemMetrics.get_ram_metrics(),
            "gpus": SystemMetrics.get_gpu_metrics(),
        }
