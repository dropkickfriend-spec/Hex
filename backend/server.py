from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
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

# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "MunkerHex Studio API", "status": "ready"}


@api_router.get("/health")
async def health():
    return {"status": "ok", "service": "munkerhex-studio"}


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
  .mh-render-toolbar button { min-height: 38px; }
  .mh-target-stage {
    position: relative;
    margin-top: 10px;
    min-height: 360px;
    border: 1px solid var(--line);
    border-radius: 12px;
    overflow: hidden;
    background:
      radial-gradient(circle at 20% 30%, rgba(255,255,0,.22), transparent 24%),
      radial-gradient(circle at 72% 35%, rgba(255,0,255,.18), transparent 28%),
      radial-gradient(circle at 55% 82%, rgba(0,255,255,.16), transparent 26%),
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
  .mh-orb { border-radius: 50%; background: #00ffff; min-height: 112px; box-shadow: 0 0 32px rgba(0,255,255,.55); }
  .mh-lines { display: grid; gap: 12px; align-content: center; }
  .mh-line { height: 14px; background: #ff00ff; box-shadow: 0 0 18px currentColor; }
  .mh-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
  .mh-card { min-height: 58px; }
  .mh-game-grid { position: absolute; inset: 0; display: grid; grid-template-columns: repeat(10, 1fr); grid-auto-rows: 34px; gap: 6px; padding: 18px; align-content: center; }
  .mh-game-cell { border: 1px solid rgba(255,255,255,.2); transform: skewY(-8deg); box-shadow: 0 0 18px rgba(255,255,255,.08); }
  .mh-stage-label { position: absolute; left: 12px; bottom: 10px; z-index: 8; font: 11px ui-monospace, monospace; color: var(--ink); background: rgba(0,0,0,.62); border: 1px solid var(--line); border-radius: 999px; padding: 7px 10px; }
  .mh-munker-field, .mh-hex-field { position: absolute; inset: -60px; pointer-events: none; z-index: 6; }
  .mh-munker-field {
    opacity: var(--mh-opacity, 1);
    background: repeating-linear-gradient(var(--mh-angle, 135deg), var(--mh-a, #ffff00) 0 var(--mh-thick, 5px), var(--mh-b, #ff00ff) var(--mh-thick, 5px) calc(var(--mh-thick, 5px) + var(--mh-gap, 10px)));
    mix-blend-mode: screen;
    animation: mh-pan var(--mh-speed, 4s) linear infinite alternate;
  }
  .mh-hex-field {
    opacity: .42;
    background-image:
      linear-gradient(30deg, transparent 24%, rgba(0,255,255,.45) 25%, rgba(0,255,255,.45) 26%, transparent 27%, transparent 74%, rgba(255,0,255,.45) 75%, rgba(255,0,255,.45) 76%, transparent 77%),
      linear-gradient(150deg, transparent 24%, rgba(255,255,0,.38) 25%, rgba(255,255,0,.38) 26%, transparent 27%, transparent 74%, rgba(0,255,255,.38) 75%, rgba(0,255,255,.38) 76%, transparent 77%);
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
  <div class="mh-render-toolbar">
    <input id="mhUrl" value="https://example.com" placeholder="https://your-site.com" />
    <select id="mhGame">
      <option value="website">Website URL render</option>
      <option value="invaders">Game render · arcade invaders</option>
      <option value="platformer">Game render · platformer</option>
      <option value="maze">Game render · puzzle maze</option>
    </select>
    <button id="mhRenderBtn">Render with this style</button>
    <button id="mhSyncBtn">Sync Munker controls</button>
  </div>
  <p class="hint" style="margin:8px 0 0">This keeps your original studio below. The target stage uses the same animated Munker controls and hex/cube colour system instead of replacing it.</p>
  <div class="mh-target-stage" id="mhTargetStage">
    <iframe class="mh-target-frame" id="mhFrame" src="https://example.com" title="Website render target"></iframe>
    <div class="mh-target-synthetic" id="mhSynthetic">
      <div class="mh-urlbar"><span class="mh-dot" style="background:#ff4b4b"></span><span class="mh-dot" style="background:#ffd24a"></span><span class="mh-dot" style="background:#00ffff"></span><span id="mhHostLabel">example.com</span></div>
      <div class="mh-block"><div class="mh-orb"></div><div class="mh-lines"><div class="mh-line" style="width:86%; color:#ffff00; background:#ffff00"></div><div class="mh-line" style="width:62%; color:#ff00ff; background:#ff00ff"></div><div class="mh-line" style="width:74%; color:#00ffff; background:#00ffff"></div></div></div>
      <div class="mh-cards"><div class="mh-card"></div><div class="mh-card"></div><div class="mh-card"></div><div class="mh-card"></div></div>
    </div>
    <div class="mh-game-grid" id="mhGameGrid" style="display:none"></div>
    <div class="mh-hex-field"></div>
    <div class="mh-munker-field" id="mhMunkerField"></div>
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
  const label = $('mhStageLabel');
  const hostLabel = $('mhHostLabel');
  const palette = ['#ffff00','#ff00ff','#00ffff','#ff3131','#39ff14','#0000ff'];
  function safeUrl(value){ const v=(value||'').trim(); if(!v) return 'https://example.com'; return /^https?:\/\//i.test(v) ? v : 'https://' + v; }
  function host(value){ try { return new URL(safeUrl(value)).host.replace(/^www\./,''); } catch(e){ return 'target.site'; } }
  function syncMunker(){
    const mode = $('munkerMode') ? $('munkerMode').value : 'diag';
    const spacing = $('munkerSpacing') ? $('munkerSpacing').value : 10;
    const thick = $('munkerThick') ? $('munkerThick').value : 5;
    const opacity = $('munkerOpacity') ? $('munkerOpacity').value : 100;
    const speed = $('munkerSpeed') ? $('munkerSpeed').value : 4;
    const angles = { h:'90deg', v:'0deg', grid:'45deg', diag:'135deg', off:'135deg' };
    stage.style.setProperty('--mh-angle', angles[mode] || '135deg');
    stage.style.setProperty('--mh-gap', spacing + 'px');
    stage.style.setProperty('--mh-thick', thick + 'px');
    stage.style.setProperty('--mh-opacity', mode === 'off' ? '.0' : String(opacity/100));
    stage.style.setProperty('--mh-speed', speed + 's');
    const a = $('hexIn') ? $('hexIn').value : '#ffff00';
    stage.style.setProperty('--mh-a', a || '#ffff00');
    stage.style.setProperty('--mh-b', '#00ffff');
  }
  function drawGame(kind){
    grid.innerHTML = '';
    grid.style.display = 'grid';
    frame.style.display = 'none';
    synthetic.style.display = 'none';
    const cells = kind === 'maze' ? 90 : 70;
    for(let i=0;i<cells;i++){
      const d=document.createElement('div');
      d.className='mh-game-cell';
      const c=palette[(i + (kind==='platformer'?2:0)) % palette.length];
      d.style.background = c;
      d.style.opacity = kind==='maze' && i%3===0 ? '.08' : String(.38 + (i%5)*.1);
      d.style.gridColumn = kind==='invaders' && i%11===0 ? 'span 2' : 'span 1';
      d.style.height = kind==='platformer' && i>48 ? '48px' : (kind==='maze' ? '28px' : '24px');
      grid.appendChild(d);
    }
    label.textContent = 'game render · ' + kind + ' · original Munker + hex field';
  }
  function render(){
    const kind = $('mhGame').value;
    syncMunker();
    if(kind === 'website'){
      const url = safeUrl($('mhUrl').value);
      frame.src = url;
      frame.style.display = 'block';
      synthetic.style.display = 'grid';
      grid.style.display = 'none';
      hostLabel.textContent = host(url);
      label.textContent = 'website render · ' + host(url) + ' · original Munker + hex field';
      return;
    }
    drawGame(kind);
  }
  ['munkerMode','munkerSpacing','munkerThick','munkerOpacity','munkerSpeed','hexIn'].forEach(id => {
    const el=$(id); if(el) el.addEventListener('input', syncMunker);
  });
  $('mhRenderBtn').addEventListener('click', render);
  $('mhSyncBtn').addEventListener('click', syncMunker);
  setTimeout(() => {
    const cubeBtn = document.querySelector('[data-tab="cube"]');
    if(cubeBtn) cubeBtn.click();
    const mode = $('munkerMode'); if(mode) mode.value = 'diag';
    const animate = $('munkerAnimate'); if(animate) animate.value = 'diag';
    syncMunker(); render();
  }, 400);
})();
</script>
"""
    return original.replace("<body>", f"<body>\n{render_patch}", 1)


@api_router.get("/tonality-renderer", response_class=HTMLResponse)
async def tonality_renderer():
    return HTMLResponse(build_tonality_renderer_html())


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
