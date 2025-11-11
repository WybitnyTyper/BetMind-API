import os, time, math, threading, requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

API_KEY = os.getenv("APIFOOTBALL_KEY")
API_BASE = "https://v3.football.api-sports.io"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

matches = {}

def sigmoid(x): return 1/(1+math.exp(-x))

def compute_scores(stats):
    # tryby fallback statystyk
    # (później podłączymy prawdziwe dane xG i momentum)
    shots = stats.get("shots", 4)
    sot = stats.get("sot", 2)
    xg = stats.get("xg", 0.30)
    corners = stats.get("corners", 2)
    minute = stats.get("minute", 60)
    goals = stats.get("goals", 0)

    ghi = sigmoid((shots + (sot*1.5) + (xg*6) + (corners*0.6) + (minute*0.1))/10)*100
    ngi = sigmoid((shots + sot + xg*10 + corners + goals*1.5 + minute*0.15)/10)*100
    return round(ghi,1), round(ngi,1)

def fetch_loop():
    s = requests.Session()
    s.headers.update({"x-apisports-key": API_KEY})
    while True:
        try:
            data = s.get(f"{API_BASE}/fixtures?live=all", timeout=10).json()["response"]
            for m in data:
                fid = str(m["fixture"]["id"])
                minute = m["fixture"]["status"]["elapsed"] or 0
                stats = {"minute": minute}
                ghi, ngi = compute_scores(stats)

                matches[fid] = {
                    "match_id": fid,
                    "home": m["teams"]["home"]["name"],
                    "away": m["teams"]["away"]["name"],
                    "score": f"{m['goals']['home']}-{m['goals']['away']}",
                    "minute": minute,
                    "ghi": ghi,
                    "ngi": ngi,
                }
        except Exception as e:
            print("error:", e)
        time.sleep(10)

@app.get("/live")
def get_live(min_ghi: float = 70, min_ngi: float = 70):
    result = [m for m in matches.values() if (m["ghi"]>=min_ghi or m["ngi"]>=min_ngi)]
    result.sort(key=lambda x: x["ngi"], reverse=True)
    return JSONResponse(result)

@app.get("/")
def root():
    return {"status": "ok", "matches_cached": len(matches)}

threading.Thread(target=fetch_loop, daemon=True).start()
