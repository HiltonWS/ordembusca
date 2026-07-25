"""Ilustração local de momentos da sessão em bitmaps PNG."""
from __future__ import annotations

import math
import random
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
        seed = random.Random(f"{scene['id']}:{scene.get('revision', 1)}:{category}")
        self._background(page, color, seed)
        self._draw_environment(page, category, color, seed)
        self._draw_action(page, category, color)
        self._insert_asset(page, scene.get("asset_thumbnail"))
        self._caption(page, scene, color)
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
    def _background(page, color, seed: random.Random) -> None:
        dark = (0.018, 0.016, 0.022)
        page.draw_rect(page.rect, color=dark, fill=dark)
        for index in range(18):
            factor = index / 17
            shade = tuple(
                dark[channel] * (1 - factor) + color[channel] * (0.08 + factor * 0.26)
                for channel in range(3)
            )
            page.draw_rect(fitz.Rect(0, index * 24, 960, (index + 1) * 24 + 1),
                           color=shade, fill=shade)
        for radius, opacity in ((230, 0.035), (165, 0.055), (105, 0.08)):
            page.draw_circle((510, 225), radius, color=color, fill=color,
                             fill_opacity=opacity, stroke_opacity=0)
        for _ in range(42):
            x, y = seed.randint(20, 940), seed.randint(28, 355)
            radius = seed.choice((1, 1, 2, 3))
            opacity = seed.uniform(0.18, 0.62)
            page.draw_circle((x, y), radius, color=color, fill=color,
                             fill_opacity=opacity, stroke_opacity=0)
        page.draw_rect(fitz.Rect(0, 0, 960, 15), color=dark, fill=dark)

    @staticmethod
    def _draw_environment(page, category: str, color, seed: random.Random) -> None:
        horizon = 354
        far = (0.055, 0.05, 0.065)
        mid = (0.035, 0.032, 0.04)
        StoryIllustrator._polygon(
            page,
            [(0, horizon), (0, 245), (110, 286), (205, 214), (335, 292),
             (455, 230), (590, 286), (735, 205), (850, 275), (960, 225),
             (960, horizon)],
            far,
        )
        if category == "perseguicao":
            StoryIllustrator._polygon(
                page, [(0, 540), (365, horizon), (595, horizon), (960, 540)], mid
            )
            page.draw_line((120, 540), (415, horizon), color=(0.32, 0.29, 0.28), width=3)
            page.draw_line((840, 540), (545, horizon), color=(0.32, 0.29, 0.28), width=3)
            for y, width in ((500, 54), (455, 38), (415, 24), (382, 13)):
                page.draw_line((480 - width / 2, y), (480 + width / 2, y),
                               color=color, width=5)
            return
        StoryIllustrator._polygon(page, [(0, 540), (0, horizon), (960, horizon),
                                         (960, 540)], mid)
        for x in (70, 178, 770, 880):
            height = seed.randint(115, 205)
            width = seed.randint(28, 48)
            page.draw_rect(fitz.Rect(x, horizon - height, x + width, horizon),
                           color=far, fill=far)
            page.draw_circle((x + width / 2, horizon - height), width * 0.72,
                             color=far, fill=far)
        for x in (180, 345, 615, 790):
            page.draw_line((480, horizon), (x, 540), color=(0.085, 0.075, 0.08), width=1)
        page.draw_line((0, horizon), (960, horizon), color=color, width=1,
                       stroke_opacity=0.55)

    def _draw_action(self, page, category: str, color) -> None:
        if category in ("ritual", "poder"):
            self._figure(page, 275, 360, facing=1, color=color, pose="cast")
            for radius, width, opacity in ((122, 2, 0.35), (88, 3, 0.7), (51, 2, 0.9)):
                page.draw_circle((520, 228), radius, color=color, width=width,
                                 stroke_opacity=opacity)
            for angle in range(0, 360, 24):
                radians = math.radians(angle)
                start = (520 + 56 * math.cos(radians), 228 + 56 * math.sin(radians))
                end = (520 + 118 * math.cos(radians), 228 + 118 * math.sin(radians))
                page.draw_line(start, end, color=color, width=1.4, stroke_opacity=0.65)
            self._polygon(page, [(492, 191), (548, 191), (520, 245)], None,
                          color=color, width=2)
            page.draw_line((320, 270), (417, 235), color=color, width=5,
                           stroke_opacity=0.75)
        elif category in ("combate", "arma"):
            self._figure(page, 335, 370, facing=1, color=color, pose="attack")
            self._figure(page, 650, 360, facing=-1, color=color, pose="guard")
            page.draw_line((393, 252), (566, 176), color=(0.24, 0.20, 0.16), width=13)
            page.draw_line((397, 248), (566, 176), color=(0.88, 0.86, 0.78), width=7)
            page.draw_line((409, 244), (558, 181), color=(1, 0.97, 0.86), width=1.5)
            page.draw_line((548, 184), (585, 225), color=(0.38, 0.19, 0.11), width=11)
            for angle in range(0, 360, 30):
                radians = math.radians(angle)
                page.draw_line((530, 220), (530 + 55 * math.cos(radians),
                                            220 + 55 * math.sin(radians)),
                               color=color, width=2, stroke_opacity=0.7)
        elif category == "perseguicao":
            self._figure(page, 390, 380, facing=1, color=color, pose="run")
            self._figure(page, 570, 342, facing=1, color=color, pose="run", scale=0.82)
            for y in (210, 245, 280):
                page.draw_line((170, y), (340, y), color=color, width=3,
                               stroke_opacity=0.5)
        elif category == "condicao":
            self._figure(page, 475, 365, facing=1, color=color, pose="weak")
            for radius in (65, 100, 138):
                box = fitz.Rect(475 - radius, 260 - radius, 475 + radius, 260 + radius)
                page.draw_arc(box, 20, 260, color=color, width=3, stroke_opacity=0.55)
        else:
            self._figure(page, 390, 365, facing=1, color=color, pose="stand")
            self._figure(page, 565, 365, facing=-1, color=color, pose="stand")

    @staticmethod
    def _figure(page, x: int, ground: int, facing: int, color,
                pose: str = "stand", scale: float = 1) -> None:
        ink = (0.022, 0.02, 0.026)
        head_y = ground - 142 * scale
        page.draw_circle((x, head_y), 31 * scale, color=color, fill=color,
                         fill_opacity=0.08, stroke_opacity=0)
        page.draw_circle((x, head_y), 17 * scale, color=ink, fill=ink)
        lean = 13 * facing * scale if pose in ("run", "attack") else 0
        shoulder = (x + lean, ground - 111 * scale)
        hip = (x, ground - 48 * scale)
        page.draw_line((x, head_y + 14 * scale), shoulder, color=ink, width=10 * scale)
        StoryIllustrator._polygon(
            page,
            [(shoulder[0] - 20 * scale, shoulder[1]),
             (shoulder[0] + 20 * scale, shoulder[1]),
             (hip[0] + 13 * scale, hip[1]),
             (hip[0] - 13 * scale, hip[1])],
            ink,
        )
        page.draw_line((shoulder[0] - facing * 18 * scale, shoulder[1] + 3 * scale),
                       (hip[0] - facing * 10 * scale, hip[1] - 2 * scale),
                       color=color, width=2 * scale, stroke_opacity=0.55)
        if pose == "run":
            arms = ((52, -12), (-42, 25))
            legs = ((45, 0), (-35, 0))
        elif pose == "attack":
            arms = ((58, -35), (-32, 28))
            legs = ((32, 0), (-28, 0))
        elif pose == "cast":
            arms = ((58, -35), (48, 5))
            legs = ((20, 0), (-18, 0))
        elif pose == "weak":
            arms = ((38, 18), (-35, 22))
            legs = ((18, 0), (-22, 0))
        elif pose == "guard":
            arms = ((-48, -20), (35, 12))
            legs = ((22, 0), (-20, 0))
        else:
            arms = ((38, 10), (-34, 12))
            legs = ((17, 0), (-17, 0))
        for dx, dy in arms:
            page.draw_line(shoulder, (shoulder[0] + facing * dx * scale,
                                     shoulder[1] + dy * scale), color=ink, width=11 * scale)
        for dx, _ in legs:
            foot = (hip[0] + facing * dx * scale, ground)
            page.draw_line(hip, foot, color=ink, width=14 * scale)
            page.draw_line(foot, (foot[0] + facing * 10 * scale, foot[1]),
                           color=ink, width=7 * scale)
        if pose == "cast":
            StoryIllustrator._polygon(
                page,
                [(x - 18 * scale, ground - 103 * scale),
                 (x + 18 * scale, ground - 103 * scale),
                 (x + 42 * scale, ground - 22 * scale),
                 (x - 38 * scale, ground - 22 * scale)],
                ink,
            )

    @staticmethod
    def _polygon(page, points, fill, color=None, width: float = 1) -> None:
        shape = page.new_shape()
        shape.draw_polyline(points)
        shape.finish(color=color or fill, fill=fill, width=width, closePath=True)
        shape.commit()

    def _insert_asset(self, page, url: str | None) -> None:
        if not url:
            return
        filename = url.split("?", 1)[0].rsplit("/", 1)[-1]
        asset = self.asset_dir / filename
        if not asset.exists() or asset.name.startswith("story-"):
            return
        try:
            page.draw_rect(fitz.Rect(700, 51, 930, 301), color=(0.01, 0.01, 0.012),
                           fill=(0.01, 0.01, 0.012), fill_opacity=0.65)
            page.insert_image(fitz.Rect(710, 58, 920, 288), filename=str(asset),
                              keep_proportion=True)
            page.draw_rect(fitz.Rect(706, 54, 924, 292), color=(0.82, 0.76, 0.64),
                           width=1, stroke_opacity=0.65)
        except (RuntimeError, ValueError):
            return

    @staticmethod
    def _caption(page, scene: dict, color) -> None:
        title = StoryIllustrator._ascii(scene.get("title", "Momento da sessao"))[:58]
        text = StoryIllustrator._ascii(scene.get("text", ""))[:112]
        page.draw_rect(fitz.Rect(0, 390, 960, 540), color=(0.012, 0.011, 0.016),
                   fill=(0.012, 0.011, 0.016), fill_opacity=0.88)
        page.draw_line((42, 414), (142, 414), color=color, width=3)
        page.insert_text((42, 454), title.upper(), fontsize=25, fontname="hebo",
                         color=(0.94, 0.90, 0.80))
        page.insert_textbox(fitz.Rect(42, 470, 900, 525), text, fontsize=13,
                    lineheight=1.25, fontname="helv", color=(0.72, 0.70, 0.68))

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
