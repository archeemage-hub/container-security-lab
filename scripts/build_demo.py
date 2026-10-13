import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
evidence = ROOT / "evidence"
site = ROOT / "docs"
results = json.loads((evidence / "checks.json").read_text())
environment = json.loads((evidence / "environment.json").read_text())
assert results["total"] == len(results["checks"])
assert results["passed"] == sum(check["passed"] for check in results["checks"])
data = {
    "version": (ROOT / "VERSION").read_text().strip(),
    "results": results,
    "snapshots": json.loads((evidence / "runtime-snapshots.json").read_text()),
    "environment": {
        "timestamp_utc": environment["timestamp_utc"],
        "kernel": environment["kernel"],
        "docker": environment["docker"]["Server"]["Version"],
        "kubernetes": environment["kubernetes"]["serverVersion"]["gitVersion"]
    }
}
encoded = json.dumps(data, ensure_ascii=False, indent=2)
(site / "data.js").write_text("const labEvidence = " + encoded + ";\n", encoding="utf-8")
(site / "evidence.json").write_text(encoded + "\n", encoding="utf-8")
(site / ".nojekyll").touch()
shutil.copy2(evidence / "project-topology.jpg", site / "topology.jpg")
print(f"Demo data updated: {results['passed']}/{results['total']} checks.")
