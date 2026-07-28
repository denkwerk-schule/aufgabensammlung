#!/usr/bin/env python3
"""
Scannt aufgaben/**/metadata.yml und lernfelder/**/metadata.yml und generiert
tasks.json bzw. lernfelder.json fuer die index.html. Erzeugt ausserdem, falls
noch nicht vorhanden, Vorschaubilder (Seite 1 als Kartenvorschau, alle Seiten
als Vollansicht fuer die Lightbox) pro Aufgabe/Lernfeld.

Wird lokal oder automatisch via GitHub Action (.github/workflows/build-tasks.yml)
ausgefuehrt. Neue Aufgaben/Lernfelder werden dadurch ohne manuelles Anpassen der
index.html auf der Website sichtbar - es braucht lediglich einen Ordner mit
aufgabe.pdf, aufgabe.md und metadata.yml unterhalb von
aufgaben/<fach>/<name>/ bzw. lernfelder/<fach>/<name>/.

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


def pdf_page_count(pdf: Path) -> int:
    try:
        out = subprocess.run(
            ["pdfinfo", str(pdf)], check=True, capture_output=True, text=True
        ).stdout
        for line in out.splitlines():
            if line.startswith("Pages:"):
                return int(line.split(":")[1].strip())
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        pass
    return 1


def ensure_page_preview(item_dir: Path, page: int, filename: str) -> str | None:
    """Erzeugt ein Vorschaubild fuer eine einzelne PDF-Seite, falls noch nicht vorhanden."""
    preview = item_dir / filename
    pdf = item_dir / "aufgabe.pdf"

    if preview.exists():
        return filename

    if not pdf.exists():
        return None

    try:
        subprocess.run(
            [
                "pdftoppm",
                "-jpeg",
                "-jpegopt", "quality=85",
                "-f", str(page), "-l", str(page),
                "-scale-to-x", "1400",
                "-scale-to-y", "-1",
                str(pdf),
                str(item_dir / preview.stem),
            ],
            check=True,
            capture_output=True,
        )
        # pdftoppm haengt bei -f/-l eine Seitennummer an: <stem>-<page>.jpg
        generated = item_dir / f"{preview.stem}-{page}.jpg"
        if generated.exists():
            generated.rename(preview)
            print(f"  Vorschau erzeugt: {preview.relative_to(ROOT)}")
            return filename
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"  Warnung: Konnte keine Vorschau fuer {pdf} (Seite {page}) erzeugen ({e})", file=sys.stderr)

    return None


def ensure_previews(item_dir: Path) -> list[str]:
    """Erzeugt Kartenvorschau (vorschau.jpg, Seite 1) sowie Vollansichten fuer
    alle Seiten des PDFs (vorschau-seite-1.jpg, vorschau-seite-2.jpg, ...) fuer
    die grosse Klick-Vorschau. Gibt die Liste der Vollansicht-Dateinamen zurueck."""
    pdf = item_dir / "aufgabe.pdf"

    # kleine Kartenvorschau (bleibt wie bisher: vorschau.jpg)
    ensure_page_preview(item_dir, 1, "vorschau.jpg")

    if not pdf.exists():
        return []

    pages = pdf_page_count(pdf)
    seiten = []
    for page in range(1, pages + 1):
        filename = ensure_page_preview(item_dir, page, f"vorschau-seite-{page}.jpg")
        if filename:
            seiten.append(filename)
    return seiten


def load_metadata(metadata_file: Path):
    raw = metadata_file.read_text(encoding="utf-8")
    # Dateien sind im YAML-Frontmatter-Format: --- ... ---
    parts = raw.split("---")
    body = parts[1] if len(parts) >= 3 else raw
    return yaml.safe_load(body)


def build_collection(source_dir: Path, output_file: Path, extra_fields=None):
    """Scannt source_dir/*/*/metadata.yml und schreibt output_file.
    extra_fields: optionale Liste zusaetzlicher YAML-Keys, die 1:1 uebernommen werden."""
    extra_fields = extra_fields or []
    items = []

    for metadata_file in sorted(source_dir.glob("*/*/metadata.yml")):
        item_dir = metadata_file.parent
        rel_path = item_dir.relative_to(ROOT).as_posix()

        try:
            data = load_metadata(metadata_file)
        except yaml.YAMLError as e:
            print(f"Fehler beim Parsen von {metadata_file}: {e}", file=sys.stderr)
            continue

        if not data:
            print(f"Warnung: {metadata_file} ist leer, wird uebersprungen.", file=sys.stderr)
            continue

        fach = data.get("fach", [])
        if isinstance(fach, str):
            fach = [fach]

        pdf_exists = (item_dir / "aufgabe.pdf").exists()
        md_exists = (item_dir / "aufgabe.md").exists()

        if not pdf_exists:
            print(f"Warnung: {rel_path} hat kein aufgabe.pdf.", file=sys.stderr)

        seiten = ensure_previews(item_dir)
        preview = "vorschau.jpg" if (item_dir / "vorschau.jpg").exists() else None

        item = {
            "id": item_dir.name,
            "titel": data.get("titel", item_dir.name),
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
            "vorschauSeiten": [f"{rel_path}/{s}" for s in seiten],
        }
        for key in extra_fields:
            item[key] = data.get(key, [] if key in ("moeglichkeiten", "anschluss") else "")

        items.append(item)

    items.sort(key=lambda t: t["titel"])

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"{len(items)} Eintrag/Eintraege in {output_file.relative_to(ROOT)} geschrieben.")
    return items


def main():
    print("=== Aufgaben ===")
    build_collection(ROOT / "aufgaben", ROOT / "tasks.json")

    print("\n=== Lernfelder ===")
    lernfelder_dir = ROOT / "lernfelder"
    if lernfelder_dir.exists():
        build_collection(
            lernfelder_dir,
            ROOT / "lernfelder.json",
            extra_fields=["typ", "moeglichkeiten", "anschluss"],
        )
    else:
        print("(kein lernfelder/-Ordner vorhanden, uebersprungen)")


if __name__ == "__main__":
    main()
