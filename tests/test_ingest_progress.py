from ingest import print_drive_progress


def test_drive_progress_shows_file_count_percentage_and_bytes(capsys):
    print_drive_progress({
        "stage": "download_progress",
        "index": 2,
        "total": 5,
        "name": "Livro.pdf",
        "downloaded": 5 * 1024 * 1024,
        "byte_total": 10 * 1024 * 1024,
    })

    output = capsys.readouterr().out
    assert "[Drive 2/5] Livro.pdf" in output
    assert "50.0%" in output
    assert "5.0 MB/10.0 MB" in output
