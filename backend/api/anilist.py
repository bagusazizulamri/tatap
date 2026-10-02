"""Ambil daftar anime per-season dari AniList GraphQL."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import HI_UA
import httpx

ANILIST_URL = "https://graphql.anilist.co"
UA = HI_UA

QUERY = """
query ($season: MediaSeason, $year: Int, $page: Int, $perPage: Int) {
  Page(page: $page, perPage: $perPage) {
    pageInfo { total perPage currentPage lastPage hasNextPage }
    media(season: $season, seasonYear: $year, type: ANIME, sort: POPULARITY_DESC) {
      id
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

def season_page(name, year, page=1, per_page=25):
    """Fetch satu halaman AniList untuk season/year tertentu. Return {pageInfo, media:[]}."""
    try:
        with httpx.Client(timeout=20) as c:
            r = c.post(ANILIST_URL, json={
                "query": QUERY,
                "variables": {"season": name.upper(), "year": year,
                              "page": page, "perPage": per_page}
            }, headers={"Content-Type": "application/json", "User-Agent": UA})
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