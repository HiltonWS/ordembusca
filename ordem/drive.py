"""Sincronização incremental de livros de uma pasta privada do Google Drive."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
SUPPORTED = {".pdf", ".txt", ".md", ".docx"}
FOLDER_MIME = "application/vnd.google-apps.folder"


class DriveSetupError(RuntimeError):
    """Configuração ou dependência necessária para o Drive está ausente."""


def folder_id_from(value: str) -> str:
    """Aceita um ID ou uma URL de pasta do Google Drive."""
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme:
        match = re.search(r"/folders/([^/?]+)", parsed.path)
        if not match:
            raise DriveSetupError("URL do Drive inválida: use o link de uma pasta")
        value = match.group(1)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise DriveSetupError("ID da pasta do Drive inválido")
    return value


class DriveSync:
    def __init__(
        self,
        folder: str,
        cache_dir: str | Path = ".ordem-drive/books",
        credentials_path: str | Path = "credentials.json",
        token_path: str | Path = ".ordem-drive/token.json",
        service=None,
    ):
        self.folder_id = folder_id_from(folder)
        self.cache_dir = Path(cache_dir)
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self.state_path = self.cache_dir.parent / "state.json"
        self._service = service

    def _get_service(self):
        if self._service is not None:
            return self._service
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise DriveSetupError(
                "dependências do Google Drive ausentes; execute pip install -r requirements.txt"
            ) from exc

        credentials = None
        if self.token_path.exists():
            credentials = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                if not self.credentials_path.exists():
                    raise DriveSetupError(
                        f"credenciais OAuth não encontradas: {self.credentials_path}"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), SCOPES
                )
                credentials = flow.run_local_server(port=0)
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(credentials.to_json(), encoding="utf-8")

        self._service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        return self._service

    def _list_files(self) -> list[dict]:
        service = self._get_service()
        files = []
        page_token = None
        while True:
            response = service.files().list(
                q=f"'{self.folder_id}' in parents and trashed = false",
                fields="nextPageToken, files(id,name,mimeType,modifiedTime,md5Checksum)",
                pageToken=page_token,
                spaces="drive",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
            files.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                return files

    def _download(self, file_id: str, destination: Path) -> None:
        try:
            from googleapiclient.http import MediaIoBaseDownload
        except ImportError as exc:
            raise DriveSetupError(
                "dependências do Google Drive ausentes; execute pip install -r requirements.txt"
            ) from exc

        request = self._get_service().files().get_media(
            fileId=file_id, supportsAllDrives=True
        )
        with destination.open("wb") as stream:
            downloader = MediaIoBaseDownload(stream, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

    def _load_state(self) -> dict[str, dict]:
        if not self.state_path.exists():
            return {}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def cached_paths(self) -> list[Path]:
        """Lista downloads válidos para recuperar uma ingestão interrompida."""
        if not self.cache_dir.exists():
            return []
        return sorted(
            path for path in self.cache_dir.glob("*/*")
            if path.is_file() and path.suffix.lower() in SUPPORTED
        )

    @staticmethod
    def _md5(path: Path) -> str:
        digest = hashlib.md5(usedforsecurity=False)
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def sync_once(self) -> list[Path]:
        """Baixa arquivos novos/alterados e devolve seus caminhos locais."""
        state = self._load_state()
        downloaded = []
        for remote in self._list_files():
            name = Path(remote.get("name", "")).name
            if remote.get("mimeType") == FOLDER_MIME or Path(name).suffix.lower() not in SUPPORTED:
                continue

            file_id = remote["id"]
            fingerprint = {
                "name": name,
                "modifiedTime": remote.get("modifiedTime"),
                "md5Checksum": remote.get("md5Checksum"),
            }
            target_dir = self.cache_dir / file_id
            target = target_dir / name
            if state.get(file_id) == fingerprint and target.exists():
                continue

            target_dir.mkdir(parents=True, exist_ok=True)
            temporary = target_dir / f".{name}.part"
            self._download(file_id, temporary)
            if remote.get("md5Checksum"):
                if self._md5(temporary) != remote["md5Checksum"]:
                    temporary.unlink(missing_ok=True)
                    raise OSError(f"download incompleto ou corrompido: {name}")
            for old_file in target_dir.iterdir():
                if old_file != temporary:
                    old_file.unlink()
            temporary.replace(target)
            state[file_id] = fingerprint
            downloaded.append(target)

        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return downloaded
