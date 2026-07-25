"""Ilustração local de momentos da sessão em bitmaps PNG."""
from __future__ import annotations

import math
import re
import unicodedata
from pathlib import Path

import fitz

PALETTES = {
    "Sangue": (0.72, 0.08, 0.12), "Morte": (0.18, 0.52, 0.32),
    "Conhecimento": (0.78, 0.58, 0.08), "Energia": (0.43, 0.25, 0.78),
    "Medo": (0.72, 0.75, 0.80), "Profundezas": (0.06, 0.42, 0.52),
}
CATEGORY_COLORS = {
    "ritual": (0.43, 0.25, 0.78), "poder": (0.66, 0.35, 0.58),
    "combate": (0.68, 0.20, 0.18), "arma": (0.64, 0.30, 0.22),
    "perseguicao": (0.72, 0.46, 0.16), "condicao": (0.70, 0.32, 0.14),
}


class StoryIllustrator:
    def __init__(self, output_dir: str | Path, asset_dir: str | Path | None = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.asset_dir = Path(asset_dir) if asset_dir else self.output_dir

    def render(self, scene: dict) -> str:
        revision = scene.get("revision", 1)
        target = self.output_dir / f"story-{scene['id']}-{revision}.png"
        document = fitz.open()
        page = document.new_page(width=960, height=540)
        category = self._primary_category(scene)
        color = self._accent(scene, category)
        self._background(page, color)
        self._draw_environment(page, category, color)
        self._draw_action(page, category, color)
        self._insert_asset(page, scene.get("asset_thumbnail"))
        self._caption(page, scene)
        page.get_pixmap(alpha=False).save(target)
        document.close()
        self._remove_old_revisions(scene["id"], target)
        return f"/thumbnails/{target.name}?v={revision}"

    @staticmethod
    def _primary_category(scene: dict) -> str:
        categories = [item.get("category") for item in scene.get("mechanics", [])]
        for category in ("ritual", "poder", "combate", "perseguicao", "arma", "condicao"):
            if category in categories:
                return category
        return categories[0] if categories else "narrativa"

    @staticmethod
    def _accent(scene: dict, category: str) -> tuple[float, float, float]:
        for item in scene.get("mechanics", []):
            element = item.get("elemento")
            if element in PALETTES:
                return PALETTES[element]
        return CATEGORY_COLORS.get(category, (0.20, 0.43, 0.48))

    @staticmethod
    def _background(page, color) -> None:
        page.draw_rect(page.rect, color=(0.025, 0.02, 0.02), fill=(0.025, 0.02, 0.02))
        for index in range(9):
            factor = index / 8
            shade = tuple(component * (0.10 + factor * 0.22) for component in color)
            page.draw_rect(fitz.Rect(0, index * 60, 960, (index + 1) * 60),
                           color=shade, fill=shade)
        page.draw_rect(fitz.Rect(0, 360, 960, 540), color=(0.03, 0.025, 0.02),
                       fill=(0.03, 0.025, 0.02))

    @staticmethod
    def _draw_environment(page, category: str, color) -> None:
        horizon = 352
        page.draw_line((0, horizon), (960, horizon), color=color, width=2)
        if category == "perseguicao":
            page.draw_polyline([(150, 540), (430, horizon), (540, horizon), (840, 540)],
                               color=(0.35, 0.33, 0.30), width=4)
            return
        for x in (80, 210, 760, 890):
            page.draw_rect(fitz.Rect(x, 210, x + 42, horizon),
                           color=(0.08, 0.07, 0.06), fill=(0.08, 0.07, 0.06))
            page.draw_circle((x + 21, 205), 34, color=(0.07, 0.06, 0.05),
                             fill=(0.07, 0.06, 0.05))

    def _draw_action(self, page, category: str, color) -> None:
        if category in ("ritual", "poder"):
            self._figure(page, 280, 350, facing=1)
            for radius in (48, 78, 112):
                page.draw_circle((505, 245), radius, color=color, width=3)
            for angle in range(0, 360, 30):
                radians = math.radians(angle)
                start = (505 + 50 * math.cos(radians), 245 + 50 * math.sin(radians))
                end = (505 + 112 * math.cos(radians), 245 + 112 * math.sin(radians))
                page.draw_line(start, end, color=color, width=2)
            page.draw_line((320, 280), (420, 245), color=color, width=7)
        elif category in ("combate", "arma"):
            self._figure(page, 330, 350, facing=1)
            self._figure(page, 610, 350, facing=-1)
            page.draw_line((390, 255), (545, 170), color=(0.82, 0.82, 0.78), width=9)
            page.draw_line((520, 190), (560, 235), color=(0.45, 0.26, 0.14), width=12)
        elif category == "perseguicao":
            self._figure(page, 390, 360, facing=1, running=True)
            self._figure(page, 560, 325, facing=1, running=True)
            for y in (210, 245, 280):
                page.draw_line((210, y), (350, y), color=color, width=4)
        elif category == "condicao":
            self._figure(page, 475, 355, facing=1)
            for radius in (65, 100, 138):
                box = fitz.Rect(475 - radius, 260 - radius, 475 + radius, 260 + radius)
                page.draw_arc(box, 20, 260, color=color, width=4)
        else:
            self._figure(page, 400, 350, facing=1)
            self._figure(page, 555, 350, facing=-1)

    @staticmethod
    def _figure(page, x: int, ground: int, facing: int, running: bool = False) -> None:
        ink = (0.035, 0.03, 0.025)
        page.draw_circle((x, ground - 132), 26, color=ink, fill=ink)
        page.draw_line((x, ground - 104), (x, ground - 42), color=ink, width=28)
        leg_shift = 28 if running else 13
        page.draw_line((x, ground - 48), (x - leg_shift, ground), color=ink, width=13)
        page.draw_line((x, ground - 48), (x + leg_shift, ground), color=ink, width=13)
        page.draw_line((x, ground - 92), (x + facing * 48, ground - 68),
                       color=ink, width=12)
        page.draw_line((x, ground - 92), (x - facing * 32, ground - 72),
                       color=ink, width=12)

    def _insert_asset(self, page, url: str | None) -> None:
        if not url:
            return
        filename = url.split("?", 1)[0].rsplit("/", 1)[-1]
        asset = self.asset_dir / filename
        if not asset.exists() or asset.name.startswith("story-"):
            return
        try:
            page.insert_image(fitz.Rect(690, 58, 920, 288), filename=str(asset),
                              keep_proportion=True)
            page.draw_rect(fitz.Rect(684, 52, 926, 294), color=(0.78, 0.72, 0.58), width=3)
        except (RuntimeError, ValueError):
            return

    @staticmethod
    def _caption(page, scene: dict) -> None:
        title = StoryIllustrator._ascii(scene.get("title", "Momento da sessao"))[:58]
        text = StoryIllustrator._ascii(scene.get("text", ""))[:112]
        page.draw_rect(fitz.Rect(0, 394, 960, 540), color=(0.015, 0.012, 0.01),
                       fill=(0.015, 0.012, 0.01), fill_opacity=0.94)
        page.insert_text((42, 440), title, fontsize=27, fontname="hebo",
                         color=(0.94, 0.90, 0.80))
        page.insert_textbox(fitz.Rect(42, 458, 910, 522), text, fontsize=14,
                            fontname="helv", color=(0.74, 0.71, 0.66))

    @staticmethod
    def _ascii(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        value = "".join(char for char in normalized if not unicodedata.combining(char))
        return re.sub(r"[^\x20-\x7E]+", " ", value).strip()

    def _remove_old_revisions(self, scene_id: int, keep: Path) -> None:
        for path in self.output_dir.glob(f"story-{scene_id}-*.png"):
            if path != keep:
                path.unlink(missing_ok=True)

    def discard(self, scene: dict) -> None:
        for path in self.output_dir.glob(f"story-{scene['id']}-*.png"):
            path.unlink(missing_ok=True)
