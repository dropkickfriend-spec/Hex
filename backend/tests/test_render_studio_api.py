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
