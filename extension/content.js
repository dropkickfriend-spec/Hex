'use strict';

// ── HexField Chess Content Script ─────────────────────────────────────────────
// Injected on chess.com and lichess.org.
// Responsibilities:
//   1. Detect an active chess board element on the page.
//   2. Extract the current FEN string (best-effort).
//   3. Respond to GET_FEN messages from the popup.
//   4. Inject a floating "HexField" button near the board.

(function () {
  if (window.__hexfieldInjected) return;
  window.__hexfieldInjected = true;

  const HOST = location.hostname;
  const IS_LICHESS   = HOST.includes('lichess.org');
  const IS_CHESS_COM = HOST.includes('chess.com');

  // ── FEN extraction ─────────────────────────────────────────────────────────

  function fenFromLichess() {
    // Lichess encodes the FEN in the URL for analysis pages, e.g. /analysis/fen/...
    const m = location.pathname.match(/\/analysis\/([^/]+)/);
    if (m) {
      try { return decodeURIComponent(m[1]); } catch (_) {}
    }
    // Lichess game pages: read from the hidden input Lichess puts in the DOM
    const el = document.querySelector('input.analyse__underboard__fen') ||
               document.querySelector('[data-fen]');
    if (el) return el.value || el.dataset.fen || null;

    // Fallback: try window.lichess
    try {
      const boot = window.lichess && window.lichess.analysis;
      if (boot && boot.data && boot.data.game && boot.data.game.fen) {
        return boot.data.game.fen;
      }
    } catch (_) {}
    return null;
  }

  function fenFromChessCom() {
    // chess.com exposes window.game on game pages
    try {
      if (window.game && typeof window.game.getFen === 'function') {
        return window.game.getFen();
      }
    } catch (_) {}

    // chess.com analysis pages: look for the FEN in the board element attributes
    const board = document.querySelector('chess-board') ||
                  document.querySelector('.board-layout-main chess-board');
    if (board) {
      const fen = board.getAttribute('fen') ||
                  board.getAttribute('data-fen') ||
                  board.getAttribute('initial-fen');
      if (fen) return fen;
    }

    // Last resort: try chess.com's global app state
    try {
      const app = window.__CHESSCOM__ || window.chesscom;
      if (app && app.store && app.store.state) {
        const state = app.store.state;
        if (state.game && state.game.fen) return state.game.fen;
      }
    } catch (_) {}
    return null;
  }

  function getCurrentFen() {
    if (IS_LICHESS)   return fenFromLichess();
    if (IS_CHESS_COM) return fenFromChessCom();
    return null;
  }

  // ── Message listener (popup → content) ─────────────────────────────────────

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg.type === 'GET_FEN') {
      const fen = getCurrentFen();
      sendResponse({ fen: fen || null });
    }
    return true; // keep channel open for async
  });

  // ── Floating inject button ──────────────────────────────────────────────────

  function findBoard() {
    return document.querySelector('chess-board') ||
           document.querySelector('cg-board') ||
           document.querySelector('.cg-wrap') ||
           document.querySelector('.board-layout-main') ||
           null;
  }

  function injectButton(boardEl) {
    if (document.getElementById('hf-chess-btn')) return; // already injected
    const btn = document.createElement('button');
    btn.id = 'hf-chess-btn';
    btn.textContent = '⬡ HexField';
    btn.title = 'Render board in HexField isometric 3D style';
    btn.addEventListener('click', () => {
      const fen = getCurrentFen() || 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
      const url = 'https://hexfield.win/?fen=' + encodeURIComponent(fen) + '#chess';
      window.open(url, '_blank', 'noopener,noreferrer');
    });

    // Position button relative to the board
    const wrap = document.createElement('div');
    wrap.id = 'hf-chess-wrap';
    boardEl.parentNode.insertBefore(wrap, boardEl.nextSibling);
    wrap.appendChild(btn);
  }

  function tryInject() {
    const board = findBoard();
    if (board) {
      injectButton(board);
    } else {
      // Retry up to 10 times over 5 seconds for SPAs that load the board asynchronously
      let tries = 0;
      const poll = setInterval(() => {
        const b = findBoard();
        if (b || ++tries > 10) {
          clearInterval(poll);
          if (b) injectButton(b);
        }
      }, 500);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', tryInject);
  } else {
    tryInject();
  }
})();
