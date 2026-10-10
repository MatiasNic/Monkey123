from mono.ideation.ideas import build_ideation_prompt, generate_ideas
from mono.llm.mock import MockLLM
from mono.prompting.builder import build_image_prompt
from mono.qc.vision_qc import evaluate


class UnsafeLLM(MockLLM):
    def _qc(self, ctx):
        return {"score": 8.5, "species_ok": True, "anatomy": 8, "limb_count_ok": True,
                "brand_safe": False, "reasons": ["objeto blanco ambiguo cerca de la cara"]}


def test_off_tone_photo_is_a_hard_fail(settings):
    ref = settings.reference_images()[0]
    result = evaluate(settings, UnsafeLLM(settings), ref, {"description": "x"})
    assert not result.passed and "tono" in result.reasons[0]


def test_image_prompt_keeps_fur_brown_not_green(settings):
    idea = generate_ideas(settings, MockLLM(settings), 1, update_bank=False)[0]
    prompt = build_image_prompt(settings, idea)["prompt"]
    assert "olive-brown" not in prompt
    assert "never green" in prompt and "green or olive tinted fur" in prompt


def test_ideation_prompt_carries_content_tone(settings):
    prompt = build_ideation_prompt(settings, [], [], 4, "feed", None, None)
    assert "everyday urban life" in prompt and "drugs" in prompt
    assert "$content" not in prompt


def test_qc_prompt_has_no_unfilled_placeholders(settings):
    seen = {}

    class Spy(MockLLM):
        def complete_json(self, prompt, **kw):
            seen["prompt"] = prompt
            return super().complete_json(prompt, **kw)

    evaluate(settings, Spy(settings), settings.reference_images()[0], {"description": "x"})
    assert "brand_safe" in seen["prompt"] and "$content" not in seen["prompt"]


class BabyLLM(MockLLM):
    def _qc(self, ctx):
        return {"score": 8, "species_ok": True, "anatomy": 8, "limb_count_ok": True, "brand_safe": True,
                "identity_match": 4, "reasons": ["parece una cría"]}


def test_low_identity_is_a_hard_fail(settings):
    result = evaluate(settings, BabyLLM(settings), settings.reference_images()[0], {"description": "x"})
    assert not result.passed and "identidad" in result.reasons[0]


def test_bible_describes_an_adult_with_a_clean_look(settings):
    bible = settings.bible
    assert "ADULT" in bible["identity"]["description"]
    assert "young" not in bible["identity"]["description"]
    for look in bible["camera_looks"].values():
        assert look["post"]["grain"] <= 0.01 and look["post"]["flash"] == 0
    assert not any("mirror" in p for p in bible["axes"]["pose"])


def test_publish_test_default_look_exists(settings, repo):
    from typer.testing import CliRunner

    from mono.cli import app

    image = settings.reference_images()[0]
    result = CliRunner().invoke(app, ["publish-test", str(image), "--dry-run"])
    assert result.exit_code == 0, result.output


def test_generator_gets_cropped_references(settings):
    from mono.ideation.ideas import generate_ideas as gen

    idea = gen(settings, MockLLM(settings), 1, update_bank=False)[0]
    refs = build_image_prompt(settings, idea)["references"]
    assert refs and all(r.startswith("character/reference_crops/") for r in refs)
    assert all("reference_crops" not in str(p) for p in settings.reference_images())


def test_prompt_and_references_focus_on_the_face(settings):
    from mono.ideation.ideas import generate_ideas as gen

    idea = gen(settings, MockLLM(settings), 1, update_bank=False)[0]
    built = build_image_prompt(settings, idea)
    assert built["prompt"].startswith("Candid real photograph of the macaque from the input images.")
    assert "heavy half-closed eyelids" in built["prompt"]
    # Las primeras referencias (las que siempre entran, aun con foto de escena) son primeros planos de la cara.
    assert all("cara" in r for r in built["references"][:3])


def test_identity_threshold_is_strict(settings):
    class Close(MockLLM):
        def _qc(self, ctx):
            return {"score": 8, "species_ok": True, "anatomy": 8, "limb_count_ok": True, "brand_safe": True,
                    "identity_match": 6, "reasons": ["la cara se parece pero no es la misma"]}

    assert not evaluate(settings, Close(settings), settings.reference_images()[0], {"description": "x"}).passed
