#!/usr/bin/env python3
"""
Scannt aufgaben/**/metadata.yml und generiert tasks.json fuer die index.html.
Erzeugt ausserdem, falls noch nicht vorhanden, ein vorschau.jpg (Seite 1 des PDFs)
pro Aufgabe.

Wird lokal oder automatisch via GitHub Action (.github/workflows/build-tasks.yml)
ausgefuehrt. Neue Aufgaben werden dadurch ohne manuelles Anpassen der index.html
auf der Website sichtbar - es braucht lediglich einen Ordner mit aufgabe.pdf,
aufgabe.md und metadata.yml unterhalb von aufgaben/<fach>/<aufgabe>/.

Nutzung:
    python3 scripts/build_tasks.py
"""
import json
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Bitte 'pip install pyyaml' ausfuehren.", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
AUFGABEN_DIR = ROOT / "aufgaben"
OUTPUT_FILE = ROOT / "tasks.json"


def parse_zeitbedarf_minuten(zeitbedarf: str) -> int:
    """Extrahiert eine grobe Minutenzahl aus Strings wie '90min' oder '90-120min'."""
    if not zeitbedarf:
        return 0
    digits = "".join(c if c.isdigit() or c == "-" else " " for c in zeitbedarf)
    parts = [p for p in digits.split() if p]
    numbers = []
    for p in parts:
        for sub in p.split("-"):
            if sub.isdigit():
                numbers.append(int(sub))
    if not numbers:
        return 0
    return round(sum(numbers) / len(numbers))


def ensure_preview(task_dir: Path) -> str | None:
    """Erzeugt vorschau.jpg aus Seite 1 von aufgabe.pdf, falls noch nicht vorhanden."""
    preview = task_dir / "vorschau.jpg"
    pdf = task_dir / "aufgabe.pdf"

    if preview.exists():
        return "vorschau.jpg"

    if not pdf.exists():
        return None

    try:
        subprocess.run(
            [
                "pdftoppm",
                "-jpeg",
                "-jpegopt", "quality=82",
                "-f", "1", "-l", "1",
                "-scale-to-x", "700",
                "-scale-to-y", "-1",
                str(pdf),
                str(task_dir / "vorschau"),
            ],
            check=True,
            capture_output=True,
        )
        # pdftoppm haengt bei -f/-l 1 eine Seitennummer an: vorschau-1.jpg
        generated = task_dir / "vorschau-1.jpg"
        if generated.exists():
            generated.rename(preview)
            print(f"  Vorschau erzeugt: {preview.relative_to(ROOT)}")
            return "vorschau.jpg"
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"  Warnung: Konnte keine Vorschau fuer {pdf} erzeugen ({e})", file=sys.stderr)

    return None


def main():
    tasks = []

    for metadata_file in sorted(AUFGABEN_DIR.glob("*/*/metadata.yml")):
        task_dir = metadata_file.parent
        rel_path = task_dir.relative_to(ROOT).as_posix()

        try:
            raw = metadata_file.read_text(encoding="utf-8")
            # Dateien sind im YAML-Frontmatter-Format: --- ... ---
            parts = raw.split("---")
            body = parts[1] if len(parts) >= 3 else raw
            data = yaml.safe_load(body)
        except yaml.YAMLError as e:
            print(f"Fehler beim Parsen von {metadata_file}: {e}", file=sys.stderr)
            continue

        if not data:
            print(f"Warnung: {metadata_file} ist leer, wird uebersprungen.", file=sys.stderr)
            continue

        fach = data.get("fach", [])
        if isinstance(fach, str):
            fach = [fach]

        pdf_exists = (task_dir / "aufgabe.pdf").exists()
        md_exists = (task_dir / "aufgabe.md").exists()

        if not pdf_exists:
            print(f"Warnung: {rel_path} hat kein aufgabe.pdf.", file=sys.stderr)

        preview = ensure_preview(task_dir)

        task = {
            "id": task_dir.name,
            "titel": data.get("titel", task_dir.name),
            "fach": fach,
            "stufe": data.get("stufe", ""),
            "niveau": data.get("niveau", ""),
            "zeitbedarf": data.get("zeitbedarf", ""),
            "zeitMinuten": parse_zeitbedarf_minuten(str(data.get("zeitbedarf", ""))),
            "regionalbezug": data.get("regionalbezug", ""),
            "themen": data.get("themen", []),
            "aufgabentyp": data.get("aufgabentyp", ""),
            "offenheitsgrad": data.get("offenheitsgrad", ""),
            "beschreibung": data.get("beschreibung", ""),
            "pfad": rel_path,
            "pdf": f"{rel_path}/aufgabe.pdf" if pdf_exists else None,
            "md": f"{rel_path}/aufgabe.md" if md_exists else None,
            "vorschau": f"{rel_path}/{preview}" if preview else None,
        }
        tasks.append(task)

    tasks.sort(key=lambda t: t["titel"])

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"\n{len(tasks)} Aufgabe(n) in {OUTPUT_FILE.relative_to(ROOT)} geschrieben.")


if __name__ == "__main__":
    main()
