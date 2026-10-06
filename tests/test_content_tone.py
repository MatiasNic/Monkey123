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
