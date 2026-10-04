from mono.ideation.dedup import Deduper

BASE = {"concept": "reading the paper", "location": "balcony", "activity": "reading the newspaper",
        "pose": "sitting on the floor", "outfit": "white tee and baggy jeans", "lighting": "hard midday sun",
        "camera_look": "35mm_kodak_portra", "description": "The macaque reads the newspaper on a sunny balcony."}


def test_rejects_near_duplicate_of_history():
    near = dict(BASE, id="new", lighting="golden hour",
                description="The macaque reads the newspaper on a sunny balcony at golden hour.")
    verdict = Deduper([dict(BASE, id="old")]).check(near, [])
    assert not verdict.ok


def test_accepts_genuinely_different_idea():
    other = {"concept": "laundromat", "location": "laundromat", "activity": "doing laundry", "pose": "on a stool",
             "outfit": "oversized hoodie", "lighting": "fluorescent interior", "camera_look": "compacta_digital_2005",
             "description": "Waiting for the dryer in a laundromat at night, legs dangling from a plastic stool."}
    assert Deduper([BASE]).check(other, []).ok


def test_rejects_same_activity_within_batch_but_allows_in_carousel():
    second = dict(BASE, concept="paper again", location="café", pose="legs crossed", outfit="tracksuit",
                  lighting="overcast flat light", camera_look="bw_tri_x",
                  description="In a café, flipping through the sports pages with a cortado.")
    d = Deduper([])
    assert not d.check(second, [BASE]).ok
    slide = dict(BASE, activity="drinking coffee", pose="leaning against something", concept="coffee break",
                 description="Same outing, now sipping an iced coffee by the railing.")
    assert d.check(slide, [BASE], carousel=True).ok


def test_select_respects_count():
    ideas = [dict(BASE, concept=f"c{i}", activity=f"a{i}", location=f"l{i}", pose=f"p{i}", outfit=f"o{i}",
                  description=f"unique scene number {i} with word{i} and thing{i}") for i in range(6)]
    picked, _ = Deduper([]).select(ideas, 3)
    assert len(picked) == 3
