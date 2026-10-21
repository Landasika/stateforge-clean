from __future__ import annotations
import shutil
import sqlite3
from pathlib import Path
_SIDECAR_SUFFIXES = ("-journal", "-wal", "-shm")
_SQLITE_MAGIC = b"SQLite format 3\x00"
def _has_sqlite_header(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(16) == _SQLITE_MAGIC
    except OSError:
        return False
class SnapshotConsistencyError(RuntimeError):
    pass

class L2Sqlite:
    CAPTURE_BACKUP = "backup"   
    CAPTURE_COPY = "copy"       
    _MODES = (CAPTURE_BACKUP, CAPTURE_COPY)

    def __init__(self, live_path: str, tpl_root: str | None = None,
                 capture: str = CAPTURE_BACKUP):
        self.live = Path(live_path)
        root = Path(tpl_root) if tpl_root else self.live.parent / "tpl"
        self.root = root
        if capture not in self._MODES:
            raise ValueError(f"capture 必须是 {self._MODES} 之一: {capture!r}")
        self.capture = capture

    

    def _tpl(self, name: str) -> Path:
        return self.root / name / "db.tpl"

    def template_exists(self, name: str = "root") -> bool:
        return self._tpl(name).exists()

    
    def _probe_conn(self) -> sqlite3.Connection | None:
        
        if not self.live.exists():
            return None
        try:
            conn = sqlite3.connect(f"file:{self.live}?mode=ro", uri=True,
                                   timeout=0)
            conn.execute("PRAGMA schema_version").fetchone()
            return conn
        except sqlite3.Error:
            return None

    def _journal_mode_is_wal(self) -> bool:
        conn = self._probe_conn()
        if conn is None:
            return False
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            return str(mode).lower() == "wal"
        except sqlite3.Error:
            return False
        finally:
            conn.close()


    def snapshot_template(self, name: str = "root") -> Path:
        
        dst = self._tpl(name)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not self.live.exists():
            return dst                       

        if self.capture == self.CAPTURE_COPY:
            if self._journal_mode_is_wal():
                raise SnapshotConsistencyError(
                    f"copy 模式(fork-COW 位级冻结)不支持 WAL 目标: "
                    f"{self.live}(backup 会重排页,破坏'模板字节==冻结进程"
                    f"页缓存'的 ADR-0004 前提;引擎路径暂不支持 WAL)")
            shutil.copyfile(self.live, dst)
            self._unlink_sidecars()          
            return dst

        src = self._probe_conn()
        if src is None:
            if _has_sqlite_header(self.live):
                
                raise SnapshotConsistencyError(
                    f"live 具 SQLite 头但不可只读打开(损坏或锁死): "
                    f"{self.live}——fail-closed,不回退普通拷贝")
            shutil.copyfile(self.live, dst)  
            return dst
        try:
            dst_conn = sqlite3.connect(dst, timeout=0)
            try:
                src.backup(dst_conn)         
            finally:
                dst_conn.close()
        finally:
            src.close()
        
        
        return dst

    

    def restore(self, name: str = "root") -> None:
        
        src_path = self._tpl(name)
        if not src_path.exists():
            return

        if self.capture == self.CAPTURE_COPY:
            self._unlink_sidecars()
            self.live.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src_path, self.live)
            return

        tpl_probe = self._probe_template_conn(src_path)
        if tpl_probe is None:
            if _has_sqlite_header(src_path):
                raise SnapshotConsistencyError(
                    f"模板具 SQLite 头但不可读(损坏): {src_path}"
                    "——fail-closed,不回退普通拷贝")
            self._unlink_sidecars()          
            self.live.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src_path, self.live)
            return
        tpl_probe.close()

        
        
        
        self.live.parent.mkdir(parents=True, exist_ok=True)
        src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True, timeout=0)
        try:
            dst = sqlite3.connect(self.live, timeout=0)
            try:
                try:
                    dst.execute("BEGIN IMMEDIATE")
                    dst.execute("ROLLBACK")
                except sqlite3.OperationalError as exc:
                    raise SnapshotConsistencyError(
                        f"恢复目标被持锁连接占用(靶侧连接未关闭?): "
                        f"{self.live}: {exc}") from exc
                src.backup(dst)
                if self._journal_mode(dst) == "wal":
                    try:                      
                        dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    except sqlite3.Error:
                        pass                   
            finally:
                dst.close()
        finally:
            src.close()
    def _journal_mode(self, conn: sqlite3.Connection) -> str:
        try:
            return str(conn.execute("PRAGMA journal_mode")
                       .fetchone()[0]).lower()
        except sqlite3.Error:
            return ""

    def _probe_template_conn(self, tpl: Path) -> sqlite3.Connection | None:
        try:
            conn = sqlite3.connect(f"file:{tpl}?mode=ro", uri=True, timeout=0)
            conn.execute("PRAGMA schema_version").fetchone()
            return conn
        except sqlite3.Error:
            return None

    def _unlink_sidecars(self) -> None:
        for suffix in _SIDECAR_SUFFIXES:
            side = Path(str(self.live) + suffix)
            if side.exists():
                side.unlink()

class L2Handle:
    

    def __init__(self, l2: L2Sqlite, name: str):
        self.l2, self.name = l2, name

    def restore(self) -> None:
        self.l2.restore(self.name)

    def snapshot_template(self, child_name: str) -> Path:
        return self.l2.snapshot_template(child_name)

    def child(self, name: str) -> "L2Handle":
        return L2Handle(self.l2, name)
