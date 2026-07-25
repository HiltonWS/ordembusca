from __future__ import annotations

import hashlib
import sqlite3

import pytest

from ordem.drive import (
    DriveSetupError,
    DriveSync,
    folder_id_from,
    load_drive_config,
    save_drive_config,
)


class FakeDriveSync(DriveSync):
    def __init__(self, folder: str, cache_dir, files: list[dict], payloads: dict[str, bytes]):
        super().__init__(folder, cache_dir=cache_dir)
        self.files = files
        self.payloads = payloads
        self.download_count = 0
        self.remote_database = None
        self.upload_count = 0

    def _list_files(self) -> list[dict]:
        return self.files

    def _download(self, file_id, destination) -> None:
        self.download_count += 1
        destination.write_bytes(self.payloads[file_id])

    def _find_remote_database(self, name: str) -> dict | None:
        return self.remote_database

    def _upload_database_file(self, snapshot, name, remote_id) -> dict:
        snapshot_conn = sqlite3.connect(snapshot)
        try:
            value = snapshot_conn.execute("SELECT value FROM data").fetchone()[0]
            assert value == self.upload_count
        finally:
            snapshot_conn.close()
        self.upload_count += 1
        self.remote_database = {
            "id": remote_id or "database-id",
            "name": name,
            "md5Checksum": self._md5(snapshot),
        }
        return self.remote_database


def test_folder_id_accepts_id_and_url():
    assert folder_id_from("abc_123-XYZ") == "abc_123-XYZ"
    assert folder_id_from("https://drive.google.com/drive/folders/abc_123?usp=sharing") == "abc_123"
    with pytest.raises(DriveSetupError):
        folder_id_from("https://drive.google.com/file/d/abc/view")


def test_drive_config_remembers_folder_and_database_preference(tmp_path):
    config_path = tmp_path / "config.json"
    folder = "https://drive.google.com/drive/folders/abc_123"

    assert load_drive_config(config_path) == {}
    save_drive_config(folder, database_backup=True, path=config_path)

    assert load_drive_config(config_path) == {
        "folder": folder,
        "database_backup": True,
    }


def test_sync_downloads_only_new_or_changed_supported_files(tmp_path):
    first_payload = b"primeira versao"
    files = [
        {
            "id": "book-id",
            "name": "Livro.pdf",
            "mimeType": "application/pdf",
            "modifiedTime": "2026-07-25T10:00:00Z",
            "md5Checksum": hashlib.md5(first_payload, usedforsecurity=False).hexdigest(),
        },
        {"id": "image-id", "name": "capa.png", "mimeType": "image/png"},
    ]
    sync = FakeDriveSync("folder-id", tmp_path / "books", files, {"book-id": first_payload})

    downloaded = sync.sync_once()
    assert [path.name for path in downloaded] == ["Livro.pdf"]
    assert downloaded[0].read_bytes() == first_payload
    assert sync.cached_paths() == downloaded
    assert sync.sync_once() == []
    assert sync.download_count == 1

    second_payload = b"segunda versao"
    files[0]["modifiedTime"] = "2026-07-25T11:00:00Z"
    files[0]["md5Checksum"] = hashlib.md5(
        second_payload, usedforsecurity=False
    ).hexdigest()
    sync.payloads["book-id"] = second_payload

    changed = sync.sync_once()
    assert changed[0].read_bytes() == second_payload
    assert sync.download_count == 2


def test_database_backup_uploads_only_when_snapshot_changes(tmp_path):
    sync = FakeDriveSync("folder-id", tmp_path / "books", [], {})
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE data(value INTEGER)")
    conn.execute("INSERT INTO data VALUES(0)")
    conn.commit()

    assert sync.backup_database(conn, tmp_path / "ordem.db") is True
    assert sync.backup_database(conn, tmp_path / "ordem.db") is False

    conn.execute("UPDATE data SET value=1")
    conn.commit()
    assert sync.backup_database(conn, tmp_path / "ordem.db") is True
    assert sync.upload_count == 2
    assert not (tmp_path / ".ordem.db.upload").exists()
