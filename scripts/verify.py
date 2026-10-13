import datetime
import json
import platform
import sqlite3
import tarfile
import time
from deploy import ROOT, kube, run

EVIDENCE = ROOT / "evidence"
RESULTS = []


def record(name, passed, actual, expected, environment):
    row = {"id": len(RESULTS) + 1, "name": name, "environment": environment,
           "passed": bool(passed), "actual": actual, "expected": expected}
    RESULTS.append(row)
    print(("PASS " if passed else "FAIL ") + environment + " " + name, flush=True)


def docker_json(container, *args):
    return json.loads(run(["docker", "exec", container, "python", *args], capture=True).stdout)


def kube_json(namespace, target, *args):
    return json.loads(kube("exec", "-n", namespace, target, "--", "python", *args, capture=True).stdout)


def valid_api(api):
    return (api["before"].get("status") == 200 and api["create"].get("status") == 201
            and api["after"].get("status") == 200
            and api["after"]["payload"]["count"] == api["before"]["payload"]["count"] + 1
            and api["create"]["payload"] in api["after"]["payload"]["notes"])


def network_probe(ns, url, allowed):
    result = {}
    for _ in range(6):
        result = kube_json(ns, "outsider", "/app/probe.py", url)
        if result.get("reachable") is allowed:
            return result
        time.sleep(2)
    return result


def image_scan(token):
    name = "csl-image-scan"
    archive = ROOT / ".runtime/image-rootfs.tar"
    run(["docker", "create", "--name", name, "container-security-lab:1.0"], capture=True)
    try:
        run(["docker", "export", name, "-o", str(archive)])
        found = False
        with tarfile.open(archive) as tf:
            for item in tf:
                if not item.isfile():
                    continue
                f = tf.extractfile(item)
                previous = b""
                while block := f.read(1024 * 1024):
                    current = previous + block
                    if token in current:
                        found = True
                        break
                    previous = current[-len(token):]
                if found:
                    break
        return not found
    finally:
        run(["docker", "rm", name], capture=True)
        archive.unlink(missing_ok=True)


def encryption_check(token):
    destination = ROOT / ".runtime/database-copy"
    destination.mkdir(mode=0o700, exist_ok=True)
    run(["docker", "pause", "csl-k3s"], capture=True)
    try:
        run(["docker", "cp", "csl-k3s:/var/lib/rancher/k3s/server/db/.", str(destination)], capture=True)
    finally:
        run(["docker", "unpause", "csl-k3s"], capture=True)
    with sqlite3.connect(destination / "state.db") as db:
        row = db.execute("SELECT value FROM kine WHERE name = ? ORDER BY id DESC LIMIT 1",
                         ("/registry/secrets/article-secure/backend-token",)).fetchone()
    raw = bytes(row[0]) if row else b""
    prefix = b"k8s:enc:aescbc:v1:"
    return {"record_found": bool(row), "encrypted_prefix": raw.startswith(prefix),
            "token_in_stored_value": token in raw,
            "storage": "SQLite/Kine", "provider": "AES-CBC"}


if __name__ == "__main__":
    EVIDENCE.mkdir(exist_ok=True)
    token = (ROOT / ".runtime/backend-token").read_bytes().strip()
    snapshots = {"docker": {}, "kubernetes": {}}
    for profile, prefix in (("baseline", "csl-baseline"), ("hardened", "csl-hardened")):
        env = "Docker " + profile
        store = prefix + "-store-1"
        state = docker_json(store, "/app/probe.py")
        snapshots["docker"][profile] = state
        record("Process identity", state["uid"] == (10001 if profile == "hardened" else 0), state["uid"],
               10001 if profile == "hardened" else 0, env)
        record("Root filesystem write", state["rootfs_write"]["allowed"] == (profile == "baseline"),
               state["rootfs_write"], "blocked" if profile == "hardened" else "allowed", env)
        record("Application data write", state["data_write"]["allowed"], state["data_write"], "allowed", env)
        record("Temporary directory write", state["temporary_write"]["allowed"], state["temporary_write"], "allowed", env)
        if profile == "hardened":
            record("Capabilities removed", int(state["cap_eff"], 16) == 0, state["cap_eff"], "zero", env)
            record("Privilege escalation blocked", state["no_new_privs"] == "1", state["no_new_privs"], "1", env)
        record("Seccomp filtering active", state["seccomp"] == "2", state["seccomp"], "2", env)
        record("No Docker socket in application", not state["docker_socket"], state["docker_socket"], False, env)
        api = docker_json(prefix + "-gateway-1", "/app/probe.py", "--notes", "http://127.0.0.1:8080/notes")
        good = valid_api(api)
        record("Create and read a note", good, {"get_before": api["before"].get("status"),
               "post": api["create"].get("status"), "get_after": api["after"].get("status")}, "200/201/200", env)
        denied = docker_json(store, "/app/probe.py", "http://127.0.0.1:8080/notes")
        record("Backend authentication", denied.get("status") == 401, denied, "401 without token", env)
    record("Runtime token absent from image filesystem", image_scan(token), "rootfs archive scanned", "absent", "Image")
    for profile, ns in (("baseline", "article-baseline"), ("hardened", "article-secure")):
        env = "Kubernetes " + profile
        state = kube_json(ns, "deployment/store", "/app/probe.py")
        snapshots["kubernetes"][profile] = state
        record("Process identity", state["uid"] == (10001 if profile == "hardened" else 0), state["uid"],
               10001 if profile == "hardened" else 0, env)
        record("Root filesystem write", state["rootfs_write"]["allowed"] == (profile == "baseline"),
               state["rootfs_write"], "blocked" if profile == "hardened" else "allowed", env)
        record("Writable data and temporary volumes", state["data_write"]["allowed"] and state["temporary_write"]["allowed"],
               {"data": state["data_write"], "tmp": state["temporary_write"]}, "both allowed", env)
        record("ServiceAccount token mount", state["service_account_token"] == (profile == "baseline"),
               state["service_account_token"], profile == "baseline", env)
        if profile == "hardened":
            record("Capabilities removed", int(state["cap_eff"], 16) == 0, state["cap_eff"], "zero", env)
            record("Privilege escalation blocked", state["no_new_privs"] == "1", state["no_new_privs"], "1", env)
            record("Seccomp filtering active", state["seccomp"] == "2", state["seccomp"], "2", env)
        store_pod = json.loads(kube("get", "pods", "-n", ns, "-l", "app=store", "-o", "json", capture=True).stdout)["items"][0]
        url = "http://" + store_pod["status"]["podIP"] + ":8080/health"
        outsider = network_probe(ns, url, profile == "baseline")
        record("Unrelated Pod to backend", outsider.get("reachable") == (profile == "baseline"), outsider,
               "blocked" if profile == "hardened" else "reachable", env)
        api = kube_json(ns, "reader", "/app/probe.py", "--notes", "http://gateway:8080/notes")
        good = valid_api(api)
        record("Allowed reader to gateway to backend", good, {"get_before": api["before"].get("status"),
               "post": api["create"].get("status"), "get_after": api["after"].get("status")}, "200/201/200", env)
    for service_account in ("notes-app", "notes-observer"):
        identity = "system:serviceaccount:article-secure:" + service_account
        for resource, allowed in (("secrets", False), ("pods", service_account == "notes-observer")):
            check = kube("auth", "can-i", "list", resource, "-n", "article-secure", "--as=" + identity, check=False, capture=True)
            actual = check.stdout.strip()
            record("RBAC " + service_account + " lists " + resource, actual == ("yes" if allowed else "no"), actual,
                   "yes" if allowed else "no", "Kubernetes hardened")
    invalid = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "rejected-privileged", "namespace": "article-secure"},
               "spec": {"containers": [{"name": "test", "image": "container-security-lab:1.0", "imagePullPolicy": "Never",
                                        "securityContext": {"privileged": True, "runAsUser": 0}}]}}
    admission = kube("create", "--dry-run=server", "-f", "-", input=json.dumps(invalid), check=False, capture=True)
    rejected = admission.returncode != 0 and "violates PodSecurity" in admission.stderr
    record("Privileged root Pod rejected before launch", rejected, admission.stderr.strip(), "Forbidden by restricted policy", "Kubernetes hardened")
    encryption = encryption_check(token)
    record("Secret encrypted in cluster datastore", encryption["record_found"] and encryption["encrypted_prefix"] and not encryption["token_in_stored_value"],
           encryption, "AES-CBC prefix, no plaintext token", "Kubernetes hardened")
    status = run(["docker", "exec", "csl-k3s", "/bin/k3s", "secrets-encrypt", "status"], capture=True).stdout
    (EVIDENCE / "encryption-status.txt").write_text(status)
    (EVIDENCE / "admission-rejection.txt").write_text(admission.stderr)
    logs = "\n".join(run(["docker", "logs", "csl-hardened-" + role + "-1"], capture=True).stdout for role in ("gateway", "store"))
    record("Structured logs contain no runtime token", token.decode() not in logs and '"status": 201' in logs, "logs scanned", "token absent and POST recorded", "Logging")
    (EVIDENCE / "application-logs.jsonl").write_text(logs)
    metadata = {"timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "kernel": platform.release(),
                "docker": json.loads(run(["docker", "version", "--format", "{{json .}}"], capture=True).stdout),
                "kubernetes": json.loads(kube("version", "-o", "json", capture=True).stdout),
                "node": json.loads(kube("get", "nodes", "-o", "json", capture=True).stdout)["items"][0]["status"]["nodeInfo"],
                "app_image": json.loads(run(["docker", "image", "inspect", "container-security-lab:1.0"], capture=True).stdout)[0]["Id"],
                "cluster_image": json.loads(run(["docker", "image", "inspect", "rancher/k3s:v1.37.1-k3s1"], capture=True).stdout)[0]["RepoDigests"],
                "secret_contents_recorded": False}
    docker_ids = {name: run(["docker", "inspect", name, "--format", "{{.Image}}"], capture=True).stdout.strip()
                  for name in ("csl-baseline-store-1", "csl-baseline-gateway-1", "csl-hardened-store-1", "csl-hardened-gateway-1")}
    kube_ids = {}
    for ns in ("article-baseline", "article-secure"):
        pods = json.loads(kube("get", "pods", "-n", ns, "-o", "json", capture=True).stdout)["items"]
        for pod in pods:
            for cs in pod["status"].get("containerStatuses", []):
                kube_ids[ns + "/" + pod["metadata"]["name"] + "/" + cs["name"]] = cs["imageID"]
    assert len(set(docker_ids.values())) == 1, "Docker variants must use identical images."
    assert len(set(kube_ids.values())) == 1, "Kubernetes variants and diagnostic Pods must use identical images."
    metadata["running_image_ids"] = {"docker": docker_ids, "kubernetes": kube_ids}
    summary = {"passed": sum(r["passed"] for r in RESULTS), "total": len(RESULTS), "checks": RESULTS}
    (EVIDENCE / "checks.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    (EVIDENCE / "runtime-snapshots.json").write_text(json.dumps(snapshots, ensure_ascii=False, indent=2))
    (EVIDENCE / "environment.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    print("Passed", summary["passed"], "of", summary["total"], "checks.")
    raise SystemExit(0 if all(r["passed"] for r in RESULTS) else 1)
