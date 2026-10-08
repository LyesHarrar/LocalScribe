"""
core/history_manager.py — Gestionnaire d'historique persistant SQLite
Permet d'enregistrer, rechercher et réexporter toutes les transcriptions passées de LocalScribe.
100 % local, zéro réseau, résilient et thread-safe.
"""

import json
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger("LocalScribe.History")


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


def init_db(db_path: Optional[Path] = None) -> None:
    """Initialise le schéma de la base de données s'il n'existe pas déjà."""
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
    """Supprime l'intégralité des enregistrements de l'historique."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.execute("DELETE FROM transcriptions")
            try:
                conn.execute("DELETE FROM sqlite_sequence WHERE name='transcriptions'")
            except sqlite3.OperationalError:
                pass
            logger.info(f"Historique complet vidé ({cursor.rowcount} enregistrements supprimés).")
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
