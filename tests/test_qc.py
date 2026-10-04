from PIL import Image

from mono.llm.mock import MockLLM
from mono.qc.heuristics import check_image
from mono.qc.vision_qc import evaluate


def _grid(settings, tmp_path, rows, cols, gutter=0):
    refs = settings.reference_images()
    w, h = 1080, 1350
    canvas = Image.new("RGB", (w, h), "white")
    cw, ch = w // cols, h // rows
    for r in range(rows):
        for c in range(cols):
            tile = Image.open(refs[(r + c) % len(refs)]).convert("RGB").resize((cw - 2 * gutter, ch - 2 * gutter))
            canvas.paste(tile, (c * cw + gutter, r * ch + gutter))
    path = tmp_path / f"grid_{rows}x{cols}_{gutter}.jpg"
    canvas.save(path)
    return path


def test_real_photos_are_not_flagged(settings):
    for ref in settings.reference_images():
        assert check_image(ref).ok, ref


def test_collages_are_flagged(settings, tmp_path):
    for rows, cols, gutter in [(2, 2, 6), (1, 2, 0), (2, 1, 0), (3, 3, 0)]:
        report = check_image(_grid(settings, tmp_path, rows, cols, gutter))
        assert not report.ok, (rows, cols, gutter)


def test_blank_image_flagged(tmp_path):
    path = tmp_path / "blank.png"
    Image.new("RGB", (1080, 1350), (120, 120, 120)).save(path)
    assert not check_image(path).ok


class StrictLLM(MockLLM):
    def _qc(self, ctx):
        return {"score": 9, "species_ok": False, "is_collage": False, "has_text": False, "reasons": ["chimpancé"]}


def test_vision_qc_hard_fail_on_species(settings):
    ref = settings.reference_images()[0]
    assert evaluate(settings, MockLLM(settings), ref, {"description": "x"}).passed
    result = evaluate(settings, StrictLLM(settings), ref, {"description": "x"})
    assert not result.passed
    assert "species" in result.reasons[0]
