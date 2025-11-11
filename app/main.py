import os, time, math, threading, requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from collections import deque

API_BASE   = os.getenv("APIFOOTBALL_BASE", "https://v3.football.api-sports.io")
API_KEY    = os.getenv("APIFOOTBALL_KEY", "")
LEAGUES    = os.getenv("APIFOOTBALL_LEAGUES", "")  # np. "39,140" (opcjonalnie)

app = FastAPI(title="BetMind API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

state = {
    "matches": {},     # mid -> snapshot
    "events": deque(maxlen=500)  # ostatnie zdarzenia do SSE
}

def sigmoid(x): return 1/(1+math.exp(-x))
def z(x, m, s): return 0.0 if s <= 1e-6 else (x-m)/s

# prosta baza ref. dla z-score (fallback)
REF = {
  "shots_10": (4.0,2.0), "sot_10": (2.0,1.5), "xg_10": (0.30,0.20),
  "corners_10": (2.0,1.2), "danger": (8.0,4.0), "press": (0.55,0.18)
}

def GHI(minute, f, odds=None, momentum=0.0):
    x = (
      1.4*z(f["shots_10"], *REF["shots_10"]) +
      2.0*z(f["sot_10"], *REF["sot_10"]) +
      2.4*z(f["xg_10"], *REF["xg_10"]) +
      0.8*z(f["corners_10"], *REF["corners_10"]) +
      1.2*z(f["danger"], *REF["danger"]) +
      0.8*z(f["press"], *REF["press"]) +
      1.0*momentum +
      (0.7 if minute>=70 else 0.3)
    )
    return 100*sigmoid(x/6.0)

def NGI(minute, f, total_goals, odds_next=None, momentum=0.0):
    time_pressure = 1.0 if minute>=80 else 0.7 if minute>=70 else 0.4
    score_pace = min(total_goals*0.15, 0.6)
    x = (
      1.2*z(f["shots_10"], *REF["shots_10"]) +
      1.8*z(f["sot_10"], *REF["sot_10"]) +
      2.2*z(f["xg_10"], *REF["xg_10"]) +
      0.6*z(f["corners_10"], *REF["corners_10"]) +
      1.0*z(f["danger"], *REF["danger"]) +
      0.8*z(f["press"], *REF["press"]) +
      1.0*momentum + 1.5*time_pressure + score_pace
    )
    return 100*sigmoid(x/6.0)

def fetch_live():
    assert API_KEY, "Brak APIFOOTBALL_KEY"
    s = requests.Session()
    s.headers.update({"x-apisports-key": API_KEY})
    while True:
        try:
            params = {"live":"all"}
            if LEAGUES: params["league"] = LEAGUES
            fx = s.get(f"{API_BASE}/fixtures", params=params, timeout=10).json().get("response", [])
            # (opcjonalnie) tu można dociągać /fixtures/statistics dla dokładniejszych cech 10'
            for item in fx:
                fid = item["fixture"]["id"]
                minute = item["fixture"]["status"]["elapsed"] or 0
                league = item["league"]["name"]
                home   = item["teams"]["home"]["name"]
                away   = item["teams"]["away"]["name"]
                goals_h = item["goals"]["home"] or 0
                goals_a = item["goals"]["away"] or 0
                total = goals_h + goals_a

                # fallback “cechy 10’” – przy planie PRO pobierz dokładne z /statistics i policz rolling 10’
                f = {"shots_10":4, "sot_10":2, "xg_10":0.30, "corners_10":1, "danger":8, "press":0.55}
                momentum = 0.0  # można policzyć z historii jeśli przechowujesz bufory

                ghi = GHI(minute, f, momentum=momentum)
                ngi = NGI(minute, f, total, momentum=momentum)

                snap = {
                  "match_id": str(fid),
                  "league": league,
                  "minute": int(minute),
                  "home": home, "away": away,
                  "score": f"{goals_h}-{goals_a}",
                  "odds": {"over_0_5": None, "next_any": None},  # dołożymy jeśli plan zawiera /odds
                  "ghi": round(ghi,1),
                  "ngi": round(ngi,1),
                  "last_update_ts": int(time.time())
                }
                state["matches"][str(fid)] = snap
                state["events"].append(snap)
        except Exception as e:
            state["events"].append({"error": str(e), "ts": int(time.time())})
        time.sleep(10)

@app.get("/live")
def live(min_ghi: float=70, min_ngi: float=70, minute_from: int=60, limit: int=50):
    items = list(state["matches"].values())
    items = [m for m in items if (m["ghi"]>=min_ghi or m["ngi"]>=min_ngi) and m["minute"]>=minute_from]
    items.sort(key=lambda m: m["ngi"], reverse=True)
    return items[:limit]

@app.get("/")
def root():
    return {"ok": True, "matches_cached": len(state["matches"])}

@app.get("/events")
def events():
    def gen():
        last_ts = 0
        while True:
            if state["events"]:
                data = state["events"][-1]
                yield f"data: {data}\n\n"
            time.sleep(2)
    return StreamingResponse(gen(), media_type="text/event-stream")

def _bg():
    t = threading.Thread(target=fetch_live, daemon=True)
    t.start()

_bg()
