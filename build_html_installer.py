"""Build a self-contained HTML file-writer tool."""
import os, json, base64

BASE = "/home/claude/geoclaw_release"

def read_file(path, is_binary=False):
    with open(path, "rb" if is_binary else "r", encoding=None if is_binary else "utf-8") as f:
        return f.read()

# Collect all files
files = {}
for root, dirs, filenames in os.walk(BASE):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for fname in filenames:
        full = os.path.join(root, fname)
        rel  = os.path.relpath(full, BASE)
        ext  = os.path.splitext(fname)[1].lower()
        if ext == ".geojson":
            content = base64.b64encode(read_file(full, True)).decode()
            files[rel] = {"type": "b64", "content": content}
        else:
            try:
                content = read_file(full)
                files[rel] = {"type": "text", "content": content}
            except Exception as e:
                print(f"Skip {rel}: {e}")

print(f"Collected {len(files)} files")

# Write JS data
js_data = json.dumps(files, ensure_ascii=False, indent=0)
print(f"JSON payload: {len(js_data):,} bytes")

with open("/home/claude/geoclaw_installer.json", "w", encoding="utf-8") as f:
    f.write(js_data)
print("Written: /home/claude/geoclaw_installer.json")
