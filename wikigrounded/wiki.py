from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from urllib import error, request
from urllib.parse import quote

from .models import WikiEvidence


class WikipediaClient:
    def search_wikipedia(self, query: str) -> list[WikiEvidence]:
        raise NotImplementedError


class FixtureWikipediaClient(WikipediaClient):
    """Small deterministic fixture backend for offline demo and tests."""

    def __init__(self, fixture_path: Path | None = None) -> None:
        self.fixture_path = fixture_path or Path(__file__).with_name("fixtures") / "wiki.json"
        self._pages = json.loads(self.fixture_path.read_text(encoding="utf-8"))

    def search_wikipedia(self, query: str) -> list[WikiEvidence]:
        query_tokens = _tokens(query)
        scored: list[tuple[int, dict[str, object]]] = []
        for page in self._pages:
            haystack_tokens = set(
                _tokens(
                " ".join(
                    [
                        str(page.get("title", "")),
                        str(page.get("extract", "")),
                        " ".join(page.get("keywords", [])),
                    ]
                )
                )
            )
            score = sum(1 for token in query_tokens if token in haystack_tokens)
            if score:
                scored.append((score, page))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [_page_to_evidence(page, score) for score, page in scored[:5]]


class MediaWikiClient(WikipediaClient):
    def __init__(
        self,
        user_agent: str = "WikiGroundedBot/0.1",
        min_request_interval: float | None = None,
        max_retries: int = 5,
    ) -> None:
        self.user_agent = user_agent
        self.min_request_interval = (
            min_request_interval
            if min_request_interval is not None
            else float(os.getenv("WIKIGROUNDED_MEDIAWIKI_DELAY", "1.0"))
        )
        self.max_retries = max_retries
        self._cache: dict[str, dict] = {}
        self._last_request_at = 0.0

    def search_wikipedia(self, query: str) -> list[WikiEvidence]:
        direct = self._direct_title_evidence(query)
        if direct:
            return [direct]

        search = self._get_json(
            "https://en.wikipedia.org/w/api.php"
            f"?action=query&list=search&srsearch={quote(query)}&srlimit=5&format=json"
        )
        page_ids = [
            str(item["pageid"])
            for item in search.get("query", {}).get("search", [])
            if item.get("pageid") is not None
        ]
        if not page_ids:
            return []

        extracts = self._get_json(
            "https://en.wikipedia.org/w/api.php"
            "?action=query&prop=extracts%7Cinfo&exintro=1&explaintext=1"
            "&inprop=url&format=json&pageids="
            + "%7C".join(page_ids[:5])
        )
        pages = extracts.get("query", {}).get("pages", {})
        evidence = [
            WikiEvidence(
                title=str(page.get("title", "")),
                url=str(page.get("fullurl", "")),
                extract=str(page.get("extract", ""))[:1200],
                page_id=int(page_id),
                last_revid=page.get("lastrevid"),
                retrieval_mode="intro",
            )
            for page_id, page in pages.items()
            if page.get("extract")
        ]
        return evidence[:5]

    def _direct_title_evidence(self, query: str) -> WikiEvidence | None:
        if "?" in query or len(query.split()) > 4:
            return None
        data = self._get_json(
            "https://en.wikipedia.org/w/api.php"
            "?action=query&prop=extracts%7Cinfo&exintro=1&explaintext=1"
            f"&inprop=url&format=json&titles={quote(query)}"
        )
        pages = data.get("query", {}).get("pages", {})
        for page_id, page in pages.items():
            if page_id == "-1" or not page.get("extract"):
                continue
            return WikiEvidence(
                title=str(page.get("title", "")),
                url=str(page.get("fullurl", "")),
                extract=str(page.get("extract", ""))[:1200],
                page_id=int(page_id),
                last_revid=page.get("lastrevid"),
                retrieval_mode="intro",
            )
        return None

    def _get_json(self, url: str) -> dict:
        if url in self._cache:
            return self._cache[url]
        req = request.Request(url, headers={"User-Agent": self.user_agent})
        last_error: error.URLError | None = None
        for attempt in range(self.max_retries):
            try:
                self._throttle()
                with request.urlopen(req, timeout=20) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    self._cache[url] = data
                    self._last_request_at = time.monotonic()
                    return data
            except error.HTTPError as exc:
                self._last_request_at = time.monotonic()
                last_error = exc
                if exc.code != 429 or attempt == self.max_retries - 1:
                    break
                retry_after = exc.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 2.0 * (attempt + 1)
                except ValueError:
                    delay = 2.0 * (attempt + 1)
                delay = min(delay, 30.0)
                time.sleep(delay)
            except error.URLError as exc:
                self._last_request_at = time.monotonic()
                last_error = exc
                break
        raise RuntimeError(f"MediaWiki request failed: {last_error}") from last_error

    def _throttle(self) -> None:
        if self.min_request_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.min_request_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)


def _page_to_evidence(page: dict[str, object], score: int) -> WikiEvidence:
    title = str(page["title"])
    return WikiEvidence(
        title=title,
        url=str(page.get("url") or f"https://en.wikipedia.org/wiki/{quote(title)}"),
        extract=str(page.get("extract", "")),
        page_id=int(page["page_id"]) if page.get("page_id") is not None else None,
        last_revid=int(page["last_revid"]) if page.get("last_revid") is not None else None,
        retrieval_mode=str(page.get("retrieval_mode", "intro")),
        score=float(score),
    )


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower())


def _tokens(text: str) -> list[str]:
    stopwords = {
        "a",
        "an",
        "and",
        "did",
        "in",
        "life",
        "late",
        "of",
        "the",
        "which",
    }
    return [token for token in _normalize(text).split() if token not in stopwords]
