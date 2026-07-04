"""Tool: Medizinische Literatur via PubMed/NCBI suchen.

Nutzt die kostenlose NCBI E-Utils API (kein API-Key für einfache Anfragen).
PubMed enthält 35M+ biomedizinische Artikel.
https://www.ncbi.nlm.nih.gov/books/NBK25499/
"""
from __future__ import annotations

REQUIRED_IMPORTS: list[str] = []
SAMPLE_INPUT = {"query": "Alzheimer disease treatment 2024", "max_results": 5}
DEFINITION = {
    "name": "pubmed_search",
    "description": (
        "Sucht in PubMed (35M+ medizinische Paper via NCBI). "
        "Ideal für: Krankheiten, Medikamente, klinische Studien, Molekularbiologie."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Medizinische Suchanfrage (englisch)"},
            "max_results": {"type": "integer", "description": "Maximale Ergebnisse (Standard: 5, Max: 10)"},
            "filter": {"type": "string", "description": "PubMed-Filter, z.B. 'clinical trial', 'review' (optional)"},
        },
        "required": ["query"],
    },
}

_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}


def pubmed_search(query: str, max_results: int = 5, filter: str = "") -> str:
    """Sucht in PubMed und gibt Titel + Abstracts zurück."""
    import httpx

    search_query = query
    if filter:
        search_query = f"{query} AND {filter}[pt]"

    # Schritt 1: IDs der relevantesten Paper abrufen
    try:
        search_resp = httpx.get(_ESEARCH, params={
            "db": "pubmed",
            "term": search_query,
            "retmax": min(max_results, 10),
            "retmode": "json",
            "sort": "relevance",
        }, timeout=15, headers=_HEADERS)
        search_data = search_resp.json()
    except Exception as exc:
        return f"[PubMed-Suchfehler: {exc}]"

    ids = search_data.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return f"[Keine PubMed-Ergebnisse für: {query}]"

    # Schritt 2: Abstracts abrufen
    try:
        fetch_resp = httpx.get(_EFETCH, params={
            "db": "pubmed",
            "id": ",".join(ids),
            "rettype": "abstract",
            "retmode": "xml",
        }, timeout=20, headers=_HEADERS)
        xml_text = fetch_resp.text
    except Exception as exc:
        return f"[PubMed-Fetch-Fehler: {exc}]\nGefundene IDs: {', '.join(ids)}"

    return _parse_pubmed_xml(xml_text, query)


def _parse_pubmed_xml(xml_text: str, query: str) -> str:
    """Parst PubMed-XML und gibt formatierte Ergebnisse zurück."""
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return f"[XML-Parse-Fehler bei PubMed-Antwort]\nRohdaten (erste 500 Zeichen): {xml_text[:500]}"

    articles = root.findall(".//PubmedArticle")
    if not articles:
        return f"[Keine PubMed-Artikel im XML gefunden]"

    lines = [f"PubMed-Suche: '{query}' — {len(articles)} Ergebnis(se)\n"]
    for i, article in enumerate(articles, 1):
        # Titel
        title = article.findtext(".//ArticleTitle") or "Kein Titel"
        title = title.replace("\n", " ").strip()

        # Autoren
        authors = []
        for author in article.findall(".//Author")[:3]:
            last = author.findtext("LastName") or ""
            first = author.findtext("ForeName") or ""
            if last:
                authors.append(f"{last} {first[:1]}." if first else last)

        # Jahr
        year = (
            article.findtext(".//PubDate/Year")
            or article.findtext(".//PubDate/MedlineDate", "")[:4]
            or "?"
        )

        # Abstract
        abstract_parts = [t for t in article.itertext() if t.strip()]
        abstract_el = article.find(".//AbstractText")
        if abstract_el is not None:
            abstract = (abstract_el.text or "").strip()
        else:
            abstract = "(kein Abstract verfügbar)"

        # PMID
        pmid = article.findtext(".//PMID") or ""
        link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""

        lines.append(
            f"[{i}] {title}\n"
            f"    Autoren: {', '.join(authors)}{' et al.' if len(authors) == 3 else ''}\n"
            f"    Jahr: {year}"
            + (f" | PMID: {pmid}" if pmid else "") + "\n"
            f"    Abstract: {abstract[:350]}{'…' if len(abstract) > 350 else ''}\n"
            + (f"    Link: {link}\n" if link else "")
        )

    return "\n".join(lines)
