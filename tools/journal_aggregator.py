#!/usr/bin/env python3
"""Utility for aggregating trade journal and signal logs into analysis datasets."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Tuple

import pandas as pd


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _prepare_output_dir(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)


def build_datasets(
    journal_path: Path,
    signals_path: Path,
    output_dir: Path,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    journal_df = load_csv(journal_path)
    signals_df = load_csv(signals_path)

    if journal_df.empty and signals_df.empty:
        raise RuntimeError("Нет данных для агрегации: отсутствуют trade_journal.csv и signals_log.csv")

    _prepare_output_dir(output_dir)

    long_df = journal_df.copy()
    if not long_df.empty:
        long_df.to_parquet(output_dir / "trade_journal_long.parquet", index=False)

    if journal_df.empty:
        wide_df = pd.DataFrame()
    else:
        base_cols = [
            'signal_id',
            'timestamp',
            'strategy',
            'signal',
            'entry_price',
            'stop_loss',
            'take_profit',
            'comment',
            'signal_strength',
            'risk_reward_ratio',
        ]
        # Убеждаемся, что столбцы присутствуют
        missing_cols = [col for col in base_cols if col not in journal_df.columns]
        if missing_cols:
            for col in missing_cols:
                journal_df[col] = None

        values = ['open', 'high', 'low', 'close', 'volume']
        available_values = [v for v in values if v in journal_df.columns]
        if not available_values:
            pivot_df = pd.DataFrame()
        else:
            pivot_df = (
                journal_df
                .pivot_table(
                    index=['signal_id'],
                    columns='tf',
                    values=available_values,
                    aggfunc='last'
                )
            )
            pivot_df.columns = [f"{col_tf}_{col_name}" for col_name, col_tf in pivot_df.columns]
            pivot_df = pivot_df.reset_index()

        wide_df = journal_df[base_cols].drop_duplicates('signal_id').merge(pivot_df, on='signal_id', how='left')
        wide_df.to_parquet(output_dir / "trade_journal_wide.parquet", index=False)

    if signals_df.empty:
        combined_df = wide_df.copy()
    else:
        combined_df = signals_df.merge(wide_df, on='signal_id', how='left', suffixes=('', '_journal'))
        combined_df.to_parquet(output_dir / "signals_dataset.parquet", index=False)

    if not signals_df.empty:
        signals_df.to_parquet(output_dir / "signals_log.parquet", index=False)

    return long_df, wide_df, combined_df


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate trade journals into reusable datasets")
    parser.add_argument('--journal', default='data/trade_journal.csv', help='Путь к trade_journal.csv')
    parser.add_argument('--signals', default='data/signals_log.csv', help='Путь к signals_log.csv')
    parser.add_argument('--output', default='data/derived', help='Каталог для агрегированных данных')

    args = parser.parse_args()

    journal_path = Path(args.journal)
    signals_path = Path(args.signals)
    output_dir = Path(args.output)

    try:
        build_datasets(journal_path, signals_path, output_dir)
        print(f"✓ Файлы с агрегированными данными сохранены в {output_dir}")
    except RuntimeError as err:
        print(f"⚠️ {err}")


if __name__ == '__main__':
    main()
