from ordem import db as dbmod
from ordem.chunk import Chunk
from ordem.extract import Page, Source
from ordem.pipeline import Pipeline


def test_condition_question_receives_extended_local_context(tmp_path):
    db_path = tmp_path / "rules.db"
    conn = dbmod.connect(db_path)
    source = Source(
        path=tmp_path / "regras.txt",
        title="Regras",
        sha256="synthetic",
        pages=[Page(1, "Fatigado. O personagem fica fraco e vulnerável.")],
    )
    dbmod.ingest_source(
        conn,
        source,
        [Chunk(source_filename="regras.txt", page=1, section="Condições",
               kind="text", content="Fatigado. O personagem fica fraco e vulnerável.")],
        [],
    )
    conn.close()

    event = Pipeline(str(db_path)).detect_text("o que fatigado dá?")
    fatigado = next(d for d in event.detections if d["term"] == "Fatigado")

    assert "Regras" in fatigado["details"]
    assert "fraco e vulnerável" in fatigado["details"]
