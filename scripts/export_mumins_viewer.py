#!/usr/bin/env python3
"""Export aligned MUMINS slice stacks from the supplied NIfTI and NumPy files.

Input NIfTI files remain unchanged. Preprocessing profiles reproduce the local
MUMINS dataloaders; the supplied error array checks the reconstructed target.
See mumins_export_cases.json and README-mumins-export.md for configuration.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "mumins-mpl-cache"))

import nibabel as nib
import numpy as np
from PIL import Image, ImageDraw
from matplotlib import colormaps
from scipy import ndimage

PLANES = {"axial": 2, "coronal": 1, "sagittal": 0}
EDGES = {
    "axial": {"top": "A", "bottom": "P", "left": "R", "right": "L"},
    "coronal": {"top": "S", "bottom": "I", "left": "R", "right": "L"},
    "sagittal": {"top": "S", "bottom": "I", "left": "A", "right": "P"},
}


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def finite(array, label):
    array = np.asarray(array, dtype=np.float32)
    if array.ndim != 3 or not np.isfinite(array).all():
        raise ValueError(f"{label}: expected a finite 3D volume, got {array.shape}")
    return array


def read_array(root, spec, label):
    """Explicit leading indices select batch/channel axes; no channel guessing."""
    if isinstance(spec, str):
        spec = {"path": spec}
    path = root / spec["path"]
    if path.name.endswith((".nii", ".nii.gz")):
        array = nib.load(path).get_fdata(dtype=np.float32)
    elif path.suffix == ".npz":
        with np.load(path, allow_pickle=False) as archive:
            array = archive[spec["key"]]
    elif path.suffix == ".npy":
        array = np.load(path, mmap_mode="r", allow_pickle=False)
    else:
        raise ValueError(f"{label}: unsupported input format: {path.name}")
    indices = spec.get("select", [])
    if indices:
        array = array[tuple(indices)]
    return finite(array, label)


def reference(root, name):
    image = nib.load(root / name)
    data = finite(image.get_fdata(dtype=np.float32), name)
    return data, np.asarray(image.affine), {
        "shape_xyz": list(data.shape),
        "spacing_mm": [float(v) for v in image.header.get_zooms()[:3]],
        "axis_codes": list(nib.aff2axcodes(image.affine)),
    }


def resize_longest_and_pad(array, size, fill):
    """Half-pixel trilinear resize, then symmetric padding, as in ResizeD.

    MONAI longest mode rounds each scaled dimension; align_corners=False
    maps output voxel centres to input centres. No arbitrary registration.
    """
    shape = np.array(array.shape)
    resized = np.array([round(int(n) * size / max(shape)) for n in shape])
    output = ndimage.zoom(array, resized / shape, order=1, grid_mode=True,
                          mode="nearest", prefilter=False)
    before = (size - resized) // 2
    padding = [(int(b), int(size - n - b)) for b, n in zip(before, resized)]
    output = np.pad(output, padding, constant_values=fill)
    # Mapping from padded model-grid voxel centres to original voxel centres.
    transform = np.eye(4)
    scale = shape / resized
    transform[:3, :3] = np.diag(scale)
    transform[:3, 3] = (scale - 1) / 2 - scale * before
    return output, transform


def prepare_references(root, case, raw0, raw1, affine, target_shape):
    profile = case["profile"]
    notes = []
    if profile == "ngp":
        wanted = np.array(target_shape)
        shape = np.array(raw0.shape)
        if np.any(shape < wanted):
            raise ValueError("CT source is smaller than the configured model grid")
        low = (shape - wanted) // 2
        slices = tuple(slice(int(a), int(a + b)) for a, b in zip(low, wanted))
        raw0, raw1 = raw0[slices], raw1[slices]
        transform = np.eye(4)
        transform[:3, 3] = low
        affine = affine @ transform
        notes.append("NGP: native XYZ centre crop; HU [-1200, 600] mapped to [-1, 1].")
        return [np.clip((a + 1200) / 900 - 1, -1, 1) for a in [raw0, raw1]], affine, notes

    if profile != "oasis":
        raise ValueError(f"Unknown preprocessing profile: {profile}")
    size = target_shape[0]
    if tuple(target_shape) != (size, size, size):
        raise ValueError("OASIS profile expects a cubic model grid")
    fill, high = case.get("intensity_scope", [-88.0, 25.0])
    # Spatial transform is the same for both original scans and prepared inputs.
    _, transform = resize_longest_and_pad(np.zeros_like(raw0), size, fill)
    affine = affine @ transform
    ready = case.get("model_ready")
    if ready:
        arrays = [read_array(root, ready[k], k) for k in ["baseline", "followup"]]
        for key in ["baseline", "followup"]:
            spec = ready[key] if isinstance(ready[key], dict) else {"path": ready[key]}
            if spec["path"].endswith((".nii", ".nii.gz")):
                if not np.allclose(nib.load(root / spec["path"]).affine, affine, atol=1e-4):
                    raise ValueError(f"Model-ready {key} NIfTI affine differs from the declared model grid")
        notes.append("Model-ready baseline/follow-up supplied on the declared model XYZ grid.")
        return arrays, affine, notes
    masks = case.get("brain_masks")
    if not masks or not all(masks.get(k) for k in ["baseline", "followup"]):
        notes.append("MRI baseline/follow-up pending: supply model_ready inputs or original brain_masks.")
        return None, affine, notes
    arrays = []
    for key, raw in zip(["baseline", "followup"], [raw0, raw1]):
        mask, mask_affine, _ = reference(root, masks[key])
        if mask.shape != raw.shape or not np.allclose(mask_affine, nib.load(root / case[key]).affine, atol=1e-4):
            raise ValueError(f"{key} brain mask must share the original scan's exact grid")
        keep = ndimage.binary_fill_holes(mask > 0)
        keep = ndimage.binary_dilation(keep, iterations=case.get("mask_dilation", 4))
        masked = np.where(keep, raw, fill)
        resized, _ = resize_longest_and_pad(masked, size, fill)
        arrays.append(np.clip((resized - fill) / (high - fill) * 2 - 1, -1, 1))
    notes.append("OASIS: mask hole-fill + dilation, background fill, longest-edge resize, symmetric pad, intensity scaling.")
    return arrays, affine, notes


def load_case(root, case, allow_partial=False):
    raw0, aff0, info0 = reference(root, case["baseline"])
    raw1, aff1, info1 = reference(root, case["followup"])
    if raw0.shape != raw1.shape or not np.allclose(aff0, aff1, atol=1e-4):
        raise ValueError("Baseline and follow-up NIfTI grids differ; register them before export")
    axes = case["prediction_axes"]
    if sorted(axes) != list("xyz"):
        raise ValueError("prediction_axes must be a permutation of xyz")
    permutation = tuple(axes.index(a) for a in "xyz")
    series, validations = {}, {}
    for setting, spec in case["predictions"].items():
        pred = read_array(root, spec["image"], "prediction").transpose(permutation)
        uncertainty = read_array(root, spec["uncertainty"], "uncertainty").transpose(permutation)
        if np.any(uncertainty < 0):
            raise ValueError("Uncertainty contains negative values")
        kind = spec["uncertainty_kind"]
        if kind == "variance":
            uncertainty = np.sqrt(uncertainty)
        elif kind != "std":
            raise ValueError("uncertainty_kind must be variance or std")
        # The training residual is (followup-baseline)/2; sigma must undo /2.
        uncertainty *= float(spec.get("residual_scale", 1))
        series[f"prediction_{setting}"] = pred
        series[f"uncertainty_{setting}"] = uncertainty
    shape = next(iter(series.values())).shape
    refs, affine, notes = prepare_references(root, case, raw0, raw1, aff0, shape)
    if refs is not None:
        series["baseline"], series["followup"] = refs
    elif not allow_partial:
        raise ValueError(notes[-1] + " Use --allow-partial to export prediction/uncertainty/stored-error only.")
    for setting, spec in case["predictions"].items():
        saved = None
        if spec.get("saved_error"):
            saved = read_array(root, spec["saved_error"], "stored error").transpose(permutation)
            if saved.shape != shape:
                raise ValueError(f"Stored error {saved.shape} does not match model grid {shape}")
            if np.any(saved < 0):
                raise ValueError("The supplied absolute-error map contains negative values")
        if refs is not None:
            calculated = np.abs(series[f"prediction_{setting}"] - series["followup"])
            if saved is not None:
                difference = np.abs(saved - calculated)
                validations[setting] = {"max_error_difference": float(difference.max()),
                                        "mean_error_difference": float(difference.mean())}
                if not np.allclose(saved, calculated, atol=5e-5, rtol=1e-5):
                    raise ValueError(f"Setting {setting}: reconstructed target does not match supplied error map "
                                     f"(max difference {difference.max():.6g}); check preprocessing")
            series[f"error_{setting}"] = calculated
        elif saved is not None:
            series[f"error_{setting}"] = saved
            validations[setting] = {"source": "supplied absolute-error volume", "target_reconstruction_checked": False}
    for name, array in series.items():
        finite(array, name)
        if array.shape != shape:
            raise ValueError(f"{name}: {array.shape} does not match model grid {shape}")
    orientation = nib.orientations.ornt_transform(nib.orientations.io_orientation(affine),
                                                 nib.orientations.axcodes2ornt(("R", "A", "S")))
    new_affine = affine @ nib.orientations.inv_ornt_aff(orientation, shape)
    series = {name: nib.orientations.apply_orientation(a, orientation) for name, a in series.items()}
    canonical_shape = next(iter(series.values())).shape
    for plane, dim in PLANES.items():
        start = case.get("default_frame", {}).get(plane, canonical_shape[dim] // 2)
        if not isinstance(start, int) or not 0 <= start < canonical_shape[dim]:
            raise ValueError(f"Invalid default frame for {plane}: {start}")
    return series, new_affine, {
        "comparison_complete": refs is not None,
        "missing_series": [] if refs is not None else ["baseline", "followup"],
        "original_scan_headers": {"baseline": info0, "followup": info1},
        "preprocessing": notes, "error_validation": validations,
    }


def get_slice(array, plane, index):
    # Canonical RAS volume -> radiological display, shared across every series.
    section = np.take(array, index, axis=PLANES[plane])
    return np.flip(section.T, axis=(0, 1))


def kind_of(name):
    return name.split("_", 1)[0] if name.startswith(("uncertainty_", "error_")) else "scan"


def render(array, limits, cmap=None):
    lo, hi = limits
    normalized = np.clip((array - lo) / (hi - lo), 0, 1)
    if cmap:
        return Image.fromarray(colormaps[cmap](normalized, bytes=True)[..., :3])
    return Image.fromarray(np.rint(normalized * 255).astype(np.uint8))


def export_case(output, case, series, affine, report, display):
    folder = output / case["id"]
    folder.mkdir()
    shape = next(iter(series.values())).shape
    spacing = nib.affines.voxel_sizes(affine)
    meta = {"id": case["id"], "modality": case["modality"], "age_years": case.get("age_years"),
            "interval_days": case.get("interval_days"), "seed": case.get("seed"),
            "shape_xyz": list(shape), "orientation": "RAS", "spacing_xyz_mm": spacing.tolist(),
            "uncertainty_kind": "std", "intensity_units": "model-normalized [-1, 1]",
            "uncertainty_units": "model-normalized intensity", "display": display,
            "settings": {key: {"delta_b": key, "oracle": key == "gt",
                               "uncertainty_multiplier": value.get("residual_scale", 1)}
                         for key, value in case["predictions"].items()},
            "series": {key: f"{{plane}}/{key}/{{frame:03d}}.png" for key in series},
            "planes": {}, **report}
    for plane, dim in PLANES.items():
        count = shape[dim]
        start = case.get("default_frame", {}).get(plane, count // 2)
        if not isinstance(start, int) or not 0 <= start < count:
            raise ValueError(f"Invalid default frame for {plane}: {start}")
        sample = get_slice(next(iter(series.values())), plane, start)
        horizontal, vertical = {"axial": (0, 1), "coronal": (0, 2), "sagittal": (1, 2)}[plane]
        meta["planes"][plane] = {"frames": count, "default_frame": start,
            "width": sample.shape[1], "height": sample.shape[0], "edge_labels": EDGES[plane],
            "pixel_aspect_ratio": float(spacing[horizontal] / spacing[vertical]),
            "physical_aspect_ratio": float(sample.shape[1] * spacing[horizontal] /
                                           (sample.shape[0] * spacing[vertical]))}
        for name, volume in series.items():
            dest = folder / plane / name
            dest.mkdir(parents=True)
            kind = kind_of(name)
            for index in range(count):
                image = render(get_slice(volume, plane, index), display[kind]["limits"],
                               display[kind].get("colormap"))
                image.save(dest / f"{index:03d}.png")
        print(f"  {case['id']} {plane}: {count} slices × {len(series)} series", flush=True)
    write_json(folder / "metadata.json", meta)
    order = [n for n in ["baseline", "followup", "prediction_0", "uncertainty_0", "error_0",
                         "prediction_gt", "uncertainty_gt", "error_gt"] if n in series]
    tile, label = 192, 28
    preview = Image.new("RGB", (tile * len(order), (tile + label) * 3), "#101820")
    draw = ImageDraw.Draw(preview)
    for row, plane in enumerate(PLANES):
        for col, name in enumerate(order):
            kind = kind_of(name)
            image = render(get_slice(series[name], plane, meta["planes"][plane]["default_frame"]),
                           display[kind]["limits"], display[kind].get("colormap")).convert("RGB")
            image = image.resize((tile, tile), Image.Resampling.NEAREST)
            preview.paste(image, (col * tile, row * (tile + label) + label))
            draw.text((col * tile + 4, row * (tile + label) + 6), f"{plane}: {name}", fill="white")
    preview.save(folder / "preview.png")
    return {"id": case["id"], "modality": case["modality"],
            "metadata": f"{case['id']}/metadata.json", "comparison_complete": meta["comparison_complete"],
            "png_frames": sum(shape) * len(series)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("mumins_export_cases.json"))
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--case", action="append", help="Select case ID; repeat for multiple cases")
    parser.add_argument("--allow-partial", action="store_true",
                        help="Export available model-grid series when MRI references are missing")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    cases = [c for c in config["cases"] if args.case is None or c["id"] in args.case]
    if not cases or (args.case and set(args.case) - {c["id"] for c in cases}):
        parser.error("Requested case IDs not found")
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r"[A-Za-z0-9_-]+", s) for s in ids):
        parser.error("Case IDs must be unique simple directory names")
    if not args.check_only and (args.output is None or args.output.exists()):
        parser.error("Choose a new --output directory; existing exports are never overwritten")
    pooled, reports = {}, {}
    # Validate every selected case before writing output; collect bounded samples.
    for case in cases:
        series, affine, report = load_case(args.input_root, case, args.allow_partial)
        reports[case["id"]] = report
        print(f"Validated {case['id']}: complete={report['comparison_complete']}; {list(series)}", flush=True)
        for name, array in series.items():
            key = (case["modality"], kind_of(name))
            flat = array.ravel()
            pooled.setdefault(key, []).append(flat[::max(1, (flat.size + 99999) // 100000)].copy())
        del series
    displays = {}
    for modality in {c["modality"] for c in cases}:
        displays[modality] = {}
        for kind in ["scan", "uncertainty", "error"]:
            spec = config["display"][modality][kind]
            limits = spec.get("limits")
            if limits is None:
                values = np.concatenate(pooled[(modality, kind)])
                percentiles = spec.get("percentiles", [0, spec.get("percentile", 99.5)])
                if len(percentiles) != 2 or not 0 <= percentiles[0] <= percentiles[1] <= 100:
                    raise ValueError(f"Invalid {modality} {kind} percentiles")
                lo, hi = [float(v) for v in np.percentile(values, percentiles)]
                if hi <= lo:
                    hi = lo + max(abs(lo) * 1e-6, 1e-6)
                limits = [lo, hi]
            if len(limits) != 2 or not np.isfinite(limits).all() or limits[1] <= limits[0]:
                raise ValueError(f"Invalid {modality} {kind} display limits")
            if spec.get("colormap"):
                colormaps[spec["colormap"]]
            displays[modality][kind] = {**spec, "limits": limits,
                                      "limits_source": "explicit" if spec.get("limits") is not None else "pooled percentiles"}
    if args.check_only:
        print(json.dumps({"display": displays, "reports": reports}, indent=2))
        return
    args.output.mkdir(parents=True)
    entries = []
    for case in cases:
        series, affine, report = load_case(args.input_root, case, args.allow_partial)
        entries.append(export_case(args.output, case, series, affine, report, displays[case["modality"]]))
        del series
    manifest = {"schema_version": 1, "cases": entries, "display": displays,
                "notes": ["Partial cases exclude baseline/follow-up rather than substituting unmatched original scans.",
                          "Error maps are computed before display clipping; partial cases use supplied error volumes."]}
    write_json(args.output / "manifest.json", manifest)
    print(f"Exported {sum(c['png_frames'] for c in entries)} PNG frames to {args.output}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        print(f"Export failed: {error}", file=sys.stderr)
        sys.exit(1)
