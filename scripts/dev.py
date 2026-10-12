"""Start both development servers; stop only their own process groups."""
import os
from pathlib import Path
import signal
import subprocess
import time

root = Path(__file__).resolve().parents[1]
processes = []


def stop(*_):
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, stop)
try:
    for folder, command in [
        ("backend", ["uv", "run", "uvicorn", "hypoweaver.app:app", "--reload", "--port", "8000"]),
        ("frontend", ["npm", "run", "dev", "--", "--host", "127.0.0.1"]),
    ]:
        processes.append(subprocess.Popen(command, cwd=root / folder, start_new_session=True))
    while all(process.poll() is None for process in processes):
        time.sleep(0.5)
    raise SystemExit(next((p.returncode for p in processes if p.returncode), 1))
except KeyboardInterrupt:
    pass
finally:
    for process in processes:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
