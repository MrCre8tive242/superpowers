"""The web page: drop a mockup, watch it work, copy the link. Runs on your PC (http://localhost:8765)."""
import hmac
import os
from pathlib import Path

from flask import Flask, Response, abort, jsonify, request, send_file

from . import config, engine, generator, notify

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024
THUMB = 520

STYLE_WORDS = {"auto": "", "3d": "3D all-over", "cut": "cut and sew"}


@app.before_request
def _auth():
    if not config.WEB_PASSWORD:
        return None
    a = request.authorization
    if a and hmac.compare_digest(a.password or "", config.WEB_PASSWORD):
        return None
    return Response("Password needed", 401, {"WWW-Authenticate": 'Basic realm="Shirt Pipeline"'})


def _shirt(wd: Path) -> dict:
    plan = engine._json(wd / "plan.json", {})
    st = engine._json(wd / "status.json", {})
    qa = engine._json(wd / "qa.json", {})
    label = plan.get("label", wd.name)
    ready = config.READY / label
    files = []
    for a in plan.get("assets", []):
        found = sorted(ready.glob(f"{a['n']:02d}_*"), key=lambda p: p.stat().st_mtime) if ready.exists() else []
        rec = qa.get(str(a["n"]), {})
        files.append({"n": a["n"], "name": a["name"], "kind": a.get("kind"),
                      "file": found[-1].name if found else None,
                      "status": rec.get("status", "missing" if not found else "unchecked"),
                      "issues": rec.get("issues", [])[:3]})
    return {"name": wd.name, "label": label, "mode": plan.get("mode", ""), "mode_reason": plan.get("mode_reason", ""),
            "link": st.get("link"), "needs_look": bool(st.get("needs_look")), "updated": st.get("updated", ""),
            "files": files, "has_preview": (wd / "preview.jpg").exists(), "review": "review" in plan.get("flags", [])}


@app.get("/api/state")
def state():
    shirts = []
    if config.WORK.exists():
        dirs = [d for d in config.WORK.iterdir() if (d / "plan.json").exists()]
        for d in sorted(dirs, key=lambda d: (d / "plan.json").stat().st_mtime, reverse=True)[:15]:
            shirts.append(_shirt(d))
    jobs = [{k: v for k, v in j.items() if k != "lines"} | {"lines": j["lines"][-60:]}
            for j in reversed(list(engine.JOBS.values()))]
    working = {j["label"] for j in jobs if j["phase"] not in ("done", "error")}
    for s in shirts:
        s["busy"] = s["label"] in working
    return jsonify({
        "settings": {"hands_off": config.AUTO_APPROVE, "planner": f"{config.PLANNER_PROVIDER}:{config.PLANNER_MODEL}",
                     "image_model": config.IMAGE_MODEL, "email": notify.email_configured(),
                     "inbox": str(config.INBOX)},
        "jobs": jobs, "shirts": shirts})


@app.post("/api/upload")
def upload():
    files = request.files.getlist("file")
    style = STYLE_WORDS.get(request.form.get("style", "auto"), "")
    notes = request.form.get("notes", "").strip()
    review = request.form.get("review") == "1"
    if not files:
        abort(400, "No file")
    config.INBOX.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in files:
        stem, ext = os.path.splitext(f.filename or "shirt")
        ext = ext.lower()
        if ext not in engine.IMG_EXT:
            abort(400, f"{f.filename}: use a PNG, JPG or WEBP image")
        label = engine.safe_label(stem)
        hint = " ".join(x for x in (style, notes, "--review" if review else "") if x)
        txt = config.INBOX / f"{label}.txt"
        if hint:
            txt.write_text(hint, encoding="utf-8")
        elif txt.exists():
            txt.unlink()
        part = config.INBOX / f"{label}{ext}.part"
        f.save(part)
        os.replace(part, config.INBOX / f"{label}{ext}")  # appears complete, so the watcher never grabs half a file
        saved.append(label)
    return jsonify({"queued": saved})


def _shirt_or_404(name):
    try:
        return engine.find_shirt(name)
    except FileNotFoundError:
        abort(404)


@app.post("/api/redo")
def redo():
    data = request.get_json(force=True)
    wd, plan = _shirt_or_404(data.get("name", ""))
    numbers = [int(n) for n in data.get("numbers", [])]
    engine.submit("redo", plan["label"], lambda: engine.redo(plan["label"], numbers))
    return jsonify({"ok": True})


@app.post("/api/approve")
def approve():
    wd, plan = _shirt_or_404(request.get_json(force=True).get("name", ""))
    engine.submit("upload", plan["label"], lambda: engine.approve(plan["label"]))
    return jsonify({"ok": True})


@app.get("/thumb/<name>/<path:file>")
def thumb(name, file):
    wd, plan = _shirt_or_404(name)
    ready = engine.ready_dir(plan)
    src = ready / Path(file).name
    if not src.exists() or src.parent.resolve() != ready.resolve():
        abort(404)
    cache = wd / "thumbs"
    cache.mkdir(exist_ok=True)
    out = cache / f"{src.stem}.{int(src.stat().st_mtime)}.png"
    if not out.exists():
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
        with Image.open(src) as im:
            im.thumbnail((THUMB, THUMB))
            im.convert("RGBA").save(out, "PNG")
    return send_file(out, mimetype="image/png", max_age=3600)


@app.get("/preview/<name>")
def preview_sheet(name):
    wd, _ = _shirt_or_404(name)
    p = wd / "preview.jpg"
    if not p.exists():
        abort(404)
    return send_file(p, mimetype="image/jpeg", max_age=0)


@app.get("/")
def index():
    return Response(PAGE, mimetype="text/html")


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Shirt Pipeline</title>
<style>
:root{--bg:#f4f5f7;--card:#fff;--ink:#1b1f27;--mute:#687083;--line:#e2e5ea;--accent:#2f6df6;--accent-ink:#fff;
--ok:#1f9d57;--warn:#d98a0b;--bad:#cf3b3b;--chip:#eef1f6;--tile:#e9ebef}
@media (prefers-color-scheme:dark){:root{--bg:#14161a;--card:#1d2026;--ink:#eceef2;--mute:#9aa2b1;--line:#2c313a;
--accent:#6b9bff;--accent-ink:#0c1226;--chip:#262b34;--tile:#2a2e36}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:980px;margin:0 auto;padding:20px 16px 60px}
header{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 14px;margin-bottom:16px}
h1{font-size:22px;margin:0}
.meta{color:var(--mute);font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:16px}
.drop{border:2px dashed var(--line);border-radius:12px;padding:28px 16px;text-align:center;cursor:pointer;transition:.15s}
.drop.over{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 8%,transparent)}
.drop b{display:block;font-size:17px;margin-bottom:4px}
.drop span{color:var(--mute);font-size:13px}
.opts{display:grid;gap:10px;margin-top:14px}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:10px;overflow:hidden;flex-wrap:wrap}
.seg button{border:0;background:transparent;color:var(--ink);padding:8px 14px;font:inherit;cursor:pointer}
.seg button.on{background:var(--accent);color:var(--accent-ink)}
label.row{display:flex;gap:8px;align-items:center;color:var(--mute);font-size:14px}
input[type=text]{width:100%;padding:10px 12px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--ink);font:inherit}
h2{font-size:15px;margin:22px 0 10px;color:var(--mute);text-transform:uppercase;letter-spacing:.05em}
.top{display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between}
.name{font-weight:650;font-size:17px}
.chip{display:inline-block;background:var(--chip);border-radius:999px;padding:2px 10px;font-size:12px;color:var(--mute)}
.chip.ok{background:color-mix(in srgb,var(--ok) 16%,transparent);color:var(--ok)}
.chip.warn{background:color-mix(in srgb,var(--warn) 18%,transparent);color:var(--warn)}
.chip.bad{background:color-mix(in srgb,var(--bad) 16%,transparent);color:var(--bad)}
.steps{display:flex;gap:6px;margin:10px 0;flex-wrap:wrap}
.step{font-size:12px;padding:3px 10px;border-radius:999px;background:var(--chip);color:var(--mute)}
.step.cur{background:var(--accent);color:var(--accent-ink)}.step.done{color:var(--ok)}
.log{font:12px/1.5 ui-monospace,Menlo,Consolas,monospace;color:var(--mute);white-space:pre-wrap;max-height:220px;overflow:auto;background:var(--chip);border-radius:8px;padding:8px;margin-top:8px}
.link{display:flex;gap:8px;align-items:center;margin:12px 0;flex-wrap:wrap}
.link code{background:var(--chip);padding:6px 10px;border-radius:8px;font-size:13px;word-break:break-all;flex:1;min-width:200px}
button.b,a.b{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:9px;padding:7px 12px;font:inherit;font-size:14px;cursor:pointer;text-decoration:none;display:inline-block}
button.b.primary{background:var(--accent);color:var(--accent-ink);border-color:transparent}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-top:12px}
.tile{border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--card)}
.img{aspect-ratio:1;background:repeating-conic-gradient(var(--tile) 0 25%,transparent 0 50%) 0 0/16px 16px;display:grid;place-items:center}
.img img{max-width:100%;max-height:100%;object-fit:contain}
.cap{padding:6px 8px;font-size:12px;display:flex;justify-content:space-between;gap:6px;align-items:center}
.cap .n{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block;margin-right:5px;background:var(--mute)}
.dot.ok{background:var(--ok)}.dot.check{background:var(--warn)}.dot.fail,.dot.missing{background:var(--bad)}.dot.wait{background:var(--mute);opacity:.5}
.cap button{border:0;background:none;color:var(--accent);cursor:pointer;font-size:12px;padding:0}
.issues{padding:0 8px 8px;font-size:11px;color:var(--mute)}
.empty{color:var(--mute);text-align:center;padding:22px}
details summary{cursor:pointer;color:var(--mute);font-size:13px}
</style>
</head>
<body><div class="wrap">
<header><h1>Shirt Pipeline</h1><span class="meta" id="meta"></span></header>

<div class="card">
  <div class="drop" id="drop"><b>Drop a shirt mockup here</b><span>or tap to choose one (you can pick several)</span>
    <input type="file" id="file" accept="image/png,image/jpeg,image/webp" multiple hidden></div>
  <div class="opts">
    <div><div class="seg" id="style">
      <button data-v="auto" class="on">Auto-detect style</button><button data-v="3d">3D all-over</button><button data-v="cut">Cut and sew</button></div></div>
    <input type="text" id="notes" placeholder="Corrections (optional)">
    <label class="row"><input type="checkbox" id="review"> Hold this shirt for my review (don't upload automatically)</label>
  </div>
</div>

<div id="jobs"></div>
<h2>Your shirts</h2>
<div id="shirts"><div class="empty">Nothing yet. Drop a mockup above.</div></div>
</div>
<script>
const $=s=>document.querySelector(s);
const h=(tag,attrs={},...kids)=>{const e=document.createElement(tag);
  for(const[k,v]of Object.entries(attrs)){if(k==='class')e.className=v;else if(k.startsWith('on'))e[k]=v;else if(v!==false&&v!=null)e.setAttribute(k,v)}
  for(const c of kids.flat())if(c!=null)e.append(c.nodeType?c:document.createTextNode(c));return e};
let style='auto',last='',openLogs=new Set();
document.querySelectorAll('#style button').forEach(b=>b.onclick=()=>{style=b.dataset.v;
  document.querySelectorAll('#style button').forEach(x=>x.classList.toggle('on',x===b))});
const drop=$('#drop'),fi=$('#file');
drop.onclick=()=>fi.click();
['dragenter','dragover'].forEach(t=>drop.addEventListener(t,e=>{e.preventDefault();drop.classList.add('over')}));
['dragleave','drop'].forEach(t=>drop.addEventListener(t,e=>{e.preventDefault();drop.classList.remove('over')}));
drop.addEventListener('drop',e=>send(e.dataTransfer.files));
fi.onchange=()=>send(fi.files);
async function send(files){
  if(!files.length)return;
  const fd=new FormData();for(const f of files)fd.append('file',f);
  fd.append('style',style);fd.append('notes',$('#notes').value);fd.append('review',$('#review').checked?'1':'0');
  drop.firstElementChild.textContent='Uploading...';
  const r=await fetch('/api/upload',{method:'POST',body:fd});
  drop.firstElementChild.textContent=r.ok?'Got it. It will start in a few seconds.':'Upload failed: '+(await r.text()).slice(0,120);
  setTimeout(()=>drop.firstElementChild.textContent='Drop a shirt mockup here',4000);
  fi.value='';$('#notes').value='';poll();
}
const post=(u,b)=>fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}).then(poll);
const PHASES=[['planning','Planning'],['generating','Making + checking layers'],['packaging','Packaging'],['uploading','Uploading'],['done','Done']];
function jobCard(j){
  const idx=PHASES.findIndex(p=>p[0]===j.phase);
  const steps=h('div',{class:'steps'},PHASES.map((p,i)=>h('span',{class:'step '+(j.phase==='error'?'':i<idx||j.phase==='done'?'done':i===idx?'cur':'')},(i<idx||j.phase==='done'?'✓ ':'')+p[1])));
  const det=h('details',{},h('summary',{},j.phase==='done'?'Show log':'Show details'),h('div',{class:'log'},j.lines.join('\n')));
  if(openLogs.has(j.id))det.open=true;det.ontoggle=()=>det.open?openLogs.add(j.id):openLogs.delete(j.id);
  const kind={shirt:'New shirt',redo:'Redoing layers',upload:'Updating Drive'}[j.kind]||j.kind;
  return h('div',{class:'card'},h('div',{class:'top'},h('span',{class:'name'},j.label),
    h('span',{class:'chip '+(j.phase==='error'?'bad':j.phase==='done'?'ok':'')},j.phase==='queued'?'Waiting in line':j.phase==='error'?'Failed':j.phase==='done'?'Finished':kind)),
    j.phase==='queued'||j.phase==='done'?null:steps,j.error?h('div',{class:'issues',style:'color:var(--bad);font-size:13px'},j.error):null,det);
}
function shirtCard(s){
  const bad=s.needs_look,busy=s.busy;
  const link=s.link?h('div',{class:'link'},h('code',{},s.link),
      h('button',{class:'b primary',onclick:e=>{navigator.clipboard.writeText(s.link);e.target.textContent='Copied';setTimeout(()=>e.target.textContent='Copy link',1500)}},'Copy link'),
      h('a',{class:'b',href:s.link,target:'_blank',rel:'noopener'},'Open')):null;
  const grid=h('div',{class:'grid'},s.files.map(f=>h('div',{class:'tile'},
    h('div',{class:'img'},f.file?h('img',{loading:'lazy',src:`/thumb/${encodeURIComponent(s.name)}/${encodeURIComponent(f.file)}`}):h('span',{class:'meta'},busy?'waiting...':'missing')),
    h('div',{class:'cap'},h('span',{class:'n',title:f.name},h('span',{class:'dot '+(busy&&!f.file?'wait':f.status)}),f.n+' '+f.name),
      busy?null:h('button',{title:'Make this layer again',onclick:()=>confirm('Redo "'+f.name+'"? This makes a new image.')&&post('/api/redo',{name:s.name,numbers:[f.n]})},'Redo')),
    f.issues.length?h('div',{class:'issues'},f.issues.join(' · ')):null)));
  return h('div',{class:'card'},
    h('div',{class:'top'},h('span',{class:'name'},s.label),
      h('span',{},h('span',{class:'chip'},s.mode),' ',busy?h('span',{class:'chip'},'Working...'):h('span',{class:'chip '+(bad?'warn':'ok')},bad?'Needs a look':'Ready'))),
    busy?null:link,
    busy?null:h('div',{class:'link'},
      s.has_preview?h('a',{class:'b',href:'/preview/'+encodeURIComponent(s.name),target:'_blank'},'Preview sheet'):null,
      h('button',{class:'b'+(s.link?'':' primary'),onclick:()=>post('/api/approve',{name:s.name})},s.link?'Update Drive with my changes':'Approve and upload to Drive')),
    grid);
}
async function poll(){
  try{
    const r=await fetch('/api/state');if(!r.ok)return;const d=await r.json();
    const key=JSON.stringify(d);if(key===last)return;last=key;
    $('#meta').textContent=(d.settings.hands_off?'Hands-off: uploads automatically':'Review mode: waits for approval')+' · planner '+d.settings.planner+(d.settings.email?' · email on':' · email off');
    const active=d.jobs.filter(j=>j.phase!=='done'||Date.now()-new Date(j.finished||j.started)<120000);
    $('#jobs').replaceChildren(...active.map(jobCard));
    $('#shirts').replaceChildren(...(d.shirts.length?d.shirts.map(shirtCard):[h('div',{class:'empty'},'Nothing yet. Drop a mockup above.')]));
  }catch(e){}
}
poll();setInterval(poll,2500);
</script></body></html>
"""
