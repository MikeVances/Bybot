"""
Singleton utility for ensuring only one instance of components
"""
import os
import fcntl
import atexit
from typing import Dict, Optional


class SingletonManager:
    """Менеджер singleton'ов для предотвращения дублирования экземпляров"""

    def __init__(self):
        self._locks: Dict[str, int] = {}
        self._lock_dir = "/tmp/bybot_locks"
        os.makedirs(self._lock_dir, exist_ok=True)
        atexit.register(self.cleanup)

    def acquire_lock(self, name: str) -> bool:
        """Получить эксклюзивную блокировку для компонента"""
        lock_file = os.path.join(self._lock_dir, f"{name}.lock")

        try:
            fd = os.open(lock_file, os.O_CREAT | os.O_WRONLY | os.O_TRUNC)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            # Записываем PID
            os.write(fd, str(os.getpid()).encode())
            os.fsync(fd)

            self._locks[name] = fd
            return True

        except (OSError, BlockingIOError):
            return False

    def release_lock(self, name: str):
        """Освободить блокировку"""
        if name in self._locks:
            try:
                fd = self._locks[name]
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
                del self._locks[name]

                # Удаляем файл блокировки
                lock_file = os.path.join(self._lock_dir, f"{name}.lock")
                if os.path.exists(lock_file):
                    os.unlink(lock_file)
            except:
                pass

    def cleanup(self):
        """Очистка всех блокировок при завершении"""
        for name in list(self._locks.keys()):
            self.release_lock(name)


# Глобальный менеджер singleton'ов
_singleton_manager = SingletonManager()


def get_singleton_manager() -> SingletonManager:
    """Получить глобальный менеджер singleton'ов"""
    return _singleton_manager


def ensure_singleton(component_name: str) -> bool:
    """
    Убедиться что запущен только один экземпляр компонента

    Returns:
        True если можно продолжать (единственный экземпляр)
        False если другой экземпляр уже запущен
    """
    return _singleton_manager.acquire_lock(component_name)


def ensure_single_instance(component_name: str) -> bool:
    """
    Альтернативное имя для ensure_singleton для совместимости

    Returns:
        True если можно продолжать (единственный экземпляр)
        False если другой экземпляр уже запущен
    """
    return ensure_singleton(component_name)