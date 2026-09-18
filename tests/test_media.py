import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

from marka.config import Settings
from marka.media import ImageInput, MediaStore, image_inputs, validate_image
from marka.queue import Queue
from marka.store import Store
from image_fixtures import JPEG, chunk, png


class ImageValidationTests(unittest.TestCase):
    def test_real_synthetic_png_and_jpeg_keep_exact_bytes_and_dimensions(self):
        for data, mime, dimensions in ((png(), "image/png", (8, 8)), (JPEG, "image/jpeg", (3, 2))):
            with self.subTest(mime=mime):
                result = validate_image(data)
                self.assertEqual(result.data, data)
                self.assertEqual(result.mime_type, mime)
                self.assertEqual((result.width, result.height), dimensions)
                self.assertEqual(result.sha256, hashlib.sha256(data).hexdigest())

    def test_corrupt_truncated_wrong_format_and_size_fail(self):
        bad_crc = bytearray(png())
        bad_crc[29] ^= 1
        for data in (b"", b"GIF89a", b"<svg/>", b"x" * (2 * 1024 * 1024 + 1), png()[:-1], bytes(bad_crc), JPEG[:-2], JPEG + b"extra"):
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                validate_image(data)

    def test_dimension_and_decompression_bombs_fail_before_unbounded_allocation(self):
        for data in (png(4097, 1, raw=b"x"), png(3000, 3000, raw=b"x"), png(1, 1, raw=b"x" * 1000000)):
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                validate_image(data)
        huge_jpeg = JPEG.replace(b"\xff\xc0\x00\x11\x08\x00\x02\x00\x03", b"\xff\xc0\x00\x11\x08\xff\xff\xff\xff")
        with self.assertRaisesRegex(ValueError, "dimensions"):
            validate_image(huge_jpeg)

    def test_jpeg_plausible_markers_without_valid_pixel_stream_are_rejected(self):
        # Complete dimensions, scan, and EOI still do not make a valid JPEG.
        forged = bytes.fromhex("ffd8ffc0000b080001000101011100ffda0008010100003f0000ffd9")
        with self.assertRaisesRegex(ValueError, "pixel data"):
            validate_image(forged)

    def test_real_progressive_jpeg_decodes_but_truncated_pixel_stream_does_not(self):
        buffer = io.BytesIO()
        with Image.new("RGB", (128, 64), (240, 20, 20)) as picture:
            picture.save(buffer, format="JPEG", progressive=True)
        data = buffer.getvalue()
        self.assertEqual(validate_image(data).width, 128)
        with self.assertRaises(ValueError):
            validate_image(data[:-15] + b"\xff\xd9")

    def test_animated_interlaced_invalid_filters_and_extra_compressed_stream_rejected(self):
        animated = png()[:33] + chunk(b"acTL", b"\0" * 8) + png()[33:]
        for data in (animated, png(interlace=1), png(1, 1, raw=b"\x05\0\0\0")):
            with self.assertRaises(ValueError):
                validate_image(data)

    def test_provider_contract_rejects_paths_forged_metadata_and_excess_count(self):
        image = validate_image(png())
        self.assertEqual(image_inputs([image, image]), (image, image))
        for inputs in ((Path("secret.png"),), ("secret.png",), (b"bytes",), [image] * 3,
                       [ImageInput(image.data, image.mime_type, "0" * 64, 8, 8)]):
            with self.assertRaises(ValueError):
                image_inputs(inputs)


class MediaStorageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.settings = Settings(Path(temporary.name))
        self.settings.prepare()
        self.store = Store(self.settings.database)
        self.queue = Queue(self.settings.database)
        self.media = MediaStore(self.settings, self.store)
        self.image = validate_image(png())

    def test_durable_source_precedes_job_and_recovers_after_restart_without_workspace_copy(self):
        receipt = self.media.save("telegram:1", 17, "What is here?", [self.image])
        identifier = self.queue.enqueue("Look", 17, source="telegram:1", kind="image")
        restored = MediaStore(self.settings, self.store).for_job(identifier)
        self.assertEqual(restored, receipt)
        self.assertEqual(list(self.settings.workspace.iterdir()), [])
        self.assertEqual(restored["images"][0].data, self.image.data)
        self.assertEqual(self.store.stats()["memories"], 0)

    def test_duplicate_source_is_immutable_and_does_not_overwrite(self):
        self.media.save("telegram:1", 17, "original", [self.image])
        self.media.save("telegram:1", 17, "original", [self.image])
        self.assertEqual(len(list(self.media.root.iterdir())), 1)
        with self.assertRaises(ValueError):
            self.media.save("telegram:1", 17, "changed", [self.image])
        with self.assertRaises(ValueError):
            self.media.get("telegram:1", 99)

    def test_missing_receipt_file_or_modified_hash_never_silently_becomes_text_only(self):
        identifier = self.queue.enqueue("Look", 17, source="telegram:1", kind="image")
        with self.assertRaisesRegex(ValueError, "receipt"):
            self.media.for_job(identifier)
        self.media.save("telegram:1", 17, "", [self.image])
        path = self.media.root / (self.image.sha256 + ".png")
        path.chmod(0o600)
        path.write_bytes(png(colour=(0, 255, 0)))
        with self.assertRaisesRegex(ValueError, "changed"):
            self.media.for_job(identifier)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            self.media.for_job(identifier)

    def test_text_and_scheduled_jobs_do_not_inherit_image_bytes(self):
        self.media.save("telegram:1", 17, "", [self.image])
        identifier = self.queue.enqueue("ordinary text", 17, source="telegram:1", kind="chat")
        self.assertIsNone(self.media.for_job(identifier))
        unrelated = self.queue.enqueue("another task", 17, source="telegram:2")
        self.assertIsNone(self.media.for_job(unrelated))

    def test_interrupted_atomic_file_write_leaves_no_partial_canonical_blob(self):
        with patch("marka.media.os.fsync", side_effect=OSError("synthetic interruption")):
            with self.assertRaises(OSError):
                self.media.save("telegram:1", 17, "", [self.image])
        self.assertEqual(list(self.media.root.iterdir()), [])
        self.assertIsNone(self.media.get("telegram:1", 17))
        self.assertIsNotNone(self.media.save("telegram:1", 17, "", [self.image]))

    def test_library_symlink_is_rejected(self):
        outside = self.settings.data_dir / "outside"
        self.media.root.rename(outside)
        try:
            self.media.root.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            if getattr(exc, "winerror", None) == 1314:
                self.skipTest("Windows symlink privilege is unavailable")
            raise
        with self.assertRaisesRegex(ValueError, "symlink|unsafe"):
            self.media.save("telegram:1", 17, "", [self.image])

    def test_canonical_blob_replaced_with_symlink_is_not_followed(self):
        self.media.save("telegram:1", 17, "", [self.image])
        canonical = self.media.root / (self.image.sha256 + ".png")
        outside = self.settings.data_dir / "outside.png"
        outside.write_bytes(self.image.data)
        canonical.chmod(0o600)
        canonical.unlink()
        try:
            canonical.symlink_to(outside)
        except OSError as exc:
            if getattr(exc, "winerror", None) == 1314:
                self.skipTest("Windows symlink privilege is unavailable")
            raise
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.media.get("telegram:1", 17)
