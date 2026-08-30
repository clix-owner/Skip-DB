import json
import os
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

# Try the official daily release dump first, then the API fallback.
DUMP_URLS = [
    "https://github.com/SkipDB-TV/skipdb/releases/latest/download/skipdb-dump.json",
    "https://api.skipdb.tv/api/dump",
]

TMDB_API = "https://api.themoviedb.org/3"
TMDB_TOKEN = os.environ["TMDB_TOKEN"]

OUTPUT = Path("Skip-DB.json")
CACHE_FILE = Path(".cache/tmdb.json")
CACHE_FILE.parent.mkdir(exist_ok=True)

def request_json(url, headers=None, retries=4):
    base_headers = {
        "User-Agent": "Skip-DB-builder/2.0",
        "Accept": "application/json",
    }
    if headers:
        base_headers.update(headers)

    last_error = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=base_headers)
            with urllib.request.urlopen(req, timeout=90) as response:
                return json.load(response)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(2 ** attempt)
    raise last_error

def load_cache():
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_cache(cache):
    CACHE_FILE.write_text(
        json.dumps(cache, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

cache = load_cache()

def tmdb_find(imdb_id):
    cached = cache.get(imdb_id)
    if cached is not None:
        return cached

    encoded = urllib.parse.quote(imdb_id)
    data = request_json(
        f"{TMDB_API}/find/{encoded}?external_source=imdb_id",
        {
            "Authorization": f"Bearer {TMDB_TOKEN}",
            "Accept": "application/json",
        },
    )

    result = {
        "movie": data.get("movie_results", []),
        "tv": data.get("tv_results", []),
    }
    cache[imdb_id] = result
    time.sleep(0.03)
    return result

# Download dump.
dump = None
last_error = None
for url in DUMP_URLS:
    try:
        print(f"Downloading: {url}", flush=True)
        dump = request_json(url)
        print("Download OK", flush=True)
        break
    except Exception as exc:
        last_error = exc
        print(f"Source failed: {exc}", flush=True)

if dump is None:
    raise RuntimeError(f"Could not download SkipDB dump: {last_error}")

segments = dump.get("segments")
if not isinstance(segments, list):
    raise RuntimeError("Unexpected SkipDB dump: segments[] not found")

print(f"Segments: {len(segments)}", flush=True)

# Group by IMDb title.
groups = {}
for row in segments:
    if row.get("status") not in (None, "approved"):
        continue
    imdb_id = row.get("imdb_id")
    if imdb_id:
        groups.setdefault(imdb_id, []).append(row)

print(f"IMDb titles: {len(groups)}", flush=True)

movies = {}
shows = {}

def clean_segment(row):
    item = {
        "start": row.get("start_ms"),
        "end": row.get("end_ms"),
    }
    duration = row.get("duration_ms")
    if duration is not None:
        item["duration"] = duration
    score = row.get("score")
    if score is not None:
        item["score"] = score
    return item

def score_of(item):
    value = item.get("score", 0)
    return value if isinstance(value, (int, float)) else 0

for index, (imdb_id, rows) in enumerate(groups.items(), 1):
    media_type = rows[0].get("media_type")

    try:
        found = tmdb_find(imdb_id)
    except Exception as exc:
        print(f"TMDb failed {imdb_id}: {exc}", flush=True)
        continue

    if media_type == "movie":
        results = found.get("movie") or []
        if not results:
            continue

        tmdb_id = str(results[0]["id"])
        entry = {
            "imdb_id": imdb_id,
            "segments": {},
        }

        for row in rows:
            kind = row.get("segment_type")
            if not kind:
                continue
            candidate = clean_segment(row)
            old = entry["segments"].get(kind)
            if old is None or score_of(candidate) >= score_of(old):
                entry["segments"][kind] = candidate

        if entry["segments"]:
            movies[tmdb_id] = entry

    elif media_type in ("series", "tv"):
        results = found.get("tv") or []
        if not results:
            continue

        tmdb_id = str(results[0]["id"])
        entry = shows.setdefault(
            tmdb_id,
            {
                "imdb_id": imdb_id,
                "seasons": {},
            },
        )

        for row in rows:
            season = row.get("season")
            episode = row.get("episode")
            kind = row.get("segment_type")

            if season is None or episode is None or not kind:
                continue

            ep = (
                entry["seasons"]
                .setdefault(str(season), {})
                .setdefault(str(episode), {})
            )

            candidate = clean_segment(row)
            old = ep.get(kind)
            if old is None or score_of(candidate) >= score_of(old):
                ep[kind] = candidate

    if index % 100 == 0:
        print(f"Processed {index}/{len(groups)} titles", flush=True)
        save_cache(cache)

# Sort numeric TMDb IDs, seasons and episodes for stable, tidy output.
def numeric_key(value):
    try:
        return (0, int(value))
    except Exception:
        return (1, str(value))

movies = dict(sorted(movies.items(), key=lambda x: numeric_key(x[0])))
shows = dict(sorted(shows.items(), key=lambda x: numeric_key(x[0])))

for show in shows.values():
    show["seasons"] = dict(
        sorted(show["seasons"].items(), key=lambda x: numeric_key(x[0]))
    )
    for season_no, episodes in list(show["seasons"].items()):
        show["seasons"][season_no] = dict(
            sorted(episodes.items(), key=lambda x: numeric_key(x[0]))
        )

database = {
    "meta": {
        "format": 1,
        "source": "SkipDB",
        "generated_at": dump.get("generated_at"),
        "timestamp_unit": "milliseconds",
        "movie_count": len(movies),
        "tv_count": len(shows),
    },
    "movies": movies,
    "tv": shows,
}

# Pretty JSON, one single database file.
OUTPUT.write_text(
    json.dumps(database, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

save_cache(cache)

print(f"Created {OUTPUT}", flush=True)
print(f"Movies: {len(movies)} | TV: {len(shows)}", flush=True)
