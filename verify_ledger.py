# -*- coding: utf-8 -*-
"""Проверка целостности публичного архива ставок (ledger.jsonl).

Автономный скрипт — БЕЗ зависимостей от кода бота. Ровно то, что может запустить
любой скептик: перечитывает цепочку и проверяет, что её никто не переписывал.

Проверяет:
  * seq идёт 1,2,3,… без пропусков;
  * prev_hash каждой записи == hash предыдущей (цепочка не разорвана);
  * hash каждой записи == SHA-256 её каноничного JSON (запись не подменена);
  * арифметика банка сходится (bank_after = старт + сумма профитов − откаты VOID).

Использование:  python scripts/verify_ledger.py path/to/ledger.jsonl [--start 100000]
Код возврата 0 — цепочка цела; 1 — обнаружено нарушение.
"""

import argparse
import hashlib
import json
import sys


def _canonical(rec: dict) -> str:
    body = {k: v for k, v in rec.items() if k != "hash"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(rec: dict) -> str:
    return hashlib.sha256(_canonical(rec).encode("utf-8")).hexdigest()


def verify(path: str, start_bank: float = 100000.0) -> list:
    errors = []
    records = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception as e:
                errors.append(f"строка {i}: невалидный JSON ({e})")
    prev_hash = "GENESIS"
    bank = start_bank
    settled_profit = {}  # bet_no -> profit (для корректного отката VOID)
    for idx, r in enumerate(records):
        exp_seq = idx + 1
        if r.get("seq") != exp_seq:
            errors.append(f"seq={r.get('seq')} ожидался {exp_seq} (пропуск/перестановка)")
        if r.get("prev_hash") != prev_hash:
            errors.append(f"seq={r.get('seq')}: prev_hash не совпал — цепочка разорвана")
        if r.get("hash") != _hash(r):
            errors.append(f"seq={r.get('seq')}: hash не совпал — запись подменена")
        # арифметика банка
        t = r.get("type")
        if t == "SETTLE":
            bn = r.get("bet_no")
            profit = float(r.get("profit") or 0.0)
            prior = settled_profit.get(bn, 0.0)
            settled_profit[bn] = profit
            # A reviewed result correction replaces the previous profit; the
            # original settlement remains in the immutable chain.
            bank = round(bank + profit - prior, 2)
            if round(float(r.get("bank_after")), 2) != bank:
                errors.append(f"seq={r.get('seq')}: bank_after={r.get('bank_after')} != {bank}")
        elif t == "VOID":
            bank = round(bank + float(r.get("adjust") or 0.0), 2)
            if round(float(r.get("bank_after")), 2) != bank:
                errors.append(f"seq={r.get('seq')}: bank_after={r.get('bank_after')} != {bank}")
        prev_hash = r.get("hash")
    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--start", type=float, default=100000.0)
    args = ap.parse_args()
    errors = verify(args.path, args.start)
    if errors:
        print("НАРУШЕНИЯ ЦЕПОЧКИ:")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    print("OK: цепочка цела, история не переписывалась.")
    sys.exit(0)


if __name__ == "__main__":
    main()
