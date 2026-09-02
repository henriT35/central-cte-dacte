from __future__ import annotations

import mimetypes
import re
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]
STATIC = PROJECT / "web_local" / "static"
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
INDEX_HTML = (STATIC / "index.html").read_text(encoding="utf-8")
STYLES = (STATIC / "styles.css").read_text(encoding="utf-8")
SERVER = (PROJECT / "web_local" / "server.py").read_text(encoding="utf-8")
COMPOSE = (PROJECT / "deploy" / "vps" / "compose.yaml").read_text(encoding="utf-8")
IMAGE = STATIC / "assets" / "easteregg" / "spamton.png"
AUDIO = STATIC / "assets" / "easteregg" / "spamton.mp3"


def test_release_version_is_r12_8() -> None:
    assert "MVP13 R12.13" in SERVER
    assert "MVP13 R12.13" in APP_JS
    assert "central-cte-dacte:r12.13" in COMPOSE


def test_konami_sequence_and_lifecycle_are_present() -> None:
    sequence = re.search(r"const KONAMI_CODE = \[(.*?)\];", APP_JS)
    assert sequence
    compact = sequence.group(1).replace(" ", "")
    assert compact == '"ArrowUp","ArrowUp","ArrowDown","ArrowDown","ArrowLeft","ArrowRight","ArrowLeft","ArrowRight","b","a"'
    assert "function openSpamtonEasterEgg()" in APP_JS
    assert "function closeSpamtonEasterEgg()" in APP_JS
    assert "handleKonamiCode(event);" in APP_JS
    assert "closeSpamtonEasterEgg();" in APP_JS
    assert "audio.currentTime = 0" in APP_JS
    assert "await audio.play()" in APP_JS
    assert "audio.pause()" in APP_JS


def test_easter_egg_is_full_screen_accessible_and_looped() -> None:
    assert 'id="spamton-easter-egg"' in INDEX_HTML
    assert 'role="dialog"' in INDEX_HTML
    assert 'aria-modal="true"' in INDEX_HTML
    assert 'id="spamton-close"' in INDEX_HTML
    assert 'src="assets/easteregg/spamton.png"' in INDEX_HTML
    assert 'src="assets/easteregg/spamton.mp3"' in INDEX_HTML
    assert re.search(r'<audio[^>]+id="spamton-audio"[^>]+loop', INDEX_HTML)
    assert ".spamton-easter-egg" in STYLES
    assert "position: fixed" in STYLES
    assert "z-index: 10000" in STYLES
    assert "image-rendering: pixelated" in STYLES
    assert "prefers-reduced-motion" in STYLES


def test_user_assets_are_embedded_and_valid() -> None:
    assert IMAGE.is_file() and IMAGE.stat().st_size > 500
    assert AUDIO.is_file() and AUDIO.stat().st_size > 100_000
    assert IMAGE.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    audio_head = AUDIO.read_bytes()[:3]
    assert audio_head == b"ID3" or audio_head[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}
    assert mimetypes.guess_type(IMAGE.name)[0] == "image/png"
    assert mimetypes.guess_type(AUDIO.name)[0] in {"audio/mpeg", "audio/mp3"}


def test_easter_egg_has_no_external_asset_dependency() -> None:
    block = INDEX_HTML.split('id="spamton-easter-egg"', 1)[1].split("</section>", 1)[0]
    assert "http://" not in block
    assert "https://" not in block
