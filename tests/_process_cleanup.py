"""Bereinigt ausschliesslich die von Integrationstests gestarteten Server."""
import os
import subprocess


def cleanup_process_tree(process, timeout=5):
    """Beendet einen gestarteten Prozess genau einmal samt seinen Kindern."""
    if getattr(process, "_finanz_cleanup_done", False):
        return
    process._finanz_cleanup_done = True
    try:
        if process.poll() is not None:
            return
        if os.name == "nt":
            _cleanup_windows_process_tree(process, timeout)
        else:
            _cleanup_process(process, timeout)
    finally:
        _close_process_streams(process)


def _cleanup_windows_process_tree(process, timeout):
    try:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
    _wait_for_exit(process, timeout)


def _cleanup_process(process, timeout):
    try:
        process.terminate()
    except OSError:
        return
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            return
        _wait_for_exit(process, timeout)


def _wait_for_exit(process, timeout):
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        pass


def _close_process_streams(process):
    for name in ("stdout", "stderr", "stdin"):
        stream = getattr(process, name, None)
        if stream is not None and not stream.closed:
            stream.close()
