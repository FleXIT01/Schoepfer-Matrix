@echo off
REM ============================================================
REM  WeKnora-RAG-Stack (Hybrid Search: Qdrant + ParadeDB-BM25,
REM  Embedding bge-m3 via Ollama, BGE-Reranker-v2). 6 Container.
REM  Voraussetzung: Docker Desktop laeuft + Ollama laeuft.
REM  UI: http://localhost   API: http://localhost:8080
REM ============================================================
setlocal
call "%~dp0env.cmd"
set "WK=%MATRIX_ROOT%/WeKnora-main"
title Schoepfer-Matrix WeKnora-RAG
echo ============================================================
echo   WeKnora-RAG-Stack starten (Profil: qdrant)
echo ============================================================
echo.

REM --- Docker-Daemon da? ---
docker info >nul 2>&1
if errorlevel 1 (
  echo [!] Docker Desktop laeuft nicht. Bitte Docker Desktop starten und erneut versuchen.
  pause
  exit /b 1
)
echo [ok] Docker laeuft.
echo [..] starte Container (beim ersten Mal werden Images gezogen) ...
docker compose --project-directory "%WK%" -f "%WK%/docker-compose.yml" --env-file "%WK%/.env" --profile qdrant up -d
echo.
echo [ok] Stack gestartet.  UI: http://localhost   API: http://localhost:8080
echo     Fuer kb_search zusaetzlich rerank.cmd starten (BGE-Reranker).
echo     Stoppen:  docker compose --project-directory "%WK%" --profile qdrant down
echo.
pause
endlocal
