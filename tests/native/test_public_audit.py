"""Documentation PNGs must not become a general media/metadata audit bypass."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("public_audit", Path(__file__).parents[2] / "tools/audit_public.py")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class DocumentationImageAuditTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.patch = patch.object(audit, "ROOT", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.path = self.root / "docs/images/workout.png"
        self.path.parent.mkdir(parents=True)
        self.png = (Path(__file__).parents[2] / "docs/images/workout.png").read_bytes()
        self.approve(self.png)

    def approve(self, content):
        self.path.write_bytes(content)
        manifest = {"images": {"docs/images/workout.png": {
            "sha256": hashlib.sha256(content).hexdigest(), "width": 1280, "height": 800,
            "kind": "synthetic-native-lvgl-desktop-render"}}}
        (self.path.parent / "manifest.json").write_text(json.dumps(manifest))

    def test_exact_reviewed_png_passes(self):
        self.assertEqual(audit.audit([self.path]), [])

    def test_unreviewed_image_hash_fails(self):
        self.path.write_bytes(self.png + b"private bytes")
        self.assertTrue(audit.audit([self.path]))

    def test_even_hash_approved_metadata_and_trailing_payload_fail(self):
        for content in [self.png + b"private payload", self.png[:-12] +
                        struct.pack(">I", 12) + b"tEXt" + b"secret=value" + b"0000" + self.png[-12:]]:
            self.approve(content)
            self.assertTrue(audit.audit([self.path]))

    def test_unlisted_image_and_firmware_still_fail(self):
        for name in ["exercise.png", "firmware.bin", "photo.jpg"]:
            path = self.root / name
            path.write_bytes(self.png)
            self.assertTrue(audit.audit([path]))


if __name__ == "__main__":
    unittest.main()
