from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import AnyHttpUrl, BaseModel, Field
from typing import List, Literal, Optional
import uuid
from datetime import datetime, timezone
import hashlib
import json
from urllib.parse import urlparse
import requests
import asyncio
from io import BytesIO
from PIL import Image, ImageDraw


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')
ORIGINAL_TONALITY_PATH = ROOT_DIR / "original_tonality.html"

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Define Models
class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str


class RenderConfig(BaseModel):
    stripe_mode: Literal["horizontal", "vertical", "diagonal", "grid"] = "diagonal"
    density: int = Field(default=10, ge=4, le=24)
    thickness: int = Field(default=5, ge=1, le=12)
    opacity: int = Field(default=82, ge=10, le=100)
    hex_enabled: bool = True
    animation_speed: int = Field(default=4, ge=1, le=12)


class RenderProjectCreate(BaseModel):
    url: AnyHttpUrl
    palette_id: str
    config: RenderConfig
    title: Optional[str] = None


class RenderProject(BaseModel):
    id: str
    title: str
    url: str
    host: str
    palette_id: str
    config: RenderConfig
    signature: str
    created_at: str


class PalettePreset(BaseModel):
    id: str
    name: str
    description: str
    anchor: str
    complement: str
    colors: List[str]
    mood: str


class RetroGameCard(BaseModel):
    id: str
    title: str
    genre: str
    description: str
    colors: List[str]
    geometry: str
    intensity: int


class GifExportPayload(BaseModel):
    a_hex: str = "#ffff00"
    b_hex: str = "#0000ff"
    centre_hex: str = "#808080"
    colors: List[str] = Field(default_factory=list)
    hue: int = Field(default=90, ge=0, le=359)
    tone: int = Field(default=50, ge=0, le=100)
    preset: str = "white-ruliad"
    mode: str = "diag"
    pattern: str = "white"
    spacing: int = Field(default=3, ge=0, le=40)
    thickness: int = Field(default=13, ge=1, le=40)
    opacity: int = Field(default=96, ge=0, le=100)
    speed: int = Field(default=4, ge=1, le=16)
    width: int = Field(default=390, ge=240, le=900)
    height: int = Field(default=430, ge=240, le=900)


PALETTE_PRESETS = [
    PalettePreset(
        id="cmy-inverse",
        name="CMY Inverse Core",
        description="Yellow, magenta and cyan lights grounded by additive RGB complements.",
        anchor="#FFFF00",
        complement="#0000FF",
        colors=["#FFFF00", "#FF00FF", "#00FFFF", "#FF3131", "#39FF14", "#0000FF"],
        mood="classic Munker illusion",
    ),
    PalettePreset(
        id="night-cube",
        name="Night Cube",
        description="Deep indigo shadows with cyan scanlines and magenta atmospheric bloom.",
        anchor="#00FFFF",
        complement="#FF00FF",
        colors=["#050505", "#09111F", "#16213E", "#00FFFF", "#FF00FF", "#B8F7FF"],
        mood="dark void / arcade glass",
    ),
    PalettePreset(
        id="solar-arcade",
        name="Solar Arcade",
        description="Hot yellow-orange light over violet shadow, tuned for platform scenes.",
        anchor="#FFFF00",
        complement="#5D00FF",
        colors=["#FFFF00", "#FF9F1C", "#FF3131", "#5D00FF", "#13001F", "#FFFFFF"],
        mood="golden hour cabinet glow",
    ),
    PalettePreset(
        id="maze-pulse",
        name="Maze Pulse",
        description="Puzzle-grid palette with green phosphor, cyan edges and blue-black tone.",
        anchor="#39FF14",
        complement="#FF00FF",
        colors=["#39FF14", "#00FFFF", "#001AFF", "#FF00FF", "#071407", "#E6FFE8"],
        mood="CRT puzzle phosphor",
    ),
]


RETRO_GALLERY = [
    RetroGameCard(
        id="void-invaders",
        title="Void Invaders",
        genre="Arcade Shooter",
        description="Rows of pixel enemies rebuilt as vibrating CMY hex prisms.",
        colors=["#00FFFF", "#FF00FF", "#FFFF00", "#050505"],
        geometry="stacked hex shields",
        intensity=92,
    ),
    RetroGameCard(
        id="magentron-runner",
        title="Magentron Runner",
        genre="Platformer",
        description="Old-school side-scroll silhouettes with additive sunset bands.",
        colors=["#FF00FF", "#FFFF00", "#5D00FF", "#FF3131"],
        geometry="stepped cube platforms",
        intensity=86,
    ),
    RetroGameCard(
        id="cyan-maze",
        title="Cyan Maze 256",
        genre="Puzzle Maze",
        description="A maze-board redesign using alternating line illusions and glow cells.",
        colors=["#00FFFF", "#39FF14", "#0000FF", "#111111"],
        geometry="cross-hatch labyrinth",
        intensity=80,
    ),
    RetroGameCard(
        id="solar-pong",
        title="Solar Pong",
        genre="Arcade Sport",
        description="Paddles and ball become kinetic neon tone ramps over a black field.",
        colors=["#FFFF00", "#FF3131", "#00FFFF", "#050505"],
        geometry="tonal scanline court",
        intensity=74,
    ),
    RetroGameCard(
        id="cube-kart",
        title="Cube Kart Drift",
        genre="Racing",
        description="Pseudo-3D road graphics reframed as isometric chroma slices.",
        colors=["#39FF14", "#FF00FF", "#00FFFF", "#0B0B16"],
        geometry="isometric speed tiles",
        intensity=88,
    ),
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_signature(url: str, palette_id: str, config: RenderConfig) -> str:
    payload = json.dumps(
        {"url": url, "palette_id": palette_id, "config": config.model_dump()},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12].upper()


def host_from_url(url: str) -> str:
    return urlparse(url).netloc.replace("www.", "") or "untitled.site"


def safe_hex_to_rgb(value: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    text = (value or "").strip().lstrip("#")
    if len(text) != 6:
        return fallback
    try:
        return tuple(int(text[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return fallback


def blend_rgb(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
    )


def draw_hex(draw: ImageDraw.ImageDraw, cx: float, cy: float, size: float, color: tuple[int, int, int]):
    top = blend_rgb(color, (255, 255, 255), 0.16)
    left = blend_rgb(color, (0, 0, 0), 0.42)
    bottom = blend_rgb(color, (0, 0, 0), 0.24)
    points = [
        (cx, cy - size),
        (cx + size * 0.866, cy - size * 0.5),
        (cx + size * 0.866, cy + size * 0.5),
        (cx, cy + size),
        (cx - size * 0.866, cy + size * 0.5),
        (cx - size * 0.866, cy - size * 0.5),
    ]
    draw.polygon([points[0], points[1], (cx, cy), points[5]], fill=top)
    draw.polygon([points[5], (cx, cy), points[3], points[4]], fill=left)
    draw.polygon([(cx, cy), points[2], points[3], points[4]], fill=bottom)


def create_palette_gif(payload: GifExportPayload) -> bytes:
    a = safe_hex_to_rgb(payload.a_hex, (255, 255, 0))
    b = safe_hex_to_rgb(payload.b_hex, (0, 0, 255))
    c = safe_hex_to_rgb(payload.centre_hex, (128, 128, 128))
    palette = [safe_hex_to_rgb(color, a) for color in payload.colors[:8]] or [a, b, c]
    width, height = payload.width, payload.height
    frames: list[Image.Image] = []
    bg = blend_rgb(c, (5, 5, 10), 0.72)
    line_alpha = max(0, min(255, round(payload.opacity * 2.55)))
    spacing = max(1, payload.spacing + payload.thickness)
    for frame_idx in range(18):
        img = Image.new("RGBA", (width, height), bg + (255,))
        draw = ImageDraw.Draw(img, "RGBA")

        # 3-plane hex ground / palette field.
        size = max(15, min(34, width / 13))
        row_step = size * 1.5
        col_step = size * 1.78
        y = size * 1.4
        row = 0
        while y < height - size:
            x = size * 1.15 + (row % 2) * col_step / 2
            col = 0
            while x < width - size:
                color = palette[(row + col + frame_idx // 3) % len(palette)]
                draw_hex(draw, x, y, size * 0.92, color)
                col += 1
                x += col_step
            row += 1
            y += row_step

        # Ruliad nodes/links.
        nodes = []
        for i in range(28):
            nx = (width * (0.12 + ((i * 37 + frame_idx * 5) % 76) / 100))
            ny = (height * (0.16 + ((i * 19 + frame_idx * 7) % 68) / 100))
            nodes.append((nx, ny, palette[i % len(palette)]))
        for i, node in enumerate(nodes):
            for j in range(i + 1, min(i + 4, len(nodes))):
                other = nodes[j]
                if abs(node[0] - other[0]) + abs(node[1] - other[1]) < width * 0.52:
                    draw.line([node[:2], other[:2]], fill=palette[(i + j) % len(palette)] + (82,), width=1)
        for nx, ny, color in nodes:
            draw.ellipse([nx - 3, ny - 3, nx + 3, ny + 3], fill=color + (180,))

        # Munker / white artifact lines animated by offset.
        line_color = (255, 255, 255) if payload.pattern in {"white", "bw"} else a
        offset = (frame_idx * spacing * 0.72) % spacing
        if payload.mode == "v":
            x = -width + offset
            while x < width * 2:
                draw.rectangle([x, -20, x + payload.thickness, height + 20], fill=line_color + (line_alpha,))
                x += spacing
        else:
            y = -height + offset
            while y < height * 2:
                if payload.mode == "h":
                    draw.rectangle([-20, y, width + 20, y + payload.thickness], fill=line_color + (line_alpha,))
                else:
                    draw.line(
                        [(-width * 0.25, y), (width * 1.25, y + width * 0.52)],
                        fill=line_color + (line_alpha,),
                        width=payload.thickness,
                    )
                    if payload.mode == "grid":
                        draw.line(
                            [(-width * 0.25, height - y), (width * 1.25, height - y - width * 0.52)],
                            fill=b + (round(line_alpha * 0.7),),
                            width=max(1, payload.thickness // 2),
                        )
                y += spacing

        draw.rectangle([0, 0, width - 1, height - 1], outline=a + (180,), width=2)
        frames.append(img.convert("P", palette=Image.Palette.ADAPTIVE, colors=128))

    output = BytesIO()
    frames[0].save(
        output,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=max(50, min(180, payload.speed * 20)),
        loop=0,
        optimize=False,
    )
    return output.getvalue()

# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "MunkerHex Studio API", "status": "ready"}


@api_router.get("/health")
async def health():
    return {"status": "ok", "service": "munkerhex-studio"}


@api_router.post("/export-gif")
async def export_gif(payload: GifExportPayload):
    gif_bytes = await asyncio.to_thread(create_palette_gif, payload)
    filename = f"munkerhex-{build_signature(payload.a_hex + payload.b_hex, payload.preset, RenderConfig())}.gif"
    return Response(
        content=gif_bytes,
        media_type="image/gif",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def build_tonality_renderer_html() -> str:
    original = ORIGINAL_TONALITY_PATH.read_text(encoding="utf-8")
    render_patch = """
<style id="munkerhex-render-adapter">
  .mh-render-adapter {
    margin: 12px;
    border: 1px solid var(--line);
    border-radius: 12px;
    background: linear-gradient(180deg, rgba(28,28,40,.98), rgba(12,12,18,.98));
    padding: 12px;
    box-shadow: 0 18px 70px rgba(0,0,0,.35);
  }
  .mh-render-adapter h2 { margin-top: 0; }
  .mh-render-toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .mh-render-toolbar input, .mh-render-toolbar select {
    min-width: 180px;
    flex: 1;
    background: #0b0b10;
    color: var(--ink);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 9px 10px;
    font: 12px ui-monospace, monospace;
  }
  .mh-render-toolbar button { min-height: 44px; }
  .mh-suite-tabs {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 6px;
    margin: 10px 0;
  }
  .mh-suite-tab {
    min-height: 44px;
    border: 1px solid var(--line);
    border-radius: 9px;
    background: rgba(0,0,0,.22);
    color: var(--ink-dim);
    font: 10px ui-monospace, monospace;
    letter-spacing: .08em;
    text-transform: uppercase;
  }
  .mh-suite-tab.active {
    color: #05050a;
    background: var(--mh-a, #ffff00);
    border-color: var(--mh-a, #ffff00);
  }
  .mh-builder-panel { display:none; margin-top:10px; border:1px solid rgba(255,255,255,.12); border-radius:10px; background:rgba(0,0,0,.18); padding:10px; }
  .mh-builder-panel.active { display:block; }
  .mh-builder-title { color:var(--ink); font:12px ui-monospace, monospace; letter-spacing:.08em; text-transform:uppercase; margin-bottom:8px; }
  .mh-web-preview { position:relative; min-height:360px; margin-top:10px; border:1px solid var(--line); border-radius:12px; overflow:hidden; background:#05050a; }
  .mh-web-preview-inner { position:relative; z-index:1; min-height:360px; padding:18px; background:radial-gradient(circle at 22% 18%, var(--mh-a-soft, rgba(255,255,0,.22)), transparent 28%), radial-gradient(circle at 78% 44%, var(--mh-b-soft, rgba(0,0,255,.18)), transparent 26%), #06060c; color:var(--ink); }
  .mh-web-nav { display:flex; align-items:center; justify-content:space-between; gap:12px; border:1px solid rgba(255,255,255,.14); border-radius:999px; padding:10px 12px; background:rgba(0,0,0,.36); font:11px ui-monospace, monospace; }
  .mh-web-logo { color:var(--mh-a, #ffff00); font-weight:700; letter-spacing:.14em; }
  .mh-web-links { display:flex; gap:10px; color:var(--ink-dim); }
  .mh-web-hero { margin-top:18px; display:grid; gap:14px; }
  .mh-web-kicker { color:var(--mh-c, #00ffff); font:10px ui-monospace, monospace; letter-spacing:.18em; text-transform:uppercase; }
  .mh-web-headline { color:#fff; font:700 31px/1.02 ui-monospace, monospace; letter-spacing:.02em; margin:0; }
  .mh-web-copy { color:var(--ink-dim); font:12px/1.55 ui-monospace, monospace; max-width:42em; }
  .mh-web-cta-row { display:flex; gap:10px; flex-wrap:wrap; }
  .mh-web-btn { min-height:44px; display:inline-flex; align-items:center; justify-content:center; border:1px solid var(--mh-a, #ffff00); border-radius:999px; padding:0 14px; color:#05050a; background:var(--mh-a, #ffff00); font:12px ui-monospace, monospace; text-decoration:none; }
  .mh-web-btn.secondary { color:var(--mh-b, #0000ff); background:rgba(0,0,0,.25); border-color:var(--mh-b, #0000ff); }
  .mh-web-card-grid { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:10px; margin-top:16px; }
  .mh-web-card { min-height:98px; border:1px solid rgba(255,255,255,.16); border-radius:12px; background:rgba(255,255,255,.045); padding:12px; font:11px/1.45 ui-monospace, monospace; color:var(--ink-dim); }
  .mh-web-card b { display:block; color:var(--mh-a, #ffff00); margin-bottom:6px; }
  .mh-extra-grid { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:8px; margin-top:10px; }
  .mh-extra-card { border:1px solid rgba(255,255,255,.12); border-radius:10px; padding:10px; min-height:82px; background:rgba(255,255,255,.035); color:var(--ink-dim); font:11px/1.45 ui-monospace, monospace; }
  .mh-extra-card b { color:var(--mh-a, #ffff00); display:block; margin-bottom:5px; }
  @media (max-width:760px){ .mh-suite-tabs { grid-template-columns:repeat(3, minmax(0,1fr)); } .mh-web-card-grid { grid-template-columns:1fr; } }
  .mh-unified-munker {
    margin-top: 10px;
    border: 1px solid rgba(255,255,255,.12);
    border-radius: 10px;
    background: rgba(0,0,0,.18);
    padding: 10px;
  }
  .mh-unified-munker-title {
    display:flex; align-items:center; justify-content:space-between; gap:8px;
    color: var(--ink);
    font: 12px ui-monospace, monospace;
    letter-spacing: .08em;
    text-transform: uppercase;
    margin-bottom: 8px;
  }
  .mh-unified-munker .mh-render-toolbar { margin-top: 6px; }
  .mh-render-toolbar .mh-mini-field {
    min-width: 170px;
    flex: 1;
    color: var(--ink-dim);
    font: 11px ui-monospace, monospace;
    letter-spacing: .02em;
  }
  .mh-render-toolbar .mh-mini-field input { min-width: 120px; width: 100%; margin-top: 5px; }
  .mh-hidden-original-munker { display: none !important; }
  .mh-painter-tip {
    margin-top: 9px;
    border: 1px solid rgba(255,255,255,.12);
    border-left: 3px solid var(--mh-c, #00ffff);
    border-radius: 8px;
    background: rgba(0,0,0,.22);
    padding: 9px 10px;
    color: var(--ink-dim);
    font: 11px/1.45 ui-monospace, monospace;
  }
  .mh-export-panel {
    margin-top: 10px;
    border: 1px solid rgba(255,255,255,.12);
    border-radius: 10px;
    background: rgba(0,0,0,.18);
    padding: 10px;
  }
  .mh-export-title {
    color: var(--ink);
    font: 12px ui-monospace, monospace;
    letter-spacing: .08em;
    text-transform: uppercase;
    margin-bottom: 8px;
  }
  .mh-code-box {
    width: 100%;
    min-height: 160px;
    margin-top: 8px;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: #07070c;
    color: var(--ink);
    padding: 10px;
    font: 11px/1.45 ui-monospace, monospace;
    resize: vertical;
    box-sizing: border-box;
  }
  .mh-export-status { margin-top: 7px; color: var(--ink-dim); font: 11px ui-monospace, monospace; }
  .mh-download-link { color: var(--mh-a, #ffff00); text-decoration: none; border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; min-height: 44px; display: inline-flex; align-items: center; }
  .mh-wheel-readout {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-top: 9px;
    font: 11px ui-monospace, monospace;
    color: var(--ink-dim);
  }
  .mh-wheel-chip { border: 1px solid var(--line); border-radius: 999px; padding: 5px 8px; background: rgba(0,0,0,.22); }
  .mh-target-stage {
    position: relative;
    margin-top: 10px;
    min-height: 360px;
    border: 1px solid var(--line);
    border-radius: 12px;
    overflow: hidden;
    background:
      radial-gradient(circle at 20% 30%, var(--mh-a-soft, rgba(255,255,0,.22)), transparent 24%),
      radial-gradient(circle at 72% 35%, var(--mh-b-soft, rgba(255,0,255,.18)), transparent 28%),
      radial-gradient(circle at 55% 82%, var(--mh-c-soft, rgba(0,255,255,.16)), transparent 26%),
      #07070c;
  }
  .mh-target-frame {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    border: 0;
    filter: saturate(1.35) contrast(1.08) hue-rotate(var(--mh-hue, 0deg));
    opacity: .74;
    background: #fff;
  }
  .mh-target-synthetic {
    position: absolute;
    inset: 0;
    padding: 18px;
    display: grid;
    grid-template-rows: 44px 1fr 70px;
    gap: 14px;
  }
  .mh-urlbar, .mh-block, .mh-card {
    border: 1px solid rgba(255,255,255,.24);
    background: rgba(10,10,16,.56);
    backdrop-filter: blur(2px);
  }
  .mh-urlbar { display: flex; align-items: center; gap: 8px; padding: 0 12px; font: 12px ui-monospace, monospace; color: var(--ink); }
  .mh-dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
  .mh-block { display: grid; grid-template-columns: .9fr 1.1fr; gap: 14px; padding: 14px; }
  .mh-orb { border-radius: 50%; background: var(--mh-a, #00ffff); min-height: 112px; box-shadow: 0 0 32px var(--mh-a-soft, rgba(0,255,255,.55)); }
  .mh-lines { display: grid; gap: 12px; align-content: center; }
  .mh-line { height: 14px; background: #ff00ff; box-shadow: 0 0 18px currentColor; }
  .mh-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
  .mh-card { min-height: 58px; }
  .mh-game-grid {
    position: absolute;
    left: 50%; top: 50%;
    transform: translate(-50%, -50%);
    display: block;
    z-index: 2;
    --mh-hex-size: 34px;
  }
  .mh-game-cell {
    position: absolute;
    width: var(--mh-hex-size);
    height: calc(var(--mh-hex-size) / 0.866);
    clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
    background: transparent;
    filter: drop-shadow(0 10px 12px rgba(0,0,0,.34));
  }
  .mh-game-face {
    position: absolute;
    inset: 0;
    pointer-events: none;
    border: 1px solid rgba(255,255,255,.14);
    background-color: var(--tile-color, #888);
    background-image: var(--munker-pattern, none);
    background-size: var(--munker-tile, auto);
  }
  .mh-game-face-top {
    clip-path: polygon(50% 0%, 100% 25%, 50% 50%, 0% 25%);
    filter: brightness(1.18) saturate(1.08);
  }
  .mh-game-face-left {
    clip-path: polygon(0% 25%, 50% 50%, 50% 100%, 0% 75%);
    filter: brightness(.62) saturate(.9);
  }
  .mh-game-face-bottom {
    clip-path: polygon(50% 50%, 100% 75%, 50% 100%, 0% 75%);
    filter: brightness(.78) saturate(.96);
  }
  .mh-token-layer { position: absolute; inset: 0; pointer-events: none; z-index: 7; }
  .mh-token {
    position: absolute;
    width: calc(var(--mh-token-size, 34px) * .96);
    height: calc(var(--mh-token-size, 34px) * 1.1);
    transform: translate(-50%, -72%);
    clip-path: polygon(50% 0%, 92% 24%, 92% 74%, 50% 100%, 8% 74%, 8% 24%);
    filter: drop-shadow(0 13px 10px rgba(0,0,0,.55));
  }
  .mh-token::before, .mh-token::after { content: ''; position: absolute; inset: 0; pointer-events: none; }
  .mh-token::before {
    background: var(--token-color, #ffff00);
    clip-path: polygon(50% 0%, 92% 24%, 50% 48%, 8% 24%);
    filter: brightness(1.22);
  }
  .mh-token::after {
    background-image: var(--munker-pattern, none);
    background-size: var(--munker-tile, auto);
    mix-blend-mode: screen;
    opacity: .86;
  }
  .mh-token.enemy { --token-color: var(--mh-b, #ff00ff); }
  .mh-token.player { --token-color: var(--mh-a, #ffff00); }
  .mh-token.pickup { --token-color: var(--mh-c, #00ffff); transform: translate(-50%, -62%) scale(.72); }
  .mh-ruliad-field, .mh-artifact-field { position: absolute; inset: 0; pointer-events: none; overflow: hidden; }
  .mh-ruliad-field { z-index: 5; mix-blend-mode: screen; opacity: .72; }
  .mh-ruliad-node {
    position: absolute;
    width: 7px; height: 7px;
    border-radius: 999px;
    transform: translate(-50%, -50%);
    background: var(--node-color, var(--mh-a, #ffff00));
    box-shadow: 0 0 12px currentColor;
  }
  .mh-ruliad-link {
    position: absolute;
    height: 1px;
    transform-origin: 0 50%;
    background: linear-gradient(90deg, transparent, var(--link-color, var(--mh-c, #00ffff)), transparent);
    opacity: .62;
  }
  .mh-artifact-field { z-index: 6; mix-blend-mode: screen; opacity: var(--mh-opacity, 1); }
  .mh-artifact-line {
    position: absolute;
    left: -20%;
    width: 140%;
    height: var(--line-h, 3px);
    top: var(--line-y, 0px);
    transform: rotate(var(--line-angle, -28deg));
    background: var(--line-color, rgba(255,255,255,.92));
    box-shadow: 0 0 9px var(--line-color, rgba(255,255,255,.92));
  }
  .mh-stage-label { position: absolute; left: 12px; bottom: 10px; z-index: 8; font: 11px ui-monospace, monospace; color: var(--ink); background: rgba(0,0,0,.62); border: 1px solid var(--line); border-radius: 999px; padding: 7px 10px; }
  .mh-munker-field, .mh-hex-field { position: absolute; inset: -60px; pointer-events: none; z-index: 4; }
  .mh-munker-field {
    opacity: var(--mh-opacity, 1);
    background: repeating-linear-gradient(var(--mh-angle, 135deg), var(--mh-a, #ffff00) 0 var(--mh-thick, 5px), var(--mh-b, #ff00ff) var(--mh-thick, 5px) calc(var(--mh-thick, 5px) + var(--mh-gap, 10px)));
    mix-blend-mode: screen;
    animation: mh-pan var(--mh-speed, 4s) linear infinite alternate;
  }
  .mh-hex-field {
    opacity: .42;
    background-image:
      linear-gradient(30deg, transparent 24%, var(--mh-a-grid, rgba(0,255,255,.45)) 25%, var(--mh-a-grid, rgba(0,255,255,.45)) 26%, transparent 27%, transparent 74%, var(--mh-b-grid, rgba(255,0,255,.45)) 75%, var(--mh-b-grid, rgba(255,0,255,.45)) 76%, transparent 77%),
      linear-gradient(150deg, transparent 24%, var(--mh-c-grid, rgba(255,255,0,.38)) 25%, var(--mh-c-grid, rgba(255,255,0,.38)) 26%, transparent 27%, transparent 74%, var(--mh-a-grid, rgba(0,255,255,.38)) 75%, var(--mh-a-grid, rgba(0,255,255,.38)) 76%, transparent 77%);
    background-size: 52px 30px;
    mix-blend-mode: screen;
  }
  @keyframes mh-pan { from { transform: translate3d(-26px,-18px,0); } to { transform: translate3d(26px,18px,0); } }
  @media (max-width: 760px) {
    .mh-render-adapter { margin: 8px; padding: 10px; }
    .mh-target-stage { min-height: 430px; }
    .mh-block { grid-template-columns: 1fr; }
    .mh-cards { grid-template-columns: repeat(2, 1fr); }
  }
</style>
<section class="mh-render-adapter" id="mhRenderAdapter">
  <h2>Render target · website/game through original Munker + hex grid</h2>
  <div class="mh-suite-tabs" id="mhSuiteTabs">
    <button class="mh-suite-tab active" data-suite-tab="web">Web</button>
    <button class="mh-suite-tab" data-suite-tab="game">Game</button>
    <button class="mh-suite-tab" data-suite-tab="character">Character</button>
    <button class="mh-suite-tab" data-suite-tab="gif">GIF</button>
    <button class="mh-suite-tab" data-suite-tab="qr">QR</button>
  </div>
  <div class="mh-builder-panel active" id="mhBuilderWeb">
    <div class="mh-builder-title">Webpage style designer · presets + CSS/JS export</div>
    <div class="mh-render-toolbar">
      <select id="mhWebPreset">
        <option value="landing">Preset · landing page hero</option>
        <option value="theme-kit">Preset · full website theme kit</option>
        <option value="overlay-plugin">Preset · overlay plugin for existing site</option>
        <option value="portfolio">Preset · creator portfolio</option>
        <option value="shop">Preset · product/shop launch</option>
      </select>
      <select id="mhWebDensity">
        <option value="clean">Clean</option>
        <option value="rich" selected>Rich</option>
        <option value="maximal">Maximal Munker</option>
      </select>
      <button id="mhGenerateWebBtn">Generate webpage style</button>
    </div>
    <div class="mh-web-preview" id="mhWebPreview">
      <div class="mh-web-preview-inner" id="mhWebPreviewInner"></div>
      <div class="mh-hex-field"></div>
      <div class="mh-ruliad-field" id="mhWebRuliadField"></div>
      <div class="mh-artifact-field" id="mhWebArtifactField"></div>
    </div>
  </div>
  <div class="mh-builder-panel" id="mhBuilderGame">
    <div class="mh-builder-title">Platform game designer · simple playable scene builder</div>
    <div class="mh-render-toolbar"><button id="mhGameBuilderBtn">Generate scene in render stage</button><span class="mh-export-status">Hex level, player, enemies, collectibles, and Munker ground use current palette.</span></div>
  </div>
  <div class="mh-builder-panel" id="mhBuilderCharacter">
    <div class="mh-builder-title">Character designer · player/enemy tokens</div>
    <div class="mh-extra-grid" id="mhCharacterPreview"></div>
  </div>
  <div class="mh-builder-panel" id="mhBuilderGif">
    <div class="mh-builder-title">GIF designer · timeline presets</div>
    <div class="mh-render-toolbar"><button id="mhGifDesignerBtn">Use current render for GIF</button><span class="mh-export-status">Exports through Website-builder export panel below.</span></div>
  </div>
  <div class="mh-builder-panel" id="mhBuilderQr">
    <div class="mh-builder-title">QR code designer · coming next</div>
    <div class="mh-extra-grid" id="mhQrPreview"><div class="mh-extra-card"><b>Styled QR</b>Palette + Munker-safe QR export will use readable contrast and your ruliad border.</div><div class="mh-extra-card"><b>Extras</b>Palette marketplace/library, social banner/avatar, card collectibles, sticker/poster packs.</div></div>
  </div>
  <div class="mh-render-toolbar">
    <input id="mhUrl" value="https://example.com" placeholder="https://your-site.com" />
    <select id="mhGame">
      <option value="website">Website URL render</option>
      <option value="invaders">Game render · arcade invaders</option>
      <option value="platformer">Game render · platformer</option>
      <option value="maze">Game render · puzzle maze</option>
    </select>
    <select id="mhGameStyle">
      <option value="hex3plane">Style · top-down 3-plane cube hex ground</option>
    </select>
    <button id="mhRenderBtn">Render with this style</button>
  </div>
  <div class="mh-unified-munker" id="mhUnifiedMunker">
    <div class="mh-unified-munker-title">
      <span>Unified Munker generator</span>
      <span id="mhAutoState">auto animate · on</span>
    </div>
    <div class="mh-render-toolbar">
      <select id="mhMunkerPreset">
        <option value="white-ruliad">Auto pattern · white ruliad artefacts</option>
        <option value="cool-dark-vibration">Auto pattern · cool dark vibration</option>
        <option value="hex-scanline">Auto pattern · hex cube scanline</option>
        <option value="palette-crosshatch">Auto pattern · palette crosshatch</option>
        <option value="thin-web-render">Auto pattern · thin website render</option>
      </select>
      <select id="mhUnifiedMode">
        <option value="diag" selected>Diagonal</option>
        <option value="grid">Grid cross-hatch</option>
        <option value="h">Horizontal</option>
        <option value="v">Vertical</option>
      </select>
      <select id="mhUnifiedPattern">
        <option value="white" selected>White artefact lines</option>
        <option value="bw">Alternating B / W</option>
        <option value="AB">Alternating A / B</option>
        <option value="A">Lines = selected hue</option>
        <option value="B">Lines = complement hue</option>
      </select>
      <select id="mhAutoAnimate">
        <option value="on" selected>Auto animate on</option>
        <option value="off">Auto animate off</option>
      </select>
    </div>
    <div class="mh-render-toolbar">
      <label class="mh-mini-field">Spacing <span id="mhUnifiedSpacingv">10</span>px
        <input id="mhUnifiedSpacing" type="range" min="0" max="40" value="10" />
      </label>
      <label class="mh-mini-field">Line thickness <span id="mhLineThicknessv">5</span>px
        <input id="mhLineThickness" type="range" min="1" max="40" value="5" />
      </label>
      <label class="mh-mini-field">Opacity <span id="mhUnifiedOpacityv">100</span>%
        <input id="mhUnifiedOpacity" type="range" min="0" max="100" value="100" />
      </label>
      <label class="mh-mini-field">Speed <span id="mhUnifiedSpeedv">4</span>s
        <input id="mhUnifiedSpeed" type="range" min="1" max="16" value="4" />
      </label>
    </div>
  </div>
  <div class="mh-painter-tip" id="mhPainterTip">Painter tip: use cool CMY-side dark vibration; avoid cad red in shadows. Let uneven Munker white spacing create optical colour instead of forcing pigment.</div>
  <div class="mh-export-panel" id="mhExportPanel">
    <div class="mh-export-title">Website-builder export · exact current palette</div>
    <div class="mh-render-toolbar">
      <button id="mhGenerateCodeBtn">Generate embed code</button>
      <button id="mhCopyCodeBtn">Copy code</button>
      <button id="mhExportGifBtn">Export animated GIF</button>
      <a id="mhGifDownload" class="mh-download-link" download="munkerhex-render.gif" style="display:none">Download GIF</a>
    </div>
    <textarea id="mhBuilderCode" class="mh-code-box" readonly placeholder="Generated website-builder CSS/JS appears here. Paste it into Webflow, Framer, Shopify, Squarespace custom code, or your site builder header/body embed."></textarea>
    <div class="mh-export-status" id="mhExportStatus">Ready to export the exact calibrated palette + Munker render.</div>
  </div>
  <div class="mh-wheel-readout" id="mhWheelReadout">
    <span class="mh-wheel-chip">A #ffff00</span>
    <span class="mh-wheel-chip">B #0000ff</span>
    <span class="mh-wheel-chip">centre #808080</span>
  </div>
  <p class="hint" style="margin:8px 0 0">This keeps your original studio below. The target stage uses the same animated Munker controls and hex/cube colour system instead of replacing it.</p>
  <div class="mh-target-stage" id="mhTargetStage">
    <iframe class="mh-target-frame" id="mhFrame" src="site-html?url=https%3A%2F%2Fexample.com" title="Website render target"></iframe>
    <div class="mh-target-synthetic" id="mhSynthetic">
      <div class="mh-urlbar"><span class="mh-dot"></span><span class="mh-dot"></span><span class="mh-dot"></span><span id="mhHostLabel">example.com</span></div>
      <div class="mh-block"><div class="mh-orb"></div><div class="mh-lines"><div class="mh-line" style="width:86%"></div><div class="mh-line" style="width:62%"></div><div class="mh-line" style="width:74%"></div></div></div>
      <div class="mh-cards"><div class="mh-card"></div><div class="mh-card"></div><div class="mh-card"></div><div class="mh-card"></div></div>
    </div>
    <div class="mh-game-grid" id="mhGameGrid" style="display:none"></div>
    <div class="mh-token-layer" id="mhTokenLayer"></div>
    <div class="mh-hex-field"></div>
    <div class="mh-munker-field" id="mhMunkerField"></div>
    <div class="mh-ruliad-field" id="mhRuliadField"></div>
    <div class="mh-artifact-field" id="mhArtifactField"></div>
    <div class="mh-stage-label" id="mhStageLabel">website · original Munker overlay active</div>
  </div>
</section>
<script id="munkerhex-render-adapter-js">
(function(){
  const $ = (id) => document.getElementById(id);
  const stage = $('mhTargetStage');
  const frame = $('mhFrame');
  const synthetic = $('mhSynthetic');
  const grid = $('mhGameGrid');
  const tokenLayer = $('mhTokenLayer');
  const ruliadField = $('mhRuliadField');
  const artifactField = $('mhArtifactField');
  const label = $('mhStageLabel');
  const hostLabel = $('mhHostLabel');
  let renderPalette = ['#ffff00','#ff00ff','#00ffff','#ff3131','#39ff14','#0000ff'];
  function safeUrl(value){ const v=(value||'').trim(); if(!v) return 'https://example.com'; return /^https?:\/\//i.test(v) ? v : 'https://' + v; }
  function host(value){ try { return new URL(safeUrl(value)).host.replace(/^www\./,''); } catch(e){ return 'target.site'; } }
  function rgba(rgb, alpha){ return `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${alpha})`; }
  function fallbackHex(rgb){ return '#' + rgb.map(v => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join(''); }
  function toHex(rgb){ try { return rgbToHex(rgb); } catch(e) { return fallbackHex(rgb); } }
  function getWheelPalette(){
    let hue = 90, tone = 50;
    let a = [255,255,0], b = [0,0,255], centre = [128,128,128];
    let colors = ['#ffff00','#ff00ff','#00ffff','#ff3131','#39ff14','#0000ff'];
    try {
      if (typeof state !== 'undefined') { hue = state.hue; tone = state.tone; }
      if (typeof rgbAt === 'function') {
        a = rgbAt(hue, tone);
        b = rgbAt(typeof additiveComplementHue === 'function' ? additiveComplementHue(hue) : hue + 180, tone);
      }
      if (typeof currentCentre === 'function') centre = currentCentre();
      else if (typeof tonalCentre === 'function') centre = tonalCentre(a, b, 'mean', 50);
      if (typeof calibratedAnchors === 'function' && typeof rgbAt === 'function') {
        colors = calibratedAnchors().map(anchor => toHex(rgbAt(anchor.a, 50)));
      } else {
        colors = [toHex(a), '#ff00ff', '#00ffff', '#ff3131', '#39ff14', toHex(b)];
      }
    } catch(e) {
      const hex = $('hexIn') ? $('hexIn').value : '#ffff00';
      colors[0] = hex || colors[0];
    }
    return { hue, tone, a, b, centre, aHex: toHex(a), bHex: toHex(b), cHex: toHex(centre), colors };
  }
  function syncLineThickness(value, updateOriginal){
    const n = Math.max(1, Math.min(40, parseInt(value || '5', 10)));
    const top = $('mhLineThickness');
    const topV = $('mhLineThicknessv');
    if (top) top.value = String(n);
    if (topV) topV.textContent = String(n);
    if (updateOriginal && $('munkerThick')) {
      $('munkerThick').value = String(Math.min(20, n));
      if ($('munkerThickv')) $('munkerThickv').textContent = String(Math.min(20, n));
      if (typeof munker !== 'undefined') munker.thick = Math.min(20, n);
      $('munkerThick').dispatchEvent(new Event('input', { bubbles: true }));
    }
    stage.style.setProperty('--mh-thick', n + 'px');
  }
  const MUNKER_PRESETS = {
    'white-ruliad': { mode:'diag', pattern:'white', spacing:3, thickness:13, opacity:96, speed:4, animate:'on' },
    'cool-dark-vibration': { mode:'grid', pattern:'bw', spacing:2, thickness:7, opacity:88, speed:6, animate:'on' },
    'hex-scanline': { mode:'v', pattern:'AB', spacing:1, thickness:5, opacity:82, speed:5, animate:'on' },
    'palette-crosshatch': { mode:'grid', pattern:'AB', spacing:5, thickness:9, opacity:92, speed:7, animate:'on' },
    'thin-web-render': { mode:'diag', pattern:'white', spacing:8, thickness:3, opacity:74, speed:8, animate:'on' },
  };
  function setVal(id, value, dispatch = false){
    const el = $(id); if (!el) return;
    el.value = String(value);
    if (dispatch) el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
  }
  function setText(id, value){ const el = $(id); if (el) el.textContent = String(value); }
  function currentUnifiedMunker(){
    return {
      mode: $('mhUnifiedMode')?.value || 'diag',
      pattern: $('mhUnifiedPattern')?.value || 'white',
      spacing: parseInt($('mhUnifiedSpacing')?.value || '10', 10),
      thickness: parseInt($('mhLineThickness')?.value || '5', 10),
      opacity: parseInt($('mhUnifiedOpacity')?.value || '100', 10),
      speed: parseInt($('mhUnifiedSpeed')?.value || '4', 10),
      animate: $('mhAutoAnimate')?.value || 'on',
    };
  }
  function exportPayload(){
    const p = getWheelPalette();
    const u = currentUnifiedMunker();
    return {
      a_hex: p.aHex,
      b_hex: p.bHex,
      centre_hex: p.cHex,
      colors: renderPalette.length ? renderPalette : [p.aHex, p.bHex, p.cHex],
      hue: Math.round(p.hue),
      tone: Math.round(p.tone),
      preset: $('mhMunkerPreset')?.value || 'custom',
      mode: u.mode,
      pattern: u.pattern,
      spacing: u.spacing,
      thickness: u.thickness,
      opacity: u.opacity,
      speed: u.speed,
      width: 390,
      height: 430,
    };
  }
  function websiteBuilderCode(){
    const p = getWheelPalette();
    const u = currentUnifiedMunker();
    const web = currentWebDesign();
    const angle = u.mode === 'h' ? '0deg' : u.mode === 'v' ? '90deg' : u.mode === 'grid' ? '45deg' : '-28deg';
    const palette = (renderPalette.length ? renderPalette : [p.aHex, p.bHex, p.cHex]).join(', ');
    return `<!-- MunkerHex exact palette render for website builders -->
<!-- preset:${web.preset}; density:${web.density}; palette:${palette} -->
<style id="munkerhex-builder-style">
  :root {
    --mh-a: ${p.aHex};
    --mh-b: ${p.bHex};
    --mh-centre: ${p.cHex};
    --mh-palette: ${palette};
    --mh-angle: ${angle};
    --mh-spacing: ${u.spacing}px;
    --mh-thickness: ${u.thickness}px;
    --mh-opacity: ${(u.opacity / 100).toFixed(2)};
    --mh-speed: ${u.speed}s;
  }
  html, body { background:#05050a; }
  body { color: var(--mh-centre); filter: saturate(1.22) contrast(1.05) hue-rotate(${Math.round(p.hue)}deg); }
  .munkerhex-section { min-height:100vh; padding:clamp(32px,8vw,96px); background:radial-gradient(circle at 20% 20%, var(--mh-a), transparent 22%), radial-gradient(circle at 78% 40%, var(--mh-b), transparent 24%), #05050a; color:white; }
  .munkerhex-card { border:1px solid color-mix(in srgb, var(--mh-a), white 20%); border-radius:18px; background:rgba(255,255,255,.055); padding:24px; backdrop-filter:blur(8px); }
  .munkerhex-button { display:inline-flex; min-height:44px; align-items:center; border-radius:999px; padding:0 18px; background:var(--mh-a); color:#05050a; text-decoration:none; }
  h1,h2,h3,h4,strong,b { color: var(--mh-a); text-shadow: 0 0 12px color-mix(in srgb, var(--mh-a), transparent 55%); }
  a, button { color: var(--mh-b); }
  .munkerhex-overlay, .munkerhex-hex, .munkerhex-ruliad { position:fixed; inset:0; pointer-events:none; z-index:2147483000; }
  .munkerhex-overlay { opacity:var(--mh-opacity); mix-blend-mode:screen; background:repeating-linear-gradient(var(--mh-angle), rgba(255,255,255,.9) 0 var(--mh-thickness), transparent var(--mh-thickness) calc(var(--mh-thickness) + var(--mh-spacing))); animation:munkerhex-pan var(--mh-speed) linear infinite alternate; }
  .munkerhex-hex { opacity:.34; mix-blend-mode:screen; background-image:linear-gradient(30deg, transparent 24%, var(--mh-a) 25%, var(--mh-a) 26%, transparent 27%, transparent 74%, var(--mh-b) 75%, var(--mh-b) 76%, transparent 77%), linear-gradient(150deg, transparent 24%, var(--mh-centre) 25%, var(--mh-centre) 26%, transparent 27%, transparent 74%, var(--mh-a) 75%, var(--mh-a) 76%, transparent 77%); background-size:52px 30px; }
  .munkerhex-ruliad { opacity:.42; mix-blend-mode:screen; background:radial-gradient(circle at 20% 22%, var(--mh-a), transparent 1.2%), radial-gradient(circle at 72% 34%, var(--mh-b), transparent 1.1%), radial-gradient(circle at 46% 78%, var(--mh-centre), transparent 1.3%); background-size:88px 88px, 110px 110px, 72px 72px; }
  @keyframes munkerhex-pan { from { transform:translate3d(-18px,-12px,0); } to { transform:translate3d(18px,12px,0); } }
</style>
<script>
(function(){
  ['munkerhex-overlay','munkerhex-hex','munkerhex-ruliad'].forEach(function(cls){
    if(!document.querySelector('.'+cls)){ var el=document.createElement('div'); el.className=cls; document.body.appendChild(el); }
  });
})();
<` + `/script>`;
  }
  function updateBuilderCode(){
    const box = $('mhBuilderCode');
    if (!box) return;
    box.value = websiteBuilderCode();
    const status = $('mhExportStatus');
    if (status) status.textContent = 'Code generated for exact palette: ' + getWheelPalette().aHex + ' → ' + getWheelPalette().bHex;
  }
  function currentWebDesign(){
    return {
      preset: $('mhWebPreset')?.value || 'landing',
      density: $('mhWebDensity')?.value || 'rich',
    };
  }
  function webPresetContent(preset){
    const map = {
      landing: {
        kicker:'MUNKERHEX WEBSITE BUILDER', headline:'A live palette render system for impossible web surfaces.',
        copy:'Generate a hero section, buttons, cards and animated overlays from the exact colour wheel calibration.',
        cards:['Hero layout','CTA buttons','Animated background']
      },
      'theme-kit': {
        kicker:'FULL WEBSITE THEME KIT', headline:'Navigation, cards, sections and buttons from one calibrated palette.',
        copy:'Use this as a complete visual kit for Webflow, Framer, Shopify, Squarespace or custom CSS.',
        cards:['Navigation','Card system','Section backgrounds']
      },
      'overlay-plugin': {
        kicker:'OVERLAY PLUGIN', headline:'Drop the MunkerHex render over an existing website.',
        copy:'Paste the exported code into a site builder custom-code area and the whole page gets palette/ruliad overlays.',
        cards:['Global overlay','Hex field','Ruliad nodes']
      },
      portfolio: {
        kicker:'CREATOR PORTFOLIO', headline:'Turn case studies into glowing palette artefacts.',
        copy:'Portfolio cards, avatar blocks and project tiles follow your live CMY calibration.',
        cards:['Project cards','Avatar block','Contact CTA']
      },
      shop: {
        kicker:'PRODUCT LAUNCH', headline:'A shop landing page with collectible visual energy.',
        copy:'Product cards, checkout CTA and banner surfaces inherit the exact MunkerHex palette.',
        cards:['Product cards','Offer banner','Checkout CTA']
      }
    };
    return map[preset] || map.landing;
  }
  function renderWebDesigner(){
    const p = getWheelPalette();
    const web = currentWebDesign();
    const content = webPresetContent(web.preset);
    const inner = $('mhWebPreviewInner');
    if (!inner) return;
    const cardCount = web.density === 'clean' ? 2 : web.density === 'maximal' ? 6 : 3;
    const cards = Array.from({ length: cardCount }, (_, i) => `<div class="mh-web-card"><b>${content.cards[i % content.cards.length]}</b>${['Palette-calibrated typography','Munker-safe contrast','Ruliad pattern surface','Export-ready CSS','Animated line field','3-plane hex depth'][i % 6]}</div>`).join('');
    inner.innerHTML = `
      <nav class="mh-web-nav"><span class="mh-web-logo">MUNKERHEX</span><span class="mh-web-links"><span>Work</span><span>Style</span><span>Export</span></span></nav>
      <section class="mh-web-hero">
        <div class="mh-web-kicker">${content.kicker}</div>
        <h1 class="mh-web-headline">${content.headline}</h1>
        <p class="mh-web-copy">${content.copy}</p>
        <div class="mh-web-cta-row"><a class="mh-web-btn">Build style</a><a class="mh-web-btn secondary">Copy code</a></div>
        <div class="mh-web-card-grid">${cards}</div>
      </section>`;
    const webR = $('mhWebRuliadField');
    const oldR = ruliadField;
    if (webR) {
      const save = ruliadField.innerHTML;
      webR.innerHTML = '';
      const rand = seededRand('web-designer-' + web.preset + p.aHex + p.bHex);
      for (let i=0;i<28;i++) {
        const node = document.createElement('div'); node.className='mh-ruliad-node';
        node.style.left = (8 + rand()*84) + '%'; node.style.top = (12 + rand()*72) + '%';
        const color = renderPalette[i % renderPalette.length]; node.style.setProperty('--node-color', color); node.style.color=color; webR.appendChild(node);
      }
    }
    const webA = $('mhWebArtifactField');
    if (webA) { webA.innerHTML = artifactField.innerHTML; }
    updateBuilderCode();
  }
  function switchSuiteTab(tab){
    document.querySelectorAll('.mh-suite-tab').forEach(btn => btn.classList.toggle('active', btn.dataset.suiteTab === tab));
    ['web','game','character','gif','qr'].forEach(name => {
      const panel = $('mhBuilder' + name.charAt(0).toUpperCase() + name.slice(1));
      if (panel) panel.classList.toggle('active', name === tab);
    });
    if (tab === 'web') renderWebDesigner();
    if (tab === 'game') { setVal('mhGame','platformer'); render(); }
    if (tab === 'character') renderCharacterDesigner();
    if (tab === 'gif') updateBuilderCode();
  }
  function renderCharacterDesigner(){
    const target = $('mhCharacterPreview'); if (!target) return;
    const p = getWheelPalette();
    target.innerHTML = ['Player token','Enemy token','Pickup token','Boss token'].map((label,i) => `<div class="mh-extra-card"><b>${label}</b><span style="display:inline-block;width:42px;height:48px;clip-path:polygon(50% 0%,92% 24%,92% 74%,50% 100%,8% 74%,8% 24%);background:${[p.aHex,p.bHex,p.cHex,renderPalette[2] || p.aHex][i]};box-shadow:0 0 18px ${[p.aHex,p.bHex,p.cHex,renderPalette[2] || p.aHex][i]};"></span><br/>Generated from exact palette + Munker field.</div>`).join('');
  }
  async function copyBuilderCode(){
    updateBuilderCode();
    const text = $('mhBuilderCode')?.value || '';
    try {
      if (navigator.clipboard) await navigator.clipboard.writeText(text);
      else { $('mhBuilderCode').select(); document.execCommand('copy'); }
      if ($('mhExportStatus')) $('mhExportStatus').textContent = 'Website-builder code copied.';
    } catch(e) {
      if ($('mhExportStatus')) $('mhExportStatus').textContent = 'Copy blocked — select the code and copy manually.';
    }
  }
  async function exportGif(){
    const status = $('mhExportStatus');
    try {
      if (status) status.textContent = 'Rendering animated GIF…';
      const response = await fetch('export-gif', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(exportPayload()),
      });
      if (!response.ok) throw new Error(await response.text());
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = $('mhGifDownload');
      link.href = url;
      link.style.display = 'inline-flex';
      link.download = `munkerhex-${Date.now()}.gif`;
      if (status) status.textContent = 'GIF ready — tap Download GIF.';
    } catch(e) {
      if (status) status.textContent = 'GIF export failed: ' + (e.message || e);
    }
  }
  function syncUnifiedLabels(){
    setText('mhUnifiedSpacingv', $('mhUnifiedSpacing')?.value || 10);
    setText('mhLineThicknessv', $('mhLineThickness')?.value || 5);
    setText('mhUnifiedOpacityv', $('mhUnifiedOpacity')?.value || 100);
    setText('mhUnifiedSpeedv', $('mhUnifiedSpeed')?.value || 4);
    setText('mhAutoState', $('mhAutoAnimate')?.value === 'on' ? 'auto animate · on' : 'auto animate · off');
  }
  function pushUnifiedToOriginal(){
    const u = currentUnifiedMunker();
    setVal('munkerMode', u.mode);
    setVal('munkerPattern', u.pattern);
    setVal('munkerSpacing', u.spacing);
    setVal('munkerThick', Math.min(20, u.thickness));
    setVal('munkerOpacity', u.opacity);
    setVal('munkerSpeed', u.speed);
    setVal('munkerAnimate', u.animate === 'on' ? (u.mode === 'v' ? 'v' : u.mode === 'h' ? 'h' : 'diag') : 'off');
    setText('munkerSpacingv', u.spacing);
    setText('munkerThickv', Math.min(20, u.thickness));
    setText('munkerOpacityv', u.opacity);
    setText('munkerSpeedv', u.speed);
    if (typeof munker !== 'undefined') {
      munker.mode = u.mode; munker.pattern = u.pattern; munker.spacing = u.spacing;
      munker.thick = Math.min(20, u.thickness); munker.opacity = u.opacity;
      munker.animate = u.animate === 'on' ? (u.mode === 'v' ? 'v' : u.mode === 'h' ? 'h' : 'diag') : 'off';
      munker.speed = u.speed;
    }
    syncUnifiedLabels();
  }
  function applyMunkerPreset(name){
    const preset = MUNKER_PRESETS[name] || MUNKER_PRESETS['white-ruliad'];
    setVal('mhUnifiedMode', preset.mode);
    setVal('mhUnifiedPattern', preset.pattern);
    setVal('mhUnifiedSpacing', preset.spacing);
    setVal('mhLineThickness', preset.thickness);
    setVal('mhUnifiedOpacity', preset.opacity);
    setVal('mhUnifiedSpeed', preset.speed);
    setVal('mhAutoAnimate', preset.animate);
    pushUnifiedToOriginal();
    syncMunker();
    render();
  }
  function painterTip(p){
    const tip = $('mhPainterTip');
    if (!tip) return;
    const tone = Math.round(p.tone);
    const advice = tone < 45
      ? 'Darks: keep vibration on the cool CMY side (cyan/blue/violet). Do not reach for cad red; neutralise with cool complement and let Munker white do the optical lift.'
      : tone > 65
        ? 'Lights: avoid killing chroma with opaque white. Use thin glaze logic—let spacing/thickness reveal the light through the palette.'
        : 'Mids: mix toward the tonal centre first, then use uneven white stripes as optical artefacts instead of adding muddy pigment.';
    tip.textContent = 'Painter tip: ' + advice;
  }
  function applyRenderPalette(){
    const p = getWheelPalette();
    renderPalette = [p.aHex, ...p.colors.slice(0, 4), p.bHex, p.cHex];
    stage.style.setProperty('--mh-hue', `${Math.round(p.hue)}deg`);
    stage.style.setProperty('--mh-a', p.aHex);
    stage.style.setProperty('--mh-b', p.bHex);
    stage.style.setProperty('--mh-c', p.cHex);
    stage.style.setProperty('--mh-a-soft', rgba(p.a, .25));
    stage.style.setProperty('--mh-b-soft', rgba(p.b, .22));
    stage.style.setProperty('--mh-c-soft', rgba(p.centre, .24));
    stage.style.setProperty('--mh-a-grid', rgba(p.a, .46));
    stage.style.setProperty('--mh-b-grid', rgba(p.b, .46));
    stage.style.setProperty('--mh-c-grid', rgba(p.centre, .42));
    document.querySelectorAll('.mh-dot').forEach((el, i) => { el.style.background = [p.aHex, p.cHex, p.bHex][i % 3]; });
    document.querySelectorAll('.mh-line').forEach((el, i) => {
      const color = [p.aHex, p.bHex, p.cHex][i % 3];
      el.style.background = color; el.style.color = color;
    });
    document.querySelectorAll('.mh-card').forEach((el, i) => {
      el.style.borderColor = renderPalette[i % renderPalette.length];
      el.style.background = rgba([p.a, p.b, p.centre][i % 3], .12);
    });
    document.querySelectorAll('.mh-game-cell').forEach((el, i) => {
      el.style.setProperty('--tile-color', renderPalette[(i + ($('mhGame')?.value === 'platformer' ? 2 : 0)) % renderPalette.length]);
    });
    const readout = $('mhWheelReadout');
    if (readout) {
      readout.innerHTML = `<span class="mh-wheel-chip">A ${p.aHex} · ${Math.round(p.hue)}°</span><span class="mh-wheel-chip">B ${p.bHex}</span><span class="mh-wheel-chip">centre ${p.cHex}</span><span class="mh-wheel-chip">tone ${Math.round(p.tone)}</span>`;
    }
    painterTip(p);
    styleWholeWebsiteFrame();
    updateBuilderCode();
    return p;
  }
  function seededRand(seedText){
    let seed = 0;
    for (let i = 0; i < seedText.length; i++) seed = ((seed << 5) - seed + seedText.charCodeAt(i)) | 0;
    return function(){ seed = (seed * 1664525 + 1013904223) | 0; return ((seed >>> 0) % 10000) / 10000; };
  }
  function buildArtifactField(seedKey){
    if (!artifactField) return;
    const p = getWheelPalette();
    artifactField.innerHTML = '';
    const rand = seededRand(seedKey + p.aHex + p.bHex + ($('mhLineThickness')?.value || '5'));
    const baseThick = Math.max(1, Math.min(40, parseInt($('mhLineThickness')?.value || '5', 10)));
    const u = currentUnifiedMunker();
    const spacing = Math.max(0, parseInt(String(u.spacing), 10));
    const mode = u.mode;
    const angle = mode === 'h' ? '0deg' : mode === 'v' ? '90deg' : mode === 'grid' ? '-18deg' : '-28deg';
    const lines = Math.max(16, Math.min(52, Math.round(430 / Math.max(4, spacing + baseThick)) + 10));
    for (let i = 0; i < lines; i++) {
      const line = document.createElement('div');
      line.className = 'mh-artifact-line';
      const uneven = Math.max(1, baseThick * (0.48 + rand() * 1.55));
      const y = -80 + i * (spacing + baseThick + rand() * 8) + rand() * 10;
      const colors = ['rgba(255,255,255,.94)', p.aHex, p.bHex, p.cHex, 'rgba(255,255,255,.72)'];
      const color = colors[(i + Math.floor(rand() * colors.length)) % colors.length];
      line.style.setProperty('--line-h', uneven.toFixed(1) + 'px');
      line.style.setProperty('--line-y', y.toFixed(1) + 'px');
      line.style.setProperty('--line-angle', angle);
      line.style.setProperty('--line-color', color);
      artifactField.appendChild(line);
    }
  }
  function buildRuliadField(seedKey){
    if (!ruliadField) return;
    const p = getWheelPalette();
    ruliadField.innerHTML = '';
    const rand = seededRand(seedKey + p.aHex + p.bHex + p.cHex);
    const rect = stage.getBoundingClientRect();
    const W = Math.max(300, rect.width || 360);
    const H = Math.max(320, rect.height || 430);
    const metrics = groundMetrics();
    const N = metrics.N;
    const nodes = [];
    for (let row = 0; row < N; row++) {
      const rowOffset = row % 2 ? 0.5 : 0;
      for (let col = 0; col < N; col++) {
        const x = W * (0.12 + (col + rowOffset) / (N + .6) * .76) + (rand() - .5) * 10;
        const y = H * (0.18 + row / Math.max(1, N - 1) * .64) + (rand() - .5) * 12;
        nodes.push({ x, y, color: renderPalette[(row + col) % renderPalette.length] });
      }
    }
    nodes.forEach((a, i) => {
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        const d = Math.hypot(a.x - b.x, a.y - b.y);
        if (d < W / (N * 1.15) && rand() > .22) {
          const link = document.createElement('div');
          link.className = 'mh-ruliad-link';
          link.style.left = a.x + 'px'; link.style.top = a.y + 'px';
          link.style.width = d + 'px';
          link.style.transform = `rotate(${Math.atan2(b.y - a.y, b.x - a.x)}rad)`;
          link.style.setProperty('--link-color', i % 2 ? p.aHex : p.cHex);
          ruliadField.appendChild(link);
        }
      }
    });
    nodes.forEach((n, i) => {
      const node = document.createElement('div');
      node.className = 'mh-ruliad-node';
      node.style.left = n.x + 'px'; node.style.top = n.y + 'px';
      node.style.setProperty('--node-color', n.color);
      node.style.color = n.color;
      ruliadField.appendChild(node);
    });
  }
  function groundMetrics(){
    let size = 34, gap = 3, N = 7;
    try {
      if (typeof cubeState !== 'undefined') { size = cubeState.size || size; gap = cubeState.gap || gap; }
      if (typeof cubeStepCount === 'function') N = cubeStepCount();
    } catch(e) {}
    const hexW = Math.max(18, Math.min(56, parseInt(size, 10) || 34));
    const hexH = hexW / 0.866;
    const rowStep = hexH * 0.75 + Math.max(0, Math.min(20, gap)) * 0.65;
    const colStep = hexW + Math.max(0, Math.min(20, gap));
    return { size: hexW, gap, N: Math.max(4, Math.min(9, N)), hexW, hexH, rowStep, colStep };
  }
  function colorForGroundCell(xi, yi, kind, p, N){
    try {
      const hue = (p.hue + (xi / Math.max(1, N - 1)) * 150 + (kind === 'maze' ? yi * 13 : yi * 7)) % 360;
      const tone = 32 + (yi / Math.max(1, N - 1)) * 38;
      return toHex(rgbAt(hue, tone));
    } catch(e) {
      return renderPalette[(xi + yi) % renderPalette.length];
    }
  }
  function makeHexTile(xPx, yPx, color, xi, yi){
    const tile = document.createElement('div');
    tile.className = 'mh-game-cell';
    tile.dataset.x = String(xi);
    tile.dataset.y = String(yi);
    tile.style.left = xPx + 'px';
    tile.style.top = yPx + 'px';
    tile.style.setProperty('--tile-color', color);
    ['top','left','bottom'].forEach(face => {
      const d = document.createElement('div');
      d.className = 'mh-game-face mh-game-face-' + face;
      tile.appendChild(d);
    });
    return tile;
  }
  function makeToken(type, x, y, size, color){
    const t = document.createElement('div');
    t.className = 'mh-token ' + type;
    t.style.left = x + 'px';
    t.style.top = y + 'px';
    t.style.setProperty('--mh-token-size', size + 'px');
    if (color) t.style.setProperty('--token-color', color);
    return t;
  }
  function tokenPlan(kind, metrics){
    const N = metrics.N;
    if (kind === 'maze') {
      return [
        { type: 'player', xi: 1, yi: N - 2 }, { type: 'enemy', xi: N - 2, yi: 1 },
        { type: 'enemy', xi: Math.floor(N/2), yi: Math.floor(N/2) }, { type: 'pickup', xi: N - 2, yi: N - 2 },
      ];
    }
    if (kind === 'invaders') {
      const enemies = [];
      for (let row = 1; row < Math.min(4, N); row++) for (let xi = 1; xi < N - 1; xi += 2) enemies.push({ type: 'enemy', xi, yi: row });
      return [{ type: 'player', xi: Math.floor(N/2), yi: N - 1 }, ...enemies];
    }
    return [
      { type: 'player', xi: 1, yi: N - 2 }, { type: 'enemy', xi: N - 2, yi: N - 3 },
      { type: 'pickup', xi: Math.floor(N/2), yi: N - 4 }, { type: 'enemy', xi: N - 1, yi: N - 2 },
    ];
  }
  function syncMunker(){
    pushUnifiedToOriginal();
    const u = currentUnifiedMunker();
    const mode = u.mode;
    const spacing = u.spacing;
    const thick = u.thickness;
    const opacity = u.opacity;
    const speed = u.speed;
    const angles = { h:'90deg', v:'0deg', grid:'45deg', diag:'135deg', off:'135deg' };
    stage.style.setProperty('--mh-angle', angles[mode] || '135deg');
    stage.style.setProperty('--mh-gap', spacing + 'px');
    syncLineThickness(thick, false);
    stage.style.setProperty('--mh-opacity', mode === 'off' ? '.0' : String(opacity/100));
    stage.style.setProperty('--mh-speed', speed + 's');
    applyRenderPalette();
    buildArtifactField($('mhGame')?.value + ($('mhUrl')?.value || ''));
  }
  function styleWholeWebsiteFrame(){
    if (!frame || !frame.contentDocument || frame.style.display === 'none') return;
    const doc = frame.contentDocument;
    const p = getWheelPalette();
    const u = currentUnifiedMunker();
    const css = `
      :root { --mh-a:${p.aHex}; --mh-b:${p.bHex}; --mh-c:${p.cHex}; --mh-centre:${p.cHex}; }
      html, body { background: #05050a !important; color: var(--mh-c) !important; }
      body { filter: saturate(1.22) contrast(1.05) hue-rotate(${Math.round(p.hue)}deg); }
      body * { border-color: color-mix(in srgb, var(--mh-a), var(--mh-b) 35%) !important; }
      h1,h2,h3,h4,strong,b { color: var(--mh-a) !important; text-shadow: 0 0 12px color-mix(in srgb, var(--mh-a), transparent 55%); }
      a, button, input, select, textarea { color: var(--mh-b) !important; outline-color: var(--mh-a) !important; }
      img, video, canvas, svg { mix-blend-mode: screen; filter: saturate(1.25) contrast(1.05); }
      .mh-site-style-overlay, .mh-site-hex-overlay, .mh-site-ruliad-overlay { position: fixed; inset: 0; pointer-events: none; z-index: 2147483600; }
      .mh-site-style-overlay { opacity: ${Math.max(0, Math.min(1, u.opacity / 100))}; mix-blend-mode: screen; background: repeating-linear-gradient(${u.mode === 'h' ? '0deg' : u.mode === 'v' ? '90deg' : u.mode === 'grid' ? '45deg' : '-28deg'}, rgba(255,255,255,.88) 0 ${u.thickness}px, transparent ${u.thickness}px ${u.thickness + Math.max(0, u.spacing)}px); animation: mhSitePan ${u.speed}s linear infinite alternate; }
      .mh-site-hex-overlay { opacity: .34; mix-blend-mode: screen; background-image: linear-gradient(30deg, transparent 24%, ${p.aHex} 25%, ${p.aHex} 26%, transparent 27%, transparent 74%, ${p.bHex} 75%, ${p.bHex} 76%, transparent 77%), linear-gradient(150deg, transparent 24%, ${p.cHex} 25%, ${p.cHex} 26%, transparent 27%, transparent 74%, ${p.aHex} 75%, ${p.aHex} 76%, transparent 77%); background-size: 52px 30px; }
      .mh-site-ruliad-overlay { opacity: .42; mix-blend-mode: screen; background: radial-gradient(circle at 20% 22%, ${p.aHex}, transparent 1.2%), radial-gradient(circle at 72% 34%, ${p.bHex}, transparent 1.1%), radial-gradient(circle at 46% 78%, ${p.cHex}, transparent 1.3%); background-size: 88px 88px, 110px 110px, 72px 72px; }
      @keyframes mhSitePan { from { transform: translate3d(-18px,-12px,0); } to { transform: translate3d(18px,12px,0); } }
    `;
    let style = doc.getElementById('mh-site-whole-style');
    if (!style) { style = doc.createElement('style'); style.id = 'mh-site-whole-style'; doc.head.appendChild(style); }
    style.textContent = css;
    ['mh-site-style-overlay','mh-site-hex-overlay','mh-site-ruliad-overlay'].forEach(cls => {
      if (!doc.querySelector('.' + cls)) {
        const div = doc.createElement('div'); div.className = cls; doc.body.appendChild(div);
      }
    });
  }
  function drawGame(kind){
    const p = applyRenderPalette();
    grid.innerHTML = '';
    tokenLayer.innerHTML = '';
    grid.style.display = 'block';
    frame.style.display = 'none';
    synthetic.style.display = 'none';
    const metrics = groundMetrics();
    const { N, hexW, hexH, rowStep, colStep } = metrics;
    const totalW = colStep * N + hexW * 0.5;
    const totalH = rowStep * (N - 1) + hexH;
    grid.style.setProperty('--mh-hex-size', hexW + 'px');
    grid.style.width = totalW + 'px';
    grid.style.height = totalH + 'px';
    const stageRect = stage.getBoundingClientRect();
    const offsetX = (stageRect.width - totalW) / 2;
    const offsetY = (stageRect.height - totalH) / 2;
    const cellCenters = {};
    for(let row=0; row<N; row++){
      const yi = row;
      const rowOffset = row % 2 ? hexW * 0.5 : 0;
      for(let xi=0; xi<N; xi++){
        if (kind === 'maze' && ((xi === 2 && row > 1 && row < N - 1) || (row === 3 && xi > 1 && xi < N - 2))) continue;
        const xPx = xi * colStep + rowOffset;
        const yPx = row * rowStep;
        const c = colorForGroundCell(xi, yi, kind, p, N);
        grid.appendChild(makeHexTile(xPx, yPx, c, xi, yi));
        cellCenters[`${xi},${yi}`] = { x: offsetX + xPx + hexW / 2, y: offsetY + yPx + hexH * 0.58 };
      }
    }
    for (const token of tokenPlan(kind, metrics)) {
      const pos = cellCenters[`${token.xi},${token.yi}`] || cellCenters[`${Math.floor(N/2)},${Math.floor(N/2)}`];
      if (!pos) continue;
      const color = token.type === 'player' ? p.aHex : token.type === 'enemy' ? p.bHex : p.cHex;
      tokenLayer.appendChild(makeToken(token.type, pos.x, pos.y, hexW, color));
    }
    buildRuliadField('game-' + kind);
    buildArtifactField('game-' + kind);
    label.textContent = 'game render · ' + kind + ' · top-down 3-plane hex ground · ' + N + '×' + N;
  }
  function render(){
    const kind = $('mhGame').value;
    syncMunker();
    if(kind === 'website'){
      const url = safeUrl($('mhUrl').value);
      frame.src = 'site-html?url=' + encodeURIComponent(url);
      frame.style.display = 'block';
      synthetic.style.display = 'none';
      grid.style.display = 'none';
      tokenLayer.innerHTML = '';
      hostLabel.textContent = host(url);
      const p = applyRenderPalette();
      buildRuliadField('site-' + host(url));
      buildArtifactField('site-' + host(url));
      label.textContent = 'website render · ' + host(url) + ' · wheel ' + p.aHex + ' → ' + p.bHex;
      return;
    }
    drawGame(kind);
  }
  ['munkerMode','munkerSpacing','munkerThick','munkerOpacity','munkerSpeed','hexIn','inH','inT','cfgY','cfgM','cfgC','cfgRot','cfgChroma','centreW','cubeSize','cubeGap','cfgSteps'].forEach(id => {
    const el=$(id); if(el) el.addEventListener('input', () => { syncMunker(); applyRenderPalette(); if ($('mhGame').value !== 'website') drawGame($('mhGame').value); });
  });
  document.querySelectorAll('#centreModes button').forEach(btn => btn.addEventListener('click', () => setTimeout(applyRenderPalette, 0)));
  ['mhUnifiedMode','mhUnifiedPattern','mhAutoAnimate'].forEach(id => {
    const el = $(id); if (el) el.addEventListener('change', () => { syncMunker(); render(); });
  });
  ['mhUnifiedSpacing','mhLineThickness','mhUnifiedOpacity','mhUnifiedSpeed'].forEach(id => {
    const el = $(id); if (el) el.addEventListener('input', () => { syncUnifiedLabels(); syncMunker(); if ($('mhGame').value !== 'website') drawGame($('mhGame').value); else styleWholeWebsiteFrame(); });
  });
  $('mhMunkerPreset').addEventListener('change', e => applyMunkerPreset(e.target.value));
  $('mhRenderBtn').addEventListener('click', render);
  $('mhGenerateCodeBtn').addEventListener('click', updateBuilderCode);
  $('mhCopyCodeBtn').addEventListener('click', copyBuilderCode);
  $('mhExportGifBtn').addEventListener('click', exportGif);
  document.querySelectorAll('.mh-suite-tab').forEach(btn => btn.addEventListener('click', () => switchSuiteTab(btn.dataset.suiteTab || 'web')));
  ['mhWebPreset','mhWebDensity'].forEach(id => { const el=$(id); if(el) el.addEventListener('change', renderWebDesigner); });
  $('mhGenerateWebBtn').addEventListener('click', renderWebDesigner);
  $('mhGameBuilderBtn').addEventListener('click', () => { switchSuiteTab('game'); setVal('mhGame','platformer'); render(); });
  $('mhGifDesignerBtn').addEventListener('click', () => { switchSuiteTab('gif'); exportGif(); });
  if ($('mhSyncBtn')) $('mhSyncBtn').addEventListener('click', syncMunker);
  frame.addEventListener('load', () => setTimeout(styleWholeWebsiteFrame, 120));
  function hideDuplicateMunkerControls(){
    document.querySelectorAll('details').forEach(details => {
      const summary = details.querySelector('summary');
      if (summary && summary.textContent && summary.textContent.toLowerCase().includes('munker filter')) {
        details.classList.add('mh-hidden-original-munker');
      }
    });
  }
  function bindLateRenderSyncControls(){
    if (window.__mhLateRenderSyncBound) return;
    window.__mhLateRenderSyncBound = true;
    ['munkerMode','munkerSpacing','munkerThick','munkerOpacity','munkerSpeed','hexIn','inH','inT','cfgY','cfgM','cfgC','cfgRot','cfgChroma','centreW','cubeSize','cubeGap','cfgSteps','cubeToneMin','cubeToneMax','cubeMode','cubeTime','cubePerspective','cubeMonet','cubePointillism','cubeSpeckles','cubeCalibratedDots','cubeGreyscale','cubeTintedShadows'].forEach(id => {
      const el = $(id);
      if (!el) return;
      const ev = el.tagName === 'SELECT' ? 'change' : 'input';
      el.addEventListener(ev, () => setTimeout(() => {
        syncMunker();
        applyRenderPalette();
        if ($('mhGame').value !== 'website') drawGame($('mhGame').value);
      }, 0));
    });
  }
  setTimeout(() => {
    hideDuplicateMunkerControls();
    bindLateRenderSyncControls();
    const cubeBtn = document.querySelector('[data-tab="cube"]');
    if(cubeBtn) cubeBtn.click();
    applyMunkerPreset('white-ruliad');
    const mode = $('munkerMode'); if(mode) mode.value = 'diag';
    const animate = $('munkerAnimate'); if(animate) animate.value = 'diag';
    if (typeof renderAll === 'function' && !renderAll.__mhPatched) {
      const originalRenderAll = renderAll;
      renderAll = function(){ const result = originalRenderAll.apply(this, arguments); setTimeout(() => { syncMunker(); applyRenderPalette(); }, 0); return result; };
      renderAll.__mhPatched = true;
    }
    syncLineThickness($('mhLineThickness') ? $('mhLineThickness').value : 5, false);
    syncMunker(); render(); renderWebDesigner(); renderCharacterDesigner();
  }, 400);
})();
</script>
"""
    return original.replace("<body>", f"<body>\n{render_patch}", 1)


@api_router.get("/tonality-renderer", response_class=HTMLResponse)
async def tonality_renderer():
    return HTMLResponse(build_tonality_renderer_html())


@api_router.get("/site-html", response_class=HTMLResponse)
async def site_html(url: str):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Enter a valid http/https URL")
    try:
        response = await asyncio.to_thread(
            requests.get,
            url,
            timeout=8,
            headers={
                "User-Agent": "Mozilla/5.0 (MunkerHex Studio renderer)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch website: {exc}") from exc

    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        html = f"""
        <!doctype html><html><head><meta charset='utf-8'><base href='{url}'></head>
        <body style='font-family:monospace;background:#fff;color:#111;padding:24px'>
        <h1>{parsed.netloc}</h1><p>Fetched non-HTML content: {content_type or 'unknown'}</p>
        </body></html>
        """
        return HTMLResponse(html)

    html = response.text
    base_tag = f"<base href='{url}'>"
    if "<head" in html.lower():
        head_end = html.lower().find(">", html.lower().find("<head"))
        html = html[: head_end + 1] + base_tag + html[head_end + 1 :]
    else:
        html = f"<!doctype html><html><head>{base_tag}</head><body>{html}</body></html>"
    return HTMLResponse(html)


@api_router.get("/palettes", response_model=List[PalettePreset])
async def get_palettes():
    return PALETTE_PRESETS


@api_router.get("/gallery", response_model=List[RetroGameCard])
async def get_gallery():
    return RETRO_GALLERY


@api_router.post("/renders", response_model=RenderProject)
async def create_render_project(input: RenderProjectCreate):
    palette_ids = {palette.id for palette in PALETTE_PRESETS}
    if input.palette_id not in palette_ids:
        raise HTTPException(status_code=400, detail="Unknown palette preset")

    url = str(input.url)
    host = host_from_url(url)
    project = RenderProject(
        id=str(uuid.uuid4()),
        title=input.title or f"{host} render",
        url=url,
        host=host,
        palette_id=input.palette_id,
        config=input.config,
        signature=build_signature(url, input.palette_id, input.config),
        created_at=utc_now_iso(),
    )
    await db.render_projects.insert_one(project.model_dump())
    return project


@api_router.get("/renders", response_model=List[RenderProject])
async def get_render_projects():
    docs = await db.render_projects.find({}, {"_id": 0}).sort("created_at", -1).limit(25).to_list(25)
    return [RenderProject(**doc) for doc in docs]

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    _ = await db.status_checks.insert_one(status_obj.model_dump())
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    return [StatusCheck(**status_check) for status_check in status_checks]

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
