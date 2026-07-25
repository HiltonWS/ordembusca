import struct
import zlib

import fitz

from ordem.thumbnails import ThumbnailResolver


def _gradient_png(width=16, height=16):
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            row.extend((x * 15, y * 15, (x + y) * 7))
        rows.append(bytes(row))

    def chunk(kind, data):
        return (
            struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + chunk(b"IEND", b"")
    )


def test_unnamed_asset_is_visually_matched_to_book_art(tmp_path):
    image = _gradient_png()
    assets = tmp_path / "extras"
    assets.mkdir()
    unnamed = assets / "token-0042.png"
    unnamed.write_bytes(image)

    books = tmp_path / "books"
    books.mkdir()
    pdf_path = books / "livro.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_image(fitz.Rect(20, 20, 220, 220), stream=image)
    document.save(pdf_path)
    document.close()

    resolver = ThumbnailResolver(
        [{
            "term": "Sopro do Caos",
            "category": "ritual",
            "aliases": [],
            "title": "Livro",
            "filename": "livro.pdf",
        }],
        asset_roots=[assets],
        source_roots=[books],
        cache_dir=tmp_path / "cache",
    )

    url = resolver.resolve({
        "term": "Sopro do Caos",
        "category": "ritual",
        "source": "Livro",
        "page": 1,
    })

    assert url and url.startswith("/thumbnails/sopro-do-caos-")
    cached = tmp_path / "cache" / url.rsplit("/", 1)[-1]
    assert cached.read_bytes() == image
