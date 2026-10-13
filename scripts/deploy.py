import base64
import json
import secrets
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args, input=None, check=True, capture=False):
    return subprocess.run(args, cwd=ROOT, input=input, text=True, check=check,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None)


def kube(*args, input=None, **kwargs):
    return run(["docker", "exec", "-i", "csl-k3s", "/bin/kubectl", *args], input=input, **kwargs)


def prepare_secret():
    directory = ROOT / ".runtime"
    directory.mkdir(mode=0o700, exist_ok=True)
    directory.chmod(0o700)
    token = directory / "backend-token"
    if not token.exists():
        token.write_text(secrets.token_hex(32), encoding="utf-8")
    token.chmod(0o444)


if __name__ == "__main__":
    prepare_secret()
    run(["docker", "build", "--pull=false", "--network=none", "-t", "container-security-lab:1.0", "."])
    for profile, name in (("baseline", "csl-baseline"), ("hardened", "csl-hardened")):
        run(["docker", "compose", "-p", name, "-f", f"compose.{profile}.yaml", "up", "-d", "--wait", "--force-recreate"])
    run(["docker", "compose", "-p", "csl-cluster", "-f", "compose.cluster.yaml", "up", "-d"])
    for attempt in range(90):
        ready = kube("get", "nodes", "-o", "json", check=False, capture=True)
        if ready.returncode == 0:
            nodes = json.loads(ready.stdout).get("items", [])
            if nodes and any(c["type"] == "Ready" and c["status"] == "True"
                             for c in nodes[0]["status"].get("conditions", [])):
                break
        time.sleep(2)
    else:
        raise SystemExit("The local K3s node did not become Ready.")
    image = ROOT / ".runtime/app-image.tar"
    run(["docker", "save", "container-security-lab:1.0", "-o", str(image)])
    run(["docker", "cp", str(image), "csl-k3s:/tmp/app-image.tar"])
    run(["docker", "exec", "csl-k3s", "/bin/ctr", "-n", "k8s.io", "images", "import", "/tmp/app-image.tar"])
    image.unlink()
    run(["docker", "exec", "csl-k3s", "rm", "-f", "/tmp/app-image.tar"])
    for profile, namespace in (("baseline", "article-baseline"), ("hardened", "article-secure")):
        kube("apply", "-f", "-", input=(ROOT / "k8s" / f"{profile}.yaml").read_text())
        secret = {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "backend-token", "namespace": namespace},
                  "type": "Opaque", "data": {"backend-token": base64.b64encode((ROOT / ".runtime/backend-token").read_bytes()).decode()}}
        kube("annotate", "secret/backend-token", "-n", namespace,
             "kubectl.kubernetes.io/last-applied-configuration-", check=False, capture=True)
        kube("apply", "--server-side", "--field-manager=csl-lab", "--force-conflicts", "-f", "-", input=json.dumps(secret))
        kube("rollout", "restart", "deployment/store", "deployment/gateway", "-n", namespace)
        kube("delete", "pod", "outsider", "reader", "-n", namespace, "--ignore-not-found=true")
        for kind in ("probe", "reader"):
            kube("apply", "-f", "-", input=(ROOT / "k8s" / f"{kind}.{profile}.yaml").read_text())
        for deployment in ("store", "gateway"):
            kube("rollout", "status", "deployment/" + deployment, "-n", namespace, "--timeout=120s")
        kube("wait", "--for=condition=Ready", "pod/outsider", "pod/reader", "-n", namespace, "--timeout=120s")
    print("Both profiles are ready. Run scripts/verify.py to reproduce the checks.")
