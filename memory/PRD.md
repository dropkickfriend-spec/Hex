# MunkerHex Studio PRD

## Problem Statement
Use the animated Munker render design over the user's hex-grid color-palette concept so people can style website/game graphics, plus provide a collection of old-school retro games redesigned in the same render language.

## Architecture
- **Frontend:** Expo SDK 54, React Native, Expo Router, custom tab navigation, animated local render canvas.
- **Backend:** FastAPI at `/api`, MongoDB via Motor for saved render projects.
- **Database:** `render_projects` collection stores URL render saves without Mongo `_id` in responses.

## User Personas
- **Visual designer:** Wants fast palette/style exploration for websites.
- **Indie game artist:** Wants retro-game inspiration in the Munker/hex visual style.
- **Color-system builder:** Wants CMY/additive complement presets and hex-grid tonal experiments.

## Core Requirements
- Render-tool-first mobile UX.
- Website URL input only for MVP.
- Local no-AI visual preview/filter system.
- Animated Munker stripes over hex-grid composition.
- CMY/additive complement palette selection.
- Retro game gallery spanning arcade, platformer, maze/puzzle inspirations.
- Saved render projects retrievable from backend.

## Implemented — 2026-05-08
- Built MunkerHex Studio mobile app with Render, Gallery, Palette, and Saves tabs.
- Added deterministic URL-to-style render canvas with animated stripe modes, hex overlay, opacity/density/thickness/speed controls, and saved signatures.
- Added FastAPI endpoints: `/api/health`, `/api/palettes`, `/api/gallery`, `/api/renders` create/list.
- Added CMY palette presets and retro game redesign gallery data.
- Added Mongo-backed saved render projects and load-back-into-render flow.
- Verified backend APIs, mobile UI screenshots, tab navigation, save/list/load flow, and small-screen control layout.

## Current Product Notes
- The MVP uses a local stylized URL composition rather than taking live website screenshots.
- No login or user accounts are required.
- No external AI/image generation is used.

## Prioritized Backlog
### P0
- Add real website screenshot capture if required for production-grade URL rendering.
- Add per-project delete/rename actions.

### P1
- Export animated render previews as image/video assets.
- Add custom palette creator with pinned colors and tonal-center controls.
- Add gallery detail pages with before/after retro redesign breakdowns.

### P2
- Add onboarding explaining Munker illusions and CMY/RGB complements.
- Add share cards for saved render signatures.
- Add more retro game packs and palette presets.

## Next Tasks
1. Decide whether URL rendering should remain a local style interpretation or capture live screenshots.
2. Add export/share capability for saved renders.
3. Expand palette editing beyond presets.