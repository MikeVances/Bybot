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
        """
        Получить эксклюзивную блокировку для компонента

        КРИТИЧНО: Проверяет stale locks от крашнутых процессов
        """
        lock_file = os.path.join(self._lock_dir, f"{name}.lock")

        # 1. Проверяем существующий lock файл
        if os.path.exists(lock_file):
            try:
                with open(lock_file, 'r') as f:
                    old_pid = f.read().strip()

                if old_pid.isdigit():
                    old_pid_int = int(old_pid)

                    # Проверяем, жив ли процесс
                    if not self._is_process_alive(old_pid_int):
                        # Процесс мертв - удаляем stale lock
                        os.unlink(lock_file)
                        print(f"🧹 Удален stale lock от крашнутого процесса PID {old_pid_int}")
            except Exception as e:
                # Если не можем прочитать - попробуем удалить
                try:
                    os.unlink(lock_file)
                except:
                    pass

        try:
            # 2. Создаем новый lock
            fd = os.open(lock_file, os.O_CREAT | os.O_WRONLY | os.O_TRUNC)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            # 3. Записываем PID текущего процесса
            os.write(fd, str(os.getpid()).encode())
            os.fsync(fd)

            self._locks[name] = fd
            return True

        except (OSError, BlockingIOError):
            # Lock все еще занят живым процессом
            return False

    def _is_process_alive(self, pid: int) -> bool:
        """
        Проверка, жив ли процесс

        Использует kill(pid, 0) - не убивает, просто проверяет существование
        """
        try:
            os.kill(pid, 0)  # Сигнал 0 = проверка без убийства
            return True
        except OSError:
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