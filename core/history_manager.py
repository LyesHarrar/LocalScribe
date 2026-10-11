"""
core/history_manager.py — Gestionnaire d'historique persistant SQLite
Permet d'enregistrer, rechercher et réexporter toutes les transcriptions passées de LocalScribe.
100 % local, zéro réseau, résilient et thread-safe.
"""

import json
import sqlite3
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Set

logger = logging.getLogger("LocalScribe.History")

# Cache mémoire pour éviter les rescans disque redondants (TTL 30s)
_FOLDER_SCAN_CACHE: Dict[str, Dict[str, Any]] = {}
# Mémoïsation des bases déjà initialisées pour éviter d'exécuter le DDL à chaque requête
_INITIALIZED_DBS: Set[str] = set()


def reset_db_cache() -> None:
    """Réinitialise le cache des bases SQLite initialisées."""
    global _INITIALIZED_DBS
    _INITIALIZED_DBS.clear()


def get_default_db_path() -> Path:
    """Retourne le chemin vers la base SQLite locale de LocalScribe."""
    project_root = Path(__file__).resolve().parent.parent
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "history.db"


def get_db_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Ouvre une connexion SQLite avec support des dictionnaires Row."""
    path = db_path if db_path is not None else get_default_db_path()
    conn = sqlite3.connect(str(path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[Path] = None, force: bool = False) -> None:
    """Initialise le schéma de la base de données s'il n'existe pas déjà."""
    target_path = str((db_path if db_path is not None else get_default_db_path()).resolve())
    if not force and target_path in _INITIALIZED_DBS:
        return

    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS transcriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                filename TEXT NOT NULL,
                filepath TEXT,
                duration REAL DEFAULT 0.0,
                language TEXT DEFAULT 'auto',
                language_probability REAL DEFAULT 100.0,
                task TEXT DEFAULT 'transcribe',
                model TEXT DEFAULT 'medium',
                speakers TEXT,
                transcript_text TEXT,
                segments TEXT,
                txt_path TEXT,
                md_path TEXT,
                srt_path TEXT
            )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_transcriptions_created ON transcriptions(created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_transcriptions_filename ON transcriptions(filename)")

            # Migration progressive si la table existait déjà sans la colonne 'segments'
            cursor = conn.execute("PRAGMA table_info(transcriptions)")
            cols = [col[1] for col in cursor.fetchall()]
            if "segments" not in cols:
                conn.execute("ALTER TABLE transcriptions ADD COLUMN segments TEXT")

            # Table des sessions de traitement par lot / dossier
            conn.execute("""
            CREATE TABLE IF NOT EXISTS batch_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_path TEXT NOT NULL,
                folder_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'in_progress',
                total_files INTEGER DEFAULT 0,
                processed_files INTEGER DEFAULT 0,
                skipped_files INTEGER DEFAULT 0,
                failed_files INTEGER DEFAULT 0,
                current_file TEXT DEFAULT '',
                total_duration REAL DEFAULT 0.0,
                elapsed_seconds REAL DEFAULT 0.0,
                started_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_batch_runs_started ON batch_runs(started_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_batch_runs_folder ON batch_runs(folder_path)")

        _INITIALIZED_DBS.add(target_path)
    finally:
        conn.close()


def add_record(entry: Dict[str, Any], db_path: Optional[Path] = None) -> int:
    """
    Enregistre une nouvelle transcription dans l'historique SQLite.
    Retourne l'ID généré.
    """
    init_db(db_path)
    conn = get_db_connection(db_path)
    
    speakers_val = entry.get("speakers")
    if isinstance(speakers_val, list):
        speakers_json = json.dumps(speakers_val, ensure_ascii=False)
    elif isinstance(speakers_val, str):
        speakers_json = speakers_val
    else:
        speakers_json = None

    segments_val = entry.get("segments")
    if isinstance(segments_val, list):
        segments_json = json.dumps(segments_val, ensure_ascii=False)
    elif isinstance(segments_val, str):
        segments_json = segments_val
    else:
        segments_json = None

    created_at = entry.get("created_at") or datetime.now().isoformat()
    
    try:
        with conn:
            cursor = conn.execute("""
            INSERT INTO transcriptions (
                created_at, filename, filepath, duration,
                language, language_probability, task, model,
                speakers, transcript_text, segments, txt_path, md_path, srt_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                created_at,
                entry.get("filename", "Sans titre"),
                str(entry.get("filepath", "")),
                float(entry.get("duration", 0.0)),
                entry.get("language", "auto"),
                float(entry.get("language_probability", 100.0)),
                entry.get("task", "transcribe"),
                entry.get("model", "medium"),
                speakers_json,
                entry.get("transcript_text", ""),
                segments_json,
                str(entry.get("txt_path", "")),
                str(entry.get("md_path", "")),
                str(entry.get("srt_path", ""))
            ))
            record_id = cursor.lastrowid
            logger.info(f"Transcription enregistrée dans l'historique (ID: {record_id}, fichier: {entry.get('filename')})")
            return record_id
    finally:
        conn.close()


def update_record(record_id: int, updates: Dict[str, Any], db_path: Optional[Path] = None) -> bool:
    """
    Met à jour un enregistrement existant dans l'historique SQLite.
    Gère la sérialisation JSON automatique pour 'speakers' et 'segments'.
    """
    init_db(db_path)
    if not updates:
        return False

    valid_cols = {
        "filename", "filepath", "duration", "language", "language_probability",
        "task", "model", "speakers", "transcript_text", "segments",
        "txt_path", "md_path", "srt_path"
    }

    set_clauses = []
    values = []

    for key, val in updates.items():
        if key not in valid_cols:
            continue

        if key in ("speakers", "segments") and isinstance(val, (list, dict)):
            val = json.dumps(val, ensure_ascii=False)
        elif key in ("duration", "language_probability") and val is not None:
            val = float(val)

        set_clauses.append(f"{key} = ?")
        values.append(val)

    if not set_clauses:
        return False

    values.append(record_id)
    sql = f"UPDATE transcriptions SET {', '.join(set_clauses)} WHERE id = ?"

    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.execute(sql, tuple(values))
            success = cursor.rowcount > 0
            if success:
                logger.info(f"Transcription ID {record_id} mise à jour avec succès dans l'historique.")
            return success
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convertit une ligne SQLite Row en dictionnaire Python."""
    data = dict(row)
    if data.get("speakers"):
        try:
            data["speakers"] = json.loads(data["speakers"])
        except Exception:
            pass
    else:
        data["speakers"] = []

    if data.get("segments"):
        try:
            data["segments"] = json.loads(data["segments"])
        except Exception:
            pass
    else:
        data["segments"] = []

    return data


def get_records(
    query: Optional[str] = None, 
    limit: int = 100, 
    offset: int = 0,
    db_path: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """
    Récupère la liste des transcriptions enregistrées, avec recherche textuelle optionnelle.
    Trie par date de création décroissante.
    """
    init_db(db_path)
    conn = get_db_connection(db_path)
    try:
        if query and query.strip():
            wildcard = f"%{query.strip()}%"
            cursor = conn.execute("""
            SELECT * FROM transcriptions
            WHERE filename LIKE ? 
               OR transcript_text LIKE ? 
               OR speakers LIKE ?
               OR language LIKE ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """, (wildcard, wildcard, wildcard, wildcard, limit, offset))
        else:
            cursor = conn.execute("""
            SELECT * FROM transcriptions
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """, (limit, offset))
            
        rows = cursor.fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_record_by_id(record_id: int, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Récupère une transcription par son identifiant unique."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute("SELECT * FROM transcriptions WHERE id = ?", (record_id,))
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def delete_record(record_id: int, db_path: Optional[Path] = None) -> bool:
    """Supprime un enregistrement de l'historique par son identifiant."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.execute("DELETE FROM transcriptions WHERE id = ?", (record_id,))
            return cursor.rowcount > 0
    finally:
        conn.close()


def clear_history(db_path: Optional[Path] = None) -> bool:
    """Supprime l'intégralité des enregistrements de l'historique (transcriptions et sessions de lot)."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor1 = conn.execute("DELETE FROM transcriptions")
            cursor2 = conn.execute("DELETE FROM batch_runs")
            try:
                conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('transcriptions', 'batch_runs')")
            except sqlite3.OperationalError:
                pass
            total_deleted = cursor1.rowcount + cursor2.rowcount
            logger.info(f"Historique complet vidé ({total_deleted} enregistrements supprimés).")
            return True
    except Exception as e:
        logger.error(f"Erreur lors de la suppression de l'historique : {e}")
        return False
    finally:
        conn.close()


def get_history_stats(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Calcule des statistiques globales sur l'historique des transcriptions."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute("""
        SELECT 
            COUNT(*) as total_count,
            COALESCE(SUM(duration), 0.0) as total_duration_seconds,
            COUNT(DISTINCT language) as distinct_languages
        FROM transcriptions
        """)
        row = cursor.fetchone()
        if row:
            total_seconds = float(row["total_duration_seconds"])
            return {
                "total_count": int(row["total_count"]),
                "total_duration_hours": round(total_seconds / 3600.0, 2),
                "total_duration_minutes": round(total_seconds / 60.0, 1),
                "distinct_languages": int(row["distinct_languages"])
            }
        return {
            "total_count": 0,
            "total_duration_hours": 0.0,
            "total_duration_minutes": 0.0,
            "distinct_languages": 0
        }
    finally:
        conn.close()


# =========================================================================
# GESTION DES SESSIONS DE TRAITEMENT PAR DOSSIER / LOT (BATCH RUNS)
# =========================================================================

def create_batch_run(
    folder_path: str,
    total_files: int,
    folder_name: Optional[str] = None,
    skipped_files: int = 0,
    db_path: Optional[Path] = None
) -> int:
    """
    Enregistre le démarrage d'une nouvelle session de traitement par dossier/lot.
    Retourne l'ID unique de la session de lot.
    """
    init_db(db_path)
    conn = get_db_connection(db_path)
    now_iso = datetime.now().isoformat()
    name = folder_name if folder_name else Path(folder_path).name or str(folder_path)
    
    try:
        with conn:
            cursor = conn.execute("""
            INSERT INTO batch_runs (
                folder_path, folder_name, status, total_files,
                processed_files, skipped_files, failed_files,
                current_file, total_duration, elapsed_seconds,
                started_at, updated_at
            ) VALUES (?, ?, 'in_progress', ?, 0, ?, 0, '', 0.0, 0.0, ?, ?)
            """, (
                str(folder_path),
                name,
                int(total_files),
                int(skipped_files),
                now_iso,
                now_iso
            ))
            batch_id = cursor.lastrowid
            logger.info(f"Session de lot créée (ID: {batch_id}, dossier: {name}, total: {total_files})")
            return batch_id
    finally:
        conn.close()


def update_batch_run_progress(
    batch_id: int,
    current_file: str = "",
    processed_files: Optional[int] = None,
    skipped_files: Optional[int] = None,
    failed_files: Optional[int] = None,
    elapsed_seconds: Optional[float] = None,
    db_path: Optional[Path] = None
) -> bool:
    """
    Met à jour la progression courante d'une session de lot.
    """
    init_db(db_path)
    updates = ["updated_at = ?"]
    values: List[Any] = [datetime.now().isoformat()]

    if current_file is not None:
        updates.append("current_file = ?")
        values.append(str(current_file))
    if processed_files is not None:
        updates.append("processed_files = ?")
        values.append(int(processed_files))
    if skipped_files is not None:
        updates.append("skipped_files = ?")
        values.append(int(skipped_files))
    if failed_files is not None:
        updates.append("failed_files = ?")
        values.append(int(failed_files))
    if elapsed_seconds is not None:
        updates.append("elapsed_seconds = ?")
        values.append(float(elapsed_seconds))

    values.append(batch_id)
    sql = f"UPDATE batch_runs SET {', '.join(updates)} WHERE id = ?"

    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.execute(sql, tuple(values))
            return cursor.rowcount > 0
    finally:
        conn.close()


def finish_batch_run(
    batch_id: int,
    status: str = "completed",
    processed_files: Optional[int] = None,
    skipped_files: Optional[int] = None,
    failed_files: Optional[int] = None,
    elapsed_seconds: Optional[float] = None,
    db_path: Optional[Path] = None
) -> bool:
    """
    Marque la session de lot comme terminée, interrompue ou en erreur.
    """
    init_db(db_path)
    now_iso = datetime.now().isoformat()
    updates = ["status = ?", "completed_at = ?", "updated_at = ?"]
    values: List[Any] = [status, now_iso, now_iso]

    if processed_files is not None:
        updates.append("processed_files = ?")
        values.append(int(processed_files))
    if skipped_files is not None:
        updates.append("skipped_files = ?")
        values.append(int(skipped_files))
    if failed_files is not None:
        updates.append("failed_files = ?")
        values.append(int(failed_files))
    if elapsed_seconds is not None:
        updates.append("elapsed_seconds = ?")
        values.append(float(elapsed_seconds))

    values.append(batch_id)
    sql = f"UPDATE batch_runs SET {', '.join(updates)} WHERE id = ?"

    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.execute(sql, tuple(values))
            logger.info(f"Session de lot ID {batch_id} clôturée avec statut '{status}'.")
            return cursor.rowcount > 0
    finally:
        conn.close()


def get_last_batch_run(
    folder_path: Optional[str] = None,
    db_path: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """
    Récupère la session de lot la plus récente (globalement ou pour un dossier spécifique).
    """
    init_db(db_path)
    conn = get_db_connection(db_path)
    try:
        if folder_path:
            cursor = conn.execute("""
            SELECT * FROM batch_runs
            WHERE folder_path = ?
            ORDER BY started_at DESC
            LIMIT 1
            """, (str(folder_path),))
        else:
            cursor = conn.execute("""
            SELECT * FROM batch_runs
            ORDER BY started_at DESC
            LIMIT 1
            """)
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_batch_runs(
    limit: int = 20,
    offset: int = 0,
    db_path: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """
    Récupère la liste des sessions de lot par date antéchronologique.
    """
    init_db(db_path)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute("""
        SELECT * FROM batch_runs
        ORDER BY started_at DESC
        LIMIT ? OFFSET ?
        """, (limit, offset))
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            total = d.get("total_files", 0)
            done = d.get("processed_files", 0) + d.get("skipped_files", 0)
            d["progress_pct"] = round((done / total * 100.0), 1) if total > 0 else 0.0
            result.append(d)
        return result
    finally:
        conn.close()


def get_batch_run_by_id(batch_id: int, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Récupère une session de lot par son identifiant unique."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute("SELECT * FROM batch_runs WHERE id = ?", (batch_id,))
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        total = d.get("total_files", 0)
        done = d.get("processed_files", 0) + d.get("skipped_files", 0)
        d["progress_pct"] = round((done / total * 100.0), 1) if total > 0 else 0.0
        return d
    finally:
        conn.close()


def delete_batch_run(batch_id: int, db_path: Optional[Path] = None) -> bool:
    """Supprime une session de lot par son identifiant."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.execute("DELETE FROM batch_runs WHERE id = ?", (batch_id,))
            return cursor.rowcount > 0
    finally:
        conn.close()


def get_folder_progress_summary(
    folder_path: Optional[str] = None,
    db_path: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """
    Fournit un résumé intelligent de l'état d'avancement d'un dossier (ou du tout dernier dossier retranscrit).
    Alimente à la fois les données de session mémorisées (SQLite) et le scan physique en direct du disque (Smart Resume).
    """
    init_db(db_path)
    last_batch = None
    target_folder = folder_path

    if target_folder:
        last_batch = get_last_batch_run(folder_path=target_folder, db_path=db_path)
    else:
        last_batch = get_last_batch_run(db_path=db_path)
        if last_batch:
            target_folder = last_batch["folder_path"]
        else:
            # Fallback : vérifier si une transcription individuelle a un filepath enregistré
            conn = get_db_connection(db_path)
            try:
                cur = conn.execute("""
                SELECT filepath FROM transcriptions
                WHERE filepath IS NOT NULL AND filepath != ''
                ORDER BY created_at DESC LIMIT 1
                """)
                row = cur.fetchone()
                if row and row["filepath"]:
                    target_folder = str(Path(row["filepath"]).parent)
            finally:
                conn.close()

    if not target_folder:
        return None

    path_obj = Path(target_folder)
    folder_name = path_obj.name or str(target_folder)

    # Extensions audio/vidéo supportées pour le scan du dossier physique
    supported_exts = {
        ".mp4", ".mkv", ".avi", ".webm", ".mov", ".m4v",
        ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma"
    }

    disk_exists = path_obj.exists() and path_obj.is_dir()
    disk_total = 0
    disk_done = 0
    disk_remaining = 0
    disk_pct = 0.0

    if disk_exists:
        now_ts = time.time()
        cached = _FOLDER_SCAN_CACHE.get(target_folder)
        if cached and (now_ts - cached.get("ts", 0.0) < 30.0):
            disk_total = cached["total"]
            disk_done = cached["done"]
            disk_remaining = cached["remaining"]
            disk_pct = cached["pct"]
        else:
            try:
                media_files = [
                    f for f in path_obj.rglob("*")
                    if f.is_file() and f.suffix.lower() in supported_exts and not f.name.startswith("ls_opt_")
                ]
                disk_total = len(media_files)
                disk_done = sum(1 for f in media_files if f.with_suffix(".txt").exists() and f.with_suffix(".txt").stat().st_size > 0)
                disk_remaining = max(0, disk_total - disk_done)
                disk_pct = round((disk_done / disk_total * 100.0), 1) if disk_total > 0 else 100.0
                _FOLDER_SCAN_CACHE[target_folder] = {
                    "ts": now_ts,
                    "total": disk_total,
                    "done": disk_done,
                    "remaining": disk_remaining,
                    "pct": disk_pct
                }
            except Exception as e:
                logger.warning(f"Erreur lors de l'analyse physique du dossier {target_folder}: {e}")

    if last_batch:
        batch_id = last_batch["id"]
        status = last_batch["status"]
        session_total = last_batch["total_files"]
        processed_files = last_batch["processed_files"]
        skipped_files = last_batch["skipped_files"]
        failed_files = last_batch.get("failed_files", 0)
        current_file = last_batch.get("current_file", "")
        elapsed_seconds = last_batch.get("elapsed_seconds", 0.0)
        started_at = last_batch.get("started_at", "")
        updated_at = last_batch.get("updated_at", "")
        completed_at = last_batch.get("completed_at")

        # Cohérence d'état : si le disque est accessible, la réalité des fichiers l'emporte
        if disk_exists and disk_total > 0:
            effective_total = disk_total
            effective_done = disk_done
            effective_pct = disk_pct
            if disk_remaining == 0:
                effective_status = "completed"
            elif status == "interrupted":
                effective_status = "interrupted"
            else:
                effective_status = status
        else:
            effective_total = session_total
            effective_done = processed_files + skipped_files
            effective_pct = round((effective_done / session_total * 100.0), 1) if session_total > 0 else 0.0
            effective_status = status
    else:
        batch_id = None
        effective_total = disk_total
        effective_done = disk_done
        effective_pct = disk_pct
        processed_files = disk_done
        skipped_files = 0
        failed_files = 0
        current_file = ""
        elapsed_seconds = 0.0
        started_at = ""
        updated_at = ""
        completed_at = None
        effective_status = "completed" if (disk_remaining == 0 and disk_total > 0) else "discovered"

    return {
        "batch_id": batch_id,
        "folder_path": target_folder,
        "folder_name": folder_name,
        "status": effective_status,
        "started_at": started_at,
        "updated_at": updated_at,
        "completed_at": completed_at,
        "total_files": effective_total,
        "processed_files": processed_files,
        "skipped_files": skipped_files,
        "failed_files": failed_files,
        "current_file": current_file,
        "elapsed_seconds": elapsed_seconds,
        "progress_pct": effective_pct,
        "disk_exists": disk_exists,
        "disk_total": disk_total,
        "disk_done": disk_done,
        "disk_remaining": disk_remaining,
        "disk_pct": disk_pct
    }

