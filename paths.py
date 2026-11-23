"""TypeKeep Path Resolution — safe across source runs and PyInstaller --onefile builds.

PyInstaller --onefile extracts bundled read-only assets (templates/, static/,
mobile/) into sys._MEIPASS (%TEMP%\\_MEIxxxxxx), which is wiped on exit.
User data (typekeep.db, config.json, clips/, backups/, typekeep.log) MUST NEVER
be placed inside sys._MEIPASS.
"""

import os
import platform
import shutil
import sys
import tempfile

# Directory containing bundled read-only web assets (templates/, static/, mobile/)
if getattr(sys, 'frozen', False):
    BUNDLE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(sys.executable)))
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_DIR = BUNDLE_DIR

# Legacy location from earlier background deployment (migrated once if larger)
_LEGACY_CODEX_DATA = os.path.join(
    os.path.expanduser('~'),
    'Documents', 'Codex', '2026-05-19', '019e3bc2-024d-7200-ba66-8432440bb22a-i-3',
    'TypeKeep', 'data',
)


def _is_in_temp(path: str) -> bool:
    try:
        temp_root = os.path.normcase(os.path.abspath(tempfile.gettempdir()))
        cand = os.path.normcase(os.path.abspath(path))
        return cand == temp_root or cand.startswith(temp_root + os.sep) or '_mei' in cand
    except Exception:
        return '_MEI' in path


def _default_user_data_dir() -> str:
    sys_name = platform.system()
    if sys_name == 'Windows':
        base = os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
        return os.path.join(base, 'TypeKeep', 'data')
    if sys_name == 'Darwin':
        return os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'TypeKeep', 'data')
    xdg = os.environ.get('XDG_DATA_HOME') or os.path.join(os.path.expanduser('~'), '.local', 'share')
    return os.path.join(xdg, 'typekeep', 'data')


def _is_writable_dir(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, '.tk_write_test')
        with open(probe, 'w', encoding='utf-8') as f:
            f.write('ok')
        os.remove(probe)
        return True
    except Exception:
        return False


def _migrate_best_existing_db(target_dir: str) -> None:
    """If target_dir has no typekeep.db yet, preserve any existing database."""
    target_db = os.path.join(target_dir, 'typekeep.db')
    if os.path.exists(target_db) and os.path.getsize(target_db) > 65536:
        return

    candidates = [
        _LEGACY_CODEX_DATA,
        os.path.join(APP_DIR, 'data'),
    ]
    best_dir = None
    best_size = os.path.getsize(target_db) if os.path.exists(target_db) else -1
    for cand in candidates:
        try:
            if not cand or os.path.normcase(os.path.abspath(cand)) == os.path.normcase(os.path.abspath(target_dir)):
                continue
            cand_db = os.path.join(cand, 'typekeep.db')
            if os.path.exists(cand_db):
                sz = os.path.getsize(cand_db)
                if sz > best_size:
                    best_size = sz
                    best_dir = cand
        except Exception:
            continue

    if not best_dir:
        return

    os.makedirs(target_dir, exist_ok=True)
    for fname in ('typekeep.db', 'typekeep.db-wal', 'typekeep.db-shm',
                  'config.json', 'config.backup.json'):
        src = os.path.join(best_dir, fname)
        dst = os.path.join(target_dir, fname)
        if os.path.exists(src) and not os.path.exists(dst):
            try:
                shutil.copy2(src, dst)
            except Exception:
                pass

    src_clips = os.path.join(best_dir, 'clips')
    dst_clips = os.path.join(target_dir, 'clips')
    if os.path.isdir(src_clips):
        os.makedirs(dst_clips, exist_ok=True)
        try:
            for item in os.listdir(src_clips):
                s = os.path.join(src_clips, item)
                d = os.path.join(dst_clips, item)
                if os.path.isfile(s) and not os.path.exists(d):
                    shutil.copy2(s, d)
        except Exception:
            pass


def resolve_data_dir() -> str:
    env_dir = os.environ.get('TYPEKEEP_DATA_DIR', '').strip()
    if env_dir:
        os.makedirs(env_dir, exist_ok=True)
        return env_dir

    user_data = _default_user_data_dir()
    local_data = os.path.join(APP_DIR, 'data')

    if getattr(sys, 'frozen', False):
        # Portable override: if a portable marker or an existing DB sits right next
        # to the exe (outside temp), honor that folder; note when installed to
        # %LOCALAPPDATA%\TypeKeep, local_data == user_data.
        portable_flag = os.path.exists(os.path.join(APP_DIR, 'portable.txt'))
        if (not _is_in_temp(APP_DIR)
                and (portable_flag or os.path.exists(os.path.join(local_data, 'typekeep.db')))
                and _is_writable_dir(local_data)):
            chosen = local_data
        else:
            chosen = user_data
    else:
        # Running from source: prefer unified user data dir if it already holds
        # TypeKeep's live database, else local repo data/ if writable.
        if os.path.exists(os.path.join(user_data, 'typekeep.db')):
            chosen = user_data
        elif not _is_in_temp(APP_DIR) and _is_writable_dir(local_data):
            chosen = local_data
        else:
            chosen = user_data

    os.makedirs(chosen, exist_ok=True)
    _migrate_best_existing_db(chosen)
    return chosen


DATA_DIR = resolve_data_dir()
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')
CLIPS_DIR = os.path.join(DATA_DIR, 'clips')
LOG_FILE = os.path.join(DATA_DIR, 'typekeep.log')
