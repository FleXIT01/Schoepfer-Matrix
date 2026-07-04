"""sitecustomize — wird von JEDEM Python-Prozess automatisch geladen.

Schoepfer-Matrix (04.07.2026): Avast macht HTTPS-Inspektion (MITM) und
re-signiert Zertifikate mit seiner eigenen CA. Die liegt im WINDOWS-
Zertifikatspeicher, aber NICHT in certifi -> httpx/requests scheiterten mit
CERTIFICATE_VERIFY_FAILED ("unable to get local issuer certificate").

truststore.inject_into_ssl() laesst ALLE Python-SSL-Verbindungen (httpx,
requests, urllib, imaplib, ...) ueber die Windows-Zertifikatpruefung laufen
-> Avast-CA bekannt, normale Pruefung bleibt aktiv.

WICHTIG (04.07.2026): pip >= 25 nutzt sein EIGENES vendored truststore.
Doppelte Injektion -> RecursionError in ssl.verify_mode. pip ist in
sitecustomize aber nicht erkennbar (sys.argv = ['-m', ...] zu diesem
Zeitpunkt). Darum LAZY: erst beim ersten Import eines Netzwerkmoduls
injizieren — und nur, wenn 'pip' dann NICHT in sys.modules ist.
Manuell abschaltbar via MATRIX_NO_TRUSTSTORE=1.
"""
import os
import sys

_NET_MODULES = {
    "http.client", "httpx", "requests", "urllib.request",
    "imaplib", "smtplib", "poplib", "ftplib", "websockets",
}


class _LazyTruststore:
    """MetaPathFinder: injiziert truststore beim ersten Netzwerkmodul-Import."""

    def find_spec(self, name, path=None, target=None):
        if name not in _NET_MODULES:
            return None
        try:
            sys.meta_path.remove(self)
        except ValueError:
            pass
        if "pip" not in sys.modules:  # pip injiziert selbst -> Rekursionsfalle
            try:
                import truststore
                truststore.inject_into_ssl()
            except Exception:
                pass  # ohne truststore laeuft alles wie vorher (certifi)
        return None  # normalen Import fortsetzen


if os.environ.get("MATRIX_NO_TRUSTSTORE", "") != "1":
    sys.meta_path.insert(0, _LazyTruststore())
