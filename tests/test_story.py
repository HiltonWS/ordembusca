import json

from ordem.story import StoryBoard
from ordem.story_images import StoryIllustrator


def test_storyboard_reads_transcript_and_keeps_only_recent_scenes(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        "\n".join(
            json.dumps({"text": f"fala {index}", "start_s": index * 21,
                        "detections": []})
            for index in range(4)
        ),
        encoding="utf-8",
    )
    board = StoryBoard(max_scenes=2)

    assert board.load_jsonl(transcript) == 4
    assert [scene["text"] for scene in board.to_json()] == ["fala 2", "fala 3"]


def test_storyboard_renews_same_moment_and_generated_image(tmp_path):
    illustrator = StoryIllustrator(tmp_path)
    board = StoryBoard(moment_seconds=20, illustrator=illustrator)
    first = board.add_event({
        "start_s": 10,
        "text": "o ocultista prepara o ritual",
        "detections": [],
    })
    second = board.add_event({
        "start_s": 16,
        "text": "conjura Sopro do Caos contra o inimigo",
        "detections": [{
            "term": "Sopro do Caos", "category": "ritual", "elemento": "Energia",
        }],
    })

    assert first is second
    assert len(board.to_json()) == 1
    assert second["revision"] == 2
    assert second["primary_category"] == "ritual"
    assert "prepara o ritual conjura Sopro do Caos" in second["text"]
    assert second["thumbnail"].endswith("story-1-2.png?v=2")
    assert not (tmp_path / "story-1-1.png").exists()
    assert (tmp_path / "story-1-2.png").exists()


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
