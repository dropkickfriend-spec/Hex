from fastapi import FastAPI, APIRouter, HTTPException, Request, Header, Depends
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import AnyHttpUrl, BaseModel, Field
from typing import Any, Dict, List, Literal, Optional
import uuid
from datetime import datetime, timezone
import hashlib
import json
from urllib.parse import urlparse
import requests
import asyncio
from io import BytesIO
from PIL import Image, ImageDraw
import stripe


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')
ORIGINAL_TONALITY_PATH = ROOT_DIR / "original_tonality.html"

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Stripe
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

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


class BrandKitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    palette: Dict[str, Any]
    munker_config: Dict[str, Any] = Field(default_factory=dict)


class BrandKit(BaseModel):
    id: str
    user_id: str
    name: str
    palette: Dict[str, Any]
    munker_config: Dict[str, Any]
    created_at: str


class FontEffect(BaseModel):
    id: str
    name: str
    css: str
    svg_filter: str
    preview_label: str
    is_premium: bool
    author_id: Optional[str] = None


class GalleryItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    config: Dict[str, Any]


class GalleryItem(BaseModel):
    id: str
    user_id: str
    title: str
    config: Dict[str, Any]
    likes: int = 0
    created_at: str


FONT_EFFECTS_SEED: List[Dict[str, Any]] = [
    # ── Free effects ───────────────────────────────────────────────────────────
    {"id": "munker-pulse", "name": "Munker Pulse", "is_premium": False,
     "preview_label": "Optical beat",
     "css": "@keyframes mhPulse{0%,100%{opacity:.55}50%{opacity:1}} .mh-ftext{animation:mhPulse 1.2s ease-in-out infinite;fill:var(--mh-a);filter:url(#mhStripeF)}",
     "svg_filter": "<feColorMatrix type='saturate' values='2.2'/>"},
    {"id": "stripe-reveal", "name": "Stripe Reveal", "is_premium": False,
     "preview_label": "Munker lines",
     "css": "@keyframes mhReveal{0%{clip-path:inset(0 100% 0 0)}100%{clip-path:inset(0 0% 0 0)}} .mh-ftext{animation:mhReveal 2s cubic-bezier(.77,0,.18,1) forwards;fill:var(--mh-b)}",
     "svg_filter": "<feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='1' result='n'/><feDisplacementMap in='SourceGraphic' in2='n' scale='4'/>"},
    {"id": "hex-glow", "name": "Hex Glow", "is_premium": False,
     "preview_label": "Illusion edge",
     "css": "@keyframes mhGlow{0%,100%{filter:drop-shadow(0 0 4px var(--mh-a))}50%{filter:drop-shadow(0 0 18px var(--mh-b))}} .mh-ftext{animation:mhGlow 2s ease-in-out infinite;fill:var(--mh-a)}",
     "svg_filter": ""},
    {"id": "wave-trace", "name": "Wave Trace", "is_premium": False,
     "preview_label": "Sine motion",
     "css": "@keyframes mhWave{0%{transform:translateY(0)}25%{transform:translateY(-6px)}75%{transform:translateY(6px)}100%{transform:translateY(0)}} .mh-ftext{animation:mhWave 1.8s ease-in-out infinite;fill:var(--mh-centre)}",
     "svg_filter": "<feGaussianBlur stdDeviation='0.6' result='b'/><feMerge><feMergeNode in='b'/><feMergeNode in='SourceGraphic'/></feMerge>"},
    {"id": "color-shift", "name": "Colour Shift", "is_premium": False,
     "preview_label": "CMY cycle",
     "css": "@keyframes mhShift{0%{fill:var(--mh-a)}33%{fill:var(--mh-b)}66%{fill:var(--mh-centre)}100%{fill:var(--mh-a)}} .mh-ftext{animation:mhShift 3s linear infinite}",
     "svg_filter": ""},
    {"id": "diagonal-crawl", "name": "Diagonal Crawl", "is_premium": False,
     "preview_label": "Munker diagonal",
     "css": "@keyframes mhCrawl{0%{stroke-dashoffset:200}100%{stroke-dashoffset:0}} .mh-ftext{fill:none;stroke:var(--mh-a);stroke-width:1.5;stroke-dasharray:200;animation:mhCrawl 2.5s linear infinite}",
     "svg_filter": ""},
    {"id": "grid-flash", "name": "Grid Flash", "is_premium": False,
     "preview_label": "Strobe grid",
     "css": "@keyframes mhFlash{0%,49%{opacity:1}50%,100%{opacity:.2}} .mh-ftext{animation:mhFlash .6s step-end infinite;fill:var(--mh-b);filter:url(#mhStripeF)}",
     "svg_filter": "<feColorMatrix type='matrix' values='1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 18 -7'/>"},
    {"id": "centre-fade", "name": "Centre Fade", "is_premium": False,
     "preview_label": "Tonal dissolve",
     "css": "@keyframes mhFade{0%{opacity:0;letter-spacing:.3em}100%{opacity:1;letter-spacing:0}} .mh-ftext{animation:mhFade 2s ease-out forwards;fill:var(--mh-centre)}",
     "svg_filter": ""},
    # ── Premium effects (Designer+) ────────────────────────────────────────────
    {"id": "cmy-split", "name": "CMY Split", "is_premium": True,
     "preview_label": "Chromatic aberration",
     "css": "@keyframes mhSplit{0%,100%{text-shadow:-3px 0 var(--mh-a),3px 0 var(--mh-b)}50%{text-shadow:-6px 0 var(--mh-a),6px 0 var(--mh-b)}} .mh-ftext{animation:mhSplit 1.5s ease-in-out infinite;fill:var(--mh-centre)}",
     "svg_filter": ""},
    {"id": "iso-extrude", "name": "Isometric Extrude", "is_premium": True,
     "preview_label": "3-plane hex depth",
     "css": "@keyframes mhExtrude{0%{transform:translate(0,0) skewX(-18deg)}100%{transform:translate(-8px,8px) skewX(-18deg)}} .mh-ftext{animation:mhExtrude 2s alternate ease-in-out infinite;fill:var(--mh-a);stroke:var(--mh-b);stroke-width:.5}",
     "svg_filter": ""},
    {"id": "ruliad-trace", "name": "Ruliad Trace", "is_premium": True,
     "preview_label": "Node network",
     "css": "@keyframes mhTrace{0%{stroke-dashoffset:600;opacity:.3}100%{stroke-dashoffset:0;opacity:1}} .mh-ftext{fill:none;stroke:var(--mh-a);stroke-width:2;stroke-dasharray:600;animation:mhTrace 3s ease-in-out infinite alternate}",
     "svg_filter": "<feTurbulence type='turbulence' baseFrequency='0.02' numOctaves='3' result='n'/><feDisplacementMap in='SourceGraphic' in2='n' scale='6'/>"},
    {"id": "variable-weight", "name": "Variable Weight", "is_premium": True,
     "preview_label": "Type mass pulse",
     "css": "@keyframes mhVW{0%,100%{font-variation-settings:'wght' 100}50%{font-variation-settings:'wght' 900}} .mh-ftext{animation:mhVW 2s ease-in-out infinite;fill:var(--mh-a)}",
     "svg_filter": ""},
    {"id": "munker-scanline", "name": "Munker Scanline", "is_premium": True,
     "preview_label": "CRT optical",
     "css": "@keyframes mhScan{0%{background-position:0 0}100%{background-position:0 100%}} .mh-ftext-wrap{background:repeating-linear-gradient(0deg,rgba(0,0,0,.18) 0px,rgba(0,0,0,.18) 1px,transparent 1px,transparent 3px);animation:mhScan 1s linear infinite} .mh-ftext{fill:var(--mh-a)}",
     "svg_filter": ""},
    {"id": "hex-morph", "name": "Hex Morph", "is_premium": True,
     "preview_label": "Polygon letterform",
     "css": "@keyframes mhMorph{0%,100%{clip-path:polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%)}50%{clip-path:polygon(25% 0%,75% 0%,100% 50%,75% 100%,25% 100%,0% 50%)}} .mh-ftext{animation:mhMorph 2s ease-in-out infinite;fill:var(--mh-b)}",
     "svg_filter": ""},
    {"id": "stripe-mask", "name": "Stripe Mask", "is_premium": True,
     "preview_label": "Munker stripe cutout",
     "css": "@keyframes mhMask{0%{mask-position:0 0}100%{mask-position:40px 0}} .mh-ftext{animation:mhMask 1s linear infinite;mask-image:repeating-linear-gradient(45deg,#000 0px,#000 4px,transparent 4px,transparent 10px);fill:var(--mh-a)}",
     "svg_filter": ""},
    {"id": "tonal-echo", "name": "Tonal Echo", "is_premium": True,
     "preview_label": "Depth shadow layers",
     "css": "@keyframes mhEcho{0%{text-shadow:2px 2px 0 var(--mh-b),4px 4px 0 var(--mh-centre)}100%{text-shadow:6px 6px 0 var(--mh-b),12px 12px 0 var(--mh-centre)}} .mh-ftext{animation:mhEcho 2s alternate ease-in-out infinite;fill:var(--mh-a)}",
     "svg_filter": ""},
    {"id": "optical-flicker", "name": "Optical Flicker", "is_premium": True,
     "preview_label": "Munker edge shimmer",
     "css": "@keyframes mhFlicker{0%{opacity:1;filter:url(#mhStripeF) brightness(1.2)}33%{opacity:.7;filter:url(#mhStripeF) brightness(.8)}66%{opacity:.9;filter:url(#mhStripeF) brightness(1.5)}100%{opacity:1;filter:url(#mhStripeF) brightness(1)}} .mh-ftext{animation:mhFlicker .9s ease-in-out infinite;fill:var(--mh-a)}",
     "svg_filter": "<feColorMatrix type='saturate' values='3'/>"},
    {"id": "chromatic-bloom", "name": "Chromatic Bloom", "is_premium": True,
     "preview_label": "Lens flare diffuse",
     "css": "@keyframes mhBloom{0%,100%{filter:drop-shadow(0 0 2px var(--mh-a)) drop-shadow(0 0 6px var(--mh-b)) brightness(1)}50%{filter:drop-shadow(0 0 12px var(--mh-a)) drop-shadow(0 0 24px var(--mh-b)) brightness(1.3)}} .mh-ftext{animation:mhBloom 2.5s ease-in-out infinite;fill:var(--mh-centre)}",
     "svg_filter": ""},
    {"id": "pixel-dither", "name": "Pixel Dither", "is_premium": True,
     "preview_label": "Retro game palette",
     "css": "@keyframes mhDither{0%,100%{filter:url(#mhStripeF) contrast(20) brightness(.8)}50%{filter:url(#mhStripeF) contrast(20) brightness(1.3)}} .mh-ftext{animation:mhDither .4s step-end infinite;fill:var(--mh-a)}",
     "svg_filter": "<feColorMatrix type='matrix' values='1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 8 -4'/>"},
]


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
  @import url('https://fonts.googleapis.com/css2?family=Space+Mono:ital,wght@0,400;0,700;1,400&display=swap');
  .mh-render-adapter {
    margin: 12px;
    border-radius: 18px;
    padding: 14px;
  }
  .mh-render-adapter h2 { margin-top: 0; }
  .mh-render-toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .mh-render-toolbar input, .mh-render-toolbar select {
    min-width: 180px;
    flex: 1;
    background: rgba(255,255,255,.04);
    color: var(--ink);
    border: none;
    border-radius: 8px;
    padding: 9px 10px;
    font: 12px 'Space Mono', monospace;
  }
  .mh-render-toolbar button { min-height: 44px; }
  .mh-suite-tabs {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(58px, 1fr));
    gap: 8px;
    margin: 10px 0 16px;
  }
  .mh-suite-tab {
    position: relative;
    display: block;
    height: 76px;
    border: none;
    background: transparent;
    padding: 0;
    cursor: pointer;
    filter: drop-shadow(0 7px 14px rgba(0,0,0,.55));
    transition: filter .14s, transform .14s cubic-bezier(.2,.8,.35,1.3);
  }
  .mh-suite-tab:hover { transform: translateY(-5px); filter: drop-shadow(0 12px 22px rgba(0,0,0,.65)); }
  .mh-suite-tab:active { transform: translateY(2px) scale(.95); filter: drop-shadow(0 3px 6px rgba(0,0,0,.5)); }
  .mh-suite-tab.active { filter: drop-shadow(0 0 18px var(--mh-a,#ffff00)) drop-shadow(0 8px 18px rgba(0,0,0,.6)); }
  .mh-ctab-cube { position:absolute; inset:0; }
  .mh-ctab-f { position:absolute; inset:0; background:rgba(255,255,255,.10); }
  .mh-ctab-t { clip-path:polygon(50% 0%,100% 25%,50% 50%,0% 25%); filter:brightness(1.55); }
  .mh-ctab-r { clip-path:polygon(100% 25%,100% 75%,50% 100%,50% 50%); filter:brightness(0.88); }
  .mh-ctab-l { clip-path:polygon(0% 25%,50% 50%,50% 100%,0% 75%); filter:brightness(0.46); }
  .mh-suite-tab.active .mh-ctab-f { background:var(--mh-a,#ffff00); animation:mhPxPulse 3.5s ease-in-out infinite alternate; }
  .mh-suite-tab.active .mh-ctab-t { filter:brightness(1.55); }
  .mh-suite-tab.active .mh-ctab-r { filter:brightness(0.88); }
  .mh-suite-tab.active .mh-ctab-l { filter:brightness(0.46); }
  .mh-ctab-lbl {
    position:absolute; top:18%; left:50%; transform:translateX(-50%);
    color:var(--ink); font:bold 7px 'Space Mono',monospace;
    letter-spacing:.06em; text-transform:uppercase;
    text-shadow:0 1px 3px rgba(0,0,0,.9); white-space:nowrap; pointer-events:none;
  }
  .mh-render-adapter h2,
  .mh-unified-munker-title,
  .mh-builder-title,
  .mh-suite-tab .mh-ctab-lbl,
  .mh-export-status {
    text-shadow: 0 1px 4px rgba(0,0,0,.95), 0 0 10px rgba(0,0,0,.7);
  }
  .mh-panels-wrap { position:relative; overflow:hidden; border-radius:14px; }
  .mh-builder-panel {
    display:none; margin-top:14px; border-radius:14px; padding:14px;
  }
  .mh-builder-panel.active { display:block; }
  #mhFoldPaper {
    display:none; position:absolute; inset:0; z-index:20; border-radius:14px;
    background-color:rgba(7,7,12,.94);
    background-image:
      linear-gradient(var(--mh-grid-line,rgba(128,128,128,.09)) 1px, transparent 1px),
      linear-gradient(90deg, var(--mh-grid-line,rgba(128,128,128,.09)) 1px, transparent 1px);
    background-size:24px 24px;
    transform-origin:top center; pointer-events:none;
  }
  #mhFoldPaper.mh-paper-cover { display:block; animation:mhPaperCover 0.3s cubic-bezier(.4,0,.2,1) forwards; }
  #mhFoldPaper.mh-paper-reveal { display:block; animation:mhPaperReveal 0.36s cubic-bezier(.15,.7,.3,1.1) forwards; }
  @keyframes mhPaperCover {
    0%   { transform:perspective(700px) rotateX(-52deg) scaleY(0.02); opacity:0; }
    25%  { opacity:1; }
    100% { transform:perspective(700px) rotateX(0deg) scaleY(1); opacity:1; }
  }
  @keyframes mhPaperReveal {
    0%   { transform:perspective(700px) rotateX(0deg) scaleY(1); opacity:1; }
    75%  { opacity:0.55; }
    100% { transform:perspective(700px) rotateX(52deg) scaleY(0.02); opacity:0; }
  }
  .mh-builder-title { color:var(--mh-a,#ffff00); font:12px 'Space Mono', monospace; letter-spacing:.08em; text-transform:uppercase; margin-bottom:8px; display:block; transform:skewY(14deg) scaleX(0.92); transform-origin:left top; }
  .mh-web-preview { position:relative; min-height:360px; margin-top:10px; border-radius:14px; overflow:hidden; background:#05050a; box-shadow:0 0 0 1px rgba(255,255,255,.04); }
  .mh-web-preview-inner { position:relative; z-index:1; min-height:360px; padding:18px; background:radial-gradient(circle at 22% 18%, var(--mh-a-soft, rgba(255,255,0,.22)), transparent 28%), radial-gradient(circle at 78% 44%, var(--mh-b-soft, rgba(0,0,255,.18)), transparent 26%), #06060c; color:var(--ink); }
  .mh-web-nav { display:flex; align-items:center; justify-content:space-between; gap:12px; border:1px solid rgba(255,255,255,.14); border-radius:999px; padding:10px 12px; background:rgba(0,0,0,.36); font:11px 'Space Mono', monospace; }
  .mh-web-logo { color:var(--mh-a, #ffff00); font-weight:700; letter-spacing:.14em; }
  .mh-web-links { display:flex; gap:10px; color:var(--ink-dim); }
  .mh-web-hero { margin-top:18px; display:grid; gap:14px; }
  .mh-web-kicker { color:var(--mh-c, #00ffff); font:10px 'Space Mono', monospace; letter-spacing:.18em; text-transform:uppercase; }
  .mh-web-headline { color:#fff; font:700 31px/1.02 'Space Mono', monospace; letter-spacing:.02em; margin:0; }
  .mh-web-copy { color:var(--ink-dim); font:12px/1.55 'Space Mono', monospace; max-width:42em; }
  .mh-web-cta-row { display:flex; gap:10px; flex-wrap:wrap; }
  .mh-web-btn { min-height:44px; display:inline-flex; align-items:center; justify-content:center; border:1px solid var(--mh-a, #ffff00); border-radius:999px; padding:0 14px; color:#05050a; background:var(--mh-a, #ffff00); font:12px 'Space Mono', monospace; text-decoration:none; }
  .mh-web-btn.secondary { color:var(--mh-b, #0000ff); background:rgba(0,0,0,.25); border-color:var(--mh-b, #0000ff); }
  .mh-web-card-grid { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:10px; margin-top:16px; }
  .mh-web-card { min-height:98px; border-radius:12px; background:rgba(255,255,255,.055); padding:14px; font:11px/1.5 'Space Mono', monospace; color:var(--ink-dim); }
  .mh-web-card b { display:block; color:var(--mh-a, #ffff00); margin-bottom:6px; }
  .mh-extra-grid { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:8px; margin-top:10px; }
  .mh-extra-card { border-radius:10px; padding:12px; min-height:82px; background:rgba(255,255,255,.045); color:var(--ink-dim); font:11px/1.45 'Space Mono', monospace; }
  .mh-extra-card b { color:var(--mh-a, #ffff00); display:block; margin-bottom:5px; }
  @media (max-width:760px){ .mh-suite-tabs { grid-template-columns:repeat(3, minmax(0,1fr)); } .mh-web-card-grid { grid-template-columns:1fr; } }
  /* Full-page isometric 3D cube hex background */
  #mhPageHexBg{position:fixed;inset:0;overflow:hidden;pointer-events:none;z-index:0}
  #mhPageHexBg.mh-bg-pulse .mh-pxhex{animation-duration:.35s!important;opacity:1!important}
  .mh-pxhex{position:absolute;animation:mhPxPulse 4s ease-in-out infinite alternate}
  .mh-pxhex.mh-pxhex-b{animation:mhPxPulseB 6s ease-in-out infinite alternate}
  @keyframes mhPxPulse{from{opacity:.55}to{opacity:.88}}
  @keyframes mhPxPulseB{from{opacity:.42}to{opacity:.72}}
  .mh-pxf{position:absolute;inset:0;background:var(--pxc,#444)}
  .mh-pxf-t{clip-path:polygon(50% 0%,100% 25%,50% 50%,0% 25%);filter:brightness(1.55);animation:mhBgFaceTop var(--mh-face-speed,9s) linear infinite alternate}
  .mh-pxf-r{clip-path:polygon(100% 25%,100% 75%,50% 100%,50% 50%);filter:brightness(0.88);animation:mhBgFaceRight var(--mh-face-speed,9s) linear infinite alternate}
  .mh-pxf-l{clip-path:polygon(0% 25%,50% 50%,50% 100%,0% 75%);filter:brightness(0.48);animation:mhBgFaceLeft var(--mh-face-speed,9s) linear infinite alternate}
  @keyframes mhBgFaceTop  {0%{background-position:0 0}100%{background-position:69px -40px}}
  @keyframes mhBgFaceRight{0%{background-position:0 0}100%{background-position:69px  40px}}
  @keyframes mhBgFaceLeft {0%{background-position:0 0}100%{background-position:80px   0px}}
  /* Template card picker */
  .mh-tpl-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin-bottom:10px}
  .mh-tpl-card{border-radius:6px;padding:6px 4px;cursor:pointer;background:rgba(255,255,255,.04);box-shadow:0 0 0 1px rgba(255,255,255,.06);text-align:center;font:9px ui-monospace,monospace;color:var(--ink-dim);transition:box-shadow .15s,background .15s;user-select:none}
  .mh-tpl-card:hover,.mh-tpl-card.active{box-shadow:0 0 0 1px var(--mh-a,#ffff00);color:var(--ink)}
  .mh-tpl-thumb{width:100%;aspect-ratio:3/2;border-radius:3px;margin-bottom:3px}
  /* Expanded web preview */
  .mh-web-preview{min-height:520px !important}
  .mh-web-preview-inner{min-height:520px !important;padding:0 !important}
  .mh-web-footer{border-top:1px solid #ffffff18;padding:18px 32px;display:flex;justify-content:space-between;font:10px ui-monospace,monospace;color:#ffffff44}
  .mh-unified-munker {
    margin-top: 10px;
    border-radius: 10px;
    padding: 10px;
  }
  .mh-unified-munker-title {
    display:flex; align-items:center; justify-content:space-between; gap:8px;
    color: var(--ink);
    font: 12px 'Space Mono', monospace;
    letter-spacing: .08em;
    text-transform: uppercase;
    margin-bottom: 8px;
  }
  .mh-unified-munker .mh-render-toolbar { margin-top: 6px; }
  .mh-render-toolbar .mh-mini-field {
    min-width: 170px;
    flex: 1;
    color: var(--ink-dim);
    font: 11px 'Space Mono', monospace;
    letter-spacing: .02em;
  }
  .mh-render-toolbar .mh-mini-field input { min-width: 120px; width: 100%; margin-top: 5px; }
  .mh-hidden-original-munker { display: none !important; }
  .mh-painter-tip {
    margin-top: 9px;
    border-left: 3px solid var(--mh-c, #00ffff);
    border-radius: 8px;
    padding: 9px 10px;
    color: var(--ink-dim);
    font: 11px/1.45 'Space Mono', monospace;
  }
  .mh-export-panel {
    margin-top: 10px;
    border-radius: 10px;
    padding: 10px;
  }
  .mh-export-title {
    color: var(--ink);
    font: 12px 'Space Mono', monospace;
    letter-spacing: .08em;
    text-transform: uppercase;
    margin-bottom: 8px;
  }
  .mh-code-box {
    width: 100%;
    min-height: 160px;
    margin-top: 8px;
    border: none;
    border-radius: 8px;
    background: #07070c;
    color: var(--ink);
    padding: 10px;
    font: 11px/1.45 'Space Mono', monospace;
    resize: vertical;
    box-sizing: border-box;
  }
  .mh-export-status { margin-top: 7px; color: var(--ink-dim); font: 11px 'Space Mono', monospace; }
  .mh-download-link { color: var(--mh-a, #ffff00); text-decoration: none; border: none; border-radius: 8px; padding: 10px 12px; min-height: 44px; display: inline-flex; align-items: center; }
  .mh-wheel-readout {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-top: 9px;
    font: 11px 'Space Mono', monospace;
    color: var(--ink-dim);
  }
  .mh-wheel-chip { border: none; border-radius: 999px; padding: 5px 8px; background: rgba(0,0,0,.22); }
  .mh-target-stage {
    position: relative;
    margin-top: 10px;
    min-height: 360px;
    border-radius: 14px;
    overflow: hidden;
    background:
      radial-gradient(circle at 20% 30%, var(--mh-a-soft, rgba(255,255,0,.22)), transparent 24%),
      radial-gradient(circle at 72% 35%, var(--mh-b-soft, rgba(255,0,255,.18)), transparent 28%),
      radial-gradient(circle at 55% 82%, var(--mh-c-soft, rgba(0,255,255,.16)), transparent 26%),
      #07070c;
    box-shadow: 0 16px 60px rgba(0,0,0,.6);
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
    background: rgba(10,10,16,.56);
    backdrop-filter: blur(2px);
  }
  .mh-urlbar { display: flex; align-items: center; gap: 8px; padding: 0 12px; font: 12px 'Space Mono', monospace; color: var(--ink); }
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
  .mh-stage-label { position: absolute; left: 12px; bottom: 10px; z-index: 8; font: 11px 'Space Mono', monospace; color: var(--ink); background: rgba(0,0,0,.52); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border-radius: 999px; padding: 7px 12px; }
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
  /* ── Tab: clip to hex outline so corners don't show dark bg ── */
  .mh-suite-tab { clip-path: polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%); }
  /* ── Strip remaining border rings ── */
  .mh-web-preview { box-shadow: 0 20px 60px rgba(0,0,0,.5) !important; }
  .mh-web-nav { border: none !important; }
  .mh-tpl-card { box-shadow: none !important; }
  /* ── Full-page fold overlay ── */
  #mhPageFold {
    position:fixed; inset:0; z-index:200; pointer-events:none; display:none;
    background:rgba(6,6,12,.97);
    background-image:linear-gradient(var(--mh-grid-line,rgba(128,128,128,.07)) 1px,transparent 1px),
      linear-gradient(90deg,var(--mh-grid-line,rgba(128,128,128,.07)) 1px,transparent 1px);
    background-size:24px 24px; transform-origin:top center;
  }
  #mhPageFold.mh-pf-cover { display:block; animation:mhPfCover 280ms cubic-bezier(.4,0,.2,1) forwards; }
  #mhPageFold.mh-pf-reveal { display:block; animation:mhPfReveal 340ms cubic-bezier(.15,.7,.3,1.1) forwards; }
  @keyframes mhPfCover {
    0%{transform:scaleY(0.01);opacity:0}25%{opacity:1}100%{transform:scaleY(1);opacity:1}
  }
  @keyframes mhPfReveal {
    0%{transform:scaleY(1);opacity:1}75%{opacity:.5}100%{transform:scaleY(0.01);opacity:0}
  }
  /* ── Splash page ── */
  #mhSplash {
    position:fixed; inset:0; z-index:40; overflow-y:auto; padding:28px 18px 60px;
    display:flex; flex-direction:column; align-items:center; justify-content:flex-start;
  }
  #mhSplash.mh-hidden { display:none; }
  .mh-splash-eye {
    font:11px 'Space Mono',monospace; letter-spacing:.22em; text-transform:uppercase;
    color:var(--mh-a,#ffff00); margin-bottom:6px; text-align:center;
    text-shadow:0 0 16px var(--mh-a,#ffff00); margin-top:18px;
  }
  .mh-splash-h {
    font:700 24px/1.05 'Space Mono',monospace; color:#fff; text-align:center;
    margin-bottom:7px; text-shadow:0 2px 24px rgba(0,0,0,.9);
  }
  .mh-splash-sub {
    font:11px/1.6 'Space Mono',monospace; color:rgba(200,200,220,.6); text-align:center;
    margin-bottom:28px; max-width:420px;
  }
  .mh-splash-grid {
    display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:13px;
    max-width:660px; width:100%;
  }
  .mh-splash-card {
    border-radius:16px; padding:15px; cursor:pointer; position:relative; overflow:hidden;
    transition:transform .15s cubic-bezier(.2,.8,.35,1.3);
    filter:drop-shadow(0 7px 24px rgba(0,0,0,.6));
  }
  .mh-splash-card:hover { transform:translateY(-5px) scale(1.01); filter:drop-shadow(0 14px 38px rgba(0,0,0,.75)); }
  .mh-splash-card:active { transform:scale(.97); }
  .mh-splash-accent {
    position:absolute; inset:0; border-radius:16px; pointer-events:none;
    box-shadow:inset 0 0 0 1px var(--mh-a,#ffff00); opacity:0; transition:opacity .18s;
  }
  .mh-splash-card:hover .mh-splash-accent { opacity:.55; }
  .mh-spr {
    width:100%; height:96px; border-radius:10px; overflow:hidden;
    position:relative; margin-bottom:11px; background:#08080f;
  }
  .mh-sc-title { font:700 11px 'Space Mono',monospace; color:#fff; letter-spacing:.1em; text-transform:uppercase; margin-bottom:3px; text-shadow:0 1px 4px rgba(0,0,0,.9); display:block; transform:skewY(14deg) scaleX(0.92); transform-origin:left top; }
  .mh-sc-desc { font:10px/1.5 'Space Mono',monospace; color:rgba(175,175,210,.58); }
  /* Preview: colour wheel */
  .mh-spr-ring {
    position:absolute; inset:14%; border-radius:50%;
    background:conic-gradient(var(--mh-a,#ffff00),var(--mh-b,#0000ff),var(--mh-c,#00ffff),var(--mh-a,#ffff00));
    animation:mhSprSpin 9s linear infinite;
    -webkit-mask:radial-gradient(circle,transparent 34%,#000 35%);
    mask:radial-gradient(circle,transparent 34%,#000 35%);
  }
  @keyframes mhSprSpin{to{transform:rotate(360deg)}}
  /* Preview: website mockup */
  .mh-spr-browser { padding:8px 10px; display:flex; flex-direction:column; gap:5px; justify-content:center; }
  .mh-spr-topbar { height:6px; border-radius:3px; background:rgba(255,255,255,.07); display:flex; align-items:center; gap:3px; padding:0 5px; }
  .mh-spr-dot { width:3px; height:3px; border-radius:50%; background:rgba(255,255,255,.18); flex-shrink:0; }
  .mh-spr-url { height:4px; flex:1; border-radius:2px; background:rgba(255,255,255,.06); }
  .mh-spr-hero { height:26px; border-radius:4px; background:linear-gradient(110deg,var(--mh-a,#ffff00)22,transparent 40%,var(--mh-b,#0000ff)22 60%,transparent 70%); opacity:.3; }
  .mh-spr-cards { display:grid; grid-template-columns:repeat(3,1fr); gap:4px; }
  .mh-spr-card { height:16px; border-radius:3px; background:rgba(255,255,255,.05); }
  .mh-spr-card:nth-child(1){box-shadow:inset 0 0 0 1px var(--mh-a,#ffff00)55}
  .mh-spr-card:nth-child(2){box-shadow:inset 0 0 0 1px var(--mh-b,#0000ff)55}
  .mh-spr-card:nth-child(3){box-shadow:inset 0 0 0 1px var(--mh-c,#00ffff)55}
  /* Preview: logo mini hexes */
  .mh-spr-logo { display:flex; align-items:center; justify-content:center; gap:1px; padding:6px; flex-wrap:wrap; max-width:160px; margin:0 auto; }
  .mh-spr-logo-c { width:20px; height:23px; position:relative; display:inline-block; margin:0 1px; }
  .mh-spr-lf { position:absolute; inset:0; }
  .mh-spr-lf.t{clip-path:polygon(50% 0%,100% 25%,50% 50%,0% 25%)}
  .mh-spr-lf.r{clip-path:polygon(100% 25%,100% 75%,50% 100%,50% 50%)}
  .mh-spr-lf.l{clip-path:polygon(0% 25%,50% 50%,50% 100%,0% 75%)}
  /* Preview: QR grid */
  .mh-spr-qr { display:flex; align-items:center; justify-content:center; }
  .mh-spr-qr-g { display:grid; grid-template-columns:repeat(7,10px); grid-template-rows:repeat(7,10px); gap:2px; }
  .mh-spr-qd { border-radius:2px; }
  .mh-spr-qd.qa { background:var(--mh-a,#ffff00); }
  .mh-spr-qd.qb { background:var(--mh-b,#0000ff); }
  .mh-spr-qd.qx { background:rgba(255,255,255,.04); }
  /* Preview: game hexes */
  .mh-spr-game { display:flex; align-items:center; justify-content:center; gap:2px; padding:8px; }
  .mh-spr-gc { width:26px; height:30px; position:relative; display:inline-block; }
  .mh-spr-gf { position:absolute; inset:0; }
  .mh-spr-gf.t{clip-path:polygon(50% 0%,100% 25%,50% 50%,0% 25%)}
  .mh-spr-gf.r{clip-path:polygon(100% 25%,100% 75%,50% 100%,50% 50%)}
  .mh-spr-gf.l{clip-path:polygon(0% 25%,50% 50%,50% 100%,0% 75%)}
  @keyframes mhSprHex{0%,100%{opacity:.4}50%{opacity:1}}
  /* Preview: GIF bars */
  .mh-spr-gif { display:flex; align-items:center; justify-content:center; flex-direction:column; gap:5px; padding:10px 14px; }
  .mh-spr-gbar { height:10px; border-radius:3px; animation:mhSprBarA 1.8s ease-in-out infinite alternate; }
  @keyframes mhSprBarA{0%{transform:scaleX(.25);transform-origin:left;opacity:.4}100%{transform:scaleX(1);transform-origin:left;opacity:1}}
  /* ── Back button in adapter ── */
  .mh-back-btn {
    display:inline-flex; align-items:center; gap:6px; background:rgba(255,255,255,.06);
    border:none; border-radius:8px; color:var(--ink-dim,#9090a8);
    font:11px 'Space Mono',monospace; letter-spacing:.06em; padding:7px 12px;
    cursor:pointer; margin-bottom:10px; transition:background .12s,color .12s;
  }
  .mh-back-btn:hover { background:rgba(255,255,255,.12); color:var(--ink,#dddde8); }
  /* ── Adapter hidden by default (splash is primary UI) ── */
  #mhRenderAdapter { display:none; }
  @media(max-width:600px){
    .mh-splash-grid{grid-template-columns:1fr}
    .mh-splash-h{font-size:18px}
    .mh-suite-tabs{grid-template-columns:repeat(3,minmax(0,1fr))}
  }
  /* ── 3D block typography ── */
  .mh-splash-h,
  .mh-sc-title,
  .mh-web-headline {
    text-shadow:
      1px 1px 0 var(--mh-b,#0000ff),
      2px 2px 0 var(--mh-b,#0000ff),
      3px 3px 0 var(--mh-c,#00ffff),
      4px 4px 0 var(--mh-c,#00ffff),
      5px 5px 0 rgba(0,0,0,.55),
      6px 6px 14px rgba(0,0,0,.4);
  }
  /* ── Arcade animated titles ── */
  @keyframes mhArcadeGlow {
    0%,100% { text-shadow:1px 1px 0 var(--mh-b,#0000ff),2px 2px 0 var(--mh-b),3px 3px 0 var(--mh-c),4px 4px 0 var(--mh-c),0 0 18px var(--mh-a,#ffff00),0 0 42px var(--mh-a,#ffff00); }
    33%      { text-shadow:1px 1px 0 var(--mh-c,#00ffff),2px 2px 0 var(--mh-c),3px 3px 0 var(--mh-a),4px 4px 0 var(--mh-a),0 0 18px var(--mh-b,#0000ff),0 0 42px var(--mh-b,#0000ff); }
    66%      { text-shadow:1px 1px 0 var(--mh-a,#ffff00),2px 2px 0 var(--mh-a),3px 3px 0 var(--mh-b),4px 4px 0 var(--mh-b),0 0 18px var(--mh-c,#00ffff),0 0 42px var(--mh-c,#00ffff); }
  }
  @keyframes mhArcadeScan {
    0%   { background-position:0 -100%; }
    100% { background-position:0 200%;  }
  }
  @keyframes mhBuilderPulse {
    0%,100% { color:var(--mh-a,#ffff00); letter-spacing:.08em; }
    50%      { color:var(--mh-c,#00ffff); letter-spacing:.16em; }
  }
  .mh-splash-h {
    animation: mhArcadeGlow 4s ease-in-out infinite;
    position: relative;
  }
  .mh-splash-h::after {
    content:''; position:absolute; inset:-4px; pointer-events:none;
    background:linear-gradient(to bottom,transparent 40%,rgba(255,255,255,.16) 50%,transparent 60%);
    animation:mhArcadeScan 2.8s linear infinite;
  }
  .mh-splash-eye { animation:mhArcadeGlow 4s ease-in-out infinite reverse; }
  .mh-builder-title { animation:mhBuilderPulse 3s ease-in-out infinite; }
  /* ── Cube-face diagonal layout for splash cards ── */
  .mh-splash-card:nth-child(odd)  { transform:perspective(900px) rotateY(10deg) skewY(2deg); }
  .mh-splash-card:nth-child(even) { transform:perspective(900px) rotateY(-10deg) skewY(-2deg); }
  .mh-splash-card:hover { transform:perspective(900px) rotateY(0deg) skewY(0deg) translateY(-5px) scale(1.02) !important; filter:drop-shadow(0 14px 38px rgba(0,0,0,.75)); }
  .mh-splash-card:active { transform:scale(.97) !important; }
  /* ── Builder panel rise animation on tab switch ── */
  .mh-builder-panel.active { animation:mhPanelRise .38s cubic-bezier(.2,.8,.35,1.3) forwards; }
  @keyframes mhPanelRise {
    from { transform:perspective(600px) rotateX(-6deg) translateY(10px); opacity:0; }
    to   { transform:perspective(600px) rotateX(0deg)  translateY(0);    opacity:1; }
  }
  /* ── View mode toggles ── */
  body.mh-grid-over #mhPageHexBg { z-index:30; mix-blend-mode:screen; opacity:0.18; pointer-events:none; }
  body.mh-shadows .mh-render-adapter h2,
  body.mh-shadows .mh-unified-munker-title,
  body.mh-shadows .mh-builder-title,
  body.mh-shadows .mh-suite-tab .mh-ctab-lbl,
  body.mh-shadows .mh-render-toolbar label,
  body.mh-shadows .mh-export-status,
  body.mh-shadows .mh-splash-eye,
  body.mh-shadows .mh-splash-h,
  body.mh-shadows .mh-splash-sub,
  body.mh-shadows .mh-splash-card { text-shadow:0 1px 6px rgba(0,0,0,.98),0 0 18px rgba(0,0,0,.8); }
  .mh-mode-btns { display:inline-flex; gap:5px; margin-left:8px; vertical-align:middle; }
  .mh-mode-btn { background:rgba(255,255,255,.06); border:none; border-radius:8px; color:var(--ink-dim,#9090a8); font:10px 'Space Mono',monospace; letter-spacing:.06em; padding:6px 10px; min-height:0; cursor:pointer; transition:background .12s,color .12s; }
  .mh-mode-btn:hover { background:rgba(255,255,255,.12); color:var(--ink,#dddde8); }
  .mh-mode-btn.active { background:rgba(255,255,255,.14); color:var(--mh-a,#ffff00); box-shadow:0 0 8px var(--mh-a,#ffff00); }
  /* ── No panel backgrounds: content floats on the hex cube field ── */
  html, body { background: var(--mh-dark, #030308) !important; }
  .mh-render-adapter, .mh-builder-panel, .mh-unified-munker,
  .mh-export-panel, .mh-painter-tip { background: none !important; }
  .mh-splash-card { background: rgba(var(--mh-dark-rgb, 3,3,8), .82); }
  /* ── Text contrast: single deep shadow, no white backfill ── */
  .mh-render-adapter *, .mh-builder-panel *, .mh-unified-munker *,
  .mh-export-panel *, .mh-painter-tip *, .mh-splash-card * {
    text-shadow: 0 1px 10px rgba(0,0,0,.98), 0 2px 4px rgba(0,0,0,.8) !important;
  }
  /* ── Dark theme inputs / selects ── */
  input:not([type="range"]):not([type="checkbox"]):not([type="radio"]):not([type="color"]),
  select, textarea {
    background: rgba(0,0,0,.55) !important;
    color: var(--ink,#e8e8f4) !important;
    border: 1px solid rgba(255,255,255,.12) !important;
    border-radius: 6px !important;
    padding: 5px 8px !important;
    outline: none !important;
  }
  input:not([type="range"]):focus, select:focus, textarea:focus {
    border-color: rgba(var(--mh-a-rgb,255,220,0),.5) !important;
    box-shadow: 0 0 0 2px rgba(var(--mh-a-rgb,255,220,0),.15) !important;
  }
  select option { background:#0e0e1e; color:#e8e8f4; }
  /* ── Range sliders: palette-A thumb with glow ── */
  input[type="range"] { -webkit-appearance:none; appearance:none; height:5px; border-radius:99px; background:rgba(255,255,255,.16); outline:none; cursor:pointer; }
  input[type="range"]::-webkit-slider-runnable-track { height:5px; border-radius:99px; background:rgba(255,255,255,.16); }
  input[type="range"]::-webkit-slider-thumb { -webkit-appearance:none; width:18px; height:18px; border-radius:50%; background:var(--mh-a,#ffff00); box-shadow:0 0 10px var(--mh-a,#ffff00),0 0 22px var(--mh-a,#ffff00); margin-top:-6px; cursor:pointer; border:2px solid rgba(0,0,0,.5); }
  input[type="range"]::-moz-range-thumb { width:18px; height:18px; border-radius:50%; border:2px solid rgba(0,0,0,.5); background:var(--mh-a,#ffff00); box-shadow:0 0 10px var(--mh-a,#ffff00); }
  /* ── TV-subtitle tonal outline: dark hue-tinted stroke on all text ── */
  body { -webkit-text-stroke:1px var(--mh-dark,#030308); paint-order:stroke fill; }
  button, input[type="text"], input[type="number"], input[type="color"],
  select, textarea, .mh-web-preview *, .mh-spr * {
    -webkit-text-stroke:0 !important; paint-order:normal !important;
  }
  /* ── Hex-face cube tabs: cube blocks with label printed on left isometric face ── */
  .mh-ctab-cube { display:block !important; }
  .mh-suite-tabs { gap:8px !important; align-items:flex-end !important; }
  .mh-suite-tab {
    position:relative; display:block;
    width:76px; height:76px !important; padding:0 !important;
    border:none !important; background:transparent !important;
    border-radius:0 !important; clip-path:none !important;
    filter:drop-shadow(0 7px 14px rgba(0,0,0,.55)) !important;
    transition:filter .14s, transform .14s cubic-bezier(.2,.8,.35,1.3) !important;
  }
  .mh-suite-tab:hover { transform:translateY(-4px) !important; filter:drop-shadow(0 10px 18px rgba(0,0,0,.7)) brightness(1.18) !important; }
  .mh-suite-tab.active { transform:translateY(-6px) scale(1.04) !important; filter:drop-shadow(0 14px 24px rgba(0,0,0,.85)) brightness(1.3) !important; }
  .mh-ctab-f { position:absolute; inset:0; background:var(--pxc, var(--mh-b,#0040ff)); }
  .mh-ctab-t { clip-path:polygon(50% 0%,100% 25%,50% 50%,0% 25%); filter:brightness(1.55); }
  .mh-ctab-r { clip-path:polygon(100% 25%,100% 75%,50% 100%,50% 50%); filter:brightness(0.88); }
  .mh-ctab-l { clip-path:polygon(0% 25%,50% 50%,50% 100%,0% 75%); filter:brightness(0.46); }
  .mh-ctab-lbl {
    position:absolute; left:3px; top:44%; width:46%; height:52%;
    display:flex; align-items:center; justify-content:center;
    color:var(--ink,#f0f0f8) !important;
    font:bold 7px 'Space Mono',monospace !important;
    letter-spacing:.07em; text-transform:uppercase;
    transform:skewY(27deg) scaleX(0.82) !important;
    transform-origin:left center; white-space:nowrap;
    text-shadow:0 1px 4px rgba(0,0,0,.95); pointer-events:none;
  }
  /* ── Neon mode ── */
  @keyframes mhNeonFlicker {
    0%,18%,22%,25%,53%,57%,100%{
      text-shadow:0 0 7px #fff,0 0 10px #fff,0 0 21px #fff,
                  0 0 42px var(--mh-a,#ffff00),0 0 82px var(--mh-a),0 0 92px var(--mh-a);
      opacity:1;
    }
    20%,24%,55%{ text-shadow:none; opacity:0.28; }
  }
  @keyframes mhNeonHue { from{filter:hue-rotate(0deg) saturate(1.6)} to{filter:hue-rotate(360deg) saturate(1.6)} }
  body.mh-neon .mh-splash-h { animation:mhNeonFlicker 3s infinite,mhArcadeGlow 4s ease-in-out infinite !important; }
  body.mh-neon .mh-splash-eye { animation:mhNeonFlicker 2.7s infinite reverse,mhArcadeGlow 4s ease-in-out infinite reverse !important; }
  body.mh-neon #mhPageHexBg { animation:mhNeonHue 10s linear infinite; }
  body.mh-neon .mh-builder-title { animation:mhBuilderPulse 1.5s ease-in-out infinite,mhNeonFlicker 2.2s infinite !important; }
  body.mh-neon .mh-suite-tab.active { animation:mhPxPulse 0.8s ease-in-out infinite alternate !important; }
  /* ── Logo sim canvas grid: iso-face diamonds ── */
  #mhLogoSimGrid { display:none; grid-template-columns:repeat(4,1fr); gap:2px; margin:6px 0; }
  #mhLogoSimGrid canvas {
    width:100%; aspect-ratio:2/1;
    cursor:pointer; image-rendering:pixelated;
    clip-path:polygon(50% 0%,100% 50%,50% 100%,0% 50%);
    border-radius:0; border:none;
    transition:filter .12s;
    filter:brightness(0.85);
  }
  #mhLogoSimGrid canvas.mh-sim-sel {
    filter:brightness(1.35) drop-shadow(0 0 6px var(--mh-a,#ff0));
  }
  /* ── Logo library: saved picks ── */
  #mhLogoLibrary { display:flex; flex-wrap:wrap; gap:6px; margin:8px 0 4px; min-height:0; }
  .mh-lib-chip {
    display:flex; flex-direction:column; align-items:center;
    background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.10);
    border-radius:6px; padding:4px 8px; cursor:pointer; font:9px 'Space Mono',monospace;
    color:var(--ink-dim,#9090a8); transition:border-color .1s,background .1s;
  }
  .mh-lib-chip:hover { border-color:var(--mh-a,#ff0); background:rgba(255,255,255,.12); color:var(--ink,#e8e8f4); }
  /* ── Wheel hide toggle ── */
  #mhWheelToggle { margin:0 8px 10px; padding:5px 12px; font:10px 'Space Mono',monospace; letter-spacing:.06em; border:1px solid rgba(255,255,255,.18); background:rgba(255,255,255,.06); border-radius:6px; cursor:pointer; color:var(--ink-dim); }
  /* ── Domino cascade: tiles squash top-to-bottom on tab switch ── */
  @keyframes mhDomino {
    0%   { transform:scaleY(1); opacity:1; }
    35%  { transform:scaleY(0.04) translateY(48%); opacity:0.65; }
    70%  { transform:scaleY(1); opacity:1; }
    100% { transform:scaleY(1); opacity:1; }
  }
  #mhPageHexBg.mh-domino .mh-pxhex {
    animation:mhDomino 0.5s calc(var(--row,0) * 38ms) ease-in-out both !important;
    transform-origin:center bottom !important;
  }
  /* ── Retro 1995 Nike LED ad splash card ── */
  .mh-card-retro {
    border:3px solid var(--mh-a,#ff0) !important;
    box-shadow:0 0 0 1px #000, 0 0 18px var(--mh-a,#ff0), 0 0 38px var(--mh-a,#ff0), inset 0 0 18px rgba(0,0,0,.85) !important;
    background:#000 !important;
  }
  .mh-retro-screen {
    position:relative; width:100%; height:96px; border-radius:10px; overflow:hidden;
    background:#000;
    background-image:
      radial-gradient(ellipse 80% 60% at 50% 45%, rgba(var(--mh-a-rgb,255,200,0),.06) 0%, transparent 70%),
      repeating-linear-gradient(0deg, transparent 0, transparent 3px, rgba(0,0,0,.45) 3px, rgba(0,0,0,.45) 4px);
    margin-bottom:11px;
  }
  .mh-retro-scanlines {
    position:absolute; inset:0; pointer-events:none; z-index:5;
    background:repeating-linear-gradient(0deg, rgba(0,0,0,.07) 0, rgba(0,0,0,.07) 1px, transparent 1px, transparent 4px);
  }
  .mh-retro-copy { position:absolute; inset:0; padding:7px 10px; display:flex; flex-direction:column; justify-content:center; }
  .mh-retro-eyebrow {
    font:600 5px 'Space Mono',monospace; letter-spacing:.22em; text-transform:uppercase;
    color:rgba(var(--mh-a-rgb,255,200,0),.45); margin-bottom:3px;
    animation:mhRetroTick 1.1s step-start infinite;
  }
  .mh-retro-line1,.mh-retro-line2,.mh-retro-line3 {
    font:900 19px 'Space Mono',monospace; line-height:1.05;
    letter-spacing:.14em; text-transform:uppercase;
    color:var(--mh-a,#ff0);
    -webkit-text-stroke:1px var(--mh-a,#ff0);
    animation:mhRetroNeon 2.8s ease-in-out infinite alternate;
  }
  .mh-retro-line1{animation-delay:0s;} .mh-retro-line2{animation-delay:.35s;} .mh-retro-line3{animation-delay:.7s;}
  .mh-retro-ticker {
    position:absolute; bottom:3px; left:0; right:0; overflow:hidden;
    font:400 5px 'Space Mono',monospace; letter-spacing:.1em; text-transform:uppercase;
    color:rgba(var(--mh-a-rgb,255,200,0),.32); white-space:nowrap;
    animation:mhRetroScroll 14s linear infinite;
  }
  @keyframes mhRetroNeon {
    0%  { text-shadow:0 0 5px var(--mh-a,#ff0),0 0 12px var(--mh-a,#ff0),2px 2px 0 rgba(0,0,0,.95); }
    60% { text-shadow:0 0 9px var(--mh-a,#ff0),0 0 24px var(--mh-a,#ff0),0 0 48px var(--mh-a,#ff0),2px 2px 0 rgba(0,0,0,.95); }
    100%{ text-shadow:0 0 7px var(--mh-a,#ff0),0 0 16px var(--mh-a,#ff0),0 0 30px var(--mh-a,#ff0),2px 2px 0 rgba(0,0,0,.95); }
  }
  @keyframes mhRetroTick { 0%,100%{opacity:1} 50%{opacity:0} }
  @keyframes mhRetroScroll { 0%{transform:translateX(100%)} 100%{transform:translateX(-900%)} }
</style>
<div id="mhPageFold"></div>
<div id="mhSplash">
  <div class="mh-splash-eye">Hexfield · Palette Engine</div>
  <h1 class="mh-splash-h">What are we building today?</h1>
  <p class="mh-splash-sub">Palette-calibrated Munker optics for every medium. Pick a tool and the animated hex grid becomes your canvas.</p>
  <div class="mh-splash-grid">
    <div class="mh-splash-card" data-dest="colour">
      <div class="mh-spr"><div class="mh-spr-ring"></div></div>
      <div class="mh-sc-title">Colour Theory</div>
      <div class="mh-sc-desc">CMY wheel · 3D hue cube · tonal analysis</div>
      <div class="mh-splash-accent"></div>
    </div>
    <div class="mh-splash-card" data-dest="web">
      <div class="mh-spr mh-spr-browser">
        <div class="mh-spr-topbar"><span class="mh-spr-dot"></span><span class="mh-spr-dot"></span><span class="mh-spr-url"></span></div>
        <div class="mh-spr-hero"></div>
        <div class="mh-spr-cards"><div class="mh-spr-card"></div><div class="mh-spr-card"></div><div class="mh-spr-card"></div></div>
      </div>
      <div class="mh-sc-title">Website Design</div>
      <div class="mh-sc-desc">Full-page templates · palette tokens · export</div>
      <div class="mh-splash-accent"></div>
    </div>
    <div class="mh-splash-card" data-dest="logo">
      <div class="mh-spr mh-spr-logo">
        <div class="mh-spr-logo-c"><div class="mh-spr-lf t" style="background:var(--mh-a,#ffff00);filter:brightness(1.5)"></div><div class="mh-spr-lf r" style="background:var(--mh-a,#ffff00);filter:brightness(.85)"></div><div class="mh-spr-lf l" style="background:var(--mh-a,#ffff00);filter:brightness(.45)"></div></div>
        <div class="mh-spr-logo-c"><div class="mh-spr-lf t" style="background:var(--mh-b,#0000ff);filter:brightness(1.5)"></div><div class="mh-spr-lf r" style="background:var(--mh-b,#0000ff);filter:brightness(.85)"></div><div class="mh-spr-lf l" style="background:var(--mh-b,#0000ff);filter:brightness(.45)"></div></div>
        <div class="mh-spr-logo-c"><div class="mh-spr-lf t" style="background:var(--mh-c,#00ffff);filter:brightness(1.5)"></div><div class="mh-spr-lf r" style="background:var(--mh-c,#00ffff);filter:brightness(.85)"></div><div class="mh-spr-lf l" style="background:var(--mh-c,#00ffff);filter:brightness(.45)"></div></div>
        <div class="mh-spr-logo-c"><div class="mh-spr-lf t" style="background:var(--mh-a,#ffff00);filter:brightness(1.5)"></div><div class="mh-spr-lf r" style="background:var(--mh-a,#ffff00);filter:brightness(.85)"></div><div class="mh-spr-lf l" style="background:var(--mh-a,#ffff00);filter:brightness(.45)"></div></div>
        <div class="mh-spr-logo-c"><div class="mh-spr-lf t" style="background:var(--mh-b,#0000ff);filter:brightness(1.5)"></div><div class="mh-spr-lf r" style="background:var(--mh-b,#0000ff);filter:brightness(.85)"></div><div class="mh-spr-lf l" style="background:var(--mh-b,#0000ff);filter:brightness(.45)"></div></div>
      </div>
      <div class="mh-sc-title">Logo Design</div>
      <div class="mh-sc-desc">Animated hex mark · randomised seed · brand type</div>
      <div class="mh-splash-accent"></div>
    </div>
    <div class="mh-splash-card" data-dest="qr">
      <div class="mh-spr mh-spr-qr">
        <div class="mh-spr-qr-g">
          <div class="mh-spr-qd qa"></div><div class="mh-spr-qd qa"></div><div class="mh-spr-qd qa"></div><div class="mh-spr-qd qx"></div><div class="mh-spr-qd qa"></div><div class="mh-spr-qd qa"></div><div class="mh-spr-qd qa"></div>
          <div class="mh-spr-qd qa"></div><div class="mh-spr-qd qx"></div><div class="mh-spr-qd qx"></div><div class="mh-spr-qd qb"></div><div class="mh-spr-qd qx"></div><div class="mh-spr-qd qx"></div><div class="mh-spr-qd qa"></div>
          <div class="mh-spr-qd qa"></div><div class="mh-spr-qd qx"></div><div class="mh-spr-qd qa"></div><div class="mh-spr-qd qx"></div><div class="mh-spr-qd qa"></div><div class="mh-spr-qd qx"></div><div class="mh-spr-qd qa"></div>
          <div class="mh-spr-qd qx"></div><div class="mh-spr-qd qb"></div><div class="mh-spr-qd qx"></div><div class="mh-spr-qd qa"></div><div class="mh-spr-qd qx"></div><div class="mh-spr-qd qb"></div><div class="mh-spr-qd qx"></div>
          <div class="mh-spr-qd qa"></div><div class="mh-spr-qd qx"></div><div class="mh-spr-qd qa"></div><div class="mh-spr-qd qx"></div><div class="mh-spr-qd qa"></div><div class="mh-spr-qd qx"></div><div class="mh-spr-qd qa"></div>
          <div class="mh-spr-qd qa"></div><div class="mh-spr-qd qx"></div><div class="mh-spr-qd qx"></div><div class="mh-spr-qd qb"></div><div class="mh-spr-qd qx"></div><div class="mh-spr-qd qx"></div><div class="mh-spr-qd qa"></div>
          <div class="mh-spr-qd qa"></div><div class="mh-spr-qd qa"></div><div class="mh-spr-qd qa"></div><div class="mh-spr-qd qx"></div><div class="mh-spr-qd qa"></div><div class="mh-spr-qd qa"></div><div class="mh-spr-qd qa"></div>
        </div>
      </div>
      <div class="mh-sc-title">QR Code</div>
      <div class="mh-sc-desc">Palette-calibrated QR · Munker overlay export</div>
      <div class="mh-splash-accent"></div>
    </div>
    <div class="mh-splash-card" data-dest="game">
      <div class="mh-spr mh-spr-game">
        <div class="mh-spr-gc" style="animation:mhSprHex 2.2s .0s ease-in-out infinite"><div class="mh-spr-gf t" style="background:var(--mh-a,#ffff00);filter:brightness(1.5)"></div><div class="mh-spr-gf r" style="background:var(--mh-a,#ffff00);filter:brightness(.85)"></div><div class="mh-spr-gf l" style="background:var(--mh-a,#ffff00);filter:brightness(.45)"></div></div>
        <div class="mh-spr-gc" style="animation:mhSprHex 2.2s .3s ease-in-out infinite"><div class="mh-spr-gf t" style="background:var(--mh-b,#0000ff);filter:brightness(1.5)"></div><div class="mh-spr-gf r" style="background:var(--mh-b,#0000ff);filter:brightness(.85)"></div><div class="mh-spr-gf l" style="background:var(--mh-b,#0000ff);filter:brightness(.45)"></div></div>
        <div class="mh-spr-gc" style="animation:mhSprHex 2.2s .6s ease-in-out infinite"><div class="mh-spr-gf t" style="background:var(--mh-c,#00ffff);filter:brightness(1.5)"></div><div class="mh-spr-gf r" style="background:var(--mh-c,#00ffff);filter:brightness(.85)"></div><div class="mh-spr-gf l" style="background:var(--mh-c,#00ffff);filter:brightness(.45)"></div></div>
        <div class="mh-spr-gc" style="animation:mhSprHex 2.2s .9s ease-in-out infinite"><div class="mh-spr-gf t" style="background:var(--mh-a,#ffff00);filter:brightness(1.5)"></div><div class="mh-spr-gf r" style="background:var(--mh-a,#ffff00);filter:brightness(.85)"></div><div class="mh-spr-gf l" style="background:var(--mh-a,#ffff00);filter:brightness(.45)"></div></div>
        <div class="mh-spr-gc" style="animation:mhSprHex 2.2s .5s ease-in-out infinite"><div class="mh-spr-gf t" style="background:var(--mh-b,#0000ff);filter:brightness(1.5)"></div><div class="mh-spr-gf r" style="background:var(--mh-b,#0000ff);filter:brightness(.85)"></div><div class="mh-spr-gf l" style="background:var(--mh-b,#0000ff);filter:brightness(.45)"></div></div>
      </div>
      <div class="mh-sc-title">Game Scene</div>
      <div class="mh-sc-desc">Hex platformer · Munker ground · level builder</div>
      <div class="mh-splash-accent"></div>
    </div>
    <div class="mh-splash-card" data-dest="gif">
      <div class="mh-spr mh-spr-gif">
        <div style="width:90%;display:flex;flex-direction:column;gap:5px">
          <div class="mh-spr-gbar" style="background:var(--mh-a,#ffff00);animation-delay:0s"></div>
          <div class="mh-spr-gbar" style="background:var(--mh-b,#0000ff);animation-delay:.35s"></div>
          <div class="mh-spr-gbar" style="background:var(--mh-c,#00ffff);animation-delay:.7s"></div>
          <div class="mh-spr-gbar" style="background:rgba(255,255,255,.42);animation-delay:.18s"></div>
        </div>
      </div>
      <div class="mh-sc-title">GIF Export</div>
      <div class="mh-sc-desc">Timeline presets · animated palette renders</div>
      <div class="mh-splash-accent"></div>
    </div>
    <div class="mh-splash-card mh-card-retro" data-dest="logo">
      <div class="mh-retro-screen">
        <div class="mh-retro-scanlines"></div>
        <div class="mh-retro-copy">
          <div class="mh-retro-eyebrow">HEXFIELD · EST. MMXXVI</div>
          <div class="mh-retro-line1">JUST</div>
          <div class="mh-retro-line2">MAKE</div>
          <div class="mh-retro-line3">ART.</div>
        </div>
        <div class="mh-retro-ticker">[ PALETTE ENGINE · NEON EDITION · V2 · MUNKER OPTICS · COLOUR THEORY · ] &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; [ JUST MAKE ART · HEXFIELD · ]</div>
      </div>
      <div class="mh-sc-title">Retro Ad</div>
      <div class="mh-sc-desc">1995 LED screen · neon poster · ad generator</div>
      <div class="mh-splash-accent"></div>
    </div>
  </div>
</div>
<section class="mh-render-adapter" id="mhRenderAdapter">
  <button class="mh-back-btn" id="mhBackBtn">&#8592; Tools</button>
  <span class="mh-mode-btns">
    <button class="mh-mode-btn" id="mhGridBtn" title="Hex grid overlay">Grid+</button>
    <button class="mh-mode-btn" id="mhShadowBtn" title="Drop shadows">Shadow</button>
    <button class="mh-mode-btn" id="mhNeonBtn" title="Neon mode">Neon</button>
  </span>
  <div class="mh-suite-tabs" id="mhSuiteTabs">
    <button class="mh-suite-tab active" data-suite-tab="web"><div class="mh-ctab-cube"><div class="mh-ctab-f mh-ctab-t"></div><div class="mh-ctab-f mh-ctab-r"></div><div class="mh-ctab-f mh-ctab-l"></div></div><span class="mh-ctab-lbl">Web</span></button>
    <button class="mh-suite-tab" data-suite-tab="game"><div class="mh-ctab-cube"><div class="mh-ctab-f mh-ctab-t"></div><div class="mh-ctab-f mh-ctab-r"></div><div class="mh-ctab-f mh-ctab-l"></div></div><span class="mh-ctab-lbl">Game</span></button>
    <button class="mh-suite-tab" data-suite-tab="character"><div class="mh-ctab-cube"><div class="mh-ctab-f mh-ctab-t"></div><div class="mh-ctab-f mh-ctab-r"></div><div class="mh-ctab-f mh-ctab-l"></div></div><span class="mh-ctab-lbl">Character</span></button>
    <button class="mh-suite-tab" data-suite-tab="gif"><div class="mh-ctab-cube"><div class="mh-ctab-f mh-ctab-t"></div><div class="mh-ctab-f mh-ctab-r"></div><div class="mh-ctab-f mh-ctab-l"></div></div><span class="mh-ctab-lbl">GIF</span></button>
    <button class="mh-suite-tab" data-suite-tab="qr"><div class="mh-ctab-cube"><div class="mh-ctab-f mh-ctab-t"></div><div class="mh-ctab-f mh-ctab-r"></div><div class="mh-ctab-f mh-ctab-l"></div></div><span class="mh-ctab-lbl">QR</span></button>
    <button class="mh-suite-tab" data-suite-tab="logo"><div class="mh-ctab-cube"><div class="mh-ctab-f mh-ctab-t"></div><div class="mh-ctab-f mh-ctab-r"></div><div class="mh-ctab-f mh-ctab-l"></div></div><span class="mh-ctab-lbl">Logo</span></button>
  </div>
  <div class="mh-panels-wrap" id="mhPanelsWrap">
  <div id="mhFoldPaper"></div>
  <div class="mh-builder-panel active" id="mhBuilderWeb">
    <div class="mh-builder-title">HEXFIELD website designer · full-page templates + export</div>
    <div class="mh-tpl-grid" id="mhTplGrid"></div>
    <div class="mh-render-toolbar">
      <select id="mhWebDensity">
        <option value="clean">Clean</option>
        <option value="rich" selected>Rich</option>
        <option value="maximal">Maximal</option>
      </select>
      <button id="mhGenerateWebBtn">Regenerate</button>
      <button id="mhSaveWebBtn">Download HTML</button>
      <button id="mhCopyWebBtn">Copy code</button>
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
    <div class="mh-builder-title">QR code designer · palette-calibrated + Munker overlay</div>
    <div class="mh-render-toolbar">
      <input id="mhQrInput" value="https://munkerhex.com" placeholder="URL or text to encode" style="flex:2" />
      <select id="mhQrStyle">
        <option value="palette">Palette · A on dark, B on light</option>
        <option value="inverse">Inverse · B on dark, A on light</option>
        <option value="mono-a">Mono A · A colour + black</option>
        <option value="mono-b">Mono B · B colour + black</option>
      </select>
      <select id="mhQrSize">
        <option value="200">Small 200 px</option>
        <option value="320" selected>Medium 320 px</option>
        <option value="480">Large 480 px</option>
      </select>
    </div>
    <div id="mhQrStage" style="position:relative;margin:10px 0;display:flex;gap:14px;flex-wrap:wrap;align-items:flex-start">
      <canvas id="mhQrCanvas" style="border-radius:8px;image-rendering:pixelated;max-width:100%"></canvas>
      <div id="mhQrInfo" style="font:11px ui-monospace,monospace;color:var(--ink-dim);max-width:220px;line-height:1.6"></div>
    </div>
    <div class="mh-render-toolbar">
      <button id="mhQrGenerateBtn">Generate QR</button>
      <button id="mhQrDownloadBtn" style="display:none">Download PNG</button>
      <button id="mhQrSvgBtn" style="display:none">Download SVG</button>
      <span id="mhQrStatus" class="mh-export-status"></span>
    </div>
  </div>
  <div class="mh-builder-panel" id="mhBuilderLogo">
    <div class="mh-builder-title">Logo designer · randomised hex mark + type</div>
    <div class="mh-render-toolbar">
      <button id="mhLogoRegenBtn">Regenerate mark</button>
      <button id="mhLogoSvgDlBtn">Download SVG</button>
    </div>
    <div id="mhLogoHexMark" style="display:flex;justify-content:center;align-items:center;padding:14px 0;min-height:100px"></div>
    <div id="mhLogoSimGrid"></div>
    <div id="mhLogoLibrary"></div>
    <div class="mh-render-toolbar" style="margin-top:4px">
      <button id="mhLogoNftBtn">Export Unique Art (PNG)</button>
    </div>
    <div class="mh-render-toolbar" style="margin-top:10px;flex-wrap:wrap">
      <input id="mhLogoTextLogo" maxlength="24" value="HEXFIELD" placeholder="Brand name" style="flex:2" />
      <select id="mhLogoMarkLogo"><option value="hex">Hex mark</option><option value="cube">Cube mark</option><option value="none">Text only</option></select>
      <select id="mhLogoLayoutLogo"><option value="left">Mark left</option><option value="top">Mark top</option><option value="text">Text only</option></select>
    </div>
    <div class="mh-render-toolbar" style="margin-top:4px;flex-wrap:wrap">
      <input id="mhLogoCategoryLogo" maxlength="40" value="" placeholder="Category  ·  e.g.  Tech · Design · Sport" style="flex:2" />
      <select id="mhLogoSimFont">
        <option value="'Space Mono',monospace">Space Mono</option>
        <option value="serif">Serif</option>
        <option value="sans-serif">Sans</option>
        <option value="Impact,display">Impact</option>
      </select>
    </div>
    <input class="mh-font-text-input" id="mhLogoTaglineLogo" value="Palette · Optics · Motion" placeholder="Tagline" style="margin-top:6px;width:100%;box-sizing:border-box" />
    <div id="mhLogoPreviewLogo" style="margin-top:14px;text-align:center"></div>
  </div>
  </div>
  <input id="mhUrl" value="https://example.com" style="display:none">
  <select id="mhGame" style="display:none"><option value="platformer" selected>platformer</option><option value="invaders">invaders</option><option value="maze">maze</option></select>
  <select id="mhGameStyle" style="display:none"><option value="hex3plane">hex3plane</option></select>
  <button id="mhRenderBtn" style="display:none"></button>
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
    <div id="mhFrame" style="display:none"></div>
    <div id="mhSynthetic" style="display:none"></div>
    <span id="mhHostLabel" style="display:none"></span>
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
  function _luma(hex) {
    if (!hex || hex.length < 7) return 0;
    const r=parseInt(hex.slice(1,3),16)/255, g=parseInt(hex.slice(3,5),16)/255, b=parseInt(hex.slice(5,7),16)/255;
    return 0.2126*Math.pow(r,2.2)+0.7152*Math.pow(g,2.2)+0.0722*Math.pow(b,2.2);
  }
  function _hexToHSL(hex) {
    if (!hex || hex.length < 7) return [0, 0, 100];
    let r=parseInt(hex.slice(1,3),16)/255, g=parseInt(hex.slice(3,5),16)/255, b=parseInt(hex.slice(5,7),16)/255;
    const max=Math.max(r,g,b), min=Math.min(r,g,b), l=(max+min)/2;
    if (max===min) return [0, 0, l*100];
    const d=max-min, s=l>0.5?d/(2-max-min):d/(max+min);
    const h=max===r?(g-b)/d+(g<b?6:0):max===g?(b-r)/d+2:(r-g)/d+4;
    return [h*60, s*100, l*100];
  }
  function _hslToHex(h, s, l) {
    h=((h%360)+360)%360; s/=100; l/=100;
    const a=s*Math.min(l,1-l);
    const f=n=>{const k=(n+h/30)%12,c=l-a*Math.max(Math.min(k-3,9-k,1),-1);return Math.round(c*255).toString(16).padStart(2,'0');};
    return '#'+f(0)+f(8)+f(4);
  }
  function getBestTextColor(bgHex) {
    const p = getWheelPalette();
    const bgLum = _luma(bgHex || '#0b0b10');
    const oppHue = (p.hue + 180) % 360;
    const textL = bgLum < 0.18 ? 88 : bgLum > 0.5 ? 12 : bgLum < 0.35 ? 80 : 20;
    return _hslToHex(oppHue, 72, textL);
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
  let _webPreset = 'landing';
  function currentWebDesign(){
    return { preset: _webPreset, density: $('mhWebDensity')?.value || 'rich' };
  }
  function webPresetContent(preset){
    const map = {
      landing: {
        kicker:'HEXFIELD STUDIO', headline:'A live palette calibration system for impossible web surfaces.',
        copy:'Generate hero sections, buttons, cards and animated Munker overlays from the exact colour wheel calibration. Every element inherits your palette.',
        cards:['Hero layout','CTA buttons','Animated background','Hex overlay','Type system','Colour tokens']
      },
      'theme-kit': {
        kicker:'FULL WEBSITE THEME KIT', headline:'Navigation, cards, sections and buttons from one calibrated palette.',
        copy:'A complete visual kit for Webflow, Framer, Shopify or custom CSS. Export all tokens and drop them in.',
        cards:['Navigation','Card system','Section backgrounds','Type scale','Colour tokens','Dark/light modes']
      },
      'overlay-plugin': {
        kicker:'OVERLAY PLUGIN', headline:'Drop the HEXFIELD render over any existing website.',
        copy:'Paste the exported snippet into a site builder custom-code area — the whole page gets palette-driven Munker overlays and hex fields.',
        cards:['Global overlay','Hex field','Ruliad nodes','Line artifacts','Opacity control','Blend modes']
      },
      portfolio: {
        kicker:'CREATOR PORTFOLIO', headline:'Turn case studies into glowing palette artefacts.',
        copy:'Portfolio cards, avatar blocks and project tiles follow your live CMY calibration. Your work, your colours.',
        cards:['Project cards','Avatar block','Contact CTA','Gallery grid','Skills section','Download CV']
      },
      shop: {
        kicker:'PRODUCT LAUNCH', headline:'A shop landing page with collectible visual energy.',
        copy:'Product cards, checkout CTAs and banner surfaces inherit the exact HEXFIELD palette. Built for conversion.',
        cards:['Product cards','Offer banner','Checkout CTA','Trust badges','Review section','Price table']
      }
    };
    return map[preset] || map.landing;
  }
  function buildTplGrid(){
    const grid = $('mhTplGrid'); if (!grid) return;
    const p = getWheelPalette();
    const TPL = [
      { id:'landing',         label:'Landing',   bg:p.aHex },
      { id:'theme-kit',       label:'Theme Kit', bg:p.bHex },
      { id:'overlay-plugin',  label:'Overlay',   bg:p.cHex },
      { id:'portfolio',       label:'Portfolio', bg:p.aHex },
      { id:'shop',            label:'Shop',      bg:p.bHex },
    ];
    grid.innerHTML = TPL.map(t =>
      `<div class="mh-tpl-card${t.id===_webPreset?' active':''}" data-tpl="${t.id}">` +
      `<div class="mh-tpl-thumb" style="background:linear-gradient(135deg,${t.bg}30 0%,transparent 70%),#0b0b10"></div>${t.label}</div>`
    ).join('');
    grid.querySelectorAll('.mh-tpl-card').forEach(el => {
      el.addEventListener('click', () => { _webPreset = el.dataset.tpl; buildTplGrid(); renderWebDesigner(); });
    });
  }
  function downloadWebHtml(){
    const p = getWheelPalette();
    const inner = $('mhWebPreviewInner');
    const bodyHtml = inner ? inner.innerHTML : '';
    const css = `*{box-sizing:border-box;margin:0;padding:0}body{background:#0b0b10;color:#e8e8f0;font-family:ui-sans-serif,system-ui,sans-serif}:root{--mh-a:${p.aHex};--mh-b:${p.bHex};--mh-c:${p.cHex}}nav{display:flex;align-items:center;justify-content:space-between;padding:12px 32px;border-bottom:1px solid #ffffff14}a{text-decoration:none;cursor:pointer}h1{font-size:clamp(24px,5vw,52px);line-height:1.05;font-weight:900}p{line-height:1.7;color:#8888a8}.mh-web-btn{display:inline-flex;align-items:center;padding:12px 24px;border-radius:999px;font-weight:700;background:${p.aHex};color:#05050a;border:none;cursor:pointer;font-size:14px}.mh-web-btn.secondary{background:transparent;color:${p.bHex};border:1.5px solid ${p.bHex}}.mh-web-card{padding:20px;border:1px solid #ffffff18;border-radius:12px;background:rgba(255,255,255,.04)}.mh-web-card b{display:block;color:${p.aHex};margin-bottom:6px;font-size:12px;letter-spacing:.1em;text-transform:uppercase}`;
    const html = `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HEXFIELD Export \xb7 ${_webPreset}</title><style>${css}</style></head><body>${bodyHtml}` + '</' + 'body></' + 'html>';
    const blob = new Blob([html], {type:'text/html'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `hexfield-${_webPreset}-${Date.now()}.html`;
    a.click();
    const st = $('mhExportStatus'); if (st) { st.textContent = 'HTML downloaded.'; setTimeout(() => st.textContent='', 2000); }
  }
  function renderWebDesigner(){
    const p = getWheelPalette();
    const web = currentWebDesign();
    const content = webPresetContent(web.preset);
    const inner = $('mhWebPreviewInner');
    if (!inner) return;
    // Derive layout from Munker spacing + thickness so sliders reshape the page
    const u = currentUnifiedMunker();
    const spacing = Math.max(2, u.spacing);
    const thick   = Math.max(1, u.thick);
    const lPad  = Math.max(14, Math.min(52, Math.round(spacing * 1.25)));   // outer padding
    const lGap  = Math.max(8,  Math.min(40, Math.round(spacing * 0.9)));    // col & card gap
    const hSize = Math.max(18, Math.min(52, Math.round(16 + thick * 0.7))); // headline px
    // Right-column fraction grows with thickness — thicker artifact = more visual stage
    const rFr   = Math.max(0.55, Math.min(1.6, thick * 0.028 + 0.6)).toFixed(2);
    const cardCount = web.density === 'clean' ? 3 : web.density === 'maximal' ? 6 : 4;
    const cardDetails = ['Palette-calibrated typography','Munker-safe contrast ratios','Ruliad pattern surface','Export-ready CSS tokens','Animated line field','3-plane hex depth'];
    const cards = Array.from({ length: cardCount }, (_, i) =>
      `<div class="mh-web-card" style="border-color:${renderPalette[i%renderPalette.length]}44"><b style="color:${renderPalette[i%renderPalette.length]}">${content.cards[i%content.cards.length]}</b>${cardDetails[i%cardDetails.length]}</div>`
    ).join('');
    const textCol = getBestTextColor ? getBestTextColor('#0b0b10') : '#e8e8f0';
    // Subtle right-column stat labels — ghost text that lets the artifact read through
    const statLabels = [
      { n: '042', label: 'palettes' },
      { n: '∞',   label: 'depth' },
      { n: `${Math.min(99,Math.round(thick*2))}%`, label: 'opacity' },
    ];
    const statsHtml = statLabels.map(s =>
      `<div style="line-height:1.1;opacity:.22">` +
        `<div style="font:700 ${Math.round(hSize*0.95)}px 'Space Mono',monospace;color:${p.aHex};letter-spacing:.04em">${s.n}</div>` +
        `<div style="font:9px 'Space Mono',monospace;color:${textCol};letter-spacing:.18em;text-transform:uppercase;margin-top:2px">${s.label}</div>` +
      `</div>`
    ).join('');
    inner.style.background = `radial-gradient(ellipse at 18% 20%,${p.aHex}1a 0%,transparent 44%),radial-gradient(ellipse at 78% 55%,${p.bHex}14 0%,transparent 40%),#06060c`;
    inner.innerHTML = `
      <nav class="mh-web-nav" style="padding:${Math.round(lPad*0.5)}px ${lPad}px">
        <span class="mh-web-logo" style="color:${p.aHex};letter-spacing:.18em">HEXFIELD</span>
        <span class="mh-web-links" style="gap:${lGap}px"><span>Work</span><span>Studio</span><span>Exports</span></span>
        <a class="mh-web-btn" style="padding:7px 14px;font-size:10px;min-height:0">Sign in</a>
      </nav>
      <section style="padding:${lPad}px;display:grid;grid-template-columns:1fr ${rFr}fr;gap:${lGap}px;align-items:center;min-height:220px">
        <div style="display:flex;flex-direction:column;gap:${Math.round(lGap*0.55)}px">
          <div class="mh-web-kicker" style="color:${p.bHex}">${content.kicker}</div>
          <h1 class="mh-web-headline" style="color:${p.aHex};font-size:${hSize}px;margin:0;line-height:1.06">${content.headline}</h1>
          <p class="mh-web-copy" style="color:${textCol}cc;margin:0">${content.copy}</p>
          <div class="mh-web-cta-row" style="gap:10px;margin-top:${Math.round(lGap*0.3)}px">
            <a class="mh-web-btn">Get started free</a>
            <a class="mh-web-btn secondary">View demo →</a>
          </div>
        </div>
        <div style="display:flex;flex-direction:column;justify-content:center;align-items:flex-start;gap:${lGap}px;padding:${Math.round(lPad*0.4)}px 0 ${Math.round(lPad*0.4)}px ${Math.round(lGap*0.5)}px">
          ${statsHtml}
        </div>
      </section>
      <div style="height:1px;background:linear-gradient(90deg,transparent,${p.aHex}77,${p.bHex}77,transparent);margin:0 ${lPad}px"></div>
      <section style="padding:${Math.round(lPad*0.8)}px ${lPad}px;display:grid;grid-template-columns:repeat(auto-fill,minmax(${Math.max(88,80+lGap)}px,1fr));gap:${Math.round(lGap*0.75)}px">
        ${cards}
      </section>
      <footer class="mh-web-footer">
        <span style="color:${p.aHex}88">HEXFIELD · ${content.kicker}</span>
        <span style="color:${textCol}44">spacing ${spacing}px · thick ${thick}px</span>
      </footer>`;
    const webR = $('mhWebRuliadField');
    if (webR) {
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
  var _logoSeed = new Date().toDateString();
  function renderLogoDesigner() {
    var hexWrap = $('mhLogoHexMark');
    if (hexWrap && typeof buildHexfieldMark === 'function') {
      hexWrap.innerHTML = buildHexfieldMark(_logoSeed);
    }
    var preview = $('mhLogoPreviewLogo');
    if (preview) {
      var p = getWheelPalette();
      var text = ($('mhLogoTextLogo') || {}).value || 'HEXFIELD';
      var mark = ($('mhLogoMarkLogo') || {}).value || 'hex';
      var layout = ($('mhLogoLayoutLogo') || {}).value || 'left';
      var tagline = ($('mhLogoTaglineLogo') || {}).value || '';
      var textCol = typeof getBestTextColor === 'function' ? getBestTextColor('#06060c') : p.aHex;
      var stack = "'Space Mono', ui-monospace, monospace";
      var W = 480, H = layout === 'top' ? 160 : 80;
      function hexPts(cx, cy, R) {
        var pts = [];
        for (var i = 0; i < 6; i++) { var a = Math.PI/3*i - Math.PI/6; pts.push((cx+R*Math.cos(a)).toFixed(1)+','+(cy+R*Math.sin(a)).toFixed(1)); }
        return pts.join(' ');
      }
      var markSvg = '', textX = 40, textY = H/2+12, tagY = H/2+30, anchor = 'start';
      if (layout === 'left' && mark !== 'none') {
        if (mark === 'hex') {
          var mini = 16, gap = 3;
          var offs = [[0,0],[0,-(mini*2+gap)],[mini*1.73+gap,-(mini+gap/2)],[mini*1.73+gap,mini+gap/2],[0,mini*2+gap],[-(mini*1.73+gap),mini+gap/2],[-(mini*1.73+gap),-(mini+gap/2)]];
          offs.forEach(function(o,i){ var col = i===0?p.cHex:i%2===0?p.aHex:p.bHex; markSvg += '<polygon points="'+hexPts(44+o[0],H/2+o[1],mini)+'" fill="'+col+'" opacity="'+(i===0?'0.9':'0.75')+'"/>'; });
        }
        textX = 106;
      } else if (layout === 'top') {
        if (mark === 'hex') {
          var mini = 14, gap = 3;
          var offs = [[0,0],[0,-(mini*2+gap)],[mini*1.73+gap,-(mini+gap/2)],[mini*1.73+gap,mini+gap/2],[0,mini*2+gap],[-(mini*1.73+gap),mini+gap/2],[-(mini*1.73+gap),-(mini+gap/2)]];
          offs.forEach(function(o,i){ var col = i===0?p.cHex:i%2===0?p.aHex:p.bHex; markSvg += '<polygon points="'+hexPts(W/2+o[0],44+o[1],mini)+'" fill="'+col+'" opacity="'+(i===0?'0.9':'0.75')+'"/>'; });
        }
        textX = W/2; textY = 108; tagY = 128; anchor = 'middle';
      } else { textX = W/2; anchor = 'middle'; }
      preview.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="'+W+'" height="'+H+'">'
        +markSvg
        +'<text x="'+textX+'" y="'+textY+'" text-anchor="'+anchor+'" font-family="'+stack+'" font-size="32" font-weight="700" fill="'+textCol+'">'+text+'</text>'
        +(tagline ? '<text x="'+textX+'" y="'+tagY+'" text-anchor="'+anchor+'" font-family="'+stack+'" font-size="11" fill="'+p.bHex+'" letter-spacing="0.14em">'+tagline+'</text>' : '')
        +'</svg>';
    }
    var regen = $('mhLogoRegenBtn');
    if (regen && !regen._mhWired) {
      regen._mhWired = true;
      regen.addEventListener('click', function() { _logoSeed = String(Date.now()); renderLogoDesigner(); });
    }
    var dlBtn = $('mhLogoSvgDlBtn');
    if (dlBtn && !dlBtn._mhWired) {
      dlBtn._mhWired = true;
      dlBtn.addEventListener('click', function() {
        var svgEl = $('mhLogoPreviewLogo')?.querySelector('svg');
        if (!svgEl) return;
        var blob = new Blob(['<?xml version="1.0"?>'+svgEl.outerHTML], {type:'image/svg+xml'});
        var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'logo-'+Date.now()+'.svg'; a.click();
      });
    }
    ['mhLogoTextLogo','mhLogoMarkLogo','mhLogoLayoutLogo','mhLogoTaglineLogo'].forEach(function(id) {
      var el = $(id);
      if (el && !el._mhWired) { el._mhWired = true; el.addEventListener('input', renderLogoDesigner); }
    });
    // restart sim on text or font change
    var _txtEl = $('mhLogoTextLogo');
    if (_txtEl && !_txtEl._lsWired) {
      _txtEl._lsWired = true;
      _txtEl.addEventListener('input', () => { clearTimeout(_lsRestartT); _lsRestartT = setTimeout(_startLogoSim, 350); });
    }
    var _fontEl = $('mhLogoSimFont');
    if (_fontEl && !_fontEl._lsWired) {
      _fontEl._lsWired = true;
      _fontEl.addEventListener('change', () => { clearTimeout(_lsRestartT); _lsRestartT = setTimeout(_startLogoSim, 100); });
    }
  }

  // ── Logo sim: billiards in letter boundary ────────────────────────────────
  let _lsGrids=[], _lsRafId=null, _lsRestartT=null;
  // 4 fonts × 4 rules = 16 combos
  const _lsFonts=["'Space Mono',monospace","serif","sans-serif","Impact,display"];
  const _lsRules=[
    {rule:'avoid',   N:4, spd:3.5, hOff:0,   font:0},
    {rule:'flock',   N:5, spd:4,   hOff:30,  font:0},
    {rule:'spiral',  N:4, spd:3,   hOff:60,  font:0},
    {rule:'chaos',   N:5, spd:4,   hOff:90,  font:0},
    {rule:'seek',    N:4, spd:3.5, hOff:120, font:1},
    {rule:'avoid',   N:6, spd:4,   hOff:150, font:1},
    {rule:'no-rep',  N:4, spd:3,   hOff:180, font:1},
    {rule:'excl',    N:5, spd:4,   hOff:210, font:1},
    {rule:'like-att',N:5, spd:3.5, hOff:240, font:2},
    {rule:'flock',   N:4, spd:5,   hOff:270, font:2},
    {rule:'chaos',   N:6, spd:3.5, hOff:300, font:2},
    {rule:'spiral',  N:3, spd:2.5, hOff:330, font:2},
    {rule:'like-rep',N:5, spd:4,   hOff:20,  font:3},
    {rule:'excl',    N:7, spd:3,   hOff:50,  font:3},
    {rule:'seek',    N:4, spd:5,   hOff:80,  font:3},
    {rule:'no-rep',  N:6, spd:2.5, hOff:110, font:3},
  ];
  function _drawLEDBall(ctx,bx,by,hue,inside,tick){
    const S=3, cx=Math.round(bx), cy=Math.round(by);
    for(let r=0;r<S;r++) for(let c=0;c<S;c++){
      const d=Math.hypot(r-1,c-1);
      if(d>1.5) continue;
      if(d>0.6 && ((tick*7+r*11+c*5)%4<1)) continue;
      const lum=d<0.6?98:d<1.1?80:58;
      ctx.fillStyle=`hsl(${hue},100%,${lum}%)`;
      ctx.fillRect(cx-1+c, cy-1+r, 1, 1);
    }
  }
  function _buildLetterMask(text, W, H, font) {
    const c=document.createElement('canvas'); c.width=W; c.height=H;
    const ctx=c.getContext('2d');
    ctx.fillStyle='#fff'; ctx.fillRect(0,0,W,H);
    ctx.fillStyle='#000';
    const ch=(text||'H').charAt(0);
    const fs=Math.round(H*0.72);
    ctx.font=`700 ${fs}px ${font||"'Space Mono',monospace"}`;
    ctx.textAlign='center'; ctx.textBaseline='middle';
    ctx.fillText(ch, W/2, H/2);
    const d=ctx.getImageData(0,0,W,H).data;
    const mask=new Uint8Array(W*H);
    for(let i=0;i<W*H;i++) mask[i]=d[i*4]<128?1:0;
    return mask;
  }
  class BilliardsLogoSim {
    constructor(W,H,mask,N=4,spd=3.5,hueStart=0){
      this.W=W; this.H=H; this.mask=mask;
      this.tick=0; this.trails=[];
      this.outerVisited=new Set(); this.innerVisited=new Set();
      this.outsideTotal=0;
      for(let i=0;i<W*H;i++) if(!mask[i]) this.outsideTotal++;
      this.expanded=false;
      this.balls=Array.from({length:N},(_,i)=>{
        let x,y,att=0;
        do{ x=3+Math.random()*(W-6); y=3+Math.random()*(H-6); att++; }
        while(mask[Math.round(y)*W+Math.round(x)] && att<200);
        const ang=Math.random()*Math.PI*2, sp=spd*0.8+Math.random()*spd*0.4;
        return {x,y,vx:Math.cos(ang)*sp,vy:Math.sin(ang)*sp,
                sx:x,sy:y,life:0,hue:(hueStart+i/N*180)%360,inside:false};
      });
    }
    _inLetter(x,y){
      const xi=Math.round(x),yi=Math.round(y);
      if(xi<0||xi>=this.W||yi<0||yi>=this.H) return false;
      return this.mask[yi*this.W+xi]===1;
    }
    _oob(x,y){ return x<3||x>=this.W-3||y<3||y>=this.H-3; }
    _applyRule(rule){
      const balls=this.balls;
      if(rule==='avoid'||rule==='seek'){
        const str=rule==='avoid'?-0.08:0.05;
        for(let i=0;i<balls.length;i++) for(let j=i+1;j<balls.length;j++){
          const dx=balls[j].x-balls[i].x, dy=balls[j].y-balls[i].y;
          const dist=Math.hypot(dx,dy)||1;
          if(dist<20){ const f=str/dist;
            balls[i].vx+=dx*f; balls[i].vy+=dy*f;
            balls[j].vx-=dx*f; balls[j].vy-=dy*f; }
        }
      }
      if(rule==='like-att'||rule==='like-rep'){
        const str=rule==='like-att'?0.06:-0.07;
        for(let i=0;i<balls.length;i++) for(let j=i+1;j<balls.length;j++){
          const hd=Math.abs(balls[i].hue-balls[j].hue)%360;
          if(hd<60||hd>300){
            const dx=balls[j].x-balls[i].x, dy=balls[j].y-balls[i].y;
            const dist=Math.hypot(dx,dy)||1;
            if(dist<18){ const f=str/dist;
              balls[i].vx+=dx*f; balls[i].vy+=dy*f;
              balls[j].vx-=dx*f; balls[j].vy-=dy*f; }
          }
        }
      }
      if(rule==='flock'){
        let ax=0,ay=0;
        for(const b of balls){ax+=b.vx;ay+=b.vy;}
        ax/=balls.length; ay/=balls.length;
        for(const b of balls){b.vx+=(ax-b.vx)*0.04;b.vy+=(ay-b.vy)*0.04;}
      }
      if(rule==='spiral'){
        for(const b of balls){
          const s=Math.hypot(b.vx,b.vy)||3;
          b.vx+=(-b.vy/s)*0.12; b.vy+=(b.vx/s)*0.12;
        }
      }
      if(rule==='chaos'){
        for(const b of balls){b.vx+=(Math.random()-.5)*0.6;b.vy+=(Math.random()-.5)*0.6;}
      }
      if(rule==='excl'){
        const occ=new Set();
        for(const b of balls){
          const k=`${b.x|0},${b.y|0}`;
          if(occ.has(k)){b.vx+=(Math.random()-.5)*2;b.vy+=(Math.random()-.5)*2;}
          else occ.add(k);
        }
      }
      if(rule==='no-rep'){
        for(const b of balls){
          const pi=Math.round(b.y)*this.W+Math.round(b.x);
          if(this.outerVisited.has(pi)||this.innerVisited.has(pi))
            {b.vx+=(Math.random()-.5)*1.0;b.vy+=(Math.random()-.5)*1.0;}
        }
      }
      for(const b of balls){
        const s=Math.hypot(b.vx,b.vy)||1;
        if(s>8){b.vx=b.vx/s*8;b.vy=b.vy/s*8;}
        if(s<1.5){b.vx=b.vx/s*1.5;b.vy=b.vy/s*1.5;}
      }
    }
    step(){
      this.tick++;
      if(!this.expanded && this.outerVisited.size/Math.max(1,this.outsideTotal)>0.60)
        this.expanded=true;
      for(const b of this.balls){
        b.life++;
        let nx=b.x+b.vx, ny=b.y+b.vy;
        if(b.inside){
          // Trapped in letter — bounce off letter boundary from inside
          if(!this._inLetter(nx,ny)){
            const hX=!this._inLetter(nx,b.y), hY=!this._inLetter(b.x,ny);
            if(hX){b.vx*=-1; nx=b.x;} if(hY){b.vy*=-1; ny=b.y;}
            if(!hX&&!hY){b.vx*=-1;b.vy*=-1; nx=b.x; ny=b.y;}
            const ang=Math.atan2(b.vy,b.vx)+(Math.random()-.5)*.5;
            const spd=Math.hypot(b.vx,b.vy)||3;
            b.vx=Math.cos(ang)*spd; b.vy=Math.sin(ang)*spd; nx=b.x; ny=b.y;
          }
        } else {
          // Outside — bounce off canvas walls
          if(this._oob(nx,b.y)){b.vx*=-1; nx=b.x;}
          if(this._oob(b.x,ny)){b.vy*=-1; ny=b.y;}
          if(this._inLetter(nx,ny)){
            if(this.expanded){
              // One-way gate: cross in, get trapped
              b.inside=true;
            } else {
              // Letter is wall: bounce
              const hX=this._inLetter(nx,b.y), hY=this._inLetter(b.x,ny);
              if(hX){b.vx*=-1; nx=b.x;} if(hY){b.vy*=-1; ny=b.y;}
              if(!hX&&!hY){b.vx*=-1;b.vy*=-1; nx=b.x; ny=b.y;}
              const ang=Math.atan2(b.vy,b.vx)+(Math.random()-.5)*.5;
              const spd=Math.hypot(b.vx,b.vy)||3;
              b.vx=Math.cos(ang)*spd; b.vy=Math.sin(ang)*spd; nx=b.x; ny=b.y;
            }
          }
          // Don't return to start
          if(b.life>40 && Math.hypot(nx-b.sx,ny-b.sy)<8){
            const ang=Math.atan2(ny-b.sy,nx-b.sx)+Math.PI+(Math.random()-.5)*1.6;
            const spd=Math.hypot(b.vx,b.vy)||3;
            b.vx=Math.cos(ang)*spd; b.vy=Math.sin(ang)*spd; nx=b.x; ny=b.y;
          }
        }
        b.x=Math.max(3,Math.min(this.W-4,nx));
        b.y=Math.max(3,Math.min(this.H-4,ny));
        b.hue=(b.hue+(b.inside?1.4:0.7))%360;
        const pi=Math.round(b.y)*this.W+Math.round(b.x);
        if(b.inside) this.innerVisited.add(pi); else this.outerVisited.add(pi);
        this.trails.push({x:b.x,y:b.y,h:b.hue,ins:b.inside,t:this.tick});
      }
      if(this.trails.length>this.balls.length*600)
        this.trails.splice(0,this.balls.length*120);
    }
  }
  async function _logBilliards(sim){
    const sb=sbClient(); if(!sb) return;
    const pts=sim.trails.slice(-sim.balls.length*20).map(p=>({x:Math.round(p.x),y:Math.round(p.y),h:Math.round(p.h)}));
    try{ await sb.from('billiards_trails').insert({tick:sim.tick,points:pts,coverage:sim.outerVisited.size,expanded:sim.expanded,ts:new Date().toISOString()}); }catch(_){}
  }
  function _stopLogoSims(){
    if(_lsRafId){cancelAnimationFrame(_lsRafId);_lsRafId=null;}
    _lsGrids=[];
  }
  async function _saveLogoLibEntry(v,sim){
    const sb=sbClient(); if(!sb) return;
    const brand=($('mhLogoTextLogo')||{}).value||'';
    const cat=($('mhLogoCategoryLogo')||{}).value||'';
    try{ await sb.from('logo_library').insert({
      font:_lsFonts[v.font||0],rule:v.rule,hue_off:v.hOff,
      brand_name:brand,category:cat,
      coverage:sim.outerVisited.size,expanded:sim.expanded
    }); _loadLogoLibrary(); }catch(_){}
  }
  async function _loadLogoLibrary(){
    const lib=$('mhLogoLibrary'); if(!lib) return;
    const sb=sbClient(); if(!sb){lib.innerHTML='';return;}
    try{
      const {data}=await sb.from('logo_library').select('*').order('ts',{ascending:false}).limit(12);
      if(!data||!data.length){lib.innerHTML='';return;}
      lib.innerHTML=data.map(r=>`<div class="mh-lib-chip" title="${r.font} · ${r.rule}">
        <span style="font-size:11px;color:var(--ink,#e8e8f4)">${r.brand_name||'?'}</span>
        <span>${(r.font||'').replace(/,.*/,'').replace(/'/g,'').slice(0,9)}</span>
        <span style="opacity:.6">${r.rule}</span>
      </div>`).join('');
    }catch(_){lib.innerHTML='';}
  }
  function _startLogoSim(){
    _stopLogoSims();
    const grid=$('mhLogoSimGrid'); if(!grid) return;
    grid.style.display='grid'; grid.innerHTML='';
    const text=($('mhLogoTextLogo')||{}).value||'H';
    const fontOverride=($('mhLogoSimFont')||{}).value||null;
    const W=60,H=30; // 2:1 ratio matches iso face diamond
    const darkHex=(getComputedStyle(document.documentElement).getPropertyValue('--mh-dark').trim()||'#0a0a14');
    const dn=parseInt(darkHex.replace('#',''),16);
    const [dr,dg,db]=[(dn>>16)&255,(dn>>8)&255,dn&255];
    const baseHue=(typeof getWheelPalette==='function'?getWheelPalette().hue:220);
    const ctxs=[];
    _lsRules.forEach((v,vi)=>{
      const canvas=document.createElement('canvas');
      canvas.width=W; canvas.height=H;
      grid.appendChild(canvas);
      const font=fontOverride||_lsFonts[v.font||0];
      const mask=_buildLetterMask(text,W,H,font);
      const sim=new BilliardsLogoSim(W,H,mask,v.N,v.spd,(baseHue+v.hOff)%360);
      sim._rule=v.rule; sim._v=v;
      _lsGrids.push(sim);
      const ctx=canvas.getContext('2d');
      ctx.fillStyle=darkHex; ctx.fillRect(0,0,W,H);
      ctx.fillStyle='rgba(255,255,255,.14)';
      for(let i=0;i<W*H;i++) if(mask[i]) ctx.fillRect(i%W,Math.floor(i/W),1,1);
      ctxs.push({ctx,W,H,sim});
      canvas.onclick=()=>{
        document.querySelectorAll('#mhLogoSimGrid canvas').forEach(c=>c.classList.remove('mh-sim-sel'));
        canvas.classList.add('mh-sim-sel');
        _saveLogoLibEntry(v,sim);
      };
      if(vi===0) canvas.classList.add('mh-sim-sel');
    });
    function _rafLoop(){
      _lsRafId=requestAnimationFrame(_rafLoop);
      for(const {ctx,W,H,sim} of ctxs){
        if(!sim) continue;
        sim._applyRule(sim._rule);
        sim.step(); sim.step(); sim.step();
        ctx.fillStyle=`rgba(${dr},${dg},${db},0.09)`; ctx.fillRect(0,0,W,H);
        const tail=sim.trails.slice(-sim.balls.length*30);
        for(const pt of tail){
          ctx.fillStyle=pt.ins?`hsla(${pt.h},90%,65%,0.8)`:`hsla(${pt.h},75%,52%,0.6)`;
          ctx.fillRect(pt.x|0,pt.y|0,1,1);
        }
        for(const b of sim.balls) _drawLEDBall(ctx,b.x,b.y,b.hue,b.inside,sim.tick);
      }
      if(_lsGrids[0]&&_lsGrids[0].tick%120===0) _logBilliards(_lsGrids[0]);
    }
    _rafLoop();
    _loadLogoLibrary();
  }

  function switchSuiteTab(tab){
    const inPanel = $('mhBuilder' + tab.charAt(0).toUpperCase() + tab.slice(1));
    const outPanel = document.querySelector('.mh-builder-panel.active');
    if (!inPanel || inPanel === outPanel) return;
    document.querySelectorAll('.mh-suite-tab').forEach(btn => btn.classList.toggle('active', btn.dataset.suiteTab === tab));
    _stopLogoSims(); // stop all logo sim instances on tab switch
    const bg = document.getElementById('mhPageHexBg');
    if (bg) {
      bg.classList.add('mh-domino','mh-bg-pulse');
      setTimeout(() => bg.classList.remove('mh-domino','mh-bg-pulse'), 1600);
    }
    const paper = document.getElementById('mhFoldPaper');
    const DUR_COVER = 300, DUR_REVEAL = 360;
    function _activateTab() {
      if (outPanel) outPanel.classList.remove('active');
      inPanel.classList.add('active');
      if (tab === 'web') renderWebDesigner();
      if (tab === 'game') { setVal('mhGame','platformer'); render(); }
      if (tab === 'character') renderCharacterDesigner();
      if (tab === 'gif') updateBuilderCode();
      if (tab === 'qr') setTimeout(() => { if (typeof generateQr === 'function') generateQr(); }, 60);
      if (tab === 'kit' && typeof renderKitGrid === 'function') renderKitGrid();
      if (tab === 'fonts' && typeof loadFontEffects === 'function') loadFontEffects();
      if (tab === 'type' && typeof renderTypeScale === 'function') renderTypeScale();
      if (tab === 'logo') { renderLogoDesigner(); setTimeout(_startLogoSim, 250); }
    }
    if (paper) {
      paper.classList.remove('mh-paper-cover','mh-paper-reveal');
      void paper.offsetWidth;
      paper.classList.add('mh-paper-cover');
      setTimeout(() => {
        _activateTab();
        paper.classList.remove('mh-paper-cover');
        void paper.offsetWidth;
        paper.classList.add('mh-paper-reveal');
        setTimeout(() => paper.classList.remove('mh-paper-reveal'), DUR_REVEAL);
      }, DUR_COVER);
    } else {
      _activateTab();
    }
  }
  function renderCharacterDesigner(){
    const target = $('mhCharacterPreview'); if (!target) return;
    const p = getWheelPalette();
    target.innerHTML = ['Player token','Enemy token','Pickup token','Boss token'].map((label,i) => `<div class="mh-extra-card"><b>${label}</b><span style="display:inline-block;width:42px;height:48px;clip-path:polygon(50% 0%,92% 24%,92% 74%,50% 100%,8% 74%,8% 24%);background:${[p.aHex,p.bHex,p.cHex,renderPalette[2] || p.aHex][i]};box-shadow:0 0 18px ${[p.aHex,p.bHex,p.cHex,renderPalette[2] || p.aHex][i]};"></span><br/>Generated from exact palette + Munker field.</div>`).join('');
  }

  // ── QR Code Generator ─────────────────────────────────────────────────────
  let _qrSvgCache = '';
  async function generateQr(){
    const status = $('mhQrStatus');
    const canvas = $('mhQrCanvas');
    const info = $('mhQrInfo');
    if (!canvas) return;
    if (!window.QRCode) {
      if (status) status.textContent = 'Loading QR library…';
      await new Promise((res,rej) => {
        const s = document.createElement('script');
        s.src = 'https://cdn.jsdelivr.net/npm/qrcode@1.5.3/build/qrcode.min.js';
        s.onload = res; s.onerror = rej;
        document.head.appendChild(s);
      });
    }
    const text = ($('mhQrInput')?.value || 'https://munkerhex.com').trim() || 'https://munkerhex.com';
    const style = $('mhQrStyle')?.value || 'palette';
    const size = parseInt($('mhQrSize')?.value || '320', 10);
    const p = getWheelPalette();
    const darkMap  = { palette: p.aHex, inverse: p.bHex, 'mono-a': p.aHex, 'mono-b': '#000000' };
    const lightMap = { palette: p.bHex, inverse: p.aHex, 'mono-a': '#000000', 'mono-b': p.bHex };
    const darkHex  = darkMap[style]  || p.aHex;
    const lightHex = lightMap[style] || p.bHex;
    if (status) status.textContent = 'Generating…';
    try {
      await QRCode.toCanvas(canvas, text, {
        width: size, margin: 2,
        color: { dark: darkHex, light: lightHex },
        errorCorrectionLevel: 'M',
      });
      // Munker diagonal stripe overlay at low opacity
      const ctx = canvas.getContext('2d');
      ctx.save();
      ctx.globalAlpha = 0.13;
      ctx.strokeStyle = p.aHex;
      ctx.lineWidth = 2.5;
      const sp = 10;
      for (let i = -size; i < size * 2; i += sp) {
        ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i + size, size); ctx.stroke();
      }
      // Hex-corner border frame
      ctx.globalAlpha = 0.7;
      ctx.strokeStyle = p.bHex;
      ctx.lineWidth = 3;
      if (ctx.roundRect) {
        ctx.beginPath(); ctx.roundRect(2, 2, size - 4, size - 4, 10); ctx.stroke();
      } else {
        ctx.strokeRect(3, 3, size - 6, size - 6);
      }
      ctx.restore();
      // Cache SVG for download
      _qrSvgCache = await QRCode.toString(text, { type: 'svg', color: { dark: darkHex, light: lightHex }, errorCorrectionLevel: 'M' });
      if (info) info.innerHTML = `<b>Content:</b> ${text.substring(0,60)}${text.length>60?'…':''}<br/><b>Colours:</b> dark <span style="color:${darkHex}">${darkHex}</span> · light <span style="color:${lightHex}">${lightHex}</span><br/><b>Size:</b> ${size}×${size} px`;
      if ($('mhQrDownloadBtn')) { $('mhQrDownloadBtn').style.display=''; $('mhQrSvgBtn').style.display=''; }
      if (status) status.textContent = 'QR ready.';
    } catch(e) {
      if (status) status.textContent = 'QR error: ' + (e.message || e);
    }
  }
  function downloadQrPng(){
    const canvas = $('mhQrCanvas'); if (!canvas) return;
    const a = document.createElement('a');
    a.href = canvas.toDataURL('image/png');
    a.download = 'munkerhex-qr.png'; a.click();
  }
  function downloadQrSvg(){
    if (!_qrSvgCache) return;
    const blob = new Blob([_qrSvgCache], {type:'image/svg+xml'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = 'munkerhex-qr.svg'; a.click();
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
    const _inkHue = (p.hue + 180) % 360;
    const _inkHex = _hslToHex(_inkHue, 45, 95);
    const _inkDimHex = _hslToHex(_inkHue, 22, 78);
    document.documentElement.style.setProperty('--ink', _inkHex);
    document.documentElement.style.setProperty('--ink-dim', _inkDimHex);
    stage.style.setProperty('--mh-a-soft', rgba(p.a, .25));
    stage.style.setProperty('--mh-b-soft', rgba(p.b, .22));
    stage.style.setProperty('--mh-c-soft', rgba(p.centre, .24));
    stage.style.setProperty('--mh-a-grid', rgba(p.a, .46));
    stage.style.setProperty('--mh-b-grid', rgba(p.b, .46));
    stage.style.setProperty('--mh-c-grid', rgba(p.centre, .42));
    const _darkHex = _hslToHex(p.hue, 55, 12);
    const _dn = parseInt(_darkHex.replace('#',''), 16);
    document.documentElement.style.setProperty('--mh-dark', _darkHex);
    document.documentElement.style.setProperty('--mh-dark-rgb', `${(_dn>>16)&255},${(_dn>>8)&255},${_dn&255}`);
    const _an=parseInt(p.aHex.replace('#',''),16);
    document.documentElement.style.setProperty('--mh-a-rgb',`${(_an>>16)&255},${(_an>>8)&255},${_an&255}`);
    document.documentElement.style.setProperty('--ink-on-a', _luma(p.aHex) > 0.35 ? '#000' : '#fff');
    document.documentElement.style.setProperty('--ink-on-b', _luma(p.bHex) > 0.35 ? '#000' : '#fff');
    document.documentElement.style.setProperty('--ink-on-c', _luma(p.cHex) > 0.35 ? '#000' : '#fff');
    const _tabPalette=[p.aHex,p.bHex,p.cHex,
      _hslToHex((p.hue+30)%360,70,50),_hslToHex((p.hue+210)%360,70,50),_hslToHex((p.hue+150)%360,70,50)];
    document.querySelectorAll('.mh-suite-tab').forEach((tab,i)=>{tab.style.setProperty('--pxc',_tabPalette[i%_tabPalette.length]);});
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
    if (typeof buildPageHexBg === 'function') buildPageHexBg();
    if (typeof buildTplGrid === 'function') buildTplGrid();
    const _logoPanel = document.getElementById('mhBuilderLogo');
    if (_logoPanel && _logoPanel.classList.contains('active')) renderLogoDesigner();
    const _webPanel = document.getElementById('mhBuilderWeb');
    if (_webPanel && _webPanel.classList.contains('active')) {
      clearTimeout(applyRenderPalette._webT);
      applyRenderPalette._webT = setTimeout(renderWebDesigner, 150);
    }
    clearTimeout(applyRenderPalette._qrT);
    applyRenderPalette._qrT = setTimeout(function(){
      const qrPanel = document.getElementById('mhBuilderQr');
      if (qrPanel && qrPanel.classList.contains('active') && typeof generateQr === 'function') generateQr();
    }, 300);
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
  function buildPageHexBg() {
    let bg = document.getElementById('mhPageHexBg');
    if (!bg) { bg = document.createElement('div'); bg.id = 'mhPageHexBg'; document.body.prepend(bg); }
    const p = getWheelPalette();
    document.documentElement.style.setProperty('--mh-a', p.aHex);
    document.documentElement.style.setProperty('--mh-b', p.bHex);
    document.documentElement.style.setProperty('--mh-c', p.cHex);
    document.documentElement.style.setProperty('--mh-grid-line',
      `rgba(${p.centre[0]},${p.centre[1]},${p.centre[2]},.09)`);
    const sz = 80, hexH = sz / 0.866, rowStep = hexH * 0.75 + 2, colStep = sz + 2;
    const cols = Math.ceil(window.innerWidth / colStep) + 2;
    const rows = Math.ceil((window.innerHeight + 200) / rowStep) + 2;
    const pal = [p.aHex, p.bHex, p.cHex, ...p.colors];
    const maxDelay = 2.4;
    function _faceStripe(angleDeg, hex1, hex2) {
      const u = typeof currentUnifiedMunker === 'function' ? currentUnifiedMunker() : {};
      const t = Math.max(2, u.thick || 4);
      const sp = Math.max(t + 2, (u.spacing || 10) + t);
      const op = Math.min(1, (u.opacity || 80) / 100);
      const toRgba = (hex, a) => {
        const n = parseInt(hex.replace('#',''), 16);
        return `rgba(${(n>>16)&255},${(n>>8)&255},${n&255},${a})`;
      };
      const c1 = toRgba(hex1, op), c2 = toRgba(hex2, op);
      if (hex1 === hex2) return `repeating-linear-gradient(${angleDeg}deg,${c1} 0 ${t}px,transparent ${t}px ${sp}px)`;
      const period = sp * 2;
      return `repeating-linear-gradient(${angleDeg}deg,${c1} 0 ${t}px,transparent ${t}px ${sp}px,${c2} ${sp}px ${sp+t}px,transparent ${sp+t}px ${period}px)`;
    }
    const sT = _faceStripe(60,  p.aHex, p.bHex);
    const sR = _faceStripe(120, p.bHex, p.cHex);
    const sL = _faceStripe(90,  p.cHex, p.aHex);
    const existing = bg.children;
    if (existing.length === cols * rows) {
      let i = 0;
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const t = existing[i++];
          t.style.setProperty('--pxc', pal[(r*cols+c) % pal.length]);
          if (t.children[0]) t.children[0].style.backgroundImage = sT;
          if (t.children[1]) t.children[1].style.backgroundImage = sR;
          if (t.children[2]) t.children[2].style.backgroundImage = sL;
        }
      }
      return;
    }
    let h = '';
    for (let r = 0; r < rows; r++) {
      const off = r % 2 ? (colStep * 0.5).toFixed(0) : 0;
      for (let c = 0; c < cols; c++) {
        const delay = Math.min(maxDelay, ((r + c) * 0.04)).toFixed(2);
        const cls = (r+c)%2===1 ? 'mh-pxhex mh-pxhex-b' : 'mh-pxhex';
        h += `<div class="${cls}" style="left:${(c*colStep+Number(off)).toFixed(0)}px;top:${(r*rowStep).toFixed(0)}px;width:${sz}px;height:${hexH.toFixed(0)}px;--pxc:${pal[(r*cols+c)%pal.length]};--row:${r};animation-delay:-${delay}s"><div class="mh-pxf mh-pxf-t" style="background-image:${sT}"></div><div class="mh-pxf mh-pxf-r" style="background-image:${sR}"></div><div class="mh-pxf mh-pxf-l" style="background-image:${sL}"></div></div>`;
      }
    }
    bg.innerHTML = h;
  }

  // ── Gray-Scott reaction-diffusion driving the hex background ──────────────
  class SimGrid {
    constructor(W, H) {
      this.W = W; this.H = H; this.N = W * H;
      this.u = new Float32Array(this.N).fill(1);
      this.v = new Float32Array(this.N).fill(0);
      this.f = 0.055; this.k = 0.062;
      this._seed();
    }
    _seed() {
      for (let i = 0; i < 12; i++) {
        const cx = (Math.random() * this.W) | 0;
        const cy = (Math.random() * this.H) | 0;
        for (let dy = -2; dy <= 2; dy++)
          for (let dx = -2; dx <= 2; dx++) {
            const idx = ((cy+dy+this.H)%this.H)*this.W + ((cx+dx+this.W)%this.W);
            this.v[idx] = 0.5 + Math.random()*0.1;
            this.u[idx] = 0.25;
          }
      }
    }
    step() {
      const {W,H,N,f,k} = this; const u = this.u, v = this.v;
      const nu = new Float32Array(N); const nv = new Float32Array(N);
      for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
        const i = y*W+x;
        const L = y*W+(x-1+W)%W, R = y*W+(x+1)%W;
        const U = ((y-1+H)%H)*W+x, D = ((y+1)%H)*W+x;
        const lu = u[L]+u[R]+u[U]+u[D] - 4*u[i];
        const lv = v[L]+v[R]+v[U]+v[D] - 4*v[i];
        const uvv = u[i]*v[i]*v[i];
        nu[i] = Math.min(1, Math.max(0, u[i] + 0.2*lu - uvv + f*(1-u[i])));
        nv[i] = Math.min(1, Math.max(0, v[i] + 0.1*lv + uvv - (f+k)*v[i]));
      }
      this.u.set(nu); this.v.set(nv);
    }
    hash() {
      const v = this.v, N = this.N; let s = '';
      for (let i = 0; i < 64; i++) {
        const idx = Math.round(i * (N-1) / 63);
        s += Math.min(7, (v[idx] * 8) | 0).toString(8);
      }
      return s;
    }
    nudge() {
      this.f = 0.03 + Math.random()*0.04;
      this.k = 0.055 + Math.random()*0.015;
      this._seed();
    }
  }

  let _sim = null, _simTiles = null, _simTimer = null;

  function startSim() {
    const bg = document.getElementById('mhPageHexBg');
    if (!bg) return;
    _simTiles = Array.from(bg.querySelectorAll('.mh-pxhex'));
    if (!_simTiles.length) return;
    const aspect = window.innerWidth / Math.max(1, window.innerHeight);
    const cols = Math.ceil(Math.sqrt(_simTiles.length * aspect));
    const rows = Math.ceil(_simTiles.length / Math.max(1, cols));
    _sim = new SimGrid(cols, rows);
    clearInterval(_simTimer);
    _simTimer = setInterval(tickSim, 120);
  }

  function tickSim() {
    if (!_sim || !_simTiles) return;
    _sim.step();
    const pal = getWheelPalette();
    const aH = pal.hue, bH = (aH+120)%360, cH = (aH+240)%360;
    _simTiles.forEach((el, i) => {
      const vv = _sim.v[i % _sim.N];
      const hue = vv < 0.33 ? aH : vv < 0.66 ? bH : cH;
      const sat = 55 + vv * 40;
      const lit = 28 + vv * 38;
      el.style.setProperty('--pxc', `hsl(${hue},${sat}%,${lit}%)`);
    });
  }

  async function syncSimState() {
    if (!_sim) return;
    const h = _sim.hash();
    const sb = sbClient(); if (!sb) return;
    try {
      const { data } = await sb.from('hex_sim_states').select('id').eq('hash', h).maybeSingle();
      if (data) {
        _sim.nudge();
      } else {
        await sb.from('hex_sim_states').insert({
          hash: h, f_param: _sim.f, k_param: _sim.k,
          palette_hue: getWheelPalette().hue
        });
      }
    } catch(e) {}
  }

  function subscribeSimRealtime() {
    const sb = sbClient(); if (!sb) return;
    try {
      sb.channel('hex-sim')
        .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'hex_sim_states' },
          payload => {
            if (!_sim) return;
            const {f_param, k_param} = payload.new;
            if (f_param) _sim.f = f_param;
            if (k_param) _sim.k = k_param;
            const bg = document.getElementById('mhPageHexBg');
            if (bg) {
              bg.style.transition = 'opacity .4s';
              bg.style.opacity = '0.6';
              setTimeout(() => { bg.style.opacity = ''; bg.style.transition = ''; }, 420);
            }
          })
        .subscribe();
    } catch(e) {}
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
    if (typeof munker !== 'undefined') {
      munker.mode    = mode;
      munker.thick   = thick;
      munker.spacing = spacing;
      munker.opacity = opacity;
      munker.pattern = u.pattern;
      munker.speed   = speed;
    }
    if (typeof applyMunker === 'function') applyMunker();
    else if (typeof renderHexView === 'function') renderHexView();
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
  const _urlInput = $('mhUrl');
  if (_urlInput) {
    _urlInput.addEventListener('change', render);
    _urlInput.addEventListener('keydown', function(e){ if (e.key === 'Enter') render(); });
  }
  $('mhGenerateCodeBtn').addEventListener('click', updateBuilderCode);
  $('mhCopyCodeBtn').addEventListener('click', copyBuilderCode);
  $('mhExportGifBtn').addEventListener('click', exportGif);
  document.querySelectorAll('.mh-suite-tab').forEach(btn => btn.addEventListener('click', () => switchSuiteTab(btn.dataset.suiteTab || 'web')));
  ['mhWebPreset','mhWebDensity'].forEach(id => { const el=$(id); if(el) el.addEventListener('change', renderWebDesigner); });
  $('mhGenerateWebBtn').addEventListener('click', renderWebDesigner);
  $('mhGameBuilderBtn').addEventListener('click', () => { switchSuiteTab('game'); setVal('mhGame','platformer'); render(); });
  $('mhGifDesignerBtn').addEventListener('click', () => { switchSuiteTab('gif'); exportGif(); });
  if ($('mhSyncBtn')) $('mhSyncBtn').addEventListener('click', syncMunker);
  if (frame && frame.tagName === 'IFRAME') frame.addEventListener('load', () => setTimeout(styleWholeWebsiteFrame, 120));
  // Colour wheel hide toggle
  (function(){
    const ww = document.getElementById('wheelWrap');
    if (!ww) return;
    const btn = document.createElement('button');
    btn.id = 'mhWheelToggle'; btn.textContent = 'Hide wheel';
    btn.addEventListener('click', () => {
      const hidden = ww.style.display === 'none';
      ww.style.display = hidden ? '' : 'none';
      btn.textContent = hidden ? 'Hide wheel' : 'Show wheel';
    });
    ww.parentNode.insertBefore(btn, ww);
  })();
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
    buildPageHexBg();
    buildTplGrid();
    window.addEventListener('resize', () => { clearTimeout(window._mhBgTimer); window._mhBgTimer = setTimeout(buildPageHexBg, 220); });
    $('mhSaveWebBtn')?.addEventListener('click', downloadWebHtml);
    $('mhCopyWebBtn')?.addEventListener('click', copyBuilderCode);
    syncMunker(); render(); renderWebDesigner(); renderCharacterDesigner();
    const qrGenBtn = $('mhQrGenerateBtn');
    if (qrGenBtn) {
      qrGenBtn.addEventListener('click', generateQr);
      $('mhQrDownloadBtn')?.addEventListener('click', downloadQrPng);
      $('mhQrSvgBtn')?.addEventListener('click', downloadQrSvg);
      $('mhQrInput')?.addEventListener('input', () => setTimeout(generateQr, 300));
      $('mhQrStyle')?.addEventListener('change', generateQr);
      $('mhQrSize')?.addEventListener('change', generateQr);
    }
    // ── Splash navigation ──
    function goToTool(dest) {
      const fold = document.getElementById('mhPageFold');
      if (!fold) return;
      fold.className = 'mh-pf-cover';
      setTimeout(() => {
        const splash = document.getElementById('mhSplash');
        const adapter = document.getElementById('mhRenderAdapter');
        if (splash) splash.classList.add('mh-hidden');
        if (dest === 'colour') {
          if (adapter) adapter.style.display = 'none';
          // Show colour theory tool by scrolling below adapter
          document.body.scrollTop = 0; document.documentElement.scrollTop = 0;
        } else {
          if (adapter) adapter.style.display = 'block';
          if (typeof switchSuiteTab === 'function') switchSuiteTab(dest);
        }
        fold.className = 'mh-pf-reveal';
        setTimeout(() => { fold.className = ''; }, 360);
      }, 280);
    }
    function backToSplash() {
      const fold = document.getElementById('mhPageFold');
      if (!fold) return;
      fold.className = 'mh-pf-cover';
      setTimeout(() => {
        const splash = document.getElementById('mhSplash');
        const adapter = document.getElementById('mhRenderAdapter');
        if (splash) splash.classList.remove('mh-hidden');
        if (adapter) adapter.style.display = 'none';
        window.scrollTo({ top: 0, behavior: 'instant' });
        fold.className = 'mh-pf-reveal';
        setTimeout(() => { fold.className = ''; }, 360);
      }, 280);
    }
    document.querySelectorAll('.mh-splash-card').forEach(card => {
      card.addEventListener('click', () => { const d = card.dataset.dest; if (d) goToTool(d); });
    });
    const backBtn = $('mhBackBtn');
    if (backBtn) backBtn.addEventListener('click', backToSplash);

    // ── Mode toggle buttons ────────────────────────────────────────────────
    [['mhGridBtn','mh-grid-over'],['mhShadowBtn','mh-shadows'],['mhNeonBtn','mh-neon']].forEach(([id, cls]) => {
      const btn = document.getElementById(id);
      if (!btn) return;
      btn.addEventListener('click', () => {
        document.body.classList.toggle(cls);
        btn.classList.toggle('active', document.body.classList.contains(cls));
      });
    });
    // ── NFT / unique art export from logo sim ────────────────────────────────
    document.addEventListener('click', function(e) {
      if (e.target.id !== 'mhLogoNftBtn') return;
      const simC = $('mhLogoSimCanvas');
      const svgEl = $('mhLogoPreviewLogo')?.querySelector('svg');
      if (!simC || simC.style.display === 'none') { alert('Open the Logo tab first — the sim needs to run.'); return; }
      const out = document.createElement('canvas');
      out.width = 480; out.height = 320;
      const ctx = out.getContext('2d');
      ctx.drawImage(simC, 0, 0, 480, 320);
      if (svgEl) {
        const blob = new Blob([svgEl.outerHTML], {type:'image/svg+xml'});
        const url = URL.createObjectURL(blob);
        const img = new Image();
        img.onload = () => {
          ctx.globalAlpha = 0.88; ctx.globalCompositeOperation = 'screen';
          ctx.drawImage(img, 0, 80, 480, 160);
          ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
          URL.revokeObjectURL(url);
          out.toBlob(b => { const a=document.createElement('a'); a.href=URL.createObjectURL(b); a.download=`hex-art-${Date.now()}.png`; a.click(); }, 'image/png');
        };
        img.src = url;
      } else {
        out.toBlob(b => { const a=document.createElement('a'); a.href=URL.createObjectURL(b); a.download=`hex-art-${Date.now()}.png`; a.click(); }, 'image/png');
      }
    });

    // ── Start Gray-Scott simulation ────────────────────────────────────────
    startSim();
    setInterval(syncSimState, 5000);
    subscribeSimRealtime();
  }, 400);
})();
(function(){
  var _paused = false, _pauseT = null;
  function _tick(){
    if (_paused || typeof state === 'undefined' || typeof applyRenderPalette !== 'function') return;
    state.hue = (state.hue + 0.18) % 360;
    var s = document.getElementById('inH');
    if (s) s.value = Math.round(state.hue);
    var v = document.getElementById('inHv');
    if (v) v.textContent = Math.round(state.hue);
    applyRenderPalette();
  }
  setInterval(_tick, 80);
  document.addEventListener('DOMContentLoaded', function(){
    var s = document.getElementById('inH');
    if (!s) return;
    s.addEventListener('input', function(){
      _paused = true;
      clearTimeout(_pauseT);
      _pauseT = setTimeout(function(){ _paused = false; }, 4000);
    });
  });
})();
</script>
"""
    # ── Inject server-side config ──────────────────────────────────────────────
    supabase_url      = os.environ.get("SUPABASE_URL", "https://ujqngoliwxquosickvza.supabase.co")
    supabase_anon_key = os.environ.get("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVqcW5nb2xpd3hxdW9zaWNrdnphIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgwNjQ1NTYsImV4cCI6MjA5MzY0MDU1Nn0.AbK1tLbghKQwXCg779zoyaE7qZ3yXItfktQWVy5YigA")
    public_url        = os.environ.get("PUBLIC_URL", "")
    price_designer    = os.environ.get("STRIPE_PRICE_DESIGNER", "")
    price_studio      = os.environ.get("STRIPE_PRICE_STUDIO", "")
    price_agency      = os.environ.get("STRIPE_PRICE_AGENCY", "")

    config_script = f"""<script>
window.MH_CONFIG = {{
  supabaseUrl: "{supabase_url}",
  supabaseAnonKey: "{supabase_anon_key}",
  publicUrl: "{public_url}",
  stripePrices: {{
    designer: "{price_designer}",
    studio: "{price_studio}",
    agency: "{price_agency}"
  }}
}};
</script>
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.js"></script>
<script src="https://cdn.jsdelivr.net/npm/qrcode@1.5.3/build/qrcode.min.js"></script>"""

    # ── Auth banner + Brand Kit tab + Font Effects tab (appended after render_patch) ──
    auth_and_features_patch = """
<style id="mh-auth-features">
  /* HEXFIELD hero */
  #mhHero{position:relative;padding:52px 24px 48px;text-align:center;overflow:hidden;background:radial-gradient(ellipse at 50% 0%,rgba(255,255,0,.06) 0%,transparent 60%)}
  #mhHeroMark{display:flex;justify-content:center;margin-bottom:18px;gap:2px}
  #mhHeroWord{font:900 44px/1 ui-monospace,monospace;letter-spacing:.18em;color:var(--mh-a,#ffff00);text-shadow:0 0 48px var(--mh-a,#ffff00)55;text-transform:uppercase}
  #mhHeroTag{font:11px ui-monospace,monospace;letter-spacing:.28em;color:var(--ink-dim);margin-top:10px;text-transform:uppercase}
  #mhHeroSub{font:13px/1.6 ui-monospace,monospace;color:var(--ink-dim);max-width:400px;margin:14px auto 0}
  #mhAuthBanner{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:7px 14px;background:rgba(12,12,20,.96);border-bottom:1px solid var(--line);font:12px ui-monospace,monospace;color:var(--ink-dim);flex-wrap:wrap}
  #mhAuthBanner a{color:var(--accent);cursor:pointer;text-decoration:none}
  .mh-tier-badge{padding:2px 8px;border-radius:20px;font:bold 10px ui-monospace,monospace;letter-spacing:.08em;text-transform:uppercase;background:var(--line);color:var(--ink)}
  .mh-tier-badge.designer{background:#7c3aed;color:#fff}
  .mh-tier-badge.studio{background:#0ea5e9;color:#fff}
  .mh-tier-badge.agency{background:#f59e0b;color:#000}
  #mhAuthModal{display:none;position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.75);align-items:center;justify-content:center}
  #mhAuthModal.open{display:flex}
  .mh-auth-box{background:#14141c;border:1px solid var(--line);border-radius:14px;padding:28px;width:340px;max-width:92vw}
  .mh-auth-box h3{margin:0 0 16px;font-size:14px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink)}
  .mh-auth-box input{width:100%;background:#0b0b10;border:1px solid var(--line);border-radius:8px;padding:10px;color:var(--ink);font:13px ui-monospace,monospace;margin-bottom:10px;box-sizing:border-box}
  .mh-auth-tabs{display:flex;gap:6px;margin-bottom:16px}
  .mh-auth-tab{flex:1;padding:7px;border:1px solid var(--line);border-radius:8px;background:none;color:var(--ink-dim);cursor:pointer;font:12px ui-monospace,monospace}
  .mh-auth-tab.active{background:var(--line);color:var(--ink)}
  .mh-auth-err{color:#f87171;font:11px ui-monospace,monospace;margin-top:4px;min-height:16px}
  .mh-upgrade-banner{background:linear-gradient(90deg,rgba(124,58,237,.18),rgba(14,165,233,.18));border:1px solid #7c3aed44;border-radius:8px;padding:10px 14px;margin:8px 0;font:12px ui-monospace,monospace;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
  .mh-upgrade-banner a{color:var(--accent);cursor:pointer}
  /* Brand Kit panel */
  .mh-kit-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px;margin-top:10px;max-height:220px;overflow-y:auto}
  .mh-kit-card{border:1px solid var(--line);border-radius:8px;padding:8px;cursor:pointer;background:#0b0b10;transition:border-color .15s}
  .mh-kit-card:hover{border-color:var(--accent)}
  .mh-kit-swatches{display:flex;gap:3px;margin-bottom:5px}
  .mh-kit-swatch{width:18px;height:18px;border-radius:3px;flex-shrink:0}
  .mh-kit-name{font:11px ui-monospace,monospace;color:var(--ink-dim);word-break:break-word}
  /* Font Effects panel */
  .mh-font-controls{display:flex;flex-direction:column;gap:8px;margin-bottom:10px}
  .mh-font-text-input{background:#0b0b10;border:1px solid var(--line);border-radius:8px;padding:9px 10px;color:var(--ink);font:14px ui-monospace,monospace;width:100%;box-sizing:border-box}
  .mh-fx-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px;max-height:200px;overflow-y:auto;margin-top:8px}
  .mh-fx-card{border:1px solid var(--line);border-radius:8px;padding:8px;cursor:pointer;background:#0b0b10;transition:border-color .15s;position:relative}
  .mh-fx-card:hover,.mh-fx-card.selected{border-color:var(--accent)}
  .mh-fx-card.locked{opacity:.55}
  .mh-fx-card.locked::after{content:'★ Pro';position:absolute;top:4px;right:4px;font:bold 9px ui-monospace,monospace;color:var(--accent);background:#0b0b10;padding:1px 4px;border-radius:4px}
  .mh-fx-name{font:11px ui-monospace,monospace;color:var(--ink-dim);margin-top:4px}
  .mh-fx-preview-svg{width:100%;height:38px;overflow:hidden}
  #mhFontSvgPreview{width:100%;height:80px;margin-top:8px;border:1px solid var(--line);border-radius:8px;background:#0b0b10;overflow:hidden}
  /* Typography panel */
  .mh-type-subtabs{display:flex;gap:6px;margin-bottom:12px}
  .mh-type-subtab{padding:5px 12px;border:1px solid var(--line);border-radius:6px;background:none;color:var(--ink-dim);cursor:pointer;font:11px ui-monospace,monospace}
  .mh-type-subtab.active{background:var(--line);color:var(--ink)}
  .mh-type-subpanel{display:none}
  .mh-type-subpanel.active{display:block}
  .mh-type-spacing-row{display:flex;gap:12px;flex-wrap:wrap;margin:8px 0;font:11px ui-monospace,monospace;color:var(--ink-dim)}
  .mh-type-spacing-row label{display:flex;align-items:center;gap:6px}
  #mhTypeScaleSvg{width:100%;min-height:260px;border:1px solid var(--line);border-radius:8px;background:#0b0b10;overflow:hidden;margin:8px 0}
  #mhLogoPreview{width:100%;height:160px;border:1px solid var(--line);border-radius:8px;background:#0b0b10;overflow:hidden;margin:8px 0;display:flex;align-items:center;justify-content:center}
</style>

<!-- HEXFIELD hero -->
<div id="mhHero">
  <div id="mhHeroMark"></div>
  <div id="mhHeroWord">HEXFIELD</div>
  <div id="mhHeroTag">Palette &middot; Optics &middot; Motion</div>
  <div id="mhHeroSub">A live calibration studio for graphic designers. Tune the colour wheel &rarr; everything moves.</div>
</div>

<!-- Auth banner (top of page) -->
<div id="mhAuthBanner">
  <span style="color:var(--ink)">MunkerHex Studio</span>
  <span id="mhAuthStatus" style="display:flex;align-items:center;gap:8px">
    <span id="mhTierBadge" class="mh-tier-badge" style="display:none"></span>
    <span id="mhUserEmail" style="display:none"></span>
    <a id="mhSignInBtn">Sign in</a>
    <a id="mhSignOutBtn" style="display:none">Sign out</a>
    <a id="mhUpgradeBtn" style="display:none;color:#a78bfa">Upgrade</a>
  </span>
</div>

<!-- Auth modal -->
<div id="mhAuthModal">
  <div class="mh-auth-box">
    <h3>MunkerHex · Account</h3>
    <div class="mh-auth-tabs">
      <button class="mh-auth-tab active" id="mhTabLogin">Log in</button>
      <button class="mh-auth-tab" id="mhTabSignup">Sign up</button>
    </div>
    <input type="email" id="mhAuthEmail" placeholder="Email" autocomplete="email" />
    <input type="password" id="mhAuthPass" placeholder="Password" autocomplete="current-password" />
    <div style="display:flex;gap:8px;margin-top:4px">
      <button id="mhAuthSubmit" style="flex:1;min-height:40px">Log in</button>
      <button id="mhAuthClose" style="min-height:40px;background:none;border-color:var(--line)">✕</button>
    </div>
    <div class="mh-auth-err" id="mhAuthErr"></div>
  </div>
</div>

<script>
(function(){
  var _sb = null;
  var _session = null;
  var _tier = 'free';
  var _kits = [];
  var _effects = [];
  var _selFx = null;

  function sbClient(){
    if(_sb) return _sb;
    var cfg = window.MH_CONFIG || {};
    if(!cfg.supabaseUrl || !window.supabase) return null;
    _sb = window.supabase.createClient(cfg.supabaseUrl, cfg.supabaseAnonKey);
    return _sb;
  }

  function authToken(){ return _session?.access_token || null; }
  function isLoggedIn(){ return !!_session; }
  function hasFeature(minTier){
    var ranks = {free:0,designer:1,studio:2,agency:3};
    return (ranks[_tier]||0) >= (ranks[minTier]||0);
  }

  function refreshBanner(){
    var email = _session?.user?.email || '';
    document.getElementById('mhUserEmail').textContent = email;
    document.getElementById('mhUserEmail').style.display = email ? '' : 'none';
    document.getElementById('mhSignInBtn').style.display = isLoggedIn() ? 'none' : '';
    document.getElementById('mhSignOutBtn').style.display = isLoggedIn() ? '' : 'none';
    var badge = document.getElementById('mhTierBadge');
    badge.textContent = _tier;
    badge.className = 'mh-tier-badge ' + _tier;
    badge.style.display = isLoggedIn() ? '' : 'none';
    document.getElementById('mhUpgradeBtn').style.display = isLoggedIn() && _tier==='free' ? '' : 'none';
  }

  async function loadTier(){
    if(!isLoggedIn()) return;
    try{
      var r = await fetch('/api/brand-kits', {headers:{Authorization:'Bearer '+authToken()}});
      if(r.status === 403){ _tier='free'; }
    }catch(e){}
    try{
      var tr = await fetch('/api/user/tier', {headers:{Authorization:'Bearer '+authToken()}});
      if(tr.ok){ var d = await tr.json(); _tier = d.tier || 'free'; }
    }catch(e){}
  }

  async function initAuth(){
    var sb = sbClient(); if(!sb) return;
    var {data:{session}} = await sb.auth.getSession();
    _session = session;
    await loadTier();
    refreshBanner();
    sb.auth.onAuthStateChange(async(_,s)=>{
      _session = s;
      await loadTier();
      refreshBanner();
      if(s) loadKits();
    });
    if(isLoggedIn()) loadKits();
  }

  // ── Auth modal ─────────────────────────────────────────────────────────────
  function openModal(){ document.getElementById('mhAuthModal').classList.add('open'); }
  function closeModal(){ document.getElementById('mhAuthModal').classList.remove('open'); document.getElementById('mhAuthErr').textContent=''; }
  var _mode = 'login';
  document.getElementById('mhTabLogin').addEventListener('click',function(){
    _mode='login';
    document.getElementById('mhTabLogin').classList.add('active');
    document.getElementById('mhTabSignup').classList.remove('active');
    document.getElementById('mhAuthSubmit').textContent='Log in';
  });
  document.getElementById('mhTabSignup').addEventListener('click',function(){
    _mode='signup';
    document.getElementById('mhTabSignup').classList.add('active');
    document.getElementById('mhTabLogin').classList.remove('active');
    document.getElementById('mhAuthSubmit').textContent='Sign up';
  });
  document.getElementById('mhSignInBtn').addEventListener('click', openModal);
  document.getElementById('mhAuthClose').addEventListener('click', closeModal);
  document.getElementById('mhAuthModal').addEventListener('click',function(e){ if(e.target===this) closeModal(); });
  document.getElementById('mhUpgradeBtn').addEventListener('click', function(){
    var prices = (window.MH_CONFIG||{}).stripePrices||{};
    var price = prices.designer; if(!price) return;
    if(!isLoggedIn()){ openModal(); return; }
    fetch('/api/stripe/checkout',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+authToken()},body:JSON.stringify({price_id:price})})
      .then(r=>r.json()).then(d=>{ if(d.url) window.location.href=d.url; });
  });
  document.getElementById('mhAuthSubmit').addEventListener('click', async function(){
    var sb=sbClient(); if(!sb) return;
    var email=document.getElementById('mhAuthEmail').value.trim();
    var pass=document.getElementById('mhAuthPass').value;
    var err=document.getElementById('mhAuthErr');
    err.textContent='';
    try{
      var res = _mode==='signup'
        ? await sb.auth.signUp({email,password:pass})
        : await sb.auth.signInWithPassword({email,password:pass});
      if(res.error) throw res.error;
      closeModal();
    }catch(e){ err.textContent = e.message || 'Auth error'; }
  });
  document.getElementById('mhSignOutBtn').addEventListener('click', async function(){
    var sb=sbClient(); if(!sb) return;
    await sb.auth.signOut();
    _kits=[]; renderKitGrid();
  });

  // ── Brand Kit tab ──────────────────────────────────────────────────────────
  async function loadKits(){
    if(!isLoggedIn()) return;
    try{
      var r = await fetch('/api/brand-kits',{headers:{Authorization:'Bearer '+authToken()}});
      if(r.ok) _kits = await r.json();
      renderKitGrid();
    }catch(e){}
  }

  function renderKitGrid(){
    var grid = document.getElementById('mhKitGrid'); if(!grid) return;
    if(!isLoggedIn()){ grid.innerHTML='<p style="color:var(--ink-dim);font:12px monospace">Sign in to save and load brand kits.</p>'; return; }
    if(!_kits.length){ grid.innerHTML='<p style="color:var(--ink-dim);font:12px monospace">No saved kits yet — save your current palette.</p>'; return; }
    grid.innerHTML = _kits.map(function(k){
      var swatches=(k.palette.colors||[k.palette.a_hex,k.palette.b_hex,k.palette.centre_hex]).slice(0,5).map(function(c){ return '<div class="mh-kit-swatch" style="background:'+c+'"></div>'; }).join('');
      return '<div class="mh-kit-card" data-kit-id="'+k.id+'"><div class="mh-kit-swatches">'+swatches+'</div><div class="mh-kit-name">'+k.name+'</div></div>';
    }).join('');
    grid.querySelectorAll('.mh-kit-card').forEach(function(el){
      el.addEventListener('click',function(){
        var kit=_kits.find(function(k){ return k.id===el.dataset.kitId; });
        if(!kit) return;
        restoreKit(kit);
      });
    });
  }

  function restoreKit(kit){
    var p=kit.palette, u=kit.munker_config||{};
    if(typeof setVal==='function'){
      if(p.a_hex) setVal('munkerMode',u.mode||'diag');
      if(u.spacing) setVal('munkerSpacing',u.spacing);
      if(u.thickness) setVal('munkerThick',Math.min(20,u.thickness));
      if(u.opacity) setVal('munkerOpacity',u.opacity);
      if(u.speed) setVal('munkerSpeed',u.speed);
      if(typeof pushUnifiedToOriginal==='function') pushUnifiedToOriginal();
      if(u.mode) setVal('mhUnifiedMode',u.mode,true);
      if(u.pattern) setVal('mhUnifiedPattern',u.pattern,true);
    }
  }

  async function saveKit(){
    if(!isLoggedIn()){ openModal(); return; }
    if(!hasFeature('free') && _kits.length>=3){ alert('Upgrade to save more than 3 kits.'); return; }
    var name=prompt('Name this palette kit:','My palette '+(Date.now()%1000));
    if(!name) return;
    var payload={};
    if(typeof exportPayload==='function') payload=exportPayload();
    var u={};
    if(typeof currentUnifiedMunker==='function') u=currentUnifiedMunker();
    try{
      var r=await fetch('/api/brand-kits',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+authToken()},body:JSON.stringify({name,palette:payload,munker_config:u})});
      if(r.ok){ var kit=await r.json(); _kits.unshift(kit); renderKitGrid(); }
      else{ var e=await r.json(); alert(e.detail||'Save failed'); }
    }catch(e){ alert('Save failed: '+e.message); }
  }

  // ── Font Effects tab ───────────────────────────────────────────────────────
  async function loadFontEffects(){
    try{
      var headers=isLoggedIn()?{Authorization:'Bearer '+authToken()}:{};
      var r=await fetch('/api/font-library',{headers});
      if(r.ok){ _effects=await r.json(); renderFxGrid(); }
    }catch(e){}
  }

  function renderFxGrid(){
    var grid=document.getElementById('mhFxGrid'); if(!grid||!_effects.length) return;
    var p = (typeof getWheelPalette==='function') ? getWheelPalette() : {aHex:'#ffff00',bHex:'#0000ff',cHex:'#808080'};
    grid.innerHTML=_effects.map(function(fx){
      var locked=fx.is_premium&&!hasFeature('designer');
      return '<div class="mh-fx-card'+(locked?' locked':'')+(fx.id===(_selFx&&_selFx.id)?' selected':'')'" data-fx-id="'+fx.id+'"><div class="mh-fx-name">'+fx.name+'</div><div style="font:10px monospace;color:var(--ink-dim)">'+fx.preview_label+'</div></div>';
    }).join('');
    grid.querySelectorAll('.mh-fx-card:not(.locked)').forEach(function(el){
      el.addEventListener('click',function(){
        _selFx=_effects.find(function(f){ return f.id===el.dataset.fxId; });
        renderFxGrid(); updateFontPreview();
      });
    });
    grid.querySelectorAll('.mh-fx-card.locked').forEach(function(el){
      el.addEventListener('click',function(){ document.getElementById('mhUpgradeBtn').click(); });
    });
  }

  function updateFontPreview(){
    var text=(document.getElementById('mhFontInput')||{}).value||'MUNKERHEX';
    var preview=document.getElementById('mhFontSvgPreview'); if(!preview) return;
    var p=(typeof getWheelPalette==='function')?getWheelPalette():{aHex:'#ffff00',bHex:'#0000ff',cHex:'#808080'};
    var fx=_selFx||{css:'',svg_filter:'',id:'none'};
    var styleEl=document.getElementById('mhFxActiveStyle');
    if(!styleEl){styleEl=document.createElement('style');styleEl.id='mhFxActiveStyle';document.head.appendChild(styleEl);}
    styleEl.textContent=fx.css.replace(/var\(--mh-a\)/g,p.aHex).replace(/var\(--mh-b\)/g,p.bHex).replace(/var\(--mh-centre\)/g,p.cHex);
    preview.innerHTML='<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="80" style="--mh-a:'+p.aHex+';--mh-b:'+p.bHex+';--mh-centre:'+p.cHex+'"><defs>'+(fx.svg_filter?'<filter id="mhStripeF">'+fx.svg_filter+'</filter>':'')+'</defs><text class="mh-ftext" x="50%" y="56" text-anchor="middle" dominant-baseline="middle" font-family="ui-monospace,monospace" font-size="28" font-weight="700">'+text.substring(0,18)+'</text></svg>';
  }

  function exportFontSvg(){
    var text=(document.getElementById('mhFontInput')||{}).value||'MUNKERHEX';
    var p=(typeof getWheelPalette==='function')?getWheelPalette():{aHex:'#ffff00',bHex:'#0000ff',cHex:'#808080'};
    var fx=_selFx||{css:'',svg_filter:'',id:'none',name:'text'};
    var svg='<?xml version="1.0" encoding="UTF-8"?><svg xmlns="http://www.w3.org/2000/svg" width="600" height="160"><defs><style>'+fx.css+'</style>'+(fx.svg_filter?'<filter id="mhStripeF">'+fx.svg_filter+'</filter>':'')+'</defs><rect width="600" height="160" fill="#0b0b10"/><text class="mh-ftext" x="300" y="95" text-anchor="middle" dominant-baseline="middle" font-family="ui-monospace,monospace" font-size="52" font-weight="700" style="--mh-a:'+p.aHex+';--mh-b:'+p.bHex+';--mh-centre:'+p.cHex+'">'+text+'</text></svg>';
    var blob=new Blob([svg],{type:'image/svg+xml'});
    var url=URL.createObjectURL(blob);
    var a=document.createElement('a'); a.href=url; a.download='munkerhex-'+fx.id+'.svg'; a.click();
  }

  // ── HEXFIELD living logo mark ─────────────────────────────────────────────
  function buildHexfieldMark(seed) {
    var rng = (typeof seededRand === 'function') ? seededRand(seed) : Math.random.bind(Math);
    var COLS=9, ROWS=9, sz=16, hexH=sz/0.866, rowStep=hexH*0.75+1.5, colStep=sz+1.5;
    var p=(typeof getWheelPalette==='function')?getWheelPalette():{aHex:'#ffff00',bHex:'#0077ff',cHex:'#888888'};
    var W=colStep*COLS+colStep*0.5+4, H=rowStep*(ROWS-1)+hexH+4;
    var cells='', idx=0, cxm=(COLS-1)*0.5, cym=(ROWS-1)*0.5;
    for(var r=0;r<ROWS;r++){
      var off=r%2?colStep*0.5:0;
      for(var c=0;c<COLS;c++){
        var dist=Math.hypot((c-cxm)/(cxm||1),(r-cym)/(cym||1));
        var keepP=dist<0.55?0.97:dist<0.82?0.85:dist<1.0?0.55:dist<1.12?0.22:0;
        if(rng()>keepP) continue;
        var px=c*colStep+off+sz*0.5+2, py=r*rowStep+hexH*0.5+2, pts=[];
        for(var i=0;i<6;i++){var a=Math.PI/3*i-Math.PI/6;pts.push((px+sz*0.5*Math.cos(a)).toFixed(1)+','+(py+hexH*0.5*Math.sin(a)).toFixed(1));}
        var palC=[p.aHex,p.bHex,p.cHex];
        var ci=(r*13+c*7)%3, col=palC[ci], altC=palC[(ci+1+Math.round(rng()))%3];
        var oa=(0.12+rng()*0.22).toFixed(2), ob=(0.52+rng()*0.48).toFixed(2);
        var dur=(2.2+rng()*3.0).toFixed(1), del=(idx*0.11%3.2).toFixed(2);
        var opA='<animate attributeName="opacity" values="'+oa+';'+ob+';'+oa+'" dur="'+dur+'s" begin="-'+del+'s" repeatCount="indefinite"/>';
        var flA=rng()>0.52?'<animate attributeName="fill" values="'+col+';'+altC+';'+col+'" dur="'+(parseFloat(dur)*2.3).toFixed(1)+'s" begin="-'+del+'s" repeatCount="indefinite"/>':'';
        cells+='<polygon points="'+pts.join(' ')+'" fill="'+col+'" opacity="'+oa+'">'+opA+flA+'</polygon>';
        idx++;
      }
    }
    return '<svg xmlns="http://www.w3.org/2000/svg" width="'+W.toFixed(0)+'" height="'+H.toFixed(0)+'" viewBox="0 0 '+W.toFixed(0)+' '+H.toFixed(0)+'">'+cells+'</svg>';
  }
  function refreshHeroMark() {
    var hm=document.getElementById('mhHeroMark'); if(!hm) return;
    hm.innerHTML=buildHexfieldMark(new Date().toDateString());
  }

  // ── Typography + Logo ──────────────────────────────────────────────────────
  var FONT_STACKS = [
    {id:'system-sans',label:'System Sans',stack:'ui-sans-serif,system-ui,-apple-system,sans-serif'},
    {id:'system-serif',label:'System Serif',stack:'ui-serif,Georgia,"Times New Roman",serif'},
    {id:'system-mono',label:'System Mono',stack:'ui-monospace,"Cascadia Code","Fira Code",monospace'},
    {id:'inter',label:'Inter',gfont:'Inter:wght@300;400;700;900',stack:'"Inter",sans-serif'},
    {id:'playfair',label:'Playfair Display',gfont:'Playfair+Display:wght@400;700;900',stack:'"Playfair Display",serif'},
    {id:'dm-mono',label:'DM Mono',gfont:'DM+Mono:ital,wght@0,400;0,500;1,400',stack:'"DM Mono",monospace'},
    {id:'space-grotesk',label:'Space Grotesk',gfont:'Space+Grotesk:wght@300;400;700',stack:'"Space Grotesk",sans-serif'},
    {id:'bebas',label:'Bebas Neue',gfont:'Bebas+Neue',stack:'"Bebas Neue",sans-serif'},
  ];
  function _loadGoogleFont(fontId){
    var fnt=FONT_STACKS.find(function(f){ return f.id===fontId; });
    if(!fnt||!fnt.gfont) return;
    var lid='gf-'+fontId;
    if(document.getElementById(lid)) return;
    var link=document.createElement('link'); link.id=lid; link.rel='stylesheet';
    link.href='https://fonts.googleapis.com/css2?family='+fnt.gfont+'&display=swap';
    document.head.appendChild(link);
  }
  function _getFontStack(fontId){
    var fnt=FONT_STACKS.find(function(f){ return f.id===fontId; });
    return fnt ? fnt.stack : 'ui-sans-serif,system-ui,sans-serif';
  }
  function renderTypeScale(){
    var svgEl=document.getElementById('mhTypeScaleSvg'); if(!svgEl) return;
    var p=(typeof getWheelPalette==='function')?getWheelPalette():{aHex:'#ffff00',bHex:'#0000ff',cHex:'#808080'};
    var fontId=(document.getElementById('mhTypeFontFamily')||{}).value||'system-sans';
    var leading=parseInt((document.getElementById('mhTypeLeading')||{}).value||145)/100;
    var tracking=parseInt((document.getElementById('mhTypeTracking')||{}).value||0);
    _loadGoogleFont(fontId);
    var stack=_getFontStack(fontId);
    var sizes=[{px:52,label:'H1 · Heading',w:900},{px:38,label:'H2 · Display',w:700},{px:28,label:'H3 · Section',w:700},{px:20,label:'Body · Regular',w:400},{px:16,label:'Small · UI',w:400},{px:13,label:'Caption',w:400},{px:11,label:'Micro',w:400}];
    var cols=[p.aHex,p.bHex,p.cHex,p.cHex+'cc','#8888a8','#6688a0','#556678'];
    var lsp=(tracking/1000).toFixed(4)+'em';
    var y=0;
    var rows=sizes.map(function(s,i){ y+=Math.round(s.px*leading)+6; return {s:s,col:cols[i]||'#556678',y:y}; });
    var totH=y+20;
    svgEl.innerHTML='<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="'+totH+'" viewBox="0 0 800 '+totH+'">'
      +rows.map(function(r){
        return '<text x="16" y="'+r.y+'" font-size="'+r.s.px+'" font-weight="'+r.s.w+'" fill="'+r.col+'" letter-spacing="'+lsp+'" style="font-family:'+stack+'">'+r.s.label+'</text>'
          +'<text x="784" y="'+r.y+'" text-anchor="end" font-size="10" fill="#556678" style="font-family:ui-monospace,monospace">'+r.s.px+'px</text>';
      }).join('')+'</svg>';
  }
  function copyTypeCss(){
    var p=(typeof getWheelPalette==='function')?getWheelPalette():{aHex:'#ffff00',bHex:'#0000ff',cHex:'#808080'};
    var fontId=(document.getElementById('mhTypeFontFamily')||{}).value||'system-sans';
    var leading=parseInt((document.getElementById('mhTypeLeading')||{}).value||145)/100;
    var tracking=parseInt((document.getElementById('mhTypeTracking')||{}).value||0);
    var stack=_getFontStack(fontId);
    var fnt=FONT_STACKS.find(function(f){ return f.id===fontId; });
    var css='/* MunkerHex typography tokens */\n';
    if(fnt&&fnt.gfont) css+='@import url("https://fonts.googleapis.com/css2?family='+fnt.gfont+'&display=swap");\n\n';
    css+=':root {\n  --font-heading: '+stack+';\n  --font-body: ui-sans-serif,system-ui,sans-serif;\n';
    css+='  --color-h1: '+p.aHex+';\n  --color-h2: '+p.bHex+';\n  --color-h3: '+p.cHex+';\n  --color-body: #e8e8f0;\n  --color-caption: #8888a8;\n';
    css+='  --size-h1: 3.25rem; --size-h2: 2.375rem; --size-h3: 1.75rem;\n  --size-body: 1.25rem; --size-small: 1rem; --size-caption: .8125rem; --size-micro: .6875rem;\n';
    css+='  --leading: '+leading+';\n  --tracking: '+(tracking/1000).toFixed(4)+'em;\n}\n';
    navigator.clipboard.writeText(css).catch(function(){});
    var st=document.getElementById('mhTypeCssStatus'); if(st){ st.textContent='Copied!'; setTimeout(function(){ st.textContent=''; },2000); }
  }
  function _getLogoSvg(){
    var p=(typeof getWheelPalette==='function')?getWheelPalette():{aHex:'#ffff00',bHex:'#0000ff',cHex:'#808080'};
    var fontId=(document.getElementById('mhTypeFontFamily')||{}).value||'system-sans';
    var stack=_getFontStack(fontId);
    var text=(document.getElementById('mhLogoText')||{}).value||'HEXFIELD';
    var tagline=(document.getElementById('mhLogoTagline')||{}).value||'';
    var mark=(document.getElementById('mhLogoMark')||{}).value||'hex';
    var layout=(document.getElementById('mhLogoLayout')||{}).value||'left';
    var W=480, H=160;
    var textCol=(typeof getBestTextColor==='function')?getBestTextColor('#0b0b10'):p.aHex;
    /* Negative-space hex mark: outer outline hex + small inner honeycomb cells as fill, gaps = background shows through */
    function hexPts(cx,cy,r){
      var pts=[];
      for(var i=0;i<6;i++){var a=Math.PI/180*(60*i-30);pts.push((cx+r*Math.cos(a)).toFixed(1)+','+(cy+r*Math.sin(a)).toFixed(1));}
      return pts.join(' ');
    }
    function hexMark(cx,cy,R){
      /* outer outline in palette A */
      var outer='<polygon points="'+hexPts(cx,cy,R)+'" fill="none" stroke="'+p.aHex+'" stroke-width="2.5"/>';
      /* inner mini-hex honeycomb — 7 cells: centre + 6 around */
      var mini=R*0.28, gap=mini*0.18;
      var offsets=[[0,0],[0,-(mini*2+gap)],[mini*1.73+gap,-(mini+gap*0.5)],[mini*1.73+gap,mini+gap*0.5],[0,mini*2+gap],[-(mini*1.73+gap),mini+gap*0.5],[-(mini*1.73+gap),-(mini+gap*0.5)]];
      var cells='';
      offsets.forEach(function(off,idx){
        var col=idx===0?p.cHex:idx%2===0?p.aHex:p.bHex;
        cells+='<polygon points="'+hexPts(cx+off[0],cy+off[1],mini)+'" fill="'+col+'" opacity="'+(idx===0?'0.9':'0.75')+'"/>';
      });
      return outer+cells;
    }
    function cubeMark(cx,cy,s){
      var hw=s*0.55,hh=s*0.32,d=s*0.22;
      /* negative space: outer outline only for top face, filled sides */
      var top='<polygon points="'+cx+','+(cy-d)+' '+(cx+hw)+','+(cy-d-hh)+' '+cx+','+(cy-d-hh*2)+' '+(cx-hw)+','+(cy-d-hh)+'" fill="none" stroke="'+p.aHex+'" stroke-width="2"/>';
      var left='<polygon points="'+(cx-hw)+','+(cy-d-hh)+' '+cx+','+(cy-d)+' '+cx+','+(cy+d)+' '+(cx-hw)+','+(cy+hh*0.28)+'" fill="'+p.bHex+'" opacity="0.7"/>';
      var right='<polygon points="'+(cx+hw)+','+(cy-d-hh)+' '+cx+','+(cy-d)+' '+cx+','+(cy+d)+' '+(cx+hw)+','+(cy+hh*0.28)+'" fill="'+p.aHex+'" opacity="0.5"/>';
      return left+right+top;
    }
    var markSvg='', textX=40, textY=H/2+13, tagY=H/2+34, anchor='start';
    if(layout==='left'&&mark!=='none'){
      if(mark==='hex') markSvg=hexMark(54,H/2,36); else markSvg=cubeMark(54,H/2,40);
      textX=106;
    } else if(layout==='top'){
      if(mark==='hex') markSvg=hexMark(W/2,44,28); else if(mark!=='none') markSvg=cubeMark(W/2,44,32);
      textX=W/2; textY=100; tagY=122; anchor='middle';
    } else {
      textX=W/2; anchor='middle';
    }
    /* transparent background — animated hex tiles show through */
    return '<?xml version="1.0" encoding="UTF-8"?><svg xmlns="http://www.w3.org/2000/svg" width="'+W+'" height="'+H+'" style="overflow:visible">'
      +markSvg
      +'<text x="'+textX+'" y="'+textY+'" text-anchor="'+anchor+'" font-family="'+stack+'" font-size="34" font-weight="700" fill="'+textCol+'">'+text+'</text>'
      +(tagline?'<text x="'+textX+'" y="'+tagY+'" text-anchor="'+anchor+'" font-family="'+stack+'" font-size="12" fill="'+p.bHex+'" letter-spacing="0.12em">'+tagline+'</text>':'')
      +'</svg>';
  }
  function renderLogo(){
    var preview=document.getElementById('mhLogoPreview'); if(!preview) return;
    preview.innerHTML=_getLogoSvg().replace('<?xml version="1.0" encoding="UTF-8"?>','');
  }
  function downloadLogoSvg(){
    var blob=new Blob([_getLogoSvg()],{type:'image/svg+xml'});
    var url=URL.createObjectURL(blob);
    var a=document.createElement('a'); a.href=url; a.download='logo-'+Date.now()+'.svg'; a.click();
  }
  function downloadLogoPng(){
    var svgStr=_getLogoSvg(); var W=480,H=160;
    var img=new Image(), canvas=document.createElement('canvas'); canvas.width=W*2; canvas.height=H*2;
    var ctx=canvas.getContext('2d'); ctx.scale(2,2);
    img.onload=function(){ ctx.drawImage(img,0,0); var url=canvas.toDataURL('image/png'); var a=document.createElement('a'); a.href=url; a.download='logo-'+Date.now()+'.png'; a.click(); };
    img.src='data:image/svg+xml;base64,'+btoa(unescape(encodeURIComponent(svgStr)));
  }

  // ── Inject new tabs after render_patch IIFE runs ───────────────────────────
  setTimeout(function(){
    var tabs=document.getElementById('mhSuiteTabs'); if(!tabs) return;

    // Kit tab button
    var kitBtn=document.createElement('button');
    kitBtn.className='mh-suite-tab'; kitBtn.dataset.suiteTab='kit';
    kitBtn.innerHTML='<div class="mh-ctab-cube"><div class="mh-ctab-f mh-ctab-t"></div><div class="mh-ctab-f mh-ctab-r"></div><div class="mh-ctab-f mh-ctab-l"></div></div><span class="mh-ctab-lbl">Kit</span>';
    tabs.appendChild(kitBtn);

    // Fonts tab button
    var fontsBtn=document.createElement('button');
    fontsBtn.className='mh-suite-tab'; fontsBtn.dataset.suiteTab='fonts';
    fontsBtn.innerHTML='<div class="mh-ctab-cube"><div class="mh-ctab-f mh-ctab-t"></div><div class="mh-ctab-f mh-ctab-r"></div><div class="mh-ctab-f mh-ctab-l"></div></div><span class="mh-ctab-lbl">Fonts</span>';
    tabs.appendChild(fontsBtn);

    // Kit panel
    var kitPanel=document.createElement('div');
    kitPanel.className='mh-builder-panel'; kitPanel.id='mhBuilderKit';
    kitPanel.innerHTML='<div class="mh-builder-title">Brand Kit · saved palettes &amp; Munker configs</div>'
      +'<div class="mh-render-toolbar"><button id="mhSaveKitBtn">Save current palette as kit</button></div>'
      +'<div class="mh-kit-grid" id="mhKitGrid"></div>';
    tabs.closest('.mh-render-adapter').insertBefore(kitPanel, tabs.nextSibling.nextSibling || null);
    // Append after the last existing panel
    var lastPanel=tabs.closest('.mh-render-adapter').querySelector('#mhBuilderQr');
    if(lastPanel) lastPanel.after(kitPanel);

    // Fonts panel
    var fontsPanel=document.createElement('div');
    fontsPanel.className='mh-builder-panel'; fontsPanel.id='mhBuilderFonts';
    fontsPanel.innerHTML='<div class="mh-builder-title">Font Effects · Munker-aware animated type</div>'
      +'<div class="mh-font-controls"><input class="mh-font-text-input" id="mhFontInput" value="MUNKERHEX" maxlength="24" placeholder="Your text here" /></div>'
      +'<div id="mhFontSvgPreview"></div>'
      +'<div class="mh-fx-grid" id="mhFxGrid"><p style="color:var(--ink-dim);font:12px monospace">Loading effects…</p></div>'
      +'<div class="mh-render-toolbar" style="margin-top:8px"><button id="mhExportFontSvgBtn">Export SVG</button><span id="mhFontStatus" class="mh-export-status"></span></div>';
    if(lastPanel) lastPanel.after(fontsPanel);

    // Tab switching for new tabs
    [kitBtn, fontsBtn].forEach(function(btn){
      btn.addEventListener('click', function(){
        if(typeof switchSuiteTab==='function') switchSuiteTab(btn.dataset.suiteTab);
      });
    });

    // Save kit button
    document.getElementById('mhSaveKitBtn')?.addEventListener('click', saveKit);

    // Font input live preview
    document.getElementById('mhFontInput')?.addEventListener('input', updateFontPreview);
    document.getElementById('mhExportFontSvgBtn')?.addEventListener('click', exportFontSvg);

    // Type tab button
    var typeBtn=document.createElement('button');
    typeBtn.className='mh-suite-tab'; typeBtn.dataset.suiteTab='type';
    typeBtn.innerHTML='<div class="mh-ctab-cube"><div class="mh-ctab-f mh-ctab-t"></div><div class="mh-ctab-f mh-ctab-r"></div><div class="mh-ctab-f mh-ctab-l"></div></div><span class="mh-ctab-lbl">Type</span>';
    tabs.appendChild(typeBtn);

    // Type panel HTML
    var typePanel=document.createElement('div');
    typePanel.className='mh-builder-panel'; typePanel.id='mhBuilderType';
    var typeFontOptions=FONT_STACKS.map(function(f){ return '<option value="'+f.id+'">'+f.label+'</option>'; }).join('');
    typePanel.innerHTML=''
      +'<div class="mh-builder-title">Typography · type scale + font pairing + logo</div>'
      +'<div class="mh-type-subtabs">'
      +'<button class="mh-type-subtab active" data-type-tab="scale">Type Scale</button>'
      +'<button class="mh-type-subtab" data-type-tab="logo">Logo Design</button>'
      +'</div>'
      +'<div id="mhTypeScalePanel" class="mh-type-subpanel active">'
      +'<div class="mh-render-toolbar"><select id="mhTypeFontFamily">'+typeFontOptions+'</select></div>'
      +'<div class="mh-type-spacing-row">'
      +'<label>Leading <input type="range" id="mhTypeLeading" min="100" max="200" value="145" step="5"/> <span id="mhTypeLeadingVal">1.45</span></label>'
      +'<label>Tracking <input type="range" id="mhTypeTracking" min="-5" max="20" value="0" step="1"/> <span id="mhTypeTrackingVal">0em</span></label>'
      +'</div>'
      +'<div id="mhTypeScaleSvg"></div>'
      +'<div class="mh-render-toolbar"><button id="mhTypeCssCopyBtn">Copy CSS tokens</button><span id="mhTypeCssStatus" class="mh-export-status"></span></div>'
      +'</div>'
      +'<div id="mhTypeLogoPanel" class="mh-type-subpanel">'
      +'<div class="mh-render-toolbar">'
      +'<input id="mhLogoText" value="MUNKERHEX" maxlength="24" placeholder="Brand name" style="flex:2"/>'
      +'<select id="mhLogoMark"><option value="hex">Hex mark</option><option value="cube">Cube mark</option><option value="none">No mark</option></select>'
      +'<select id="mhLogoLayout"><option value="left">Mark left</option><option value="top">Mark top</option><option value="text">Text only</option></select>'
      +'</div>'
      +'<input class="mh-font-text-input" id="mhLogoTagline" value="Palette \xb7 Type \xb7 Optics" placeholder="Tagline" style="margin-top:6px"/>'
      +'<div id="mhLogoPreview"></div>'
      +'<div class="mh-render-toolbar"><button id="mhLogoSvgBtn">Download SVG</button><button id="mhLogoPngBtn">Download PNG</button><span id="mhLogoStatus" class="mh-export-status"></span></div>'
      +'</div>';
    if(lastPanel) lastPanel.after(typePanel);

    // Type tab click handler
    typeBtn.addEventListener('click', function(){
      if(typeof switchSuiteTab==='function') switchSuiteTab('type');
    });

    // Type sub-tab switching
    typePanel.querySelectorAll('.mh-type-subtab').forEach(function(btn){
      btn.addEventListener('click', function(){
        typePanel.querySelectorAll('.mh-type-subtab').forEach(function(b){ b.classList.remove('active'); });
        typePanel.querySelectorAll('.mh-type-subpanel').forEach(function(sp){ sp.style.display='none'; sp.classList.remove('active'); });
        btn.classList.add('active');
        var spEl=document.getElementById('mhType'+btn.dataset.typeTab.charAt(0).toUpperCase()+btn.dataset.typeTab.slice(1)+'Panel');
        if(spEl){ spEl.style.display='block'; spEl.classList.add('active'); }
        if(btn.dataset.typeTab==='scale') renderTypeScale();
        if(btn.dataset.typeTab==='logo') renderLogo();
      });
    });

    // Type panel live controls
    document.getElementById('mhTypeFontFamily')?.addEventListener('change', function(){ renderTypeScale(); renderLogo(); });
    document.getElementById('mhTypeLeading')?.addEventListener('input', function(){
      var sp=document.getElementById('mhTypeLeadingVal'); if(sp) sp.textContent=(this.value/100).toFixed(2);
      renderTypeScale();
    });
    document.getElementById('mhTypeTracking')?.addEventListener('input', function(){
      var sp=document.getElementById('mhTypeTrackingVal'); if(sp) sp.textContent=(this.value/1000).toFixed(3)+'em';
      renderTypeScale();
    });
    document.getElementById('mhTypeCssCopyBtn')?.addEventListener('click', copyTypeCss);
    document.getElementById('mhLogoText')?.addEventListener('input', renderLogo);
    document.getElementById('mhLogoTagline')?.addEventListener('input', renderLogo);
    document.getElementById('mhLogoMark')?.addEventListener('change', renderLogo);
    document.getElementById('mhLogoLayout')?.addEventListener('change', renderLogo);
    document.getElementById('mhLogoSvgBtn')?.addEventListener('click', downloadLogoSvg);
    document.getElementById('mhLogoPngBtn')?.addEventListener('click', downloadLogoPng);

    // Living logo + palette hook
    refreshHeroMark();
    if (typeof applyRenderPalette === 'function' && !applyRenderPalette.__mhHeroHooked) {
      var _origARP = applyRenderPalette;
      applyRenderPalette = function() { var r=_origARP.apply(this,arguments); refreshHeroMark(); return r; };
      applyRenderPalette.__mhHeroHooked = true;
    }

    // Init auth
    initAuth();
  }, 600);
})();
</script>
"""

    output = original.replace("</head>", config_script + "\n</head>", 1)
    output = output.replace("<body>", f"<body>\n{render_patch}\n{auth_and_features_patch}", 1)
    return output


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


# ── Auth helpers ──────────────────────────────────────────────────────────────
from auth import UserContext, get_current_user, require_tier, TIER_LIMITS


async def _get_user(authorization: Optional[str] = Header(default=None)) -> UserContext:
    return await get_current_user(authorization=authorization, db=db)


@api_router.get("/user/tier")
async def get_user_tier(user: UserContext = Depends(_get_user)):
    if not user.user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"tier": user.tier, "limits": TIER_LIMITS.get(user.tier, TIER_LIMITS["free"])}


# ── Brand Kits ────────────────────────────────────────────────────────────────
@api_router.get("/brand-kits")
async def list_brand_kits(user: UserContext = Depends(_get_user)):
    if not user.user_id:
        raise HTTPException(status_code=401, detail="Sign in to access brand kits")
    docs = await db.brand_kits.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return docs


@api_router.post("/brand-kits", response_model=BrandKit)
async def create_brand_kit(payload: BrandKitCreate, user: UserContext = Depends(_get_user)):
    if not user.user_id:
        raise HTTPException(status_code=401, detail="Sign in to save brand kits")
    count = await db.brand_kits.count_documents({"user_id": user.user_id})
    limit = user.limit("brand_kits")
    if count >= limit:
        raise HTTPException(
            status_code=403,
            detail=f"Your plan allows {limit} saved kits. Upgrade to save more."
        )
    kit = BrandKit(
        id=str(uuid.uuid4()),
        user_id=user.user_id,
        name=payload.name,
        palette=payload.palette,
        munker_config=payload.munker_config,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    await db.brand_kits.insert_one(kit.model_dump())
    return kit


@api_router.delete("/brand-kits/{kit_id}")
async def delete_brand_kit(kit_id: str, user: UserContext = Depends(_get_user)):
    if not user.user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    result = await db.brand_kits.delete_one({"id": kit_id, "user_id": user.user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Kit not found")
    return {"deleted": kit_id}


# ── Font Library ──────────────────────────────────────────────────────────────
async def _seed_font_effects():
    count = await db.font_effects.count_documents({})
    if count == 0:
        await db.font_effects.insert_many([dict(fx) for fx in FONT_EFFECTS_SEED])


@api_router.get("/font-library")
async def list_font_effects(user: UserContext = Depends(_get_user)):
    await _seed_font_effects()
    docs = await db.font_effects.find({}, {"_id": 0}).to_list(100)
    # Mark premium effects as locked for free users
    for doc in docs:
        doc["locked"] = doc.get("is_premium", False) and not user.has_tier("designer")
    return docs


@api_router.post("/font-library")
async def save_font_effect(payload: Dict[str, Any], user: UserContext = Depends(_get_user)):
    if not user.has_tier("studio"):
        raise HTTPException(status_code=403, detail="Studio plan required to save custom font effects")
    effect = FontEffect(
        id=str(uuid.uuid4()),
        name=payload.get("name", "Custom effect"),
        css=payload.get("css", ""),
        svg_filter=payload.get("svg_filter", ""),
        preview_label=payload.get("preview_label", "Custom"),
        is_premium=True,
        author_id=user.user_id,
    )
    await db.font_effects.insert_one(effect.model_dump())
    return effect


# ── Gallery ───────────────────────────────────────────────────────────────────
@api_router.get("/gallery/public")
async def list_gallery(page: int = 1, per_page: int = 20):
    skip = (page - 1) * per_page
    docs = await db.gallery_items.find(
        {"public": True}, {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(per_page).to_list(per_page)
    return docs


@api_router.post("/gallery")
async def publish_to_gallery(payload: GalleryItemCreate, user: UserContext = Depends(_get_user)):
    if not user.has_tier("designer"):
        raise HTTPException(status_code=403, detail="Designer plan required to publish to gallery")
    item = GalleryItem(
        id=str(uuid.uuid4()),
        user_id=user.user_id,
        title=payload.title,
        config=payload.config,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    doc = item.model_dump()
    doc["public"] = True
    await db.gallery_items.insert_one(doc)
    return item


# ── Stripe ────────────────────────────────────────────────────────────────────
@api_router.post("/stripe/checkout")
async def stripe_checkout(payload: Dict[str, Any], user: UserContext = Depends(_get_user)):
    if not user.user_id:
        raise HTTPException(status_code=401, detail="Sign in before subscribing")
    price_id = payload.get("price_id", "")
    if not price_id:
        raise HTTPException(status_code=400, detail="price_id required")
    public_url = os.environ.get("PUBLIC_URL", "http://localhost")
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{public_url}/?sub=success",
            cancel_url=f"{public_url}/?sub=cancel",
            customer_email=user.email or None,
            metadata={"user_id": user.user_id},
        )
        return {"url": session.url}
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@api_router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    from stripe_webhooks import handle_webhook
    return await handle_webhook(request, db)


class CheckoutSessionRequest(BaseModel):
    success_url: str
    cancel_url: str


@api_router.post("/create-checkout-session")
async def create_checkout_session(body: CheckoutSessionRequest):
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Stripe not configured. Set STRIPE_SECRET_KEY env var.")
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "unit_amount": 100,
                    "product_data": {"name": "Hexfield Logo Art — Unique Colour Render"},
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=body.success_url,
            cancel_url=body.cancel_url,
        )
        return {"checkout_url": session.url}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@api_router.get("/verify-payment")
async def verify_payment(session_id: str):
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Stripe not configured.")
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        return {"paid": session.payment_status == "paid"}
    except Exception:
        return {"paid": False}


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
