"""
Local filesystem lock for refresh concurrency control.
Prevents overlapping runs from corrupting candidate or active generation state.
"""

import fcntl
import os
import time

class RefreshLockError(Exception):
    """Raised when unable to acquire the refresh lock."""
    pass

class RefreshLock:
    def __init__(self, lock_file_path: str, timeout: float = 5.0):
        self.lock_file_path = lock_file_path
        self.timeout = timeout
        self._fd = None

    def acquire(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.lock_file_path)), exist_ok=True)
        # Open in append/read-write mode without truncating existing active lock file
        self._fd = open(self.lock_file_path, 'a+')
        start = time.time()
        while True:
            try:
                fcntl.flock(self._fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                # Acquired: truncate and write PID safely
                self._fd.seek(0)
                self._fd.truncate(0)
                self._fd.write(f"pid: {os.getpid()}\ntime: {time.time()}\n")
                self._fd.flush()
                return self
            except (BlockingIOError, OSError):
                if time.time() - start >= self.timeout:
                    self._fd.close()
                    self._fd = None
                    raise RefreshLockError(
                        f"Another refresh process holds the lock on {self.lock_file_path}. Exiting."
                    )
                time.sleep(0.5)

    def release(self):
        if self._fd:
            try:
                fcntl.flock(self._fd.fileno(), fcntl.LOCK_UN)
                self._fd.close()
            except Exception:
                pass
            finally:
                self._fd = None
                # Retaining lock file on POSIX prevents inode deletion races while maintaining clean fd locks

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
