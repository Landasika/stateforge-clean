from __future__ import annotations
import json
import signal
import socket


class LeafTimeout(Exception):
    pass


def _send(sock, obj, fds=()):
    data = (json.dumps(obj) + "\n").encode()
    if fds:
        socket.send_fds(sock, [data], fds)
    else:
        sock.sendall(data)


def _recv(sock, maxfds=4):
    data, fds, _, _ = socket.recv_fds(sock, 65536, maxfds)
    if not data:
        return None, ()
    return json.loads(data.decode()), tuple(fds)


def _pss_kb(pid):
    try:
        with open("/proc/%d/smaps_rollup" % pid) as fh:
            for line in fh:
                if line.startswith("Pss:"):
                    return int(line.split()[1])
    except OSError:
        pass
    return -1


def _rss_kb(pid):
    with open("/proc/%d/status" % pid) as fh:
        for line in fh:
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    return -1


def _on_alarm(signum, frame):
    raise LeafTimeout()
