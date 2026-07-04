@echo off
REM ============================================================
REM  BGE-Reranker-v2-m3 Dienst (fuer WeKnora-RAG / kb_search)
REM  Laeuft auf http://localhost:8011 . Erster Start laedt ~2.3 GB
REM  von HuggingFace. CPU-Default (kein VRAM-Konflikt mit Ollama).
REM  Fenster offen lassen.
REM ============================================================
setlocal
call "%~dp0env.cmd"
set "RERANK_DEVICE=cpu"
set "RERANK_PORT=8011"
set "PYTHONIOENCODING=utf-8"
title Schoepfer-Matrix Reranker (BGE-v2)
echo Starte BGE-Reranker-v2-m3 auf http://localhost:8011 ...
echo (Erster Start laedt ~2.3 GB; danach ~30s Ladezeit.)
echo ------------------------------------------------------------
%PYTHON_EXE% "%MATRIX_ROOT%\rerank-server\server.py"
echo.
echo [!] Reranker beendet.
pause
endlocal
