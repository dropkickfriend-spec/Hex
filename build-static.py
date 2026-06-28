#!/usr/bin/env python3
"""Build a self-contained static index.html for GitHub Pages deployment.

Merges backend/original_tonality.html with the render_patch from backend/server.py,
then patches the two backend-dependent API calls so everything runs client-side:
  - /api/site-html proxy   → https://api.allorigins.win/raw?url=
  - /api/export-gif (PIL)  → client-side html2canvas + gif.js capture
Output: docs/index.html
"""
import os

# ── Read source files ──────────────────────────────────────────────────────────
with open("backend/original_tonality.html", encoding="utf-8") as f:
    original = f.read()

with open("backend/server.py", encoding="utf-8") as f:
    server_code = f.read()

# ── Extract render_patch from server.py ───────────────────────────────────────
START = '    render_patch = """\n'
END   = '"""\n    # ── Inject server-side config'

s = server_code.index(START) + len(START)
e = server_code.index(END, s)
render_patch = server_code[s:e]

print(f"  Extracted render_patch: {len(render_patch):,} chars")

# ── Patch 1: website preview — replace backend proxy with public CORS proxy ───
render_patch = render_patch.replace(
    'src="site-html?url=https%3A%2F%2Fexample.com"',
    'src="https://api.allorigins.win/raw?url=https%3A%2F%2Fexample.com"',
)
render_patch = render_patch.replace(
    "frame.src = 'site-html?url=' + encodeURIComponent(url);",
    "frame.src = 'https://api.allorigins.win/raw?url=' + encodeURIComponent(url);",
)

# ── Patch 2: GIF export — replace server-side PIL call with html2canvas+gif.js
OLD_EXPORT = """  async function exportGif(){
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
  }"""

NEW_EXPORT = """  function _loadScript(src){
    return new Promise((res,rej)=>{
      const s = document.createElement('script');
      s.src = src; s.onload = res; s.onerror = rej;
      document.head.appendChild(s);
    });
  }
  async function exportGif(){
    const status = $('mhExportStatus');
    try {
      if (status) status.textContent = 'Loading export libraries…';
      if (!window.GIF) await _loadScript('https://cdnjs.cloudflare.com/ajax/libs/gif.js/0.2.0/gif.js');
      if (!window.html2canvas) await _loadScript('https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js');
      const stage = $('mhTargetStage');
      if (!stage) throw new Error('Stage element not found');
      const payload = exportPayload();
      const frameCount = 18;
      const frameDelay = Math.max(40, Math.round(800 / Math.max(1, payload.speed || 4)));
      if (status) status.textContent = 'Capturing 18 frames…';
      const gif = new GIF({
        workers: 2,
        quality: 8,
        width: stage.offsetWidth || 390,
        height: stage.offsetHeight || 430,
        workerScript: 'https://cdnjs.cloudflare.com/ajax/libs/gif.js/0.2.0/gif.worker.js',
      });
      for (let i = 0; i < frameCount; i++) {
        await new Promise(r => setTimeout(r, frameDelay));
        const canvas = await html2canvas(stage, {
          useCORS: true,
          backgroundColor: null,
          logging: false,
          scale: 1,
        });
        gif.addFrame(canvas, { delay: frameDelay, copy: true });
        if (status) status.textContent = `Capturing frame ${i + 1}/${frameCount}…`;
      }
      gif.on('finished', blob => {
        const url = URL.createObjectURL(blob);
        const link = $('mhGifDownload');
        link.href = url;
        link.style.display = 'inline-flex';
        link.download = `munkerhex-${Date.now()}.gif`;
        if (status) status.textContent = 'GIF ready — tap Download GIF.';
      });
      gif.on('progress', p => {
        if (status) status.textContent = `Encoding GIF… ${Math.round(p * 100)}%`;
      });
      gif.render();
    } catch(e) {
      if (status) status.textContent = 'GIF export failed: ' + (e.message || e);
    }
  }"""

assert OLD_EXPORT in render_patch, (
    "Could not find exportGif() in render_patch — check server.py for changes"
)
render_patch = render_patch.replace(OLD_EXPORT, NEW_EXPORT)

# ── localStorage persistence block ────────────────────────────────────────────
LOCAL_STORAGE_SCRIPT = """
<script>
(function(){
  var KEY = 'mhDesign';
  var IDS = ['mhUnifiedMode','mhUnifiedPattern','mhUnifiedSpacing','mhLineThickness',
    'mhUnifiedOpacity','mhUnifiedSpeed','mhAutoAnimate','mhMunkerPreset',
    'mhGame','mhUrl','mhWebPreset','mhWebDensity','mhGameStyle'];
  function save(){
    var saved = {};
    IDS.forEach(function(id){
      var el = document.getElementById(id);
      if (el) saved[id] = el.value;
    });
    try { localStorage.setItem(KEY, JSON.stringify(saved)); } catch(_){}
  }
  function restore(){
    var saved;
    try { saved = JSON.parse(localStorage.getItem(KEY) || 'null'); } catch(_){}
    if (!saved) return;
    Object.keys(saved).forEach(function(id){
      var el = document.getElementById(id);
      if (!el) return;
      el.value = saved[id];
      el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
    });
  }
  document.addEventListener('DOMContentLoaded', function(){
    setTimeout(restore, 700);
    document.addEventListener('input', save, { passive: true });
    document.addEventListener('change', save, { passive: true });
  });
})();
</script>
"""

# ── Assemble output HTML ──────────────────────────────────────────────────────
output = original.replace("<body>", "<body>\n" + render_patch, 1)
# Use rfind so we target the real closing </body>, not one that may appear
# inside a JS string literal (e.g. downloadWebHtml's template literal)
last_body = output.rfind("</body>")
output = output[:last_body] + LOCAL_STORAGE_SCRIPT + output[last_body:]

# ── Write output ──────────────────────────────────────────────────────────────
os.makedirs("docs", exist_ok=True)
with open("docs/index.html", "w", encoding="utf-8") as f:
    f.write(output)

print(f"Built docs/index.html")
print(f"  Base HTML:     {len(original):>10,} chars")
print(f"  Render patch:  {len(render_patch):>10,} chars")
print(f"  Output total:  {len(output):>10,} chars")
