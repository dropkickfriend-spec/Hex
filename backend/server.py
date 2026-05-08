from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
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
