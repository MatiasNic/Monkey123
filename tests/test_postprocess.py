import numpy as np
import pytest
from PIL import Image

from mono.postprocess.looks import MAX_BYTES, crop_to_aspect, process


@pytest.fixture
def photo(tmp_path):
    rng = np.random.default_rng(0)
    arr = (rng.random((1280, 1024, 3)) * 80 + np.linspace(60, 180, 1024)[None, :, None]).astype(np.uint8)
    path = tmp_path / "raw.png"
    img = Image.fromarray(arr)
    exif = Image.Exif()
    exif[0x010F] = "FakeCam"
    img.save(path, exif=exif)
    return path


@pytest.mark.parametrize("size", [(1080, 1350), (1080, 1920)])
def test_process_outputs_clean_jpeg_at_format_size(settings, photo, tmp_path, size):
    for name, look in settings.bible["camera_looks"].items():
        out = process(photo, tmp_path / f"{name}.jpg", size, look["post"], seed=3)
        with Image.open(out) as img:
            assert img.format == "JPEG"
            assert img.size == size
            assert img.mode == "RGB"
            assert not img.info.get("exif")
        assert out.stat().st_size <= MAX_BYTES


def test_crop_keeps_target_ratio():
    img = Image.new("RGB", (1920, 1080))
    assert crop_to_aspect(img, 1080, 1350).size == (1080, 1350)


def test_look_changes_pixels_and_is_deterministic(settings, photo, tmp_path):
    look = settings.bible["camera_looks"]["35mm_kodak_portra"]["post"]
    a = process(photo, tmp_path / "a.jpg", (1080, 1350), look, seed=1)
    b = process(photo, tmp_path / "b.jpg", (1080, 1350), look, seed=1)
    assert a.read_bytes() == b.read_bytes()
    plain = np.asarray(crop_to_aspect(Image.open(photo).convert("RGB"), 1080, 1350), dtype=float)
    assert np.abs(np.asarray(Image.open(a), dtype=float) - plain).mean() > 2
