import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
files = [ROOT / name for name in (".dockerignore", ".gitignore", "Dockerfile", "README.md", "VERSION", "docs/.nojekyll")]
files.extend(ROOT.glob("compose.*.yaml"))
extensions = {".py", ".yaml", ".md", ".json", ".txt", ".jsonl", ".jpg", ".html", ".css", ".js"}
for folder in ("app", "scripts", "k8s", "docs", "evidence"):
    for path in (ROOT / folder).rglob("*"):
        parts = path.relative_to(ROOT).parts
        if (path.is_file() and not path.is_symlink() and path.suffix in extensions
                and "__pycache__" not in parts and not any(part.startswith(".") for part in parts)):
            files.append(path)
lines = []
for path in sorted(files):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    lines.append(f"{digest}  {path.relative_to(ROOT)}\n")
(ROOT / "MANIFEST.sha256").write_text("".join(lines), encoding="utf-8")
print(f"Updated MANIFEST.sha256 for {len(files)} files.")
