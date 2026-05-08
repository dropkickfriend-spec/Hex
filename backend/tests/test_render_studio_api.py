"""Core API regression tests for MunkerHex Studio endpoints."""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv


# Load frontend env because public base URL is configured there for preview testing
load_dotenv(Path("/app/frontend/.env"))

BASE_URL = (
    os.environ.get("EXPO_BACKEND_URL")
    or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
)

ORIGINAL_TONALITY_PATH = Path("/app/backend/original_tonality.html")


def _require_base_url() -> str:
    if not BASE_URL:
        raise RuntimeError("Missing EXPO_BACKEND_URL/EXPO_PUBLIC_BACKEND_URL in environment")
    return BASE_URL.rstrip("/")


def _assert_render_shape(item: dict):
    assert isinstance(item.get("id"), str)
    assert isinstance(item.get("url"), str)
    assert isinstance(item.get("host"), str)
    assert isinstance(item.get("signature"), str)
    assert "_id" not in item
    cfg = item.get("config")
    assert isinstance(cfg, dict)
    assert isinstance(cfg.get("stripe_mode"), str)
    assert isinstance(cfg.get("density"), int)


# Health/status core endpoint checks
def test_health_endpoint_ok():
    base = _require_base_url()
    response = requests.get(f"{base}/api/health", timeout=20)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "munkerhex-studio"


# Palette catalogue endpoint checks
def test_palettes_endpoint_returns_presets():
    base = _require_base_url()
    response = requests.get(f"{base}/api/palettes", timeout=20)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    first = data[0]
    assert isinstance(first.get("id"), str)
    assert isinstance(first.get("colors"), list)
    assert "_id" not in first


# Retro gallery endpoint checks
def test_gallery_endpoint_returns_cards():
    base = _require_base_url()
    response = requests.get(f"{base}/api/gallery", timeout=20)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    first = data[0]
    assert isinstance(first.get("title"), str)
    assert isinstance(first.get("genre"), str)
    assert "_id" not in first


# Render project create/list checks with persistence verification pattern
def test_create_render_and_verify_list_contains_it():
    base = _require_base_url()

    palettes_response = requests.get(f"{base}/api/palettes", timeout=20)
    assert palettes_response.status_code == 200
    palette_id = palettes_response.json()[0]["id"]

    payload = {
        "url": "https://example.com",
        "palette_id": palette_id,
        "config": {
            "stripe_mode": "diagonal",
            "density": 10,
            "thickness": 5,
            "opacity": 82,
            "hex_enabled": True,
            "animation_speed": 4,
        },
        "title": "TEST_pytest render",
    }

    create_response = requests.post(f"{base}/api/renders", json=payload, timeout=20)
    assert create_response.status_code == 200
    created = create_response.json()
    _assert_render_shape(created)
    created_id = created["id"]
    assert created["palette_id"] == palette_id
    assert created["host"] == "example.com"

    list_response = requests.get(f"{base}/api/renders", timeout=20)
    assert list_response.status_code == 200
    projects = list_response.json()
    assert isinstance(projects, list)
    assert len(projects) >= 1
    for project in projects:
        _assert_render_shape(project)

    matched = [project for project in projects if project.get("id") == created_id]
    assert len(matched) == 1
    assert matched[0]["title"] == "TEST_pytest render"


# Validation/error handling checks for bad palette input
def test_create_render_rejects_unknown_palette():
    base = _require_base_url()
    payload = {
        "url": "https://example.com",
        "palette_id": "not-a-real-palette",
        "config": {
            "stripe_mode": "diagonal",
            "density": 10,
            "thickness": 5,
            "opacity": 82,
            "hex_enabled": True,
            "animation_speed": 4,
        },
    }
    response = requests.post(f"{base}/api/renders", json=payload, timeout=20)
    assert response.status_code == 400
    body = response.json()
    assert body["detail"] == "Unknown palette preset"


# Tonality renderer endpoint checks (original source + injected adapter)
def test_tonality_renderer_contains_original_layout_and_adapter():
    base = _require_base_url()
    response = requests.get(f"{base}/api/tonality-renderer", timeout=20)
    assert response.status_code == 200
    html = response.text

    assert "<title>Tonality" in html
    assert "Color wheel · CMY axis" in html
    assert "Hue cube · hue × tone × chroma" in html
    assert 'id="mhRenderAdapter"' in html
    assert "Render target · website/game through original Munker + hex grid" in html
    assert 'id="mhRenderBtn"' in html


# Unified Munker section + hidden original details contract checks
def test_tonality_renderer_contains_unified_munker_and_hides_original_details():
    base = _require_base_url()
    response = requests.get(f"{base}/api/tonality-renderer", timeout=20)
    assert response.status_code == 200
    html = response.text

    # Unified control section is present
    assert 'id="mhUnifiedMunker"' in html
    assert 'id="mhMunkerPreset"' in html
    assert 'id="mhUnifiedMode"' in html
    assert 'id="mhUnifiedPattern"' in html
    assert 'id="mhUnifiedSpacing"' in html
    assert 'id="mhLineThickness"' in html
    assert 'id="mhUnifiedOpacity"' in html
    assert 'id="mhUnifiedSpeed"' in html
    assert 'id="mhAutoAnimate"' in html

    # Original duplicate details are hidden via adapter behavior
    assert "mh-hidden-original-munker" in html
    assert "hideDuplicateMunkerControls" in html


# Unified preset mapping + hidden original sync contract checks
def test_unified_munker_preset_mapping_and_sync_contract_present():
    base = _require_base_url()
    response = requests.get(f"{base}/api/tonality-renderer", timeout=20)
    assert response.status_code == 200
    html = response.text

    # At least five preset options available
    assert html.count('Auto pattern ·') >= 5
    assert "cool-dark-vibration" in html

    # Cool-dark-vibration mapping contract
    assert "'cool-dark-vibration': { mode:'grid', pattern:'bw', spacing:2, thickness:7, opacity:88, speed:6, animate:'on' }" in html

    # Unified controls sync into original controls
    assert "setVal('munkerMode', u.mode)" in html
    assert "setVal('munkerPattern', u.pattern)" in html
    assert "setVal('munkerSpacing', u.spacing)" in html
    assert "setVal('munkerThick', Math.min(20, u.thickness))" in html
    assert "setVal('munkerOpacity', u.opacity)" in html
    assert "setVal('munkerSpeed', u.speed)" in html
    assert "setVal('munkerAnimate', u.animate === 'on'" in html


# Website proxy render + full-page style overlay injection contract checks
def test_website_render_proxy_and_overlay_injection_contract_present():
    base = _require_base_url()
    response = requests.get(f"{base}/api/tonality-renderer", timeout=20)
    assert response.status_code == 200
    html = response.text

    assert "site-html?url=" in html
    assert "styleWholeWebsiteFrame" in html
    assert "mh-site-whole-style" in html
    assert "mh-site-style-overlay" in html
    assert "mh-site-hex-overlay" in html
    assert "mh-site-ruliad-overlay" in html
    assert "applyRenderPalette();" in html
    assert "styleWholeWebsiteFrame();" in html


# Website proxy endpoint checks (/api/site-html)
def test_site_html_proxy_inserts_base_tag_for_html_pages():
    base = _require_base_url()
    response = requests.get(f"{base}/api/site-html", params={"url": "https://example.com"}, timeout=20)
    assert response.status_code == 200
    html = response.text
    assert "<base href='https://example.com'>" in html
    assert "<html" in html.lower()


# Website proxy validation checks
def test_site_html_proxy_rejects_invalid_scheme():
    base = _require_base_url()
    response = requests.get(f"{base}/api/site-html", params={"url": "javascript:alert(1)"}, timeout=20)
    assert response.status_code == 400
    body = response.json()
    assert body["detail"] == "Enter a valid http/https URL"


# Original source file preservation checks
def test_original_tonality_source_file_exists_with_required_sections():
    assert ORIGINAL_TONALITY_PATH.exists()
    original = ORIGINAL_TONALITY_PATH.read_text(encoding="utf-8")
    assert "Color wheel · CMY axis" in original
    assert "Hue cube · hue × tone × chroma" in original


# Original source cool-CMY vibration and landscape-cooling checks
def test_original_source_uses_cool_cmy_logic_for_speckles_and_landscape_depth():
    original = ORIGINAL_TONALITY_PATH.read_text(encoding="utf-8")
    assert "function coolCMYVibrationRgb" in original
    assert "function nearestCoolCMYHue" in original
    assert "function applyWarmthAndYellow" in original
    assert "nearestCoolCMYHue(hue)" in original
    assert "cad red" in original.lower()
    assert "cool side" in original.lower() or "cool cmy-side" in original.lower()


# Adapter controls and calibrated wheel integration checks
def test_tonality_renderer_contains_line_thickness_controls_and_live_wheel_hooks():
    base = _require_base_url()
    response = requests.get(f"{base}/api/tonality-renderer", timeout=20)
    assert response.status_code == 200
    html = response.text

    # Top-level line thickness slider + readout
    assert 'id="mhLineThickness"' in html
    assert 'id="mhLineThicknessv"' in html
    assert "Line thickness" in html
    assert "--mh-thick" in html

    # Adapter reads original wheel live state/functions
    assert "typeof state !== 'undefined'" in html
    assert "typeof rgbAt === 'function'" in html
    assert "typeof additiveComplementHue === 'function'" in html
    assert "typeof currentCentre === 'function'" in html
    assert "typeof calibratedAnchors === 'function'" in html

    # Adapter updates calibrated CSS + labels/cells
    assert "--mh-a" in html
    assert "--mh-b" in html
    assert "mhStageLabel" in html
    assert "mh-game-cell" in html


# Retro game top-down 3-plane hex renderer contract checks
def test_tonality_renderer_contains_top_down_hex_game_style_contract():
    base = _require_base_url()
    response = requests.get(f"{base}/api/tonality-renderer", timeout=20)
    assert response.status_code == 200
    html = response.text

    # Game mode + style selector
    assert 'id="mhGame"' in html
    assert 'value="invaders"' in html
    assert 'value="platformer"' in html
    assert 'value="maze"' in html
    assert 'id="mhGameStyle"' in html
    assert "top-down 3-plane cube hex ground" in html

    # Three-face ground cell contract
    assert "mh-game-face-top" in html
    assert "mh-game-face-left" in html
    assert "mh-game-face-bottom" in html

    # Token layer generated from same render/palette hooks
    assert 'id="mhTokenLayer"' in html
    assert ".mh-token.player" in html
    assert ".mh-token.enemy" in html
    assert ".mh-token.pickup" in html
    assert "--token-color" in html

    # Cube controls hooked into game redraw path
    assert "cubeSize" in html
    assert "cubeGap" in html
    assert "grid.style.setProperty('--mh-hex-size', hexW + 'px')" in html
    assert "if ($('mhGame').value !== 'website') drawGame($('mhGame').value);" in html
