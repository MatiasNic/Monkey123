import pytest

from mono.jsonutil import extract_json


def test_fenced_and_inline():
    assert extract_json('blah ```json\n{"a": 1}\n``` blah') == {"a": 1}
    assert extract_json('Respuesta: {"ideas": []} fin') == {"ideas": []}


def test_invalid():
    with pytest.raises(ValueError):
        extract_json("nada por acá")
