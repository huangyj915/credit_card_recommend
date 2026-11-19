"""SQLite persistence layer for credit cards, reward rules, and scrape logs."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Dict, Iterator, List, Optional, Tuple

from app.models import CardIn, CardOut, RewardRuleIn, RewardRuleOut

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "cards.db"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


@contextmanager
def get_connection(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    target = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Optional[Path] = None) -> None:
    with get_connection(db_path) as conn:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bank_name TEXT NOT NULL,
                card_name TEXT NOT NULL,
                card_slug TEXT NOT NULL UNIQUE,
                official_url TEXT NOT NULL DEFAULT '',
                annual_fee TEXT NOT NULL DEFAULT '',
                base_rate_domestic REAL NOT NULL DEFAULT 0.3,
                base_rate_foreign REAL NOT NULL DEFAULT 0.3,
                reward_unit TEXT NOT NULL DEFAULT '現金回饋',
                notes TEXT NOT NULL DEFAULT '',
                source_type TEXT NOT NULL DEFAULT 'seed',
                last_updated TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reward_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id INTEGER NOT NULL,
                channel_code TEXT NOT NULL,
                channel_label TEXT NOT NULL,
                plan_name TEXT,
                rate REAL NOT NULL,
                monthly_cap_ntd REAL,
                cap_group TEXT,
                cap_applies_to TEXT NOT NULL DEFAULT 'total',
                min_spend_ntd REAL,
                payment_methods TEXT NOT NULL DEFAULT '[]',
                conditions TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (card_id) REFERENCES cards (id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS scrape_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bank_code TEXT NOT NULL,
                card_slug TEXT NOT NULL,
                url TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                rules_count INTEGER NOT NULL DEFAULT 0,
                scraped_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bank_card_directory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bank_code TEXT NOT NULL,
                bank_name TEXT NOT NULL,
                card_name TEXT NOT NULL,
                official_url TEXT NOT NULL DEFAULT '',
                discovered_at TEXT NOT NULL,
                UNIQUE(bank_code, card_name)
            );
            """
        )
        # Migrate existing reward_rules tables created before cap_group/cap_applies_to existed
        existing_cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(reward_rules)").fetchall()
        }
        if "cap_group" not in existing_cols:
            conn.execute("ALTER TABLE reward_rules ADD COLUMN cap_group TEXT;")
        if "cap_applies_to" not in existing_cols:
            conn.execute(
                "ALTER TABLE reward_rules ADD COLUMN cap_applies_to TEXT NOT NULL DEFAULT 'total';"
            )


def _row_to_rule(row: sqlite3.Row) -> RewardRuleOut:
    raw_methods = row["payment_methods"] or "[]"
    try:
        methods = json.loads(raw_methods)
    except json.JSONDecodeError:
        methods = []
    keys = row.keys()
    cap_group = row["cap_group"] if "cap_group" in keys else None
    raw_applies = (row["cap_applies_to"] if "cap_applies_to" in keys else None) or "total"
    cap_applies_to = "bonus" if raw_applies == "bonus" else "total"
    return RewardRuleOut(
        id=row["id"],
        card_id=row["card_id"],
        channel_code=row["channel_code"],
        channel_label=row["channel_label"],
        plan_name=row["plan_name"],
        rate=float(row["rate"]),
        monthly_cap_ntd=row["monthly_cap_ntd"],
        cap_group=cap_group,
        cap_applies_to=cap_applies_to,
        min_spend_ntd=row["min_spend_ntd"],
        payment_methods=methods,
        conditions=row["conditions"] or "",
    )


def _load_rules_for_card(conn: sqlite3.Connection, card_id: int) -> List[RewardRuleOut]:
    rows = conn.execute(
        "SELECT * FROM reward_rules WHERE card_id = ? ORDER BY id ASC",
        (card_id,),
    ).fetchall()
    return [_row_to_rule(r) for r in rows]


def _build_card_out(row: sqlite3.Row, rules: List[RewardRuleOut]) -> CardOut:
    return CardOut(
        id=row["id"],
        bank_name=row["bank_name"],
        card_name=row["card_name"],
        card_slug=row["card_slug"],
        official_url=row["official_url"] or "",
        annual_fee=row["annual_fee"] or "",
        base_rate_domestic=float(row["base_rate_domestic"]),
        base_rate_foreign=float(row["base_rate_foreign"]),
        reward_unit=row["reward_unit"] or "",
        notes=row["notes"] or "",
        source_type=row["source_type"] or "seed",
        last_updated=row["last_updated"],
        rules=rules,
    )


def _row_to_card(conn: sqlite3.Connection, row: sqlite3.Row) -> CardOut:
    return _build_card_out(row, _load_rules_for_card(conn, row["id"]))


def _list_cards_conn(conn: sqlite3.Connection) -> List[CardOut]:
    card_rows = conn.execute("SELECT * FROM cards ORDER BY id ASC").fetchall()
    if not card_rows:
        return []
    rule_rows = conn.execute("SELECT * FROM reward_rules ORDER BY id ASC").fetchall()
    rules_by_card: Dict[int, List[RewardRuleOut]] = {}
    for r in rule_rows:
        rule = _row_to_rule(r)
        rules_by_card.setdefault(rule.card_id, []).append(rule)
    return [_build_card_out(row, rules_by_card.get(row["id"], [])) for row in card_rows]


def upsert_card(card: CardIn, db_path: Optional[Path] = None) -> CardOut:
    now = _utc_now_iso()
    with get_connection(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM cards WHERE card_slug = ?",
            (card.card_slug,),
        ).fetchone()

        if existing:
            card_id = existing["id"]
            conn.execute(
                """
                UPDATE cards
                SET bank_name = ?, card_name = ?, official_url = ?, annual_fee = ?,
                    base_rate_domestic = ?, base_rate_foreign = ?, reward_unit = ?,
                    notes = ?, source_type = ?, last_updated = ?
                WHERE id = ?
                """,
                (
                    card.bank_name,
                    card.card_name,
                    card.official_url,
                    card.annual_fee,
                    card.base_rate_domestic,
                    card.base_rate_foreign,
                    card.reward_unit,
                    card.notes,
                    card.source_type,
                    now,
                    card_id,
                ),
            )
            conn.execute("DELETE FROM reward_rules WHERE card_id = ?", (card_id,))
        else:
            cursor = conn.execute(
                """
                INSERT INTO cards (
                    bank_name, card_name, card_slug, official_url, annual_fee,
                    base_rate_domestic, base_rate_foreign, reward_unit, notes,
                    source_type, last_updated
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card.bank_name,
                    card.card_name,
                    card.card_slug,
                    card.official_url,
                    card.annual_fee,
                    card.base_rate_domestic,
                    card.base_rate_foreign,
                    card.reward_unit,
                    card.notes,
                    card.source_type,
                    now,
                ),
            )
            card_id = cursor.lastrowid

        for rule in card.rules:
            _insert_rule(conn, card_id, rule)

        row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        return _row_to_card(conn, row)


def _insert_rule(conn: sqlite3.Connection, card_id: int, rule: RewardRuleIn) -> None:
    conn.execute(
        """
        INSERT INTO reward_rules (
            card_id, channel_code, channel_label, plan_name, rate,
            monthly_cap_ntd, cap_group, cap_applies_to, min_spend_ntd,
            payment_methods, conditions
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            card_id,
            rule.channel_code,
            rule.channel_label,
            rule.plan_name,
            rule.rate,
            rule.monthly_cap_ntd,
            rule.cap_group,
            rule.cap_applies_to,
            rule.min_spend_ntd,
            json.dumps(rule.payment_methods, ensure_ascii=False),
            rule.conditions,
        ),
    )


def list_cards(db_path: Optional[Path] = None) -> List[CardOut]:
    with get_connection(db_path) as conn:
        return _list_cards_conn(conn)


def get_card_by_slug(card_slug: str, db_path: Optional[Path] = None) -> Optional[CardOut]:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM cards WHERE card_slug = ?",
            (card_slug,),
        ).fetchone()
        return _row_to_card(conn, row) if row else None


def count_cards(db_path: Optional[Path] = None) -> int:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM cards").fetchone()
        return int(row["cnt"])


def log_scrape(
    bank_code: str,
    card_slug: str,
    url: str,
    status: str,
    message: str,
    rules_count: int = 0,
    db_path: Optional[Path] = None,
) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO scrape_logs (
                bank_code, card_slug, url, status, message, rules_count, scraped_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (bank_code, card_slug, url, status, message, rules_count, _utc_now_iso()),
        )


def list_scrape_logs(limit: int = 20, db_path: Optional[Path] = None) -> List[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM scrape_logs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def _upsert_directory_cards_conn(
    conn: sqlite3.Connection,
    bank_code: str,
    bank_name: str,
    entries: List[dict],
    now: str,
) -> None:
    for entry in entries:
        card_name = (entry.get("card_name") or "").strip()
        if not card_name:
            continue
        official_url = (entry.get("official_url") or "").strip()
        conn.execute(
            """
            INSERT INTO bank_card_directory (
                bank_code, bank_name, card_name, official_url, discovered_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(bank_code, card_name) DO UPDATE SET
                bank_name = excluded.bank_name,
                official_url = CASE
                    WHEN excluded.official_url != '' THEN excluded.official_url
                    ELSE bank_card_directory.official_url
                END,
                discovered_at = excluded.discovered_at
            """,
            (bank_code, bank_name, card_name, official_url, now),
        )


def upsert_directory_cards(
    bank_code: str,
    bank_name: str,
    entries: List[dict],
    db_path: Optional[Path] = None,
) -> None:
    now = _utc_now_iso()
    with get_connection(db_path) as conn:
        _upsert_directory_cards_conn(conn, bank_code, bank_name, entries, now)


def list_directory_cards(bank_code: str, db_path: Optional[Path] = None) -> List[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT bank_code, bank_name, card_name, official_url, discovered_at
            FROM bank_card_directory
            WHERE bank_code = ?
            ORDER BY id ASC
            """,
            (bank_code,),
        ).fetchall()
        return [dict(r) for r in rows]


def load_catalog_snapshot(
    db_path: Optional[Path] = None,
) -> Tuple[List[CardOut], Dict[str, List[dict]]]:
    """Load all saved cards and all discovered directory rows in a single SQLite connection."""
    with get_connection(db_path) as conn:
        cards = _list_cards_conn(conn)
        dir_rows = conn.execute(
            """
            SELECT bank_code, bank_name, card_name, official_url, discovered_at
            FROM bank_card_directory
            ORDER BY id ASC
            """
        ).fetchall()
        by_bank: Dict[str, List[dict]] = {}
        for r in dir_rows:
            d = dict(r)
            by_bank.setdefault(d["bank_code"], []).append(d)
        return cards, by_bank


def replace_directory_cards(
    bank_code: str,
    bank_name: str,
    entries: List[dict],
    db_path: Optional[Path] = None,
) -> None:
    now = _utc_now_iso()
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM bank_card_directory WHERE bank_code = ?", (bank_code,))
        _upsert_directory_cards_conn(conn, bank_code, bank_name, entries, now)
