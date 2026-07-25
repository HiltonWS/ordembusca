"""Sincronização incremental de livros de uma pasta privada do Google Drive."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
]
SUPPORTED = {".pdf", ".txt", ".md", ".docx"}
FOLDER_MIME = "application/vnd.google-apps.folder"
SHORTCUT_MIME = "application/vnd.google-apps.shortcut"
DEFAULT_CONFIG_PATH = Path(".ordem-drive/config.json")
GOOGLE_EXPORTS = {
    "application/vnd.google-apps.document": (
        ".docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    "application/vnd.google-apps.presentation": (".pdf", "application/pdf"),
}


class DriveSetupError(RuntimeError):
    """Configuração ou dependência necessária para o Drive está ausente."""


def folder_access_from(value: str) -> tuple[str, str | None]:
    """Extrai ID e resource key de um ID ou link compartilhado de pasta."""
    value = value.strip()
    parsed = urlparse(value)
    resource_key = None
    if parsed.scheme:
        match = re.search(r"/folders/([^/?]+)", parsed.path)
        if not match:
            raise DriveSetupError("URL do Drive inválida: use o link de uma pasta")
        value = match.group(1)
        resource_key = parse_qs(parsed.query).get("resourcekey", [None])[0]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise DriveSetupError("ID da pasta do Drive inválido")
    return value, resource_key


def folder_id_from(value: str) -> str:
    """Aceita um ID ou uma URL de pasta do Google Drive."""
    return folder_access_from(value)[0]


def load_drive_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict:
    config_path = Path(path)
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_drive_config(
    folder: str,
    database_backup: bool = False,
    path: str | Path = DEFAULT_CONFIG_PATH,
) -> None:
    folder_id_from(folder)
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {"folder": folder, "database_backup": database_backup},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


class DriveSync:
    def __init__(
        self,
        folder: str,
        cache_dir: str | Path = ".ordem-drive/books",
        credentials_path: str | Path = "credentials.json",
        token_path: str | Path = ".ordem-drive/token.json",
        service=None,
    ):
        self.folder_id, self.folder_resource_key = folder_access_from(folder)
        self.cache_dir = Path(cache_dir)
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self.state_path = self.cache_dir.parent / "state.json"
        self._service = service
        self._folder_validated = False

    def _execute_folder_request(self, request):
        return self._execute_resource_request(
            request, self.folder_id, self.folder_resource_key
        )

    @staticmethod
    def _execute_resource_request(request, file_id: str, resource_key: str | None):
        if resource_key:
            request.headers["X-Goog-Drive-Resource-Keys"] = (
                f"{file_id}/{resource_key}"
            )
        return request.execute()

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
            if not credentials.has_scopes(SCOPES):
                credentials = None
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

    def _validate_folder(self) -> None:
        if self._folder_validated:
            return
        try:
            request = self._get_service().files().get(
                fileId=self.folder_id,
                fields="id,name,mimeType",
                supportsAllDrives=True,
            )
            folder = self._execute_folder_request(request)
        except Exception as exc:  # noqa: BLE001
            status = getattr(getattr(exc, "resp", None), "status", None)
            if status == 404:
                raise DriveSetupError(
                    "pasta não encontrada ou sem acesso para a conta autorizada. "
                    "Compartilhe a pasta com essa conta ou apague "
                    ".ordem-drive/token.json e autorize a conta correta"
                ) from exc
            raise
        if folder.get("mimeType") != FOLDER_MIME:
            raise DriveSetupError(
                f"o ID configurado pertence a um arquivo, não a uma pasta: {folder.get('name')}"
            )
        self._folder_validated = True

    def _list_files(self) -> list[dict]:
        self._validate_folder()
        service = self._get_service()
        files = []
        page_token = None
        while True:
            request = service.files().list(
                q=f"'{self.folder_id}' in parents and trashed = false",
                fields=(
                    "nextPageToken, files(id,name,mimeType,modifiedTime,md5Checksum,"
                    "shortcutDetails(targetId,targetMimeType,targetResourceKey))"
                ),
                pageToken=page_token,
                spaces="drive",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            response = self._execute_folder_request(request)
            files.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                return files

    def _download(
        self,
        file_id: str,
        destination: Path,
        export_mime: str | None = None,
        resource_key: str | None = None,
    ) -> None:
        try:
            from googleapiclient.http import MediaIoBaseDownload
        except ImportError as exc:
            raise DriveSetupError(
                "dependências do Google Drive ausentes; execute pip install -r requirements.txt"
            ) from exc

        if export_mime:
            request = self._get_service().files().export_media(
                fileId=file_id, mimeType=export_mime
            )
        else:
            request = self._get_service().files().get_media(
                fileId=file_id, supportsAllDrives=True
            )
        if resource_key:
            request.headers["X-Goog-Drive-Resource-Keys"] = f"{file_id}/{resource_key}"
        with destination.open("wb") as stream:
            downloader = MediaIoBaseDownload(stream, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

    def _resolve_shortcut(self, remote: dict) -> dict:
        details = remote.get("shortcutDetails") or {}
        target_id = details.get("targetId")
        if not target_id:
            raise DriveSetupError(f"atalho sem arquivo de destino: {remote.get('name')}")
        resource_key = details.get("targetResourceKey")
        request = self._get_service().files().get(
            fileId=target_id,
            fields="id,name,mimeType,modifiedTime,md5Checksum",
            supportsAllDrives=True,
        )
        target = self._execute_resource_request(request, target_id, resource_key)
        target["name"] = remote.get("name") or target.get("name")
        target["resourceKey"] = resource_key
        return target

    def _find_remote_database(self, name: str) -> dict | None:
        self._validate_folder()
        request = self._get_service().files().list(
            q=(
                f"'{self.folder_id}' in parents and trashed = false and "
                "appProperties has { key='ordemBusca' and value='database' }"
            ),
            fields="files(id,name,md5Checksum)",
            spaces="drive",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        response = self._execute_folder_request(request)
        return next(
            (item for item in response.get("files", []) if item.get("name") == name),
            None,
        )

    def _upload_database_file(
        self,
        snapshot: Path,
        name: str,
        remote_id: str | None,
    ) -> dict:
        try:
            from googleapiclient.http import MediaFileUpload
        except ImportError as exc:
            raise DriveSetupError(
                "dependências do Google Drive ausentes; execute pip install -r requirements.txt"
            ) from exc

        media = MediaFileUpload(
            str(snapshot), mimetype="application/x-sqlite3", resumable=True
        )
        service = self._get_service()
        if remote_id:
            request = service.files().update(
                fileId=remote_id,
                body={"name": name},
                media_body=media,
                fields="id,name,md5Checksum,modifiedTime",
                supportsAllDrives=True,
            )
        else:
            request = service.files().create(
                body={
                    "name": name,
                    "parents": [self.folder_id],
                    "appProperties": {"ordemBusca": "database"},
                },
                media_body=media,
                fields="id,name,md5Checksum,modifiedTime",
                supportsAllDrives=True,
            )
        return request.execute()

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
            cache_id = remote["id"]
            if remote.get("mimeType") == SHORTCUT_MIME:
                remote = self._resolve_shortcut(remote)
            name = Path(remote.get("name", "")).name
            mime_type = remote.get("mimeType", "")
            export = GOOGLE_EXPORTS.get(mime_type)
            if export:
                extension, export_mime = export
                if Path(name).suffix.lower() != extension:
                    name = f"{name}{extension}"
            else:
                export_mime = None
            if mime_type.startswith("application/vnd.google-apps.") and not export:
                continue
            if Path(name).suffix.lower() not in SUPPORTED:
                continue

            file_id = remote["id"]
            fingerprint = {
                "targetId": file_id,
                "name": name,
                "modifiedTime": remote.get("modifiedTime"),
                "md5Checksum": remote.get("md5Checksum"),
            }
            target_dir = self.cache_dir / cache_id
            target = target_dir / name
            if state.get(cache_id) == fingerprint and target.exists():
                if cache_id != file_id:
                    state.pop(file_id, None)
                continue

            target_dir.mkdir(parents=True, exist_ok=True)
            temporary = target_dir / f".{name}.part"
            self._download(
                file_id,
                temporary,
                export_mime=export_mime,
                resource_key=remote.get("resourceKey"),
            )
            if remote.get("md5Checksum"):
                if self._md5(temporary) != remote["md5Checksum"]:
                    temporary.unlink(missing_ok=True)
                    raise OSError(f"download incompleto ou corrompido: {name}")
            for old_file in target_dir.iterdir():
                if old_file != temporary:
                    old_file.unlink()
            temporary.replace(target)
            state[cache_id] = fingerprint
            if cache_id != file_id:
                state.pop(file_id, None)
            downloaded.append(target)

        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return downloaded

    def backup_database(self, conn: sqlite3.Connection, db_path: str | Path) -> bool:
        """Envia um snapshot consistente do SQLite se o conteúdo mudou."""
        name = Path(db_path).name
        snapshot = self.cache_dir.parent / f".{name}.upload"
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot_conn = sqlite3.connect(snapshot)
        try:
            conn.backup(snapshot_conn)
        finally:
            snapshot_conn.close()

        try:
            remote = self._find_remote_database(name)
            checksum = self._md5(snapshot)
            if remote and remote.get("md5Checksum") == checksum:
                return False
            self._upload_database_file(snapshot, name, remote.get("id") if remote else None)
            return True
        finally:
            snapshot.unlink(missing_ok=True)
