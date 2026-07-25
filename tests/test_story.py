import json

from ordem.story import StoryBoard


def test_storyboard_reads_transcript_and_keeps_only_recent_scenes(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        "\n".join(
            json.dumps({"text": f"fala {index}", "detections": []})
            for index in range(4)
        ),
        encoding="utf-8",
    )
    board = StoryBoard(max_scenes=2)

    assert board.load_jsonl(transcript) == 4
    assert [scene["text"] for scene in board.to_json()] == ["fala 2", "fala 3"]


def test_storyboard_uses_mechanic_and_thumbnail_to_explain_scene():
    board = StoryBoard()
    scene = board.add_event({
        "start_s": 12,
        "text": "conjuro Sopro do Caos",
        "detections": [{
            "term": "Sopro do Caos",
            "category": "ritual",
            "summary": "Manipula o elemento Energia.",
            "thumbnail": "/thumbnails/sopro.png",
        }],
    })

    assert scene["title"] == "Ritual: Sopro do Caos"
    assert scene["thumbnail"] == "/thumbnails/sopro.png"
    assert (
        scene["mechanics"][0]["summary"]
        == "Manipula o elemento Energia."
    )


def test_storyboard_labels_path_as_path_not_character():
    scene = StoryBoard().add_event({
        "text": "combatente aniquilador",
        "detections": [{"term": "Aniquilador", "category": "trilha"}],
    })

    assert scene["title"] == "Trilha: Aniquilador"
