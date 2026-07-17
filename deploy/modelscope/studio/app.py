"""NOVA ModelScope Studio preflight service.

This first deployment intentionally avoids downloading model weights. It verifies
the assigned runtime before the heavier EchoMimicV3 worker is enabled.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import gradio as gr


def _command_output(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"unavailable: {exc}"
    output = (completed.stdout or completed.stderr).strip()
    return output or f"exit code {completed.returncode}"


def inspect_runtime() -> str:
    disk_root = Path("/mnt/workspace")
    if not disk_root.exists():
        disk_root = Path.cwd()
    total, used, free = shutil.disk_usage(disk_root)
    gpu = _command_output(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader",
        ]
    )
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "phase": "preflight",
        "gpu": gpu,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "disk_root": str(disk_root),
        "disk_total_gib": round(total / 1024**3, 1),
        "disk_used_gib": round(used / 1024**3, 1),
        "disk_free_gib": round(free / 1024**3, 1),
        "model_cache": os.environ.get("MODELSCOPE_CACHE", "not configured"),
        "ready_for_echo_mimic": "unavailable" not in gpu.lower() and free >= 45 * 1024**3,
    }
    return json.dumps(report, ensure_ascii=False, indent=2)


with gr.Blocks(title="NOVA 数字人 · 算力预检") as demo:
    gr.Markdown(
        """
        # NOVA 数字人 · 魔搭算力预检

        私有预检服务：确认 GPU、显存和磁盘达到要求后，才启用 EchoMimicV3 Flash，
        避免错误规格导致大模型下载和无效占用。
        """
    )
    run = gr.Button("检查当前算力", variant="primary")
    output = gr.Code(label="运行环境", language="json", value=inspect_runtime())
    run.click(fn=inspect_runtime, outputs=output)
    gr.Markdown("最低目标：NVIDIA GPU 12GB 显存、45GiB 可用磁盘。")


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", "7860")))
