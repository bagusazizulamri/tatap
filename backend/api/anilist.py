"""Ambil daftar anime per-season dari AniList GraphQL."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import HI_UA
import httpx

ANILIST_URL = "https://graphql.anilist.co"
UA = HI_UA

QUERY = """
query ($season: MediaSeason, $year: Int, $page: Int, $perPage: Int, $statusIn: [MediaStatus]) {
  Page(page: $page, perPage: $perPage) {
    pageInfo { total perPage currentPage lastPage hasNextPage }
    media(season: $season, seasonYear: $year, status_in: $statusIn, type: ANIME, sort: POPULARITY_DESC) {
      id
      status
      title { romaji english }
      format
      episodes
      duration
      averageScore
      season
      seasonYear
      coverImage { large medium }
      siteUrl
    }
  }
}
"""

def current_season():
    """Return (year, season_name) untuk bulan hari ini."""
    import datetime as _dt
    m = _dt.date.today().month
    name = "winter" if m in (1,2,3) else "spring" if m in (4,5,6) \
          else "summer" if m in (7,8,9) else "fall"
    return _dt.date.today().year, name

def prev_season(name, year):
    order = ["winter", "spring", "summer", "fall"]
    idx = order.index(name)
    if idx == 0:
        return year - 1, "fall"
    return year, order[idx - 1]

_al_client = None

def _get_al_client():
    global _al_client
    if _al_client is None:
        limits = httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=60.0)
        _al_client = httpx.Client(
            timeout=httpx.Timeout(12.0, connect=5.0),
            limits=limits,
            headers={"Content-Type": "application/json", "User-Agent": UA}
        )
    return _al_client

def season_page(name, year, page=1, per_page=25, status_in=None):
    """Fetch satu halaman AniList untuk season/year tertentu. Return {pageInfo, media:[]}."""
    try:
        c = _get_al_client()
        variables = {
            "season": name.upper(),
            "year": year,
            "page": page,
            "perPage": per_page
        }
        if status_in:
            variables["statusIn"] = status_in
        r = c.post(ANILIST_URL, json={
            "query": QUERY,
            "variables": variables
        })
        if r.status_code != 200:
            return {"pageInfo": {"total": 0, "perPage": per_page, "currentPage": page,
                                 "lastPage": 1, "hasNextPage": False}, "media": []}
        d = r.json().get("data", {}).get("Page", {})
        d.setdefault("pageInfo", {})
        d.setdefault("media", [])
        # AniList PageInfo untuk season-filter sering over-report (total=5000, lastPage=200).
        # Batas hanya didasarkan pada item terisi — kalau page ini < per_page, tidak ada next.
        items = d.get("media") or []
        pi = d.get("pageInfo") or {}
        pi["hasNextPage"] = bool(pi.get("hasNextPage")) and len(items) >= per_page
        pi["lastPage"] = max(1, pi.get("currentPage") or page)
        pi["perPage"] = per_page
        d["pageInfo"] = pi
        return d
    except Exception:
        return {"pageInfo": {"total": 0, "perPage": per_page, "currentPage": page,
                             "lastPage": 1, "hasNextPage": False}, "media": []}


SCHEDULE_QUERY = """
query ($now: Int, $end: Int, $perPage: Int) {
  Page(perPage: $perPage) {
    airingSchedules(airingAt_greater: $now, airingAt_lesser: $end, sort: TIME) {
      id airingAt episode
      media {
        id title { romaji english }
        season seasonYear format
        coverImage { large medium }
      }
    }
  }
}
"""



def anilist_schedules(now_ts, end_ts, per_page=50):
    """Episode yang tayang antara now_ts..end_ts (unix detik). Return list schedule.
    Longgar: anime apapun, tidak difilter by season. Caller yang filter matched."""
    try:
        with httpx.Client(timeout=20) as c:
            r = c.post(ANILIST_URL, json={
                "query": SCHEDULE_QUERY,
                "variables": {"now": now_ts, "end": end_ts, "perPage": per_page}
            }, headers={"Content-Type": "application/json", "User-Agent": UA})
            if r.status_code != 200:
                return []
            return r.json().get("data", {}).get("Page", {}).get("airingSchedules", []) or []
    except Exception:
        return []
