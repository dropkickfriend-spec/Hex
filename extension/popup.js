'use strict';

const CHESS_GLYPHS = {
  K:'♔',Q:'♕',R:'♖',B:'♗',N:'♘',P:'♙',
  k:'♚',q:'♛',r:'♜',b:'♝',n:'♞',p:'♟'
};

const DEFAULT_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const HEXFIELD_URL = 'https://dropkickfriend-spec.github.io/hex/';

// Default palette (CMY — matches the app's default)
let palette = { light: '#ffff00', dark: '#0033cc' };

function parseFen(fen) {
  const board = [];
  const rows = (fen || '').trim().split(' ')[0].split('/');
  for (const row of rows) {
    const cells = [];
    for (const ch of row) {
      const n = parseInt(ch);
      if (!isNaN(n)) for (let i = 0; i < n; i++) cells.push(null);
      else cells.push(ch);
    }
    board.push(cells);
  }
  return board;
}

function hexToRgb(h) {
  const n = parseInt((h || '#888').replace('#', ''), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function drawBoard(fen) {
  const canvas = document.getElementById('hfCanvas');
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = '#030308';
  ctx.fillRect(0, 0, W, H);

  const board = parseFen(fen || DEFAULT_FEN);
  const tileW = W / 10.5;
  const tileH = tileW * 0.52;
  const cubeH = tileH * 0.55;
  const startX = W * 0.5;
  const startY = H * 0.05;
  const lightRgb = hexToRgb(palette.light);
  const darkRgb = hexToRgb(palette.dark);

  function rgba(r, g, b, a = 1) { return `rgba(${r|0},${g|0},${b|0},${a})`; }
  function tint([r, g, b], f) { return [Math.min(255, r + f * 255), Math.min(255, g + f * 255), Math.min(255, b + f * 255)]; }
  function shade([r, g, b], f) { return [r * f, g * f, b * f]; }

  function drawCube(sx, sy, rgb, isLight) {
    ctx.fillStyle = rgba(...tint(rgb, 0.18));
    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.lineTo(sx + tileW * 0.5, sy + tileH * 0.5);
    ctx.lineTo(sx, sy + tileH);
    ctx.lineTo(sx - tileW * 0.5, sy + tileH * 0.5);
    ctx.closePath(); ctx.fill();

    ctx.fillStyle = rgba(...shade(rgb, 0.72));
    ctx.beginPath();
    ctx.moveTo(sx + tileW * 0.5, sy + tileH * 0.5);
    ctx.lineTo(sx + tileW * 0.5, sy + tileH * 0.5 + cubeH);
    ctx.lineTo(sx, sy + tileH + cubeH);
    ctx.lineTo(sx, sy + tileH);
    ctx.closePath(); ctx.fill();

    ctx.fillStyle = rgba(...shade(rgb, 0.46));
    ctx.beginPath();
    ctx.moveTo(sx - tileW * 0.5, sy + tileH * 0.5);
    ctx.lineTo(sx, sy + tileH);
    ctx.lineTo(sx, sy + tileH + cubeH);
    ctx.lineTo(sx - tileW * 0.5, sy + tileH * 0.5 + cubeH);
    ctx.closePath(); ctx.fill();

    ctx.strokeStyle = isLight ? 'rgba(255,255,255,0.09)' : 'rgba(0,0,0,0.2)';
    ctx.lineWidth = 0.4;
    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.lineTo(sx + tileW * 0.5, sy + tileH * 0.5);
    ctx.lineTo(sx, sy + tileH);
    ctx.lineTo(sx - tileW * 0.5, sy + tileH * 0.5);
    ctx.closePath(); ctx.stroke();
  }

  function drawPiece(sx, sy, piece) {
    const isWhite = piece === piece.toUpperCase();
    const glyph = CHESS_GLYPHS[piece] || '';
    if (!glyph) return;
    const fs = tileW * 0.28;
    ctx.font = `${fs}px serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const cy = sy + tileH * 0.38;
    ctx.fillStyle = 'rgba(0,0,0,0.5)';
    ctx.fillText(glyph, sx + 1, cy + 1);
    ctx.shadowColor = isWhite ? palette.light : palette.dark;
    ctx.shadowBlur = fs * 0.45;
    ctx.fillStyle = isWhite ? palette.light : '#aabbff';
    ctx.fillText(glyph, sx, cy);
    ctx.shadowBlur = 0;
  }

  for (let r = 7; r >= 0; r--) {
    for (let c = 0; c < 8; c++) {
      const sx = startX + (c - r) * tileW * 0.5;
      const sy = startY + (c + r) * tileH * 0.5;
      const isLight = (r + c) % 2 === 0;
      drawCube(sx, sy, isLight ? lightRgb : darkRgb, isLight);
    }
  }

  for (let r = 7; r >= 0; r--) {
    for (let c = 0; c < 8; c++) {
      const fenRow = 7 - r;
      const piece = board[fenRow] && board[fenRow][c];
      if (piece) {
        const sx = startX + (c - r) * tileW * 0.5;
        const sy = startY + (c + r) * tileH * 0.5;
        drawPiece(sx, sy, piece);
      }
    }
  }

  ctx.font = '8px monospace';
  ctx.fillStyle = 'rgba(255,255,255,0.2)';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'bottom';
  ctx.fillText('HEXFIELD CHESS', 6, H - 4);
}

function setStatus(msg) {
  const el = document.getElementById('hfStatus');
  if (el) el.textContent = msg;
}

function getFenFromPage() {
  return new Promise((resolve) => {
    chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
      if (!tab) { resolve(null); return; }
      chrome.tabs.sendMessage(tab.id, { type: 'GET_FEN' }, (resp) => {
        if (chrome.runtime.lastError) { resolve(null); return; }
        resolve(resp && resp.fen ? resp.fen : null);
      });
    });
  });
}

async function init() {
  // Load saved palette
  const stored = await chrome.storage.local.get(['palette', 'fen']);
  if (stored.palette) palette = stored.palette;

  const fenEl = document.getElementById('hfFen');
  let currentFen = stored.fen || DEFAULT_FEN;
  if (fenEl) fenEl.value = currentFen;

  // Try to auto-detect FEN from page
  const pageFen = await getFenFromPage();
  if (pageFen) {
    currentFen = pageFen;
    if (fenEl) fenEl.value = pageFen;
    setStatus('Board detected from page.');
    await chrome.storage.local.set({ fen: pageFen });
  } else {
    setStatus('Paste a FEN or click "Get from page".');
  }

  drawBoard(currentFen);

  document.getElementById('hfRender').addEventListener('click', () => {
    const fen = fenEl ? fenEl.value.trim() : DEFAULT_FEN;
    drawBoard(fen || DEFAULT_FEN);
    setStatus('Rendered.');
  });

  document.getElementById('hfGetFen').addEventListener('click', async () => {
    setStatus('Reading board…');
    const fen = await getFenFromPage();
    if (fen) {
      if (fenEl) fenEl.value = fen;
      drawBoard(fen);
      await chrome.storage.local.set({ fen });
      setStatus('FEN loaded from page.');
    } else {
      setStatus('No board found on this page.');
    }
  });

  document.getElementById('hfExport').addEventListener('click', () => {
    const canvas = document.getElementById('hfCanvas');
    const link = document.createElement('a');
    link.download = 'hexfield-chess.png';
    link.href = canvas.toDataURL('image/png');
    link.click();
    setStatus('PNG saved!');
  });

  document.getElementById('hfOpen').addEventListener('click', () => {
    const fen = fenEl ? fenEl.value.trim() : DEFAULT_FEN;
    const url = HEXFIELD_URL + '?fen=' + encodeURIComponent(fen) + '#chess';
    chrome.tabs.create({ url });
  });
}

init().catch(err => setStatus('Error: ' + err.message));
