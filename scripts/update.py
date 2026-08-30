import json, os, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path

DUMP_URLS = [
    "https://github.com/SkipDB-TV/skipdb/releases/latest/download/skipdb-dump.json",
    "https://api.skipdb.tv/api/dump",
]
TMDB_API = "https://api.themoviedb.org/3"
TOKEN = os.environ["TMDB_TOKEN"]
MOVIE, TV, CACHE = Path("movie"), Path("tv"), Path(".cache/tmdb.json")
MOVIE.mkdir(exist_ok=True); TV.mkdir(exist_ok=True); CACHE.parent.mkdir(exist_ok=True)

def request_json(url, headers=None, retries=4):
    h = {"User-Agent":"skip-timestamps-db/1.1","Accept":"application/json"}
    if headers: h.update(headers)
    for n in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=90) as r:
                return json.load(r)
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            if n == retries-1: raise
            time.sleep(2 ** n)

def load_cache():
    try: return json.loads(CACHE.read_text()) if CACHE.exists() else {}
    except Exception: return {}

cache = load_cache()

def tmdb_find(imdb):
    if imdb in cache and cache[imdb] is not None:
        return cache[imdb]
    q = urllib.parse.quote(imdb)
    data = request_json(
        f"{TMDB_API}/find/{q}?external_source=imdb_id",
        {"Authorization": f"Bearer {TOKEN}"}
    )
    result = None
    # SkipDB dump explicitly tells us movie vs series; caller will select matching result.
    cache[imdb] = {
        "movie": data.get("movie_results", []),
        "tv": data.get("tv_results", [])
    }
    time.sleep(0.03)
    return cache[imdb]

dump = None
last_error = None
for dump_url in DUMP_URLS:
    try:
        print(f"Downloading SkipDB dump: {dump_url}")
        dump = request_json(dump_url)
        print("Download OK")
        break
    except Exception as e:
        last_error = e
        print(f"Dump source failed: {e}")

if dump is None:
    raise RuntimeError(f"All SkipDB dump sources failed: {last_error}")

segments = dump.get("segments")
if not isinstance(segments, list):
    raise RuntimeError("Unexpected SkipDB dump schema: missing segments[]")

groups = {}
for r in segments:
    if r.get("status") not in (None, "approved"):
        continue
    imdb = r.get("imdb_id")
    if imdb:
        groups.setdefault(imdb, []).append(r)

movies, shows = {}, {}

for i, (imdb, rows) in enumerate(groups.items(), 1):
    media = rows[0].get("media_type")
    try:
        found = tmdb_find(imdb)
    except Exception as e:
        print("TMDb lookup failed:", imdb, e)
        continue

    if media == "movie":
        results = found.get("movie", [])
        if not results: continue
        tid = results[0]["id"]
        obj = {"tmdb_id":tid,"imdb_id":imdb,"type":"movie","segments":{}}
        for r in rows:
            typ = r.get("segment_type")
            if typ in ("intro","recap","outro","preview"):
                obj["segments"][typ] = {
                    "start": r.get("start_ms"),
                    "end": r.get("end_ms"),
                    "duration": r.get("duration_ms"),
                    "score": r.get("score", 0)
                }
        movies[str(tid)] = obj

    elif media in ("series", "tv"):
        results = found.get("tv", [])
        if not results: continue
        tid = results[0]["id"]
        obj = shows.setdefault(str(tid), {
            "tmdb_id":tid,"imdb_id":imdb,"type":"tv","seasons":{}
        })
        for r in rows:
            s, e, typ = r.get("season"), r.get("episode"), r.get("segment_type")
            if s is None or e is None or typ not in ("intro","recap","outro","preview"):
                continue
            ep = obj["seasons"].setdefault(str(s), {}).setdefault(str(e), {})
            candidate = {
                "start": r.get("start_ms"),
                "end": r.get("end_ms"),
                "duration": r.get("duration_ms"),
                "score": r.get("score", 0)
            }
            # Dump can contain multiple approved submissions; keep best score.
            if typ not in ep or candidate["score"] > ep[typ].get("score", 0):
                ep[typ] = candidate

    if i % 250 == 0:
        print(f"{i}/{len(groups)} titles processed")

def write_dir(folder, data):
    wanted = set()
    for tid, obj in data.items():
        p = folder/f"{tid}.json"; wanted.add(p.name)
        p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",",":")))
    for p in folder.glob("*.json"):
        if p.name not in wanted: p.unlink()

write_dir(MOVIE, movies)
write_dir(TV, shows)
CACHE.write_text(json.dumps(cache, separators=(",",":")))
print(f"Done: {len(movies)} movies, {len(shows)} TV shows; SkipDB generated_at={dump.get('generated_at')}")
