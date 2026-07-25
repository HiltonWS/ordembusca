from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from ordem.drive import (
    DriveSetupError,
    DriveSync,
    folder_access_from,
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
        self.downloads = []
        self.remote_database = None
        self.upload_count = 0

    def _validate_folder(self) -> None:
        pass

    def _list_files(self) -> list[dict]:
        return self.files

    def _download(self, file_id, destination, export_mime=None, resource_key=None) -> None:
        self.download_count += 1
        self.downloads.append((file_id, destination.name, export_mime, resource_key))
        destination.write_bytes(self.payloads[file_id])

    def _resolve_shortcut(self, remote: dict) -> dict:
        return remote["resolved"]

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


def test_folder_link_preserves_resource_key():
    folder_id, resource_key = folder_access_from(
        "https://drive.google.com/drive/folders/abc_123?resourcekey=key-456&usp=sharing"
    )
    assert folder_id == "abc_123"
    assert resource_key == "key-456"

    class Request:
        headers = {}

        def execute(self):
            return {"ok": True}

    sync = DriveSync(
        "https://drive.google.com/drive/folders/abc_123?resourcekey=key-456"
    )
    request = Request()
    assert sync._execute_folder_request(request) == {"ok": True}
    assert request.headers["X-Goog-Drive-Resource-Keys"] == "abc_123/key-456"


def test_validate_folder_explains_missing_access():
    class MissingRequest:
        def execute(self):
            error = RuntimeError("not found")
            error.resp = type("Response", (), {"status": 404})()
            raise error

    class MissingFiles:
        def get(self, **kwargs):
            return MissingRequest()

    class MissingService:
        def files(self):
            return MissingFiles()

    sync = DriveSync("folder-id", service=MissingService())
    with pytest.raises(DriveSetupError, match="sem acesso para a conta autorizada"):
        sync._validate_folder()


def test_list_files_recurses_into_subfolders_and_folder_shortcuts():
    folder_mime = "application/vnd.google-apps.folder"
    shortcut_mime = "application/vnd.google-apps.shortcut"
    contents = {
        "root": [
            {"id": "root-file", "name": "Raiz.pdf", "mimeType": "application/pdf"},
            {"id": "child", "name": "Livros", "mimeType": folder_mime},
            {
                "id": "folder-link",
                "name": "Homebrews",
                "mimeType": shortcut_mime,
                "shortcutDetails": {
                    "targetId": "linked-folder",
                    "targetMimeType": folder_mime,
                    "targetResourceKey": "linked-key",
                },
            },
        ],
        "child": [
            {"id": "child-file", "name": "Livro.pdf", "mimeType": "application/pdf"}
        ],
        "linked-folder": [
            {"id": "linked-file", "name": "Casa.docx", "mimeType": "application/docx"}
        ],
    }

    class Request:
        def __init__(self, response):
            self.response = response
            self.headers = {}

        def execute(self):
            return self.response

    class Files:
        def list(self, q, **kwargs):
            folder_id = q.split("'")[1]
            return Request({"files": contents[folder_id]})

    class Service:
        def files(self):
            return Files()

    sync = DriveSync("root", service=Service())
    sync._folder_validated = True

    assert [item["id"] for item in sync._list_files()] == [
        "root-file", "child-file", "linked-file"
    ]


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


def test_sync_exports_native_google_document_as_docx(tmp_path):
    files = [
        {
            "id": "document-id",
            "name": "Anotações da campanha",
            "mimeType": "application/vnd.google-apps.document",
            "modifiedTime": "2026-07-25T12:00:00Z",
        },
        {
            "id": "sheet-id",
            "name": "Tabela",
            "mimeType": "application/vnd.google-apps.spreadsheet",
            "modifiedTime": "2026-07-25T12:00:00Z",
        },
    ]
    sync = FakeDriveSync(
        "folder-id",
        tmp_path / "books",
        files,
        {"document-id": b"docx exportado"},
    )

    downloaded = sync.sync_once()

    assert [path.name for path in downloaded] == ["Anotações da campanha.docx"]
    assert sync.downloads == [
        (
            "document-id",
            ".Anotações da campanha.docx.part",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            None,
        )
    ]


def test_sync_resolves_shortcut_to_binary_target(tmp_path):
    files = [
        {
            "id": "shortcut-id",
            "name": "Livro.pdf",
            "mimeType": "application/vnd.google-apps.shortcut",
            "resolved": {
                "id": "target-id",
                "name": "Livro.pdf",
                "mimeType": "application/pdf",
                "modifiedTime": "2026-07-25T13:00:00Z",
                "md5Checksum": hashlib.md5(b"pdf", usedforsecurity=False).hexdigest(),
                "resourceKey": "target-key",
            },
        }
    ]
    sync = FakeDriveSync(
        "folder-id",
        tmp_path / "books",
        files,
        {"target-id": b"pdf"},
    )

    downloaded = sync.sync_once()

    assert [path.name for path in downloaded] == ["Livro.pdf"]
    assert downloaded[0].parent.name == "shortcut-id"
    assert "shortcut-id" in sync._load_state()
    assert "target-id" not in sync._load_state()
    assert sync.downloads == [
        ("target-id", ".Livro.pdf.part", None, "target-key")
    ]

    state = sync._load_state()
    state["target-id"] = state["shortcut-id"]
    sync.state_path.write_text(json.dumps(state), encoding="utf-8")
    assert sync.sync_once() == []
    assert "target-id" not in sync._load_state()


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
