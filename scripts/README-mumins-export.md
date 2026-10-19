# MUMINS slice exporter

`export_mumins_viewer.py` reads the cases in `mumins_export_cases.json` and
exports native-resolution PNG frames plus a manifest and per-case metadata.
It does not change the input volumes or publish anything to the website.

## Run

```bash
python3 -m venv /tmp/mumins-export-venv
/tmp/mumins-export-venv/bin/python -m pip install -r scripts/requirements-mumins-export.txt
/tmp/mumins-export-venv/bin/python scripts/export_mumins_viewer.py \
  --input-root /home/anna.oliveras@local.eurecat.org/Downloads/MUMINS_images \
  --output /home/anna.oliveras@local.eurecat.org/Documents/mumins-viewer-complete
```

Choose an output directory that does not exist. The exporter never deletes or
overwrites an existing export. `--case ct_01` selects only the complete CT case;
`--check-only` validates inputs and reports limits without exporting images.

The current files supply one prediction per case, both confirmed as Δb = 0.
No GT-oracle prediction is invented. Add a `gt` entry under `predictions` when
corresponding image/uncertainty/error volumes become available. All cases of a
modality share the display limits established by the first validation pass.
Uncertainty uses pooled 0.5th/99.5th percentiles to show variation above the
common uncertainty floor; error uses the 0th/99.5th percentiles. Actual numeric
limits and chosen percentiles are recorded, and values outside these display
limits are clipped for PNG rendering only. Change `limits` to fix them manually.

## MRI preprocessing

Both source MRI NIfTI headers specify 122 × 146 × 122 voxels at 1.5 mm.
The predictions are saved as 1 × 1 × 128 × 128 × 128 arrays. The OASIS model
pipeline fills the background using the original brain segmentation, resizes
the longest edge to 128 (107 × 128 × 107), and pads to 128³. Its intensity
scope is [-88, 25], mapped to [-1, 1].

The original segmentation files are now configured as
`OASIS/OAS30062_MR_d1134segm.nii.gz` and
`OASIS/OAS30062_MR_d1745segm.nii.gz`. Both have exactly the same shape and
affine as their respective scans. The reconstructed MRI error agrees with
the supplied error volume to a maximum absolute difference of approximately
3.8e-6; the CT check agrees within 1.2e-7. Both cases export all five series
and report `comparison_complete: true`.

For additional cases, set `brain_masks.baseline` and `brain_masks.followup`
to the original NIfTI segmentation files on their exact source scan grids.
Alternatively, set `model_ready` to:

```json
{
  "baseline": {"path": "OASIS/model_baseline.npy", "select": [0, 0]},
  "followup": {"path": "OASIS/model_followup.npy", "select": [0, 0]}
}
```

`select` explicitly removes leading batch/channel axes; use an empty list for
an already 3D array. Prepared MRI arrays must use the model's native XYZ grid
and normalized intensity units. Prepared NIfTI arrays must also have affines
matching the model grid computed from the original scan and profile.
The reconstructed target must reproduce the supplied absolute-error map,
otherwise export fails with a preprocessing mismatch.

For a future case with missing masks, `--allow-partial` exports only the
available prediction, uncertainty, and supplied error. Metadata explicitly
marks missing reference series and sets `comparison_complete: false`.
Without that flag, an incomplete case fails before output is written.

## Orientation and uncertainty

NGP's SimpleITK-based loader produces model arrays in native ZYX order;
OASIS's NiBabel-based loader uses native XYZ. The config specifies this
explicitly. NIfTI affines provide orientation and spacing. Every series is
then reoriented identically to RAS and sliced for radiological display, with
edge labels and physical pixel aspect ratios recorded in metadata. Original
scan dimensions and orientation codes are included without source file paths.

`_var.npy` contains batch × two channels × spatial dimensions. Channel 1 is
the residual variance. The training residual is `(followup - baseline) / 2`,
so follow-up standard deviation is `2 * sqrt(residual_variance)`. The explicit
`residual_scale` config records this multiplier; change it if exporting a
different inference convention. A stored standard deviation instead uses
`uncertainty_kind: "std"`. Error is computed before display clipping.

Each case contains axial/coronal/sagittal folders, one folder per available
series, and `000.png` etc. `preview.png` is a labelled contact sheet for QA;
the individual frames have no text or borders. It is a pixel-space thumbnail,
while the viewer should respect the physical aspect ratios in metadata.
Intervals in days come from the source filenames; unknown ages and seeds
remain null. No numeric age or sampling seed is guessed.

## Checks

```bash
/tmp/mumins-export-venv/bin/python -m unittest discover -s scripts -p 'test_export_mumins_viewer.py' -v
```

Checks cover asymmetric spatial landmarks, radiological slice orientation,
residual variance scaling, saved-error mismatch detection, actual PNG export,
MRI resizing/padding, and the explicit partial-export behavior.

## Prepare the portfolio viewers

```bash
MPLCONFIGDIR=/tmp/mumins-mpl-cache /tmp/mumins-export-venv/bin/python \
  scripts/prepare_mumins_web_assets.py \
  /home/anna.oliveras@local.eurecat.org/Documents/mumins-viewer-complete \
  --case ct_01 --case mri_01 --prediction-only-case mri_01 \
  --destination /tmp/mumins-web-review
```

The helper requires explicit case selection, verifies every frame path, and
copies only the selected series. Full comparisons require complete cases.
`--prediction-only-case mri_01` packages just `prediction_0` and
`uncertainty_0` under `mri_01_predicted`: no baseline, observed follow-up,
error images, contact sheets, original scan headers, or error-validation
metadata are copied. Manifest counts and display scales reflect that subset.
It prepares the JavaScript metadata bundle
and exact colormap strips used for the webpage legends. It refuses to
overwrite an existing destination; use a new `--destination` to prepare
an updated bundle for review before replacing existing assets.

`publications/mumins-viewer.js` reads the bundle directly, so static local
page previews work without a fetch-based JSON loader. Each viewer loads
all panel images before displaying a new slice, uses a bounded image cache,
and preloads only two nearby slices. Playback starts only after pressing Play,
and pauses off-screen or when the document is hidden. Reduced-motion changes
also pause playback. Zoom uses the +, −, and Reset buttons, shared across all
panels; hovering, mouse movement, dragging, and wheel/trackpad scrolling do
not change zoom. The plane's physical aspect ratio comes from metadata.
CT and MRI appear beside each other on wide screens. Image panels stay in a
single row; on narrow screens, CT panels scroll horizontally inside the viewer.
The image overlays omit anatomical initial letters; plane choices include
plain-language view descriptions.
The current local website candidate packages all 64 slices per plane for the
CT comparison, plus all 128 slices per plane for MRI prediction and predicted
uncertainty, both at Δb = 0. The MRI source/reference stacks remain outside
the website repository; `/figs/mumins/viewer/mri_01/` is also ignored by Git.
Existing paper figures and quantitative GT-oracle rows remain unchanged.
Preparing this local bundle does not publish it or establish permission to
redistribute patient-conditioned predictions; verify the applicable OASIS
agreement before public release.

## Local central-slice MRI illustration

```bash
python3 scripts/prepare_mumins_central_preview.py \
  /home/anna.oliveras@local.eurecat.org/Documents/mumins-viewer-complete/mri_01 \
  --output /home/anna.oliveras@local.eurecat.org/Documents/mumins-central-slice-preview
```

This copies exactly one central slice per plane across the five series,
producing 15 PNGs, a selection manifest, and a standalone local HTML preview.
It does not copy complete stacks or put the selected images in the website
repository. A smaller selection is not proof of permission to redistribute:
confirm that illustrative use is covered by the applicable OASIS agreement
or written permission before publishing any new OASIS images.
Current terms: https://sites.wustl.edu/oasisbrains/home/access/
