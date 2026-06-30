# HexField Chess — Chrome Extension

Renders chess.com and lichess.org boards in HexField's isometric 3D palette style.

## Install (developer mode)

1. Open Chrome and go to `chrome://extensions`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked** and select this `/extension` folder
4. The HexField hex icon will appear in your toolbar

## Features

- **Popup**: Shows an isometric 3D canvas render of the current board position
  - Auto-detects the FEN from chess.com or lichess.org when you click the icon
  - Paste any FEN manually, render, and export as PNG
  - "Open in HexField" opens the full HexField tool with the position pre-loaded
- **Injected button**: A `⬡ HexField` button appears below chess boards on supported sites, opening a new tab with the HexField isometric render of the current position

## Supported sites

| Site | FEN detection | Injected button |
|------|--------------|-----------------|
| chess.com (game page) | `window.game.getFen()` | ✓ |
| chess.com (analysis) | `chess-board[fen]` attribute | ✓ |
| lichess.org (analysis) | URL + DOM input | ✓ |
| lichess.org (game) | DOM / lichess API | ✓ |

## Palette

The extension uses the CMY primary palette by default (yellow light squares, blue dark squares). The full HexField palette engine is available in the web app.

## Permissions

- `activeTab` / `scripting`: to read the FEN from the page you are viewing
- `storage`: to remember the last FEN between popup opens
- `host_permissions` for chess.com and lichess.org: to inject the content script
