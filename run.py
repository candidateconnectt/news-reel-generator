#!/usr/bin/env python
"""
Unified Launcher for Autonomous News Reel Generator (MVP)
Runs FastAPI backend and Next.js frontend concurrently, streams logs,
and handles clean process tree termination on Windows.
"""

import os
import sys
import time
import socket
import signal
import subprocess
import threading

# ANSI Escape Sequences for terminal styling
COLOR_BACKEND = "\033[92m"   # Light Green
COLOR_FRONTEND = "\033[96m"  # Light Cyan
COLOR_SYSTEM = "\033[93m"    # Yellow
COLOR_ERROR = "\033[91m"     # Light Red
COLOR_RESET = "\033[0m"

# Configurations
BACKEND_PORT = 8000
FRONTEND_PORT = 3000
BACKEND_CWD = os.path.abspath(os.path.join(os.path.dirname(__file__), "backend"))
FRONTEND_CWD = os.path.abspath(os.path.join(os.path.dirname(__file__), "frontend"))

# Find OS-specific Python executable and commands
if os.name == "nt":
    BACKEND_PYTHON = os.path.join(BACKEND_CWD, ".venv", "Scripts", "python.exe")
    FRONTEND_CMD = ["cmd", "/c", f"npx next dev -p {FRONTEND_PORT}"]
else:
    BACKEND_PYTHON = os.path.join(BACKEND_CWD, ".venv", "bin", "python")
    FRONTEND_CMD = ["npx", "next", "dev", "-p", str(FRONTEND_PORT)]

# Standard uvicorn run command
BACKEND_CMD = [BACKEND_PYTHON, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(BACKEND_PORT)]

processes = []

def check_port_in_use(port: int) -> bool:
    """Check if a port is in use on localhost (IPv4 or IPv6) or wildcard address."""
    # 1. Try connecting to IPv4 localhost
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            s.connect(("127.0.0.1", port))
            return True
    except Exception:
        pass

    # 2. Try connecting to IPv6 localhost
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            s.connect(("::1", port))
            return True
    except Exception:
        pass

    # 3. Try binding to the wildcard address
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", port))
    except OSError:
        return True

    return False

def kill_process_on_port(port: int) -> None:
    """Attempts to find and kill the process occupying the specified port on Windows/Unix."""
    print(f"{COLOR_SYSTEM}[System] Port {port} is occupied. Attempting to free it...{COLOR_RESET}")
    if os.name == "nt":
        try:
            # Query netstat to find PID list
            output = subprocess.check_output(f"netstat -ano", shell=True).decode()
            for line in output.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        print(f"{COLOR_SYSTEM}[System] Found PID {pid} using port {port}. Terminating process...{COLOR_RESET}")
                        subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        time.sleep(1)
        except Exception as e:
            print(f"{COLOR_ERROR}[Error] Could not automatically free port {port}: {e}{COLOR_RESET}")
    else:
        try:
            subprocess.run(f"lsof -t -i:{port} | xargs kill -9", shell=True)
            time.sleep(1)
        except Exception as e:
            print(f"{COLOR_ERROR}[Error] Could not automatically free port {port}: {e}{COLOR_RESET}")

def stream_logs(pipe, prefix, color):
    """Read logs from a process stdout/stderr pipe and print with colored prefix."""
    try:
        for line in iter(pipe.readline, ""):
            if not line:
                break
            clean_line = line.rstrip()
            if clean_line:
                print(f"{color}{prefix}{COLOR_RESET} {clean_line}")
    except (ValueError, OSError):
        pass
    finally:
        try:
            pipe.close()
        except Exception:
            pass

def kill_child_processes(pid):
    """Kills a process and all of its sub-processes recursively."""
    if os.name == "nt":
        # On Windows, kill process tree recursively using taskkill
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

def clean_shutdown(signum=None, frame=None):
    """Shutdown all running sub-processes cleanly."""
    print(f"\n{COLOR_SYSTEM}[System] Shutting down application runner...{COLOR_RESET}")
    for p in processes:
        if p.poll() is None:
            print(f"{COLOR_SYSTEM}[System] Stopping process {p.pid}...{COLOR_RESET}")
            kill_child_processes(p.pid)
    sys.exit(0)

# Register signals for clean exit on Unix/CLI
signal.signal(signal.SIGINT, clean_shutdown)
signal.signal(signal.SIGTERM, clean_shutdown)

def print_banner():
    """Prints a beautiful colored ASCII art banner to look extremely premium."""
    # Ensure stdout handles UTF-8 formatting if supported
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    banner = f"""
{COLOR_FRONTEND}========================================================================
             AUTONOMOUS NEWS REEL GENERATOR -- RUNNER
========================================================================{COLOR_RESET}
    
  >> {COLOR_BACKEND}FastAPI Backend:{COLOR_RESET}  Running at {COLOR_SYSTEM}http://localhost:{BACKEND_PORT}{COLOR_RESET}
     -> OpenAPI Docs:   {COLOR_SYSTEM}http://localhost:{BACKEND_PORT}/docs{COLOR_RESET}
     
  >> {COLOR_FRONTEND}Next.js Frontend:{COLOR_RESET} Running at {COLOR_SYSTEM}http://localhost:{FRONTEND_PORT}{COLOR_RESET}
  
  >> {COLOR_SYSTEM}Mock Mode Status:{COLOR_RESET} Active (Runs entirely locally, bypasses Make.com)
  
  >> {COLOR_SYSTEM}Tip:{COLOR_RESET} Press {COLOR_ERROR}Ctrl + C{COLOR_RESET} at any time to shut down both servers cleanly.
{COLOR_FRONTEND}========================================================================{COLOR_RESET}
"""
    print(banner)

def main():
    print(f"{COLOR_SYSTEM}[System] Initializing runner...{COLOR_RESET}")
    
    # 1. Check & free ports if necessary
    for port in [BACKEND_PORT, FRONTEND_PORT]:
        if check_port_in_use(port):
            kill_process_on_port(port)
            if check_port_in_use(port):
                print(f"{COLOR_ERROR}[Error] Port {port} is still in use. Please close the program using it and try again.{COLOR_RESET}")
                sys.exit(1)

    # 2. Print dashboard info
    print_banner()

    # 3. Start Backend
    print(f"{COLOR_SYSTEM}[System] Launching Backend...{COLOR_RESET}")
    try:
        backend_proc = subprocess.Popen(
            BACKEND_CMD,
            cwd=BACKEND_CWD,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace"
        )
        processes.append(backend_proc)
    except Exception as e:
        print(f"{COLOR_ERROR}[Error] Failed to start backend: {e}{COLOR_RESET}")
        sys.exit(1)

    # Start Backend log thread
    t_backend = threading.Thread(target=stream_logs, args=(backend_proc.stdout, "[Backend]", COLOR_BACKEND), daemon=True)
    t_backend.start()

    # Give backend a moment to initialize
    time.sleep(1.5)

    # 4. Start Frontend
    print(f"{COLOR_SYSTEM}[System] Launching Frontend...{COLOR_RESET}")
    try:
        frontend_proc = subprocess.Popen(
            FRONTEND_CMD,
            cwd=FRONTEND_CWD,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace"
        )
        processes.append(frontend_proc)
    except Exception as e:
        print(f"{COLOR_ERROR}[Error] Failed to start frontend: {e}{COLOR_RESET}")
        clean_shutdown()

    # Start Frontend log thread
    t_frontend = threading.Thread(target=stream_logs, args=(frontend_proc.stdout, "[Frontend]", COLOR_FRONTEND), daemon=True)
    t_frontend.start()

    # 5. Monitor processes
    try:
        while True:
            # If any process dies, print status and initiate shutdown
            if backend_proc.poll() is not None:
                print(f"{COLOR_ERROR}[Error] Backend process terminated unexpectedly with code {backend_proc.returncode}{COLOR_RESET}")
                break
            if frontend_proc.poll() is not None:
                print(f"{COLOR_ERROR}[Error] Frontend process terminated unexpectedly with code {frontend_proc.returncode}{COLOR_RESET}")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        clean_shutdown()

if __name__ == "__main__":
    main()
