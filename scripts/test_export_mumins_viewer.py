"""Synthetic checks for orientation, target validation, and uncertainty units."""
import json
from pathlib import Path
import tempfile
import unittest

import nibabel as nib
import numpy as np
from PIL import Image

import export_mumins_viewer as exporter


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def nifti(self, name, array, affine):
        nib.save(nib.Nifti1Image(np.array(array, dtype=np.float32), affine), self.root / name)

    def prediction(self, image, error=None):
        np.save(self.root / "prediction.npy", image[None, None])
        variance = np.stack([np.full_like(image, 0.36), np.full_like(image, 0.01)])[None]
        np.save(self.root / "variance.npy", variance)
        result = {"image": {"path": "prediction.npy", "select": [0, 0]},
                  "uncertainty": {"path": "variance.npy", "select": [0, 1]},
                  "uncertainty_kind": "variance", "residual_scale": 2}
        if error is not None:
            np.save(self.root / "error.npy", error[None, None])
            result["saved_error"] = {"path": "error.npy", "select": [0, 0]}
        return result

    def test_ct_landmarks_error_check_and_png_export(self):
        # A non-cubic, asymmetric volume exposes swaps/flips hidden by cubes.
        raw = np.arange(6 * 5 * 4, dtype=np.float32).reshape(6, 5, 4) * 10 - 1100
        affine = np.diag([-1.2, -1.3, 1.4, 1])
        self.nifti("baseline.nii", raw - 9, affine)
        self.nifti("followup.nii", raw, affine)
        target = np.clip((raw + 1200) / 900 - 1, -1, 1).transpose(2, 1, 0)
        pred = target + 0.05
        setting = self.prediction(pred, np.abs(pred - target))
        case = {"id": "ct", "modality": "CT", "profile": "ngp", "prediction_axes": "zyx",
                "baseline": "baseline.nii", "followup": "followup.nii", "predictions": {"0": setting}}
        series, out_affine, report = exporter.load_case(self.root, case)
        expected = pred.transpose(2, 1, 0)[::-1, ::-1, :]
        np.testing.assert_allclose(series["prediction_0"], expected)
        self.assertEqual(tuple(nib.aff2axcodes(out_affine)), ("R", "A", "S"))
        np.testing.assert_allclose(series["uncertainty_0"], 0.2)
        np.testing.assert_allclose(series["error_0"], 0.05, atol=1e-6)
        axial = exporter.get_slice(expected, "axial", 2)
        self.assertEqual(axial[0, 0], expected[-1, -1, 2])
        self.assertEqual(axial[-1, -1], expected[0, 0, 2])
        self.assertTrue(report["comparison_complete"])
        display = {"scan": {"limits": [-1, 1]}, "uncertainty": {"limits": [0, .4], "colormap": "magma"},
                   "error": {"limits": [0, .1], "colormap": "viridis"}}
        entry = exporter.export_case(self.root, case, series, out_affine, report, display)
        self.assertEqual(entry["png_frames"], (6 + 5 + 4) * 5)
        files = list((self.root / "ct").glob("*/*/*.png"))
        self.assertEqual(len(files), entry["png_frames"])
        with Image.open(self.root / "ct/axial/prediction_0/002.png") as image:
            self.assertEqual(image.size, (6, 5))
        metadata = json.loads((self.root / "ct/metadata.json").read_text())
        self.assertEqual(metadata["planes"]["sagittal"]["frames"], 6)
        self.assertNotIn(str(self.root), json.dumps(metadata))
        # Incorrect preprocessing must fail, rather than exporting a false target.
        np.save(self.root / "error.npy", np.zeros_like(pred)[None, None])
        with self.assertRaisesRegex(ValueError, "does not match supplied error"):
            exporter.load_case(self.root, case)

    def test_mri_partial_is_explicit_and_mask_profile_resizes_correctly(self):
        x, y, z = np.indices((4, 6, 4), dtype=np.float32)
        ramp = x + 2*y + 3*z
        affine = np.diag([1.5, 1.5, 1.5, 1])
        self.nifti("baseline.nii", ramp - 1, affine)
        self.nifti("followup.nii", ramp, affine)
        setting = self.prediction(np.zeros((8, 8, 8), np.float32))
        case = {"id": "mri", "modality": "MRI", "profile": "oasis", "prediction_axes": "xyz",
                "baseline": "baseline.nii", "followup": "followup.nii", "predictions": {"0": setting}}
        with self.assertRaisesRegex(ValueError, "baseline/follow-up pending"):
            exporter.load_case(self.root, case)
        series, _, report = exporter.load_case(self.root, case, allow_partial=True)
        self.assertFalse(report["comparison_complete"])
        self.assertNotIn("followup", series)
        self.nifti("mask.nii", np.ones_like(ramp), affine)
        case["brain_masks"] = {"baseline": "mask.nii", "followup": "mask.nii"}
        series, _, report = exporter.load_case(self.root, case)
        # Half-pixel resize location for output [2,3,2], including symmetric pad:
        # original coordinates (.7, 2.125, .7), whose ramp value is 7.05.
        expected = (7.05 + 88) / 113 * 2 - 1
        self.assertAlmostEqual(float(series["followup"][2, 3, 2]), expected, places=5)
        self.assertEqual(series["followup"][0, 0, 0], -1)
        self.assertTrue(report["comparison_complete"])

    def test_display_mapping_is_fixed_and_finite_data_required(self):
        array = np.array([[0, .5, 1]], dtype=np.float32)
        image = np.asarray(exporter.render(array, [0, 1]))
        np.testing.assert_array_equal(image, [[0, 128, 255]])
        with self.assertRaisesRegex(ValueError, "finite 3D"):
            exporter.finite(np.full((2, 2, 2), np.nan), "test")


if __name__ == "__main__":
    unittest.main()
