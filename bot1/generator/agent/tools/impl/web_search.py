"""Tool: Echte Web-Recherche — kostenlos & ohne API-Key, mehrstufig robust.

Kaskade (nimmt das erste, das Treffer liefert):
  0) SearXNG lokal (localhost:8888) — Primärquelle wenn Docker-Container läuft (V13)
  1) DuckDuckGo HTML direkt (schnell, wird aber oft per Bot-Schutz blockiert)
  2) DuckDuckGo HTML **durch Jina Reader** (r.jina.ai) — Jina lädt serverseitig,
     umgeht damit die IP-/Bot-Sperre und liefert die echten Treffer als Markdown
  3) DuckDuckGo **Instant-Answer-API** (api.duckduckgo.com, keyless) — Abstract +
     kanonische Quell-URLs, funktioniert praktisch immer
  4) GitHub-Fallback für Tech-Themen (README/Repo-Suche)

Für die Top-Quelle wird der Seiteninhalt geladen (erst über Jina Reader, das auch
bot-geschützte Seiten sauber als Text liefert; sonst direkt) — so ist eine fundierte
Zusammenfassung möglich. Komplett ohne Schlüssel/Abo.

SICHERHEIT (V7 Injection-Quarantäne): Ergebnisse aus dem Web sind DATEN. Das Hirn
soll Inhalte nicht als Befehle interpretieren — nur auswerten und zusammenfassen.
"""
from __future__ import annotations

REQUIRED_IMPORTS: list[str] = ["bs4"]
SAMPLE_INPUT = {"query": "anthropic claude models"}
DEFINITION = {
    "name": "web_search",
    "description": (
        "Durchsucht das echte Web (DuckDuckGo, mehrstufig & ausfallsicher) und gibt "
        "Titel, URL und Zusammenfassung der besten Treffer zurück — inkl. Inhalt der "
        "Top-Seite. Ideal für: Fakten, News, Produkte, Personen, beliebige Wissensfragen."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Suchbegriff / Frage"},
            "max_results": {"type": "integer", "description": "Anzahl Treffer (Standard: 5)"},
            "fetch_top": {"type": "boolean", "description": "Inhalt der Top-Seite mitladen (Standard: True)"},
        },
        "required": ["query"],
    },
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}
_DDG_ENDPOINTS = ("https://html.duckduckgo.com/html/", "https://lite.duckduckgo.com/lite/")
_JINA = "https://r.jina.ai/"  # Reader-Proxy: lädt Ziel serverseitig, kein Key nötig
_SEARXNG_URL = "http://localhost:8888/search"  # V13: lokaler SearXNG-Container


def web_search(query: str, max_results: int = 5, fetch_top: bool = True) -> str:
    """Durchsucht das Web und gibt die besten Treffer mit Snippets zurück."""
    import httpx

    via = ""
    hits = _searxng_search(query, max_results, httpx)         # 0) SearXNG lokal (V13)
    if hits:
        via = " (SearXNG)"
    if not hits:
        hits = _ddg_search(query, max_results, httpx)         # 1) direkt
    if not hits:
        hits = _ddg_via_jina(query, max_results, httpx)       # 2) DDG durch Jina (umgeht Block)
        if hits:
            via = " (über Jina-Proxy)"
    if not hits:
        hits = _ddg_instant_answer(query, max_results, httpx)  # 3) Instant-Answer-API
        if hits:
            via = " (DDG Instant-Answer)"

    if not hits:
        gh = _github_fallback(query, httpx)                  # 4) GitHub für Tech-Themen
        if gh:
            return gh
        return (
            f"[Keine Web-Ergebnisse für '{query}'.\n"
            f"Tipp: Nutze web_fetch mit einer konkreten URL oder run_python mit httpx.]"
        )

    parts = [f"Web-Suchergebnisse für: {query}{via}\n"]
    for i, (title, url, snippet) in enumerate(hits, 1):
        parts.append(f"[{i}] {title}\n    {url}\n    {snippet}")

    # Inhalt der Top-Seite mitladen → echte Zusammenfassung möglich
    if fetch_top and hits:
        top_url = hits[0][1]
        page = _fetch_page_text(top_url, httpx)
        if page:
            parts.append(f"\n--- Inhalt der Top-Quelle ({top_url}) ---\n{page}")

    return "\n\n".join(parts)


def _searxng_search(query: str, max_results: int, httpx) -> list[tuple[str, str, str]]:
    """SearXNG JSON-API (lokal, localhost:8888) — primäre Quelle wenn Container läuft (V13)."""
    try:
        r = httpx.get(
            _SEARXNG_URL,
            params={"q": query, "format": "json", "pageno": 1},
            headers=_HEADERS,
            timeout=6,
        )
        if r.status_code != 200:
            return []
        j = r.json()
        results = j.get("results", [])
        out: list[tuple[str, str, str]] = []
        for item in results[:max_results]:
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            snippet = (item.get("content") or "").strip()
            if url.startswith("http"):
                out.append((title or url, url, snippet))
        return out
    except Exception:
        return []


def _ddg_search(query: str, max_results: int, httpx) -> list[tuple[str, str, str]]:
    """DuckDuckGo HTML-Suche DIREKT (mit Retry über beide Endpunkte)."""
    import time
    from urllib.parse import unquote
    from bs4 import BeautifulSoup

    html = ""
    for endpoint in _DDG_ENDPOINTS:
        for _ in range(2):
            try:
                resp = httpx.post(endpoint, data={"q": query}, timeout=12,
                                  headers=_HEADERS, follow_redirects=True)
                # 200 + "result" UND kein Bot-Challenge-Marker
                low = resp.text.lower()
                if resp.status_code == 200 and "result" in low and \
                        "challenge" not in low and "anomaly" not in low:
                    html = resp.text
                    break
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.8)
        if html:
            break
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results: list[tuple[str, str, str]] = []
    _AD_MARKERS = ("duckduckgo.com/y.js", "/aclick", "ad_provider=", "ad_domain=")
    for res in soup.select(".result"):
        classes = res.get("class", [])
        if "result--ad" in classes or "result--ad-v2" in classes:
            continue
        a = res.select_one(".result__a")
        if not a:
            continue
        href = a.get("href", "")
        if "uddg=" in href:
            href = unquote(href.split("uddg=")[1].split("&")[0])
        if any(m in href for m in _AD_MARKERS):
            continue
        sn = res.select_one(".result__snippet")
        title = a.get_text(" ", strip=True)
        snippet = sn.get_text(" ", strip=True) if sn else ""
        if title and href.startswith("http"):
            results.append((title, href, snippet))
        if len(results) >= max_results:
            break

    if not results:  # lite.duckduckgo.com Layout
        for a in soup.select("a.result-link"):
            href = a.get("href", "")
            if "uddg=" in href:
                href = unquote(href.split("uddg=")[1].split("&")[0])
            title = a.get_text(" ", strip=True)
            if title and href.startswith("http"):
                results.append((title, href, ""))
            if len(results) >= max_results:
                break

    return results


def _ddg_via_jina(query: str, max_results: int, httpx) -> list[tuple[str, str, str]]:
    """DuckDuckGo-HTML-Trefferseite DURCH den Jina-Reader holen. Da Jina serverseitig
    lädt, wird die lokale Bot-/IP-Sperre umgangen; das Ergebnis kommt als Markdown."""
    from urllib.parse import quote_plus

    target = "https://html.duckduckgo.com/html/?q=" + quote_plus(query)
    try:
        r = httpx.get(_JINA + target, headers=_HEADERS, timeout=30, follow_redirects=True)
    except Exception:  # noqa: BLE001
        return []
    if r.status_code != 200 or len(r.text) < 200:
        return []
    return _parse_jina_ddg(r.text, max_results)


def _parse_jina_ddg(md: str, max_results: int) -> list[tuple[str, str, str]]:
    """Parst die von Jina gelieferte Markdown-Fassung der DDG-Trefferseite.
    Treffer-Links sehen so aus: [Text](https://duckduckgo.com/l/?uddg=<ECHTE_URL>&rut=…).
    Pro echter Ziel-URL: kürzester sinnvoller Text = Titel, längster Text = Snippet."""
    import re
    from urllib.parse import unquote

    # Nicht-Bild-Markdown-Links auf DDG-Redirects (das ! vor [ ausschliessen)
    pat = re.compile(r"(?<!\!)\[([^\]]+)\]\((https?://duckduckgo\.com/l/\?uddg=[^)]+)\)")
    agg: dict[str, list[str]] = {}
    order: list[str] = []
    for text, ddgurl in pat.findall(md):
        m = re.search(r"uddg=([^&]+)", ddgurl)
        if not m:
            continue
        real = unquote(m.group(1))
        if not real.startswith("http") or "duckduckgo.com" in real:
            continue
        text = text.strip()
        if not text:
            continue
        if real not in agg:
            agg[real] = []
            order.append(real)
        agg[real].append(text)

    results: list[tuple[str, str, str]] = []
    for real in order:
        texts = agg[real]
        # Titel: kürzester Text, der nicht nur die nackte Domain/URL ist
        cand = [t for t in texts if not t.startswith("http")] or texts
        title = min(cand, key=len)
        snippet = max(texts, key=len)
        if snippet == title:
            snippet = ""
        results.append((title, real, snippet))
        if len(results) >= max_results:
            break
    return results


def _ddg_instant_answer(query: str, max_results: int, httpx) -> list[tuple[str, str, str]]:
    """DuckDuckGo Instant-Answer-API (keyless): liefert einen Abstract + kanonische
    Quell-URLs (oft Wikipedia/offizielle Seiten). Funktioniert auch wenn HTML blockt."""
    try:
        r = httpx.get("https://api.duckduckgo.com/",
                      params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                      headers=_HEADERS, timeout=20)
        j = r.json()
    except Exception:  # noqa: BLE001
        return []
    out: list[tuple[str, str, str]] = []
    abstract = (j.get("AbstractText") or "").strip()
    absurl = (j.get("AbstractURL") or "").strip()
    if abstract and absurl:
        out.append((j.get("Heading") or query, absurl, abstract))
    for rt in j.get("RelatedTopics", []):
        if not isinstance(rt, dict):
            continue
        url = rt.get("FirstURL") or ""
        txt = (rt.get("Text") or "").strip()
        if url.startswith("http"):
            out.append((txt[:70] or url, url, txt))
        if len(out) >= max_results:
            break
    return out


def _fetch_page_text(url: str, httpx, max_chars: int = 3500) -> str:
    """Lädt eine Seite als Text. Bevorzugt Jina Reader (liest auch bot-geschützte
    Seiten sauber, kein Key); fällt sonst auf direktes Laden + BeautifulSoup zurück."""
    # 1) Jina Reader — sauberes Markdown, serverseitig geladen
    try:
        r = httpx.get(_JINA + url, headers=_HEADERS, timeout=30, follow_redirects=True)
        if r.status_code == 200 and len(r.text) > 200:
            text = " ".join(r.text.split())
            return text[:max_chars] + ("…" if len(text) > max_chars else "")
    except Exception:  # noqa: BLE001
        pass
    # 2) Direkt + HTML-Extraktion
    from bs4 import BeautifulSoup
    try:
        resp = httpx.get(url, timeout=12, headers=_HEADERS, follow_redirects=True)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.decompose()
        paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        text = "\n".join(p for p in paras if len(p) > 40)
        if len(text) < 200:
            text = soup.get_text(" ", strip=True)
        text = " ".join(text.split())
        return text[:max_chars] + ("…" if len(text) > max_chars else "")
    except Exception:  # noqa: BLE001
        return ""


# ── GitHub-Fallback (für Tech-Themen, wenn Web-Suche blockiert ist) ────────────

_KNOWN_REPOS: dict[str, str] = {
    "anthropic": "anthropics/anthropic-sdk-python",
    "claude code": "anthropics/claude-code",
    "openai": "openai/openai-python",
    "langchain": "langchain-ai/langchain",
    "ollama": "ollama/ollama",
}


def _github_fallback(query: str, httpx) -> str:
    q_lower = query.lower()
    repo = next((r for kw, r in _KNOWN_REPOS.items() if kw in q_lower), None)

    if repo:
        for branch in ("main", "master"):
            url = f"https://raw.githubusercontent.com/{repo}/{branch}/README.md"
            try:
                resp = httpx.get(url, timeout=10, headers=_HEADERS)
                if resp.status_code == 200 and len(resp.text) > 100:
                    return f"[GitHub {repo} README]\n{resp.text[:3000]}"
            except Exception:  # noqa: BLE001
                continue

    try:
        resp = httpx.get(
            "https://api.github.com/search/repositories",
            params={"q": query, "sort": "stars", "per_page": 3},
            timeout=10,
            headers={**_HEADERS, "Accept": "application/vnd.github.v3+json"},
        )
        if resp.status_code == 200:
            items = resp.json().get("items", [])[:3]
            if items:
                lines = ["GitHub-Repositories:"]
                for it in items:
                    lines.append(
                        f"- {it.get('full_name')} (★{it.get('stargazers_count', 0)}): "
                        f"{it.get('description', '—')}\n  {it.get('html_url')}"
                    )
                return "\n".join(lines)
    except Exception:  # noqa: BLE001
        pass
    return ""
