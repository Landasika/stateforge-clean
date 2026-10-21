from __future__ import annotations
import os
import signal
import socket
import time
from stateforge.runtime.snapshot.protocol import LeafTimeout, _on_alarm, _pss_kb, _recv, _rss_kb, _send

def control_loop(server, ctrl, name, l2=None):
    
    signal.signal(signal.SIGALRM, _on_alarm)
    while True:
        msg, _ = _recv(ctrl)
        if msg is None:
            break
        cmd = msg.get("cmd")
        if cmd == "serve":
            _handle_serve(server, msg, ctrl, l2)
        elif cmd == "freeze_child":
            _handle_freeze(server, msg, ctrl, name, l2)
        elif cmd == "rss":
            _send(ctrl, {"evt": "rss", "name": name, "pid": os.getpid(),
                         "pss_kb": _pss_kb(os.getpid()), "rss_kb": _rss_kb(os.getpid())})
        elif cmd == "ping":
            _send(ctrl, {"evt": "pong", "name": name})
        elif cmd == "exit":
            break
    os._exit(0)


def _handle_serve(server, msg, ctrl, l2):
    
    quota = int(msg.get("quota", 1))
    budget = msg.get("budget")
    rcount, wcount = os.pipe()
    server.quota, server.served = quota, 0
    if l2 is not None:
        l2.restore()                      
    t0 = time.perf_counter()
    pid = os.fork()
    if pid == 0:                          
        try:
            while server.served < quota:
                server.handle_request()
        finally:
            os.close(rcount)
            try:
                os.write(wcount, b"%d" % server.served)
            except OSError:
                pass
            os.close(wcount)
            os._exit(0)
    os.close(wcount)
    fork_ms = (time.perf_counter() - t0) * 1e3
    _send(ctrl, {"evt": "leaf_forked", "fork_ms": fork_ms, "pid": pid})
    timed_out, t0 = False, time.perf_counter()
    if budget is not None:
        signal.setitimer(signal.ITIMER_REAL, float(budget))
    try:
        _, status = os.waitpid(pid, 0)
    except LeafTimeout:
        signal.setitimer(signal.ITIMER_REAL, 0)
        timed_out = True
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        _, status = os.waitpid(pid, 0)
    finally:
        if budget is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)
    raw = b""                              
    while True:
        chunk = os.read(rcount, 16)
        if not chunk:
            break
        raw += chunk
    os.close(rcount)
    _send(ctrl, {"evt": "done", "reap_ms": (time.perf_counter() - t0) * 1e3,
                 "served": int(raw or b"0"), "timed_out": timed_out, "status": status})

def _handle_freeze(server, msg, ctrl, parent_name, l2):
    
    name, build, depth = msg["name"], msg.get("build", 0), msg.get("depth")
    parent_end, child_end = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    t0 = time.perf_counter()
    pid = os.fork()
    if pid == 0:
        parent_end.close()
        for _ in range(build):             
            server.handle_request()
        if l2 is not None:
            l2.snapshot_template(name)    
        _send(child_end, {"evt": "frozen", "name": name})
        control_loop(server, child_end, name, l2=(l2.child(name) if l2 else None))
        os._exit(0)
    child_end.close()
    fork_ms = (time.perf_counter() - t0) * 1e3
    _send(ctrl, {"evt": "checkpoint_forked", "name": name, "pid": pid,
                 "fork_ms": fork_ms}, fds=[parent_end.fileno()])
    parent_end.close()
