#!/usr/bin/env python3
"""Prepare a local illustration of one central slice per plane (15 PNGs)."""
import argparse
import html
import json
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_case", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output directory")
    metadata = json.loads((args.source_case / "metadata.json").read_text())
    series = [("baseline", "Baseline"), ("followup", "True follow-up"),
              ("prediction_0", "MUMINS prediction"), ("uncertainty_0", "Uncertainty σ"),
              ("error_0", "Absolute error")]
    selection, sections, files = {}, [], []
    # Check every chosen file before writing the local preview.
    for plane, info in metadata["planes"].items():
        index = info["default_frame"]
        selection[plane] = index
        for name, _ in series:
            path = Path(plane) / name / f"{index:03d}.png"
            if not (args.source_case / path).is_file():
                parser.error(f"Missing selected image: {path}")
            files.append(path)
    args.output.mkdir(parents=True)
    for path in files:
        (args.output / path.parent).mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.source_case / path, args.output / path)
    for plane, index in selection.items():
        figures = []
        for name, label in series:
            path = Path(plane) / name / f"{index:03d}.png"
            figures.append(f'<figure><figcaption>{html.escape(label)}</figcaption>'
                           f'<img src="{path.as_posix()}" alt="{html.escape(plane + " " + label)}"></figure>')
        sections.append(f'<section><h2>{plane.title()} · selected slice {index + 1}</h2>'
                        '<div class="panels">' + ''.join(figures) + '</div></section>')
    uncertainty = metadata["display"]["uncertainty"]["limits"]
    error = metadata["display"]["error"]["limits"]
    document = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MUMINS — central MRI slice preview</title>
<style>body{margin:0;padding:36px;background:#f2f5f4;color:#121a20;font-family:system-ui,sans-serif}
main{max-width:1080px;margin:auto}h1,h2{font-family:Georgia,serif}p{line-height:1.7;color:#52616a}
.panels{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:2px;background:#24333d;border-radius:12px;overflow:hidden}
figure{margin:0;background:#080e13;color:#dbe7ea}figcaption{padding:10px 4px;min-height:32px;font-size:11px;text-align:center}
img{display:block;width:100%;height:auto}section{margin:32px 0}
@media(max-width:650px){body{padding:20px}.panels{grid-template-columns:repeat(6,minmax(0,1fr))}figure{grid-column:span 2}figure:nth-child(n+4){grid-column:span 3}}</style>
<main><p>Local illustration draft · not published</p><h1>Brain MRI · selected central slices</h1>
<p>One central slice per anatomical plane, shown as baseline, true follow-up, prediction,
uncertainty, and absolute error. Δb = 0. This preview contains 15 image files and no full slice stacks.</p>
''' + ''.join(sections) + f'''<p>Uncertainty σ: {uncertainty[0]:.4f}–{uncertainty[1]:.4f} (magma).
Absolute error: {error[0]:.2e}–{error[1]:.4f} (viridis). Units are model-normalized intensity;
display limits are shared across the selected planes.</p></main></html>'''
    (args.output / "index.html").write_text(document)
    (args.output / "selection.json").write_text(json.dumps({
        "case": metadata["id"], "selected_frames": selection,
        "files": [p.as_posix() for p in files], "image_count": len(files),
        "publication_status": "local draft; permission to publish must be confirmed",
    }, indent=2) + '\n')
    print(f"Prepared {len(files)} selected images in {args.output}")


if __name__ == "__main__":
    main()
