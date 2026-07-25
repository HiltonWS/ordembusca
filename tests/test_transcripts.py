import json

from ordem.transcripts import TranscriptStore


def test_transcript_store_writes_jsonl_and_review_markdown(tmp_path):
    store = TranscriptStore(tmp_path, session_id="session-test")
    store.append(
        {
            "text": "faz Fortitude DT 15 para não ficar fatigado",
            "start_s": 65.2,
            "duration_s": 2.4,
            "detections": [{"term": "Fatigado", "score": 100.0}],
        },
        origin="audio",
    )

    records = [
        json.loads(line)
        for line in store.jsonl_path.read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["origin"] == "audio"
    assert records[0]["review"]["status"] == "pending"
    assert records[0]["text"] == "faz Fortitude DT 15 para não ficar fatigado"

    report = store.markdown_path.read_text(encoding="utf-8")
    assert "01:05" in report
    assert "erro de transcrição" in report
    assert "Correção sugerida" in report


def test_transcript_store_ignores_empty_events(tmp_path):
    store = TranscriptStore(tmp_path, session_id="empty")
    store.append({"text": "", "detections": []}, origin="audio")
    assert not store.jsonl_path.exists()
