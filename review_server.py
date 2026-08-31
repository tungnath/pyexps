#!/usr/bin/env python3
"""
review_server.py - local review harness for candidate videos
------------------------------------------------------------
Loads candidates_sphere1.json, serves a browser UI that plays each candidate
inline, and writes your approve/reject/notes/pacing decisions straight back to
the JSON on every click (atomic write - an interrupt can't corrupt the file).

No cap: every candidate gets its own decision. Keep as many per concept as you like.

Usage:
    pip install flask
    python3 review_server.py --file candidates_sphere1.json
    # then open http://127.0.0.1:5000

Keyboard shortcuts (when not typing in the notes box):
    a = approve current   r = reject current   u = unset
    s = mark pacing slow-cut   f = mark pacing FAST (auto-rejects)
    j / k = next / previous candidate
"""
import argparse
import json
import os
import threading
from flask import Flask, request, jsonify, Response

app = Flask(__name__)
LOCK = threading.Lock()
STATE = {"path": None, "data": None}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def flat_index(data):
    """Return a flat list of (concept_idx, cand_idx) for stable addressing."""
    out = []
    for ci, c in enumerate(data.get("concepts", [])):
        for vi, _ in enumerate(c.get("candidates", [])):
            out.append((ci, vi))
    return out


@app.route("/")
def index():
    return Response(PAGE, mimetype="text/html")


@app.route("/api/data")
def api_data():
    with LOCK:
        return jsonify(STATE["data"])


@app.route("/api/decide", methods=["POST"])
def api_decide():
    body = request.get_json(force=True)
    ci, vi = body["ci"], body["vi"]
    field = body["field"]          # safety_review_status | reviewer_notes | pacing_flag
    value = body["value"]
    with LOCK:
        cand = STATE["data"]["concepts"][ci]["candidates"][vi]
        cand[field] = value
        # marking pacing FAST auto-rejects, matching your framework rule
        if field == "pacing_flag" and value == "fast-REJECT":
            cand["safety_review_status"] = "rejected"
        save(STATE["path"], STATE["data"])
        return jsonify({"ok": True, "candidate": cand})


@app.route("/api/stats")
def api_stats():
    with LOCK:
        data = STATE["data"]
    approved = rejected = pending = total = 0
    for c in data["concepts"]:
        for v in c["candidates"]:
            total += 1
            s = v.get("safety_review_status", "pending")
            approved += s == "approved"
            rejected += s == "rejected"
            pending += s == "pending"
    return jsonify({"total": total, "approved": approved,
                    "rejected": rejected, "pending": pending})


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Video Review</title>
<style>
  :root{--bg:#0f1117;--panel:#181b24;--line:#262a36;--txt:#e6e8ee;--dim:#8a90a2;
        --green:#2ecc71;--red:#e74c3c;--amber:#f2c94c;--blue:#4f8cff;}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--txt);
       font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif}
  header{position:sticky;top:0;z-index:10;background:var(--panel);
         border-bottom:1px solid var(--line);padding:12px 20px;
         display:flex;gap:20px;align-items:center;flex-wrap:wrap}
  header h1{font-size:16px;margin:0;font-weight:600}
  .bar{flex:1;height:8px;background:#242836;border-radius:6px;overflow:hidden;min-width:180px}
  .bar > span{display:block;height:100%;background:var(--green)}
  .stat{font-size:13px;color:var(--dim)}
  .stat b{color:var(--txt)}
  .wrap{max-width:900px;margin:0 auto;padding:20px}
  .concept{background:var(--panel);border:1px solid var(--line);border-radius:12px;
           margin-bottom:22px;overflow:hidden}
  .concept-head{padding:12px 16px;border-bottom:1px solid var(--line);
                display:flex;justify-content:space-between;align-items:center;gap:10px}
  .concept-head .meta{font-size:12px;color:var(--dim)}
  .age{display:inline-block;font-size:11px;background:#232a3d;color:var(--blue);
       padding:2px 8px;border-radius:20px;margin-left:8px}
  .cand{padding:14px 16px;border-bottom:1px solid var(--line);display:grid;
        grid-template-columns:320px 1fr;gap:16px}
  .cand:last-child{border-bottom:none}
  .cand.approved{background:rgba(46,204,113,.06)}
  .cand.rejected{background:rgba(231,76,60,.05);opacity:.7}
  .frame{width:320px;aspect-ratio:16/9;border:0;border-radius:8px;background:#000}
  .info h3{margin:0 0 6px;font-size:14px;font-weight:600}
  .info .ch{color:var(--dim);font-size:13px}
  .tags{margin:8px 0;display:flex;flex-wrap:wrap;gap:6px}
  .tag{font-size:11px;padding:2px 8px;border-radius:20px;background:#232633;color:var(--dim)}
  .tag.trusted{background:#1e3a2a;color:var(--green)}
  .tag.mfk{background:#1e2b45;color:var(--blue)}
  .tag.warn{background:#3a2e1a;color:var(--amber)}
  .btns{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
  button{font:inherit;border:1px solid var(--line);background:#20242f;color:var(--txt);
         padding:6px 12px;border-radius:8px;cursor:pointer}
  button:hover{border-color:#3a4152}
  button.on-app{background:var(--green);color:#08150c;border-color:var(--green);font-weight:600}
  button.on-rej{background:var(--red);color:#1a0806;border-color:var(--red);font-weight:600}
  button.on-slow{background:#233d2c;border-color:var(--green);color:var(--green)}
  button.on-fast{background:#3d231f;border-color:var(--red);color:var(--red)}
  .notes{margin-top:8px;width:100%;background:#12151d;border:1px solid var(--line);
         color:var(--txt);border-radius:8px;padding:6px 10px;font:inherit;resize:vertical}
  .hint{color:var(--dim);font-size:12px;margin-left:auto}
  a.link{color:var(--blue);font-size:12px;text-decoration:none}
  .filters{display:flex;gap:8px;align-items:center}
  select{background:#20242f;color:var(--txt);border:1px solid var(--line);
         border-radius:8px;padding:5px 8px;font:inherit}
</style>
</head>
<body>
<header>
  <h1>Video Review</h1>
  <div class="bar"><span id="prog" style="width:0%"></span></div>
  <div class="stat"><b id="s-app">0</b> approved &middot;
       <b id="s-rej">0</b> rejected &middot;
       <b id="s-pen">0</b> pending / <b id="s-tot">0</b></div>
  <div class="filters">
    <select id="filter">
      <option value="all">Show all</option>
      <option value="pending">Only pending</option>
      <option value="approved">Only approved</option>
      <option value="rejected">Only rejected</option>
    </select>
  </div>
  <span class="hint">a approve &middot; r reject &middot; s slow &middot; f fast &middot; j/k move</span>
</header>
<div class="wrap" id="wrap">Loading…</div>

<script>
let DATA=null, FLAT=[], cur=0;

function iso2dur(s){ if(!s) return ""; const m=s.match(/PT(?:(\d+)M)?(?:(\d+)S)?/);
  if(!m) return s; const mm=m[1]||0, ss=(m[2]||0).toString().padStart(2,'0'); return mm+":"+ss; }
function views(n){ if(n==null) return "—"; if(n>=1e7) return (n/1e7).toFixed(1)+"Cr";
  if(n>=1e5) return (n/1e5).toFixed(1)+"L"; if(n>=1e3) return (n/1e3).toFixed(1)+"K"; return n; }

async function boot(){
  DATA = await (await fetch('/api/data')).json();
  FLAT = [];
  DATA.concepts.forEach((c,ci)=>c.candidates.forEach((v,vi)=>FLAT.push([ci,vi])));
  render(); refreshStats();
}

function render(){
  const filter=document.getElementById('filter').value;
  const wrap=document.getElementById('wrap'); wrap.innerHTML='';
  DATA.concepts.forEach((c,ci)=>{
    const vis=c.candidates.filter(v=>filter==='all'||v.safety_review_status===filter);
    if(vis.length===0) return;
    const box=document.createElement('div'); box.className='concept';
    box.innerHTML=`<div class="concept-head">
        <div><b>#${c.concept_id}</b> ${c.concept}
             <span class="age">${c.age_band||''}</span></div>
        <div class="meta">query: ${c.query_used||''}</div></div>`;
    c.candidates.forEach((v,vi)=>{
      if(filter!=='all' && v.safety_review_status!==filter) return;
      box.appendChild(candNode(c,ci,v,vi));
    });
    wrap.appendChild(box);
  });
}

function candNode(c,ci,v,vi){
  const d=document.createElement('div');
  d.className='cand '+(v.safety_review_status||'');
  d.id=`cand-${ci}-${vi}`;
  const mfk = v.made_for_kids===true?'<span class="tag mfk">madeForKids</span>':
              (v.made_for_kids===false?'<span class="tag warn">NOT madeForKids</span>':'');
  const trust = v.trusted_channel?'<span class="tag trusted">trusted channel</span>':'';
  const emb = v.embeddable===false?'<span class="tag warn">not embeddable</span>':'';
  d.innerHTML=`
    <iframe class="frame" loading="lazy"
      src="https://www.youtube-nocookie.com/embed/${v.video_id}" allowfullscreen></iframe>
    <div class="info">
      <h3>${v.title||''}</h3>
      <div class="ch">${v.channel_title||''} &middot; ${iso2dur(v.duration_iso)} &middot;
           ${views(v.view_count)} views
           &middot; <a class="link" target="_blank" href="${v.url}">open ↗</a></div>
      <div class="tags">${trust}${mfk}${emb}</div>
      <div class="btns">
        <button data-act="approve" class="${v.safety_review_status==='approved'?'on-app':''}">✓ Approve</button>
        <button data-act="reject"  class="${v.safety_review_status==='rejected'?'on-rej':''}">✗ Reject</button>
        <button data-act="unset">Unset</button>
        <button data-act="slow" class="${v.pacing_flag==='slow-cut'?'on-slow':''}">slow-cut</button>
        <button data-act="fast" class="${v.pacing_flag==='fast-REJECT'?'on-fast':''}">FAST</button>
      </div>
      <textarea class="notes" rows="1" placeholder="reviewer notes…">${v.reviewer_notes||''}</textarea>
    </div>`;
  d.querySelectorAll('button').forEach(b=>{
    b.onclick=()=>act(ci,vi,b.dataset.act);
  });
  const ta=d.querySelector('.notes');
  ta.onblur=()=>decide(ci,vi,'reviewer_notes',ta.value);
  return d;
}

async function decide(ci,vi,field,value){
  const r=await fetch('/api/decide',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({ci,vi,field,value})});
  const j=await r.json();
  DATA.concepts[ci].candidates[vi]=j.candidate;
  const node=document.getElementById(`cand-${ci}-${vi}`);
  if(node){ const fresh=candNode(DATA.concepts[ci],ci,j.candidate,vi);
            node.replaceWith(fresh); }
  refreshStats();
}

function act(ci,vi,a){
  const map={approve:['safety_review_status','approved'],
             reject:['safety_review_status','rejected'],
             unset:['safety_review_status','pending'],
             slow:['pacing_flag','slow-cut'],
             fast:['pacing_flag','fast-REJECT']};
  const [f,val]=map[a]; decide(ci,vi,f,val);
}

async function refreshStats(){
  const s=await (await fetch('/api/stats')).json();
  document.getElementById('s-app').textContent=s.approved;
  document.getElementById('s-rej').textContent=s.rejected;
  document.getElementById('s-pen').textContent=s.pending;
  document.getElementById('s-tot').textContent=s.total;
  const done=s.approved+s.rejected;
  document.getElementById('prog').style.width=(s.total? (done/s.total*100):0)+'%';
}

document.getElementById('filter').onchange=render;

document.addEventListener('keydown',e=>{
  if(e.target.tagName==='TEXTAREA'||e.target.tagName==='SELECT') return;
  const cards=[...document.querySelectorAll('.cand')];
  if(!cards.length) return;
  cur=Math.max(0,Math.min(cur,cards.length-1));
  const id=cards[cur].id.split('-'); const ci=+id[1], vi=+id[2];
  if(e.key==='a') act(ci,vi,'approve');
  else if(e.key==='r') act(ci,vi,'reject');
  else if(e.key==='u') act(ci,vi,'unset');
  else if(e.key==='s') act(ci,vi,'slow');
  else if(e.key==='f') act(ci,vi,'fast');
  else if(e.key==='j'){cur=Math.min(cur+1,cards.length-1);cards[cur].scrollIntoView({block:'center'});}
  else if(e.key==='k'){cur=Math.max(cur-1,0);cards[cur].scrollIntoView({block:'center'});}
});

boot();
</script>
</body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="candidates JSON to review")
    ap.add_argument("--port", type=int, default=5000)
    args = ap.parse_args()
    STATE["path"] = args.file
    STATE["data"] = load(args.file)
    n = sum(len(c["candidates"]) for c in STATE["data"]["concepts"])
    print(f"Loaded {len(STATE['data']['concepts'])} concepts, {n} candidates.")
    print(f"Open http://127.0.0.1:{args.port}  (Ctrl+C to stop; every click is saved)")
    app.run(port=args.port, debug=False)


if __name__ == "__main__":
    main()
