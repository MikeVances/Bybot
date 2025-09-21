# bot/core/position_tracker.py
"""
🎯 СИСТЕМА ОТСЛЕЖИВАНИЯ ПРОИСХОЖДЕНИЯ ПОЗИЦИЙ
Отличает позиции, открытые системой, от внешних (ручных) позиций
"""

import json
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum
import threading


class PositionOrigin(Enum):
    """Происхождение позиции"""
    SYSTEM = "system"           # Открыта алгоритмом
    EXTERNAL = "external"       # Открыта вручную/внешним терминалом
    INHERITED = "inherited"     # Существовала до запуска системы
    UNKNOWN = "unknown"         # Неизвестно


@dataclass
class TrackedPosition:
    """Отслеживаемая позиция"""
    symbol: str
    side: str
    size: float
    entry_price: float
    origin: PositionOrigin
    strategy: Optional[str] = None
    created_time: Optional[datetime] = None
    bybit_created_time: Optional[datetime] = None
    system_order_id: Optional[str] = None
    comment: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь для JSON"""
        data = asdict(self)
        data['origin'] = self.origin.value
        if self.created_time:
            data['created_time'] = self.created_time.isoformat()
        if self.bybit_created_time:
            data['bybit_created_time'] = self.bybit_created_time.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TrackedPosition':
        """Создание из словаря"""
        if 'created_time' in data and data['created_time']:
            data['created_time'] = datetime.fromisoformat(data['created_time'])
        if 'bybit_created_time' in data and data['bybit_created_time']:
            data['bybit_created_time'] = datetime.fromisoformat(data['bybit_created_time'])
        data['origin'] = PositionOrigin(data['origin'])
        return cls(**data)


class PositionTracker:
    """
    🔍 ТРЕКЕР ПОЗИЦИЙ

    Функции:
    - Отслеживает все открытые позиции
    - Определяет происхождение (система vs внешняя)
    - Ведет историю позиций
    - Предоставляет данные для нейронки
    """

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.positions_file = os.path.join(data_dir, "tracked_positions.json")
        self.history_file = os.path.join(data_dir, "position_history.json")

        # Создаем директорию
        os.makedirs(data_dir, exist_ok=True)

        # Загружаем существующие данные
        self.tracked_positions: Dict[str, TrackedPosition] = {}
        self.position_history: List[Dict[str, Any]] = []
        self._load_data()

        # Система запущена
        self.system_startup_time = datetime.now(timezone.utc)

        # Thread safety
        self._lock = threading.RLock()

        # Логирование
        self.logger = logging.getLogger('position_tracker')
        self.logger.info(f"🎯 PositionTracker инициализирован (startup: {self.system_startup_time})")

    def _load_data(self) -> None:
        """Загрузка сохраненных данных"""
        try:
            # Загружаем позиции
            if os.path.exists(self.positions_file):
                with open(self.positions_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, pos_data in data.items():
                        self.tracked_positions[key] = TrackedPosition.from_dict(pos_data)

            # Загружаем историю
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.position_history = json.load(f)

        except Exception as e:
            self.logger.error(f"Ошибка загрузки данных трекера: {e}")

    def _save_data(self) -> None:
        """Сохранение данных"""
        try:
            # Сохраняем позиции
            with open(self.positions_file, 'w', encoding='utf-8') as f:
                data = {key: pos.to_dict() for key, pos in self.tracked_positions.items()}
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Сохраняем историю (только последние 1000 записей)
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.position_history[-1000:], f, indent=2, ensure_ascii=False)

        except Exception as e:
            self.logger.error(f"Ошибка сохранения данных трекера: {e}")

    def track_system_position(self, symbol: str, side: str, size: float,
                            entry_price: float, strategy: str,
                            order_id: Optional[str] = None) -> str:
        """
        Регистрация позиции, открытой системой

        Returns:
            Уникальный ключ позиции
        """
        with self._lock:
            position_key = f"{symbol}_{side}_{int(entry_price)}_{int(size*1000000)}"

            tracked_pos = TrackedPosition(
                symbol=symbol,
                side=side,
                size=size,
                entry_price=entry_price,
                origin=PositionOrigin.SYSTEM,
                strategy=strategy,
                created_time=datetime.now(timezone.utc),
                system_order_id=order_id,
                comment=f"Opened by {strategy} strategy"
            )

            self.tracked_positions[position_key] = tracked_pos

            # Добавляем в историю
            self.position_history.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": "position_opened",
                "position_key": position_key,
                "data": tracked_pos.to_dict()
            })

            self._save_data()

            self.logger.info(f"✅ System position tracked: {symbol} {side} {size} @ {entry_price} ({strategy})")
            return position_key

    def scan_and_classify_positions(self, current_positions: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Сканирование текущих позиций и классификация их происхождения

        Args:
            current_positions: Список позиций от API Bybit

        Returns:
            Словарь с классифицированными позициями
        """
        with self._lock:
            classified = {}

            for pos in current_positions:
                if float(pos.get('size', 0)) == 0:
                    continue  # Пропускаем пустые позиции

                symbol = pos.get('symbol')
                side = pos.get('side')
                size = float(pos.get('size', 0))
                entry_price = float(pos.get('avgPrice', 0))
                created_time_ms = pos.get('createdTime')

                # Конвертируем время создания
                bybit_created_time = None
                if created_time_ms:
                    bybit_created_time = datetime.fromtimestamp(
                        int(created_time_ms) / 1000, timezone.utc
                    )

                # Определяем ключ
                position_key = f"{symbol}_{side}_{int(entry_price)}_{int(size*1000000)}"

                # Классифицируем позицию
                origin = self._classify_position(pos, bybit_created_time)

                # Если позиция не отслеживается, добавляем её
                if position_key not in self.tracked_positions:
                    tracked_pos = TrackedPosition(
                        symbol=symbol,
                        side=side,
                        size=size,
                        entry_price=entry_price,
                        origin=origin,
                        created_time=datetime.now(timezone.utc),
                        bybit_created_time=bybit_created_time,
                        comment=self._get_origin_comment(origin, bybit_created_time)
                    )

                    self.tracked_positions[position_key] = tracked_pos

                    # Логируем обнаружение
                    self.logger.info(f"🔍 Discovered position: {symbol} {side} {size} @ {entry_price} ({origin.value})")

                # Добавляем в результат
                classified[position_key] = {
                    'position_data': pos,
                    'tracked_data': self.tracked_positions[position_key].to_dict(),
                    'classification': {
                        'origin': self.tracked_positions[position_key].origin.value,
                        'is_system': self.tracked_positions[position_key].origin == PositionOrigin.SYSTEM,
                        'strategy': self.tracked_positions[position_key].strategy,
                        'age_days': self._calculate_position_age(bybit_created_time),
                        'comment': self.tracked_positions[position_key].comment
                    }
                }

            self._save_data()
            return classified

    def _classify_position(self, pos: Dict[str, Any], created_time: Optional[datetime]) -> PositionOrigin:
        """Классификация происхождения позиции"""

        # Если позиция была создана до запуска системы
        if created_time and created_time < self.system_startup_time - timedelta(minutes=5):
            return PositionOrigin.INHERITED

        # Если позиция очень старая (более 7 дней)
        if created_time and (datetime.now(timezone.utc) - created_time).days > 7:
            return PositionOrigin.EXTERNAL

        # Если позиция создана недавно, нужно проверить торговый журнал
        symbol = pos.get('symbol')
        side = pos.get('side')
        entry_price = float(pos.get('avgPrice', 0))

        if self._check_in_trade_journal(symbol, side, entry_price, created_time):
            return PositionOrigin.SYSTEM

        # По умолчанию считаем внешней
        return PositionOrigin.EXTERNAL

    def _check_in_trade_journal(self, symbol: str, side: str, entry_price: float,
                              created_time: Optional[datetime]) -> bool:
        """Проверка есть ли позиция в торговом журнале"""
        try:
            journal_file = os.path.join(self.data_dir, "trade_journal.csv")
            if not os.path.exists(journal_file):
                return False

            # Читаем последние 1000 строк (для производительности)
            with open(journal_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Проверяем последние записи
            price_tolerance = 10.0  # $10 tolerance
            time_tolerance = timedelta(minutes=10)  # 10 минут tolerance

            for line in lines[-1000:]:
                try:
                    fields = line.strip().split(',')
                    if len(fields) >= 4:
                        log_price = float(fields[3])  # entry_price
                        log_signal = fields[2].upper()  # signal

                        # Проверяем цену и направление
                        if (abs(log_price - entry_price) < price_tolerance and
                            side.upper() in log_signal):
                            return True

                except (ValueError, IndexError):
                    continue

            return False

        except Exception as e:
            self.logger.error(f"Ошибка проверки торгового журнала: {e}")
            return False

    def _calculate_position_age(self, created_time: Optional[datetime]) -> float:
        """Расчет возраста позиции в днях"""
        if not created_time:
            return 0.0

        age = datetime.now(timezone.utc) - created_time
        return age.total_seconds() / (24 * 3600)  # В днях

    def _get_origin_comment(self, origin: PositionOrigin, created_time: Optional[datetime]) -> str:
        """Генерация комментария о происхождении"""
        if origin == PositionOrigin.SYSTEM:
            return "Opened by trading system"
        elif origin == PositionOrigin.EXTERNAL:
            return "Opened externally (manual trading)"
        elif origin == PositionOrigin.INHERITED:
            age_days = self._calculate_position_age(created_time)
            return f"Inherited from before system startup ({age_days:.1f} days old)"
        else:
            return "Unknown origin"

    def get_neural_data(self) -> Dict[str, Any]:
        """
        🧠 Данные для нейронной сети

        Returns:
            Структурированные данные о позициях для ML
        """
        with self._lock:
            neural_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "system_startup": self.system_startup_time.isoformat(),
                "positions_summary": {
                    "total": len(self.tracked_positions),
                    "system": len([p for p in self.tracked_positions.values() if p.origin == PositionOrigin.SYSTEM]),
                    "external": len([p for p in self.tracked_positions.values() if p.origin == PositionOrigin.EXTERNAL]),
                    "inherited": len([p for p in self.tracked_positions.values() if p.origin == PositionOrigin.INHERITED])
                },
                "positions": [],
                "insights": self._generate_insights()
            }

            # Добавляем данные по каждой позиции
            for key, pos in self.tracked_positions.items():
                neural_data["positions"].append({
                    "key": key,
                    "symbol": pos.symbol,
                    "side": pos.side,
                    "size": pos.size,
                    "entry_price": pos.entry_price,
                    "origin": pos.origin.value,
                    "strategy": pos.strategy,
                    "age_hours": self._calculate_position_age(pos.bybit_created_time) * 24,
                    "is_profitable": None,  # Нужна текущая цена для расчета
                    "risk_level": self._assess_position_risk(pos)
                })

            return neural_data

    def _generate_insights(self) -> Dict[str, Any]:
        """Генерация инсайтов для нейронки"""
        insights = {
            "external_position_ratio": 0.0,
            "avg_position_age_days": 0.0,
            "most_common_origin": "unknown",
            "risk_indicators": []
        }

        if not self.tracked_positions:
            return insights

        # Соотношение внешних позиций
        external_count = len([p for p in self.tracked_positions.values() if p.origin == PositionOrigin.EXTERNAL])
        insights["external_position_ratio"] = external_count / len(self.tracked_positions)

        # Средний возраст позиций
        ages = [self._calculate_position_age(p.bybit_created_time) for p in self.tracked_positions.values()]
        insights["avg_position_age_days"] = sum(ages) / len(ages) if ages else 0.0

        # Самое частое происхождение
        origins = [p.origin.value for p in self.tracked_positions.values()]
        if origins:
            insights["most_common_origin"] = max(set(origins), key=origins.count)

        # Индикаторы риска
        if external_count > 0:
            insights["risk_indicators"].append("external_positions_detected")
        if insights["avg_position_age_days"] > 7:
            insights["risk_indicators"].append("old_positions_present")

        return insights

    def _assess_position_risk(self, pos: TrackedPosition) -> str:
        """Оценка риска позиции"""
        age_days = self._calculate_position_age(pos.bybit_created_time)

        if pos.origin == PositionOrigin.EXTERNAL:
            return "high"  # Внешние позиции = высокий риск
        elif age_days > 7:
            return "medium"  # Старые позиции = средний риск
        else:
            return "low"  # Системные новые позиции = низкий риск

    def close_position(self, position_key: str, exit_price: float, reason: str = "") -> None:
        """Регистрация закрытия позиции"""
        with self._lock:
            if position_key in self.tracked_positions:
                pos = self.tracked_positions[position_key]

                # Добавляем в историю
                self.position_history.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "action": "position_closed",
                    "position_key": position_key,
                    "exit_price": exit_price,
                    "reason": reason,
                    "data": pos.to_dict()
                })

                # Удаляем из активных
                del self.tracked_positions[position_key]
                self._save_data()

                self.logger.info(f"❌ Position closed: {pos.symbol} {pos.side} @ {exit_price} ({reason})")

    def get_stats(self) -> Dict[str, Any]:
        """Статистика трекера"""
        with self._lock:
            return {
                "active_positions": len(self.tracked_positions),
                "total_history": len(self.position_history),
                "origins_breakdown": {
                    origin.value: len([p for p in self.tracked_positions.values() if p.origin == origin])
                    for origin in PositionOrigin
                },
                "system_startup": self.system_startup_time.isoformat(),
                "last_scan": datetime.now(timezone.utc).isoformat()
            }


# Глобальный экземпляр
_position_tracker = None
_tracker_lock = threading.RLock()


def get_position_tracker() -> PositionTracker:
    """Получение синглтона трекера позиций"""
    global _position_tracker

    if _position_tracker is None:
        with _tracker_lock:
            if _position_tracker is None:
                _position_tracker = PositionTracker()

    return _position_tracker