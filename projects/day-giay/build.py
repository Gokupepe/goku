#!/usr/bin/env python3
"""Dựng video affiliate "dây giày hai màu".

1. Giọng đọc edge-tts cho từng cảnh, lấy mốc thời gian từng từ.
2. Ghép nền từ 2 clip gốc (scale cố định, cảnh tiêu cực trắng đen) -> hf/bg.mp4
3. Trộn tiếng: giọng đọc + tiếng sân gốc nhỏ + hiệu ứng âm thanh -> hf/mix.wav
4. Sinh hf/index.html (HyperFrames) với graphics canh đúng điểm cắt / đúng từ.

Chạy: python3 build.py   (sau đó: cd hf && hyperframes snapshot / render)
"""
import asyncio, json, os, re, subprocess, sys, html
from pathlib import Path

D = Path(__file__).resolve().parent
HF = D / "hf"
CACHE = D / "cache"
SRC = {"cam0": D / "cam0.mp4", "cam1": D / "cam1.mp4"}  # đặt 2 video gốc (dây giày 0, 1) cạnh file này
FONTS = D / "fonts"
FPS, SR = 30, 48000


def run(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"FAIL {' '.join(map(str, cmd[:8]))}\n{r.stderr[-2000:]}")
    return r.stdout


def norm(w):
    return re.sub(r"[^\wÀ-ỹ]", "", w.lower())


# ---------- 1. TTS ----------
def tts(text, voice, rate, out):
    js = out.with_suffix(".json")
    if out.exists() and js.exists():
        return json.loads(js.read_text())
    import edge_tts

    async def go():
        c = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary",
                                 proxy=os.environ.get("HTTPS_PROXY"))
        words = []
        with open(out, "wb") as f:
            async for ch in c.stream():
                if ch["type"] == "audio":
                    f.write(ch["data"])
                elif ch["type"] == "WordBoundary":
                    s = ch["offset"] / 1e7
                    words.append([ch["text"], s, s + ch["duration"] / 1e7])
        return words
    for attempt in range(4):
        try:
            words = asyncio.run(go()); break
        except Exception as e:
            print('tts retry', attempt, e); import time; time.sleep(2 * (attempt + 1))
    else:
        sys.exit('TTS failed: ' + text)
    js.write_text(json.dumps(words, ensure_ascii=False))
    return words


# ---------- SFX (tổng hợp bằng ffmpeg, không cần tải) ----------
SFX = {
    "whoosh": "anoisesrc=d=0.55:c=pink:a=0.9,highpass=f=300,lowpass=f=5000,"
              "afade=t=in:d=0.3:curve=exp,afade=t=out:st=0.3:d=0.25,volume=0.55",
    "pop": "aevalsrc='0.6*sin(2*PI*(500+1800*exp(-t*35))*t)*exp(-t*28)':d=0.18:s=48000",
    "glitch": "aevalsrc='0.35*sgn(sin(2*PI*70*t))*exp(-t*7)+0.25*sin(2*PI*1400*t)*lt(mod(t,0.06),0.03)*exp(-t*8)':d=0.35:s=48000",
    "ding": "aevalsrc='0.35*(sin(2*PI*1568*t)+0.6*sin(2*PI*2093*t)+0.3*sin(2*PI*3136*t))*exp(-t*3.5)':d=1.3:s=48000",
    "hit": "aevalsrc='0.8*sin(2*PI*(55+120*exp(-t*25))*t)*exp(-t*9)':d=0.4:s=48000",
}


def make_sfx():
    for k, f in SFX.items():
        p = CACHE / f"sfx_{k}.wav"
        if not p.exists():
            run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f, "-ac", "2", "-ar", SR, p])


def main():
    cfg = json.loads((D / "script.json").read_text())
    CACHE.mkdir(exist_ok=True)
    HF.mkdir(exist_ok=True)
    import shutil
    shutil.copytree(FONTS, HF / "assets" / "fonts", dirs_exist_ok=True)
    make_sfx()

    # --- timings ---
    t = 0.0
    scenes = []
    for i, s in enumerate(cfg["scenes"]):
        mp3 = CACHE / f"vo_{s['id']}.mp3"
        words = tts(s["vo"], cfg["voice"], s.get("rate", cfg["rate"]), mp3)
        dur = round(max(words[-1][2] + 0.22 + s.get("tail", 0), 1.2) * FPS) / FPS
        kw_off = next((w[1] for w in words if norm(w[0]) == norm(s["kw_at"])), words[0][1])
        scenes.append(dict(s, start=round(t, 4), dur=dur, kw_time=round(t + kw_off, 3),
                           words=words, mp3=str(mp3)))
        t += dur
    total = round(t, 4)

    # --- 2. background video ---
    parts = []
    for i, s in enumerate(scenes):
        out = CACHE / f"bg_{i}.mp4"
        avail = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", SRC[s["src"]]])) - s["in"] - 0.05
        slow = s["dur"] / avail if avail < s["dur"] else 1.0  # thiếu cảnh -> quay chậm thay vì đứng hình
        vf = f"setpts={slow:.4f}*PTS,scale=1080:1920:flags=lanczos,setsar=1,fps=30"
        if s["mood"] == "negative":
            vf += ",hue=s=0,eq=contrast=1.12:brightness=-0.06"
        vf += f",tpad=stop_mode=clone:stop_duration={s['dur']}"
        run(["ffmpeg", "-v", "error", "-y", "-ss", s["in"], "-i", SRC[s["src"]], "-t", s["dur"],
             "-vf", vf, "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "16",
             "-pix_fmt", "yuv420p", "-r", FPS, "-t", s["dur"], out])
        parts.append(out)
    lst = CACHE / "bg.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", HF / "bg.mp4"])

    # --- 3. audio mix ---
    inputs, filters, labels = [], [], []

    nin = [0]

    def add(path, at, vol, extra=""):
        k = nin[0]; nin[0] += 1
        inputs.extend(["-i", path])
        filters.append(f"[{k}:a]aresample={SR},aformat=channel_layouts=stereo{extra},"
                       f"volume={vol},adelay={int(at*1000)}|{int(at*1000)}[a{k}]")
        labels.append(f"[a{k}]")

    for s in scenes:
        add(s["mp3"], s["start"], 1.0)
        # tiếng sân gốc, nhỏ, cho cảm giác thật
        k = nin[0]; nin[0] += 1
        inputs.extend(["-ss", str(s["in"]), "-t", str(s["dur"]), "-i", SRC[s["src"]]])
        filters.append(f"[{k}:a]aresample={SR},aformat=channel_layouts=stereo,volume=0.10,"
                       f"afade=t=in:d=0.05,afade=t=out:st={max(s['dur']-0.08,0)}:d=0.08,"
                       f"adelay={int(s['start']*1000)}|{int(s['start']*1000)}[a{k}]")
        labels.append(f"[a{k}]")
        if s["start"] > 0 or s["sfx"] != "whoosh":
            cut_sfx = s["sfx"] if s["sfx"] in ("whoosh", "glitch") else "hit"
            add(CACHE / f"sfx_{cut_sfx}.wav", max(s["start"] - (0.3 if cut_sfx == "whoosh" else 0), 0), 0.8)
        add(CACHE / f"sfx_{'ding' if s.get('cta') else 'pop'}.wav", s["kw_time"], 0.7)
    filters.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0,"
                   f"atrim=0:{total},loudnorm=I=-14:TP=-1.5:LRA=11[out]")
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filters),
         "-map", "[out]", "-ar", SR, "-ac", "2", HF / "mix.wav"])

    # --- 4. HyperFrames composition ---
    (HF / "index.html").write_text(render_html(cfg, scenes, total), encoding="utf-8")
    (D / "timeline.json").write_text(json.dumps(
        [{k: s[k] for k in ("id", "src", "in", "start", "dur", "kw_time", "vo")} for s in scenes],
        ensure_ascii=False, indent=2))
    print(f"total {total:.2f}s")
    for s in scenes:
        print(f"{s['start']:6.2f}  {s['dur']:5.2f}  {s['src']}@{s['in']:<5} kw@{s['kw_time']:.2f}  {s['vo']}")


def kw_html(kw):
    a, _, b = kw.partition("|")
    return html.escape(a) + (f"<em>{html.escape(b)}</em>" if b else "")


ART = {
    "swatch": '''<svg width="760" height="420" viewBox="0 0 760 420" fill="none">
      <rect class="draw" x="20" y="30" width="720" height="70" rx="35" fill="#f4f1ec"/>
      <rect class="draw" x="20" y="175" width="720" height="70" rx="35" fill="#ff7a1a"/>
      <rect class="draw" x="20" y="320" width="720" height="70" rx="35" fill="#f4f1ec"/>
      <rect class="draw" x="380" y="320" width="360" height="70" rx="35" fill="#ff7a1a"/></svg>''',
    "shoe": '''<svg width="800" height="440" viewBox="0 0 800 440" fill="none" stroke-linecap="round" stroke-linejoin="round">
      <path class="stroke" d="M40 330 L60 170 Q90 120 150 150 L330 230 Q420 250 520 260 L700 280 Q760 290 760 340 L760 360 L40 360 Z" stroke="#f4f1ec" stroke-width="14"/>
      <path class="stroke" d="M180 170 L230 230 M240 190 L290 250 M300 210 L350 260" stroke="#ff7a1a" stroke-width="16"/>
      <path class="stroke" d="M40 390 L760 390" stroke="#a7a39c" stroke-width="10"/></svg>''',
    "lace": '''<svg width="760" height="520" viewBox="0 0 760 520" fill="none" stroke-linecap="round">
      <path class="stroke" d="M80 470 C 250 340, 420 230, 690 50" stroke="#f4f1ec" stroke-width="26"/>
      <path class="stroke" d="M80 50 C 290 190, 450 320, 690 470" stroke="#ff7a1a" stroke-width="26"/>
      <circle class="stroke" cx="385" cy="262" r="64" stroke="#ff7a1a" stroke-width="8" stroke-dasharray="14 14"/></svg>''',
}


def render_html(cfg, scenes, total):
    lt = cfg["lower_third"]
    els, anim = [], []
    for i, s in enumerate(scenes):
        st, du = s["start"], s["dur"]
        sid = s["id"]
        if s["mood"] == "card":
            cd = s["card"]
            cid = f"{sid}-card"
            a, _, b = cd["title"].partition("|")
            title = "<br/>".join(html.escape(x) for x in a.split("\n")) + f'<span class="hl">{html.escape(b)}</span>'
            els.append(f'''<div id="{cid}" class="card clip" data-start="{st}" data-duration="{du}">
        <div class="num">{cd["num"]}</div><div class="title">{title}</div>
        <div class="sub">{html.escape(cd["sub"])}</div><div class="art">{ART[cd["art"]]}</div></div>''')
            anim.append(f'tl.fromTo("#{cid} .num",{{y:60,opacity:0}},{{y:0,opacity:1,duration:0.22,ease:"power3.out"}},{st});')
            anim.append(f'tl.fromTo("#{cid} .title",{{y:40,opacity:0}},{{y:0,opacity:1,duration:0.22,ease:"power3.out"}},{st+0.06});')
            anim.append(f'tl.fromTo("#{cid} .hl",{{color:"#f4f1ec"}},{{color:"#ff7a1a",duration:0.08,ease:"none"}},{s["kw_time"]});')
            anim.append(f'tl.fromTo("#{cid} .sub",{{opacity:0}},{{opacity:1,duration:0.2}},{st+0.25});')
            anim.append(f'tl.fromTo("#{cid} .draw",{{scaleX:0,transformOrigin:"left center"}},{{scaleX:1,duration:0.35,stagger:0.08,ease:"power2.out"}},{st+0.2});')
            anim.append(f'tl.fromTo("#{cid} .stroke",{{strokeDasharray:1600,strokeDashoffset:1600}},{{strokeDashoffset:0,duration:0.6,stagger:0.12,ease:"power2.inOut"}},{st+0.2});')
        elif s["mood"] == "negative":
            els.append(f'''<div id="{sid}-neg" class="neg clip" data-start="{st}" data-duration="{du}">
        <div class="lead">{html.escape(s["lead"])}</div>
        <div class="neon">{kw_html(s["kw"]).replace("<em>", "").replace("</em>", "")}</div></div>''')
            anim.append(f'tl.fromTo("#{sid}-neg .lead",{{y:24,opacity:0}},{{y:0,opacity:1,duration:0.18,ease:"power3.out"}},{st});')
            anim.append(f'tl.fromTo("#{sid}-neg .neon",{{opacity:0,scale:1.08}},{{opacity:1,scale:1,duration:0.06,ease:"none"}},{s["kw_time"]});')
            anim.append(f'tl.to("#{sid}-neg .neon",{{opacity:0.35,duration:0.04,yoyo:true,repeat:3,ease:"none"}},{s["kw_time"]+0.08});')
        else:
            els.append(f'''<div id="{sid}-cap" class="cap clip" data-start="{st}" data-duration="{du}">
        <div class="lead">{html.escape(s["lead"])}</div>
        <div class="kw">{kw_html(s["kw"])}</div></div>''')
            anim.append(f'tl.fromTo("#{sid}-cap .lead",{{y:24,opacity:0}},{{y:0,opacity:1,duration:0.18,ease:"power3.out"}},{st});')
            anim.append(f'tl.fromTo("#{sid}-cap .kw",{{scale:1.3,opacity:0}},{{scale:1,opacity:1,duration:0.16,ease:"power4.out"}},{s["kw_time"]});')
        if i > 0 and scenes[i - 1]["mood"] == "negative" and s["mood"] == "color":
            els.append(f'<div id="flash{i}" class="flash clip" data-start="{st}" data-duration="0.25"></div>')
            anim.append(f'tl.fromTo("#flash{i}",{{opacity:0.9}},{{opacity:0,duration:0.25,ease:"power2.out"}},{st});')
        if s.get("lower_third"):
            els.append(f'''<div id="lt" class="clip" data-start="{st}" data-duration="{du}">
        <div class="bar"></div><div><div class="name">{html.escape(lt["name"])}</div>
        <div class="meta">{(html.escape(lt["role"]).upper() + " · ") if lt.get("role") else ""}<b>{html.escape(lt["brand"]).upper()}</b></div></div></div>''')
            anim.append(f'tl.fromTo("#lt",{{x:-80,opacity:0}},{{x:0,opacity:1,duration:0.3,ease:"power3.out"}},{st});')
        if s.get("cta"):
            els.append(f'''<div id="cta" class="clip" data-start="{st}" data-duration="{du}">
        <div class="btn"><svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#0d0f12" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="20" r="1.6"/><circle cx="18" cy="20" r="1.6"/><path d="M2 3h3l2.6 11.5a1.5 1.5 0 0 0 1.5 1.2h8.6a1.5 1.5 0 0 0 1.5-1.1L21 7H6.2"/></svg>
        <span>THÊM VÀO GIỎ HÀNG</span></div>
        <svg class="arrow" width="90" height="120" viewBox="0 0 90 120" fill="none" stroke="#ff7a1a" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"><path d="M45 10 V100 M12 68 L45 102 L78 68"/></svg></div>''')
            anim.append(f'tl.fromTo("#cta .btn",{{scale:0.6,opacity:0}},{{scale:1,opacity:1,duration:0.25,ease:"back.out(2)"}},{st});')
            anim.append(f'tl.to("#cta .btn",{{scale:1.06,duration:0.22,yoyo:true,repeat:{int((du-0.3)/0.44)},ease:"sine.inOut"}},{st+0.3});')
            anim.append(f'tl.fromTo("#cta .arrow",{{y:-20,opacity:0}},{{y:0,opacity:1,duration:0.2}},{st+0.15});')
            anim.append(f'tl.to("#cta .arrow",{{y:18,duration:0.25,yoyo:true,repeat:{int((du-0.4)/0.5)},ease:"sine.inOut"}},{st+0.4});')

    font_faces = "\n".join(
        f'@font-face {{ font-family:"BC"; font-weight:{w}; src:url(assets/fonts/barlow-condensed-{sub}-{w}-normal.woff2) format("woff2"); unicode-range:{rng}; }}'
        for w in (500, 700, 800)
        for sub, rng in (("vietnamese", "U+0102-0103,U+0110-0111,U+0128-0129,U+0168-0169,U+01A0-01A1,U+01AF-01B0,U+0300-0301,U+0303-0304,U+0308-0309,U+0323,U+0329,U+1EA0-1EF9,U+20AB"),
                         ("latin", "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+2122,U+2212")))
    body = "\n      ".join(els)
    js = "\n      ".join(anim)
    return f'''<!doctype html>
<html lang="vi" data-resolution="portrait">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1080, height=1920" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
    <style>
      {font_faces}
      :root {{ --ground:#0d0f12; --ink:#f4f1ec; --muted:#c9c4bc; --accent:#ff7a1a; }}
      * {{ margin:0; padding:0; box-sizing:border-box; }}
      html, body {{ width:1080px; height:1920px; overflow:hidden; background:var(--ground); }}
      #root {{ position:relative; width:100%; height:100%; font-family:"BC",sans-serif; color:var(--ink); }}
      #root > .clip {{ position:absolute; }}
      #bg {{ inset:0; width:1080px; height:1920px; object-fit:cover; }}
      #shade {{ inset:0; background:linear-gradient(rgba(13,15,18,0.55) 0%, transparent 20%, transparent 36%, rgba(13,15,18,0.78) 54%, rgba(13,15,18,0.9) 72%, rgba(13,15,18,0.7) 100%); }}
      .cap {{ left:64px; width:860px; top:1130px; }}
      .cap .lead {{ font-weight:500; font-size:46px; color:var(--muted); }}
      .cap .kw {{ font-weight:800; font-size:150px; line-height:0.95; margin-top:6px; transform-origin:left bottom; }}
      .kw em {{ font-style:normal; color:var(--accent); }}
      .neg {{ left:0; right:0; top:700px; text-align:center; }}
      .neg .lead {{ font-weight:500; font-size:48px; color:#e4e0da; }}
      .neg .neon {{ font-weight:800; font-size:190px; line-height:0.92; margin:56px 60px 0; color:#fff4ea;
        text-shadow:0 0 6px #fff, 0 0 18px var(--accent), 0 0 42px var(--accent), 0 0 90px var(--accent); }}
      .flash {{ inset:0; background:#fff; }}
      #lt {{ left:64px; top:180px; display:flex; gap:20px; }}
      #lt .bar {{ width:10px; background:var(--accent); }}
      #lt .name {{ font-weight:800; font-size:68px; line-height:1; text-transform:uppercase; }}
      #lt .meta {{ font-weight:500; font-size:32px; color:var(--muted); margin-top:8px; letter-spacing:0.04em; }}
      #lt .meta b {{ color:var(--accent); font-weight:700; }}
      .card {{ inset:0; background:var(--ground); }}
      .card .num {{ position:absolute; left:64px; top:200px; font-weight:800; font-size:260px; line-height:1; color:var(--accent); }}
      .card .hl {{ display:block; }}
      .card .title {{ position:absolute; left:64px; right:120px; top:500px; font-weight:800; font-size:128px; line-height:0.95; text-transform:uppercase; }}
      .card .sub {{ position:absolute; left:64px; right:120px; top:770px; font-weight:500; font-size:46px; color:var(--muted); }}
      .card .art {{ position:absolute; left:140px; top:960px; }}
      #cta {{ left:64px; top:1420px; width:860px; }}
      #cta .btn {{ display:inline-flex; align-items:center; gap:22px; background:var(--accent); color:#0d0f12;
        padding:26px 44px; border-radius:999px; font-weight:800; font-size:62px; letter-spacing:0.02em; transform-origin:left center; }}
      #cta .arrow {{ display:block; margin:18px 0 0 60px; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{total}" data-width="1080" data-height="1920">
      <video id="bg" class="clip" src="bg.mp4" muted playsinline data-start="0" data-duration="{total}"></video>
      <audio id="mix" class="clip" src="mix.wav" data-start="0" data-duration="{total}"></audio>
      <div id="shade" class="clip" data-start="0" data-duration="{total}"></div>
      {body}
    </div>
    <script>
      const tl = gsap.timeline({{ paused: true }});
      {js}
      window.__timelines["main"] = tl;
      tl.seek(0);
    </script>
  </body>
</html>
'''


if __name__ == "__main__":
    main()
