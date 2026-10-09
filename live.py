#!/usr/bin/env python3
"""YouTube broadcast ဖန်တီး + ffmpeg နဲ့ stream (မနက်/ညနေ ၂ ကြိမ် × ၃ channel title)"""
import os, json, time, subprocess, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

MMT = ZoneInfo("Asia/Yangon")
SESSION = os.environ.get("SESSION", "morning")   # morning | evening | test
TEST = SESSION == "test"

# ---------- ပြင်ရန် ----------
SUFFIXES = ["", " VIP", " VVIP"]                      # live ၃ ခု၏ title နောက်ဆက်တွဲ
SESSIONS = [                                          # မြန်မာအချိန်
    {"name": "morning", "label": "မနက်", "draw": "12:01 PM", "start": "10:30", "end": "12:30"},
    {"name": "evening", "label": "ညနေ", "draw": "04:30 PM", "start": "14:30", "end": "17:00"},
]
DESCRIPTION = open(os.path.join(os.path.dirname(__file__), "description.txt"), encoding="utf-8").read().strip()
# -----------------------------

AUDIO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio")
AUDIO_FILTER = "aresample=44100:async=1,aformat=sample_rates=44100:channel_layouts=stereo,volume=0.6"   # volume ပြင်ရန်

SILENT = ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

def audio_ok(path):
    """ဖိုင်က တကယ်ဖွင့်လို့ရတဲ့ audio ဟုတ်မဟုတ် ffprobe နဲ့စစ်၊ မကောင်းရင် ကျော်"""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "format=duration", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30)
        dur = float(r.stdout.strip().split("\n")[0])
        if r.returncode == 0 and dur > 1:
            return True
    except Exception:
        pass
    print("skip bad audio:", os.path.basename(path), flush=True)
    return False

def audio_input():
    """audio/ folder ထဲက သီချင်းတွေကို ရောနှောပြီး အဆုံးမရှိ ပြန်ဖွင့်။ မရှိရင် အသံတိတ်။"""
    import glob, random
    files = [f for ext in ("mp3", "m4a", "wav", "ogg", "flac") for f in glob.glob(os.path.join(AUDIO_DIR, "*." + ext))]
    if not files:
        print("audio/ ထဲမှာ ဖိုင်မရှိ -> အသံတိတ်", flush=True)
        return ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    files = [f for f in files if audio_ok(f)]
    if not files:
        print("audio ဖိုင်အားလုံး မသုံးနိုင် -> အသံတိတ်", flush=True)
        return SILENT
    random.shuffle(files)
    with open("/tmp/playlist.txt", "w", encoding="utf-8") as f:
        for _ in range(max(1, 400 // len(files))):          # ပုံတူရေးထပ် = ပြန်ဖွင့် (stream_loop မသုံး)
            random.shuffle(files)
            for p in files:
                f.write("file '" + p.replace("'", "'\\''") + "'\n")
    print(f"audio playlist: {len(files)} tracks", flush=True)
    return ["-f", "concat", "-safe", "0", "-i", "/tmp/playlist.txt"]

_tok = {"v": None, "exp": 0}

def token():
    if time.time() < _tok["exp"] - 60:
        return _tok["v"]
    data = urllib.parse.urlencode({
        "client_id": os.environ["YT_CLIENT_ID"],
        "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"],
        "grant_type": "refresh_token"}).encode()
    with urllib.request.urlopen("https://oauth2.googleapis.com/token", data, timeout=30) as r:
        j = json.loads(r.read())
    _tok["v"], _tok["exp"] = j["access_token"], time.time() + j["expires_in"]
    return _tok["v"]

def api(method, path, params=None, body=None, quiet=False):
    url = "https://www.googleapis.com/youtube/v3/" + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + token(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        if not quiet:
            print("API error:", path, e.read().decode()[:500], flush=True)
        raise

def make_title(day, session, suffix):
    d = f"{day.day}.{day.month}.{day.year}"           # 6.10.2026 (သုညမပါ)
    return f"({d}) {session['label']} ({session['draw']}) 2D3D Live တိုက်ရိုက်{suffix}"

def create_broadcast(title):
    start = (datetime.now(timezone.utc) + timedelta(seconds=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    # stream key အသစ် (အလိုအလျောက်)
    st = api("POST", "liveStreams", {"part": "snippet,cdn,contentDetails"}, {
        "snippet": {"title": title},
        "cdn": {"frameRate": "variable", "ingestionType": "rtmp", "resolution": "variable"},
        "contentDetails": {"isReusable": False}})
    # broadcast ID အသစ် (အလိုအလျောက်)
    br = api("POST", "liveBroadcasts", {"part": "snippet,status,contentDetails"}, {
        "snippet": {"title": title, "description": DESCRIPTION, "scheduledStartTime": start},
        "status": {"privacyStatus": "private" if TEST else "public", "selfDeclaredMadeForKids": False},
        "contentDetails": {"enableAutoStart": True, "enableAutoStop": True}})
    api("POST", "liveBroadcasts/bind", {"id": br["id"], "part": "id,contentDetails", "streamId": st["id"]})
    info = st["cdn"]["ingestionInfo"]
    key = info["streamName"]
    print("::add-mask::" + key, flush=True)           # log ထဲ key မပေါ်စေရန်
    print(f"created: {br['id']} | {title}", flush=True)
    return {"id": br["id"], "url": info["ingestionAddress"] + "/" + key}

def complete(bid):
    """live ဖြစ်ခဲ့ရင် complete၊ မစခဲ့ဘူးဆိုရင် (stream မတက်) broadcast ကို ဖျက်"""
    try:
        st = api("GET", "liveBroadcasts", {"part": "status", "id": bid}, quiet=True)
        life = st["items"][0]["status"]["lifeCycleStatus"] if st.get("items") else "gone"
        if life in ("live", "testing"):
            api("POST", "liveBroadcasts/transition", {"broadcastStatus": "complete", "id": bid, "part": "status"}, quiet=True)
            print("completed:", bid, flush=True)
        elif life in ("created", "ready"):
            api("DELETE", "liveBroadcasts", {"id": bid}, quiet=True)
            print("never started -> deleted:", bid, flush=True)
        else:
            print("status", life, ":", bid, flush=True)
    except Exception as e:
        print("complete skipped:", bid, flush=True)

def at(day, hhmm):
    h, m = map(int, hhmm.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=MMT)

def run_session(s, day):
    now = datetime.now(MMT)
    if TEST:
        end = now + timedelta(minutes=5)
    else:
        start, end = at(day, s["start"]), at(day, s["end"])
        if now >= end:
            print("skip", s["label"]); return
        if now < start:
            time.sleep((start - now).total_seconds())
    broadcasts = []
    for suf in SUFFIXES:
        try:
            broadcasts.append(create_broadcast(("TEST " if TEST else "") + make_title(day, s, suf)))
        except Exception as e:
            print("create failed:", e, flush=True)
    if not broadcasts:
        return
    dur = max(60, int((end - datetime.now(MMT)).total_seconds()))
    tee = "|".join(f"[f=flv:onfail=ignore]{b['url']}" for b in broadcasts)   # encode တစ်ခါတည်း၊ output ၃ ခု
    audio = audio_input()
    fails = 0
    while True:
        left = int((end - datetime.now(MMT)).total_seconds())
        if left < 20:
            break
        t0 = time.time()
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "warning",
            "-f", "x11grab", "-draw_mouse", "0", "-framerate", "30", "-video_size", "1280x720", "-i", ":99",
            *audio,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "veryfast", "-b:v", "3000k", "-maxrate", "3000k", "-bufsize", "6000k",
            "-pix_fmt", "yuv420p", "-g", "60", "-af", AUDIO_FILTER, "-c:a", "aac", "-b:a", "128k",
            "-flags", "+global_header", "-t", str(left), "-f", "tee", tee])
        if r.returncode == 0:
            break                                  # အချိန်ပြည့်လို့ ပုံမှန်ပြီး
        fails += 1
        print(f"ffmpeg exited rc={r.returncode} after {int(time.time()-t0)}s (fail #{fails})", flush=True)
        if audio is not SILENT:
            print("-> အသံတိတ်နဲ့ ပြန်ကြိုးစား", flush=True)
            audio = SILENT
        if fails >= 5:
            break
        time.sleep(5)
    for b in broadcasts:
        complete(b["id"])

if __name__ == "__main__":
    day = datetime.now(MMT)
    if TEST:   # test ဆိုရင် လက်ရှိအချိန်နဲ့ကိုက်တဲ့ session ကို ရွေး (13:30 မတိုင်ခင် = မနက်၊ ပြီးရင် ညနေ)
        names = ["morning"] if day.hour * 60 + day.minute < 13 * 60 + 30 else ["evening"]
    else:
        names = [SESSION]
    for s in [x for x in SESSIONS if x["name"] in names]:
        run_session(s, day)
