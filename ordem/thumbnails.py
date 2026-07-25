"""Associação local de artes a termos do léxico e páginas das fontes."""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import fitz

from .extract import normalize_term

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
THUMBNAIL_CATEGORIES = {
    "ritual", "poder", "arma", "item", "armadura", "vestimenta", "acessorio",
    "mascara", "caracteristica",
}


class ThumbnailResolver:
    def __init__(
        self,
        lexicon: list[dict],
        asset_roots: list[str | Path],
        source_roots: list[str | Path],
        cache_dir: str | Path = ".ordem-thumbnails",
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._forms: dict[str, str] = {}
        self._source_files: dict[str, str] = {}
        for entry in lexicon:
            term = entry["term"]
            self._forms[normalize_term(term)] = term
            for alias in entry.get("aliases", []):
                self._forms[normalize_term(alias)] = term
            title = entry.get("title")
            filename = entry.get("filename")
            if title and filename:
                self._source_files[normalize_term(title)] = filename
        self._assets = self._index_assets(asset_roots)
        self._unknown_assets = self._index_unknown_assets(asset_roots)
        self._hash_cache: dict[Path, int | None] = {}
        self._sources = self._index_sources(source_roots)

    def _index_assets(self, roots: list[str | Path]) -> dict[str, Path]:
        assets: dict[str, Path] = {}
        for root_value in roots:
            root = Path(root_value)
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                    canonical = self._forms.get(normalize_term(path.stem))
                    if canonical:
                        assets.setdefault(normalize_term(canonical), path)
        return assets

    def _index_unknown_assets(self, roots: list[str | Path]) -> list[Path]:
        assets = set(self._assets.values())
        return [
            path
            for root_value in roots
            if (root := Path(root_value)).exists()
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in IMAGE_EXTENSIONS
            and not path.name.startswith("story-")
            and path not in assets
        ]

    @staticmethod
    def _index_sources(roots: list[str | Path]) -> dict[str, Path]:
        sources: dict[str, Path] = {}
        for root_value in roots:
            root = Path(root_value)
            if not root.exists():
                continue
            for path in root.rglob("*.pdf"):
                if path.is_file():
                    sources.setdefault(normalize_term(path.name), path)
                    sources.setdefault(normalize_term(path.stem), path)
        return sources

    def resolve(self, detection: dict) -> str | None:
        if detection.get("category") not in THUMBNAIL_CATEGORIES:
            return None
        term = detection.get("term") or ""
        named_asset = self._assets.get(normalize_term(term))
        if named_asset:
            return self._cache_asset(named_asset, term)
        source = detection.get("source")
        page = detection.get("page")
        if not source or not page:
            return None
        filename = self._source_files.get(normalize_term(source), source)
        pdf = self._sources.get(normalize_term(filename))
        if not pdf:
            pdf = self._sources.get(normalize_term(Path(filename).stem))
        if not pdf:
            return None
        page_image = self._extract_page_image(pdf, int(page), term)
        if not page_image:
            return None
        visual_match = self._closest_visual_asset(page_image)
        if visual_match:
            return self._cache_asset(visual_match, term)
        return f"/thumbnails/{page_image.name}"

    def _cache_asset(self, source: Path, term: str) -> str:
        digest = hashlib.sha256(str(source.resolve()).encode()).hexdigest()[:12]
        target = self.cache_dir / f"{normalize_term(term).replace(' ', '-')}-{digest}{source.suffix.lower()}"
        if not target.exists() or source.stat().st_mtime_ns > target.stat().st_mtime_ns:
            shutil.copy2(source, target)
        return f"/thumbnails/{target.name}"

    def _extract_page_image(self, pdf: Path, page_number: int, term: str) -> Path | None:
        key = f"{pdf.resolve()}:{page_number}:{term}"
        digest = hashlib.sha256(key.encode()).hexdigest()[:12]
        existing = next(self.cache_dir.glob(f"book-{digest}.*"), None)
        if existing:
            return existing
        try:
            with fitz.open(pdf) as document:
                if not 1 <= page_number <= document.page_count:
                    return None
                images = document[page_number - 1].get_images(full=True)
                if not images:
                    return None
                image = max(images, key=lambda item: item[2] * item[3])
                extracted = document.extract_image(image[0])
        except (OSError, RuntimeError, ValueError):
            return None
        extension = extracted.get("ext", "png").lower()
        if extension not in {"png", "jpg", "jpeg", "webp"}:
            extension = "png"
        target = self.cache_dir / f"book-{digest}.{extension}"
        target.write_bytes(extracted["image"])
        return target

    def _closest_visual_asset(self, reference: Path) -> Path | None:
        reference_hash = self._cached_hash(reference)
        if reference_hash is None:
            return None
        best: tuple[int, Path] | None = None
        for candidate in self._unknown_assets:
            candidate_hash = self._cached_hash(candidate)
            if candidate_hash is None:
                continue
            distance = (reference_hash ^ candidate_hash).bit_count()
            if best is None or distance < best[0]:
                best = (distance, candidate)
        return best[1] if best and best[0] <= 6 else None

    def _cached_hash(self, path: Path) -> int | None:
        if path not in self._hash_cache:
            self._hash_cache[path] = self._average_hash(path)
        return self._hash_cache[path]

    @staticmethod
    def _average_hash(path: Path) -> int | None:
        try:
            pixmap = fitz.Pixmap(path)
        except Exception:  # noqa: BLE001 -- assets locais podem ter conteúdo inválido
            return None
        if pixmap.width < 2 or pixmap.height < 2:
            return None
        values = []
        for row in range(8):
            y = min(pixmap.height - 1, int((row + 0.5) * pixmap.height / 8))
            for column in range(8):
                x = min(pixmap.width - 1, int((column + 0.5) * pixmap.width / 8))
                pixel = pixmap.pixel(x, y)
                values.append(sum(pixel[:3]) / min(3, len(pixel)))
        average = sum(values) / len(values)
        result = 0
        for value in values:
            result = (result << 1) | int(value >= average)
        return result
