#!/usr/bin/env python3
"""
fetch_candidates.py  (v2 - crash-safe, resumable)
-------------------------------------------------
Pulls candidate videos from the OFFICIAL YouTube Data API v3 for each concept.
No scraping. Every result is a real video ID from Google's endpoint.

KEY IMPROVEMENTS over v1:
  * Saves after EVERY concept - an interrupt or quota-stop never loses work.
  * RESUMES automatically - skips concepts already in the output file.
  * Correctly detects quota/rate-limit errors and stops cleanly.
  * --start / --end let you batch across days within the 100-search daily cap.

Usage:
    export YOUTUBE_API_KEY="your_key_here"

    # Day 1: first 90 concepts (stays safely under the 100/day cap)
    python3 fetch_candidates.py --concepts concepts_sphere1.json \
        --out candidates_sphere1.json --end 90

    # Day 2+: just re-run; it auto-resumes from where it stopped
    python3 fetch_candidates.py --concepts concepts_sphere1.json \
        --out candidates_sphere1.json
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    build = None
    HttpError = Exception


DEFAULT_PARAMS = {
    "regionCode": "IN",
    "relevanceLanguage": "hi",
    "videoDuration": "short",
    "safeSearch": "strict",
    "type": "video",
    "videoEmbeddable": "true",
    "maxResults": 10,
    "order": "relevance",
}

TRUSTED_CHANNEL_HINTS = {
    "chuchu tv", "infobells", "jugnu kids", "kiddiestv", "t-series kids",
    "videogyan", "appu series", "cvs 3d", "kids channel india",
}

STORY_KEYWORDS = {"story", "tale", "panchatantra", "jataka", "kahani",
                  "birbal", "tenali", "folk", "hanuman", "krishna"}


def iso_now():
    return datetime.now(timezone.utc).isoformat()


def build_query(concept):
    base = concept.get("query") or concept.get("concept") or concept.get("title", "")
    if not any(w in base.lower() for w in ("kids", "toddler", "baby", "rhyme")):
        base = f"{base} kids toddler"
    return base.strip()


def is_story(concept):
    text = (concept.get("concept", "") + " " +
            concept.get("title", "") + " " +
            concept.get("query", "")).lower()
    return any(k in text for k in STORY_KEYWORDS)


def channel_is_trusted(channel_title):
    ct = (channel_title or "").lower()
    return any(hint in ct for hint in TRUSTED_CHANNEL_HINTS)


def is_quota_error(err):
    """YouTube signals quota exhaustion in several wordings. Catch them all."""
    s = str(err).lower()
    status = getattr(getattr(err, "resp", None), "status", None)
    return status == 429 or "quota" in s or "ratelimitexceeded" in s \
        or "dailylimitexceeded" in s


def search_one(youtube, concept, params):
    q = build_query(concept)
    p = dict(params)
    p["q"] = q
    if is_story(concept):
        p["videoDuration"] = "medium"
    response = youtube.search().list(part="snippet", **p).execute()
    candidates = []
    for item in response.get("items", []):
        vid = item["id"]["videoId"]
        sn = item["snippet"]
        candidates.append({
            "video_id": vid,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "embed_url": f"https://www.youtube.com/embed/{vid}",
            "title": sn.get("title", ""),
            "channel_title": sn.get("channelTitle", ""),
            "channel_id": sn.get("channelId", ""),
            "published_at": sn.get("publishedAt", ""),
            "description_snippet": (sn.get("description", "") or "")[:200],
            "thumbnail": sn.get("thumbnails", {}).get("high", {}).get("url", ""),
            "trusted_channel": channel_is_trusted(sn.get("channelTitle", "")),
            "safety_review_status": "pending",
            "reviewer_notes": "",
            "pacing_flag": "",
        })
    return q, candidates


def enrich_stats(youtube, candidates):
    ids = [c["video_id"] for c in candidates]
    if not ids:
        return
    by_id = {c["video_id"]: c for c in candidates}
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        resp = youtube.videos().list(
            part="statistics,contentDetails,status",
            id=",".join(chunk),
        ).execute()
        for item in resp.get("items", []):
            c = by_id.get(item["id"])
            if not c:
                continue
            stats = item.get("statistics", {})
            content = item.get("contentDetails", {})
            status = item.get("status", {})
            c["view_count"] = int(stats.get("viewCount", 0)) if stats.get("viewCount") else None
            c["like_count"] = int(stats.get("likeCount", 0)) if stats.get("likeCount") else None
            c["duration_iso"] = content.get("duration", "")
            c["made_for_kids"] = status.get("madeForKids")
            c["embeddable"] = status.get("embeddable")


def load_existing(path):
    if not os.path.exists(path):
        return None, set()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        done = {c.get("concept_id") for c in data.get("concepts", [])}
        return data, done
    except (json.JSONDecodeError, OSError):
        return None, set()


def save(results, path):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--concepts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--per-concept", type=int, default=10)
    ap.add_argument("--duration", default=None,
                    choices=["short", "medium", "long", "any"])
    ap.add_argument("--sleep", type=float, default=0.2)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--start", type=int, default=None)
    ap.add_argument("--end", type=int, default=None)
    ap.add_argument("--max-searches", type=int, default=95,
                    help="hard stop after this many searches this run "
                         "(default 95, safely under the 100/day free cap)")
    args = ap.parse_args()

    with open(args.concepts, encoding="utf-8") as f:
        concepts = json.load(f)

    if args.start is not None:
        concepts = [c for c in concepts if c.get("id", 0) >= args.start]
    if args.end is not None:
        concepts = [c for c in concepts if c.get("id", 0) <= args.end]

    params = dict(DEFAULT_PARAMS)
    params["maxResults"] = args.per_concept
    if args.duration:
        params["videoDuration"] = args.duration

    if args.dry_run:
        print(f"[dry-run] {len(concepts)} concepts in range. Sample:\n")
        for c in concepts[:15]:
            print(f"  #{c.get('id','?'):>4}  {build_query(c)}")
        return

    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        sys.exit("ERROR: set YOUTUBE_API_KEY env var.")
    if build is None:
        sys.exit("ERROR: pip install google-api-python-client")

    youtube = build("youtube", "v3", developerKey=api_key, cache_discovery=False)

    results, done_ids = load_existing(args.out)
    if results is None:
        results = {
            "generated_at": iso_now(),
            "sphere": concepts[0].get("sphere", "unknown") if concepts else "unknown",
            "note": "All video_ids from official YouTube Data API v3. "
                    "Every candidate is 'pending' until you human-review it.",
            "concepts": [],
        }
    todo = [c for c in concepts if c.get("id") not in done_ids]
    if done_ids:
        print(f"Resuming: {len(done_ids)} done, {len(todo)} remaining in range.\n")

    searches = 0
    stopped_reason = "completed range"
    for concept in todo:
        if searches >= args.max_searches:
            stopped_reason = f"hit --max-searches ({args.max_searches})"
            break
        try:
            query, candidates = search_one(youtube, concept, params)
            searches += 1
            enrich_stats(youtube, candidates)
            results["concepts"].append({
                "concept_id": concept.get("id"),
                "concept": concept.get("concept") or concept.get("title"),
                "age_band": concept.get("age_band", ""),
                "query_used": query,
                "candidate_count": len(candidates),
                "candidates": candidates,
            })
            save(results, args.out)
            trusted = sum(1 for c in candidates if c["trusted_channel"])
            print(f"[{concept.get('id')}] {query[:42]:<42} "
                  f"-> {len(candidates)} ({trusted} trusted)  [saved]")
        except HttpError as e:
            if is_quota_error(e):
                stopped_reason = "QUOTA EXHAUSTED - resets ~12:30 PM IST"
                print(f"\n{stopped_reason}. Progress saved. "
                      f"Re-run the same command tomorrow to continue.",
                      file=sys.stderr)
                break
            print(f"[{concept.get('id')}] non-quota error: {e}", file=sys.stderr)
        time.sleep(args.sleep)

    results["last_run"] = iso_now()
    results["total_concepts_done"] = len(results["concepts"])
    save(results, args.out)

    print(f"\nStopped: {stopped_reason}")
    print(f"Searches this run: {searches} (~{searches*100 + searches} quota units)")
    print(f"Total concepts in {args.out}: {len(results['concepts'])}")
    remaining = len(concepts) - len([c for c in results['concepts']
                                     if args.start is None or c['concept_id'] >= (args.start or 0)])
    print("Re-run the same command to continue where it stopped.")


if __name__ == "__main__":
    main()
