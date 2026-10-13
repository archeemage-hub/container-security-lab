import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def write_test(path):
    try:
        p = Path(path)
        p.write_text("lab-probe", encoding="utf-8")
        p.unlink()
        return {"allowed": True}
    except OSError as error:
        return {"allowed": False, "errno": error.errno, "error": error.strerror}


def runtime():
    status = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            status[key] = value.strip()
    return {"uid": os.getuid(), "gid": os.getgid(),
            "cap_eff": status.get("CapEff"), "no_new_privs": status.get("NoNewPrivs"),
            "seccomp": status.get("Seccomp"),
            "rootfs_write": write_test("/etc/article-probe"),
            "temporary_write": write_test("/tmp/article-probe"),
            "data_write": write_test("/data/article-probe"),
            "service_account_token": Path("/var/run/secrets/kubernetes.io/serviceaccount/token").exists(),
            "docker_socket": Path("/var/run/docker.sock").exists(),
            "secret_mount": Path(os.environ.get("TOKEN_FILE", "/run/secrets/backend-token")).exists()}


def http(url, method="GET", payload=None):
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("PROBE_TOKEN_FILE")
    if token:
        headers["Authorization"] = "Bearer " + Path(token).read_text().strip()
    req = urllib.request.Request(url, data=json.dumps(payload).encode() if payload else None,
                                 headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=2) as response:
            return {"reachable": True, "status": response.status,
                    "payload": json.loads(response.read(131072))}
    except urllib.error.HTTPError as error:
        return {"reachable": True, "status": error.code}
    except OSError as error:
        return {"reachable": False, "error_type": type(error).__name__, "error": str(error)}


def check_notes(url):
    before = http(url)
    created = http(url, "POST", {"text": "Container security experiment"})
    after = http(url)
    return {"before": before, "create": created, "after": after}


if __name__ == "__main__":
    if len(sys.argv) == 1:
        result = runtime()
    elif sys.argv[1] == "--notes":
        result = check_notes(sys.argv[2])
    else:
        result = http(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False))
