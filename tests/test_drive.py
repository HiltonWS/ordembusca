from __future__ import annotations

import hashlib

import pytest

from ordem.drive import DriveSetupError, DriveSync, folder_id_from


class FakeDriveSync(DriveSync):
    def __init__(self, folder: str, cache_dir, files: list[dict], payloads: dict[str, bytes]):
        super().__init__(folder, cache_dir=cache_dir)
        self.files = files
        self.payloads = payloads
        self.download_count = 0

    def _list_files(self) -> list[dict]:
        return self.files

    def _download(self, file_id, destination) -> None:
        self.download_count += 1
        destination.write_bytes(self.payloads[file_id])


def test_folder_id_accepts_id_and_url():
    assert folder_id_from("abc_123-XYZ") == "abc_123-XYZ"
    assert folder_id_from("https://drive.google.com/drive/folders/abc_123?usp=sharing") == "abc_123"
    with pytest.raises(DriveSetupError):
        folder_id_from("https://drive.google.com/file/d/abc/view")


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
