"""F7: Zentrales Groessenlimit fuer Datei-Uploads (Belege, Bank-/Excel-Import).

Ohne Limit liest jeder betroffene Endpunkt die komplette Datei in den
Arbeitsspeicher (kein Content-Length-Check, kein ASGI-Limit) - ein
mehrere GB grosser Upload kann den Container (RAM geteilt mit Ollama)
unter Druck setzen und die Platte fuellen. lies_upload() liest hoechstens
`maximal + 1` Bytes und bricht mit 413 ab, sobald die Grenze ueberschritten
wird, statt die Datei vollstaendig einzulesen.
"""
from fastapi import HTTPException, UploadFile

# 25 MB: reicht fuer Fotos/Scans und Kassabuch-Exporte deutlich, verhindert
# aber mehrere-GB-Uploads.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def lies_upload(datei: UploadFile, maximal: int | None = None) -> bytes:
    """Liest hoechstens `maximal` (Default: MAX_UPLOAD_BYTES) Bytes einer
    UploadFile; 413 bei Ueberschreitung. Liest MAX_UPLOAD_BYTES bei jedem
    Aufruf frisch aus dem Modul (nicht als Default-Parameter gebunden),
    damit Tests das Limit per monkeypatch aendern koennen."""
    grenze = MAX_UPLOAD_BYTES if maximal is None else maximal
    inhalt = datei.file.read(grenze + 1)
    if len(inhalt) > grenze:
        raise HTTPException(413, f"Datei zu gross (max. {grenze // (1024 * 1024)} MB)")
    return inhalt
