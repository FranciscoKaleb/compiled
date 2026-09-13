"""Level 6 — the data layer: locking, N+1, pagination, live migration.

Uses its own SQLite file (app_files/db/lab.db) with its own SQLAlchemy engine,
so the demos can rewrite rows and even schema without touching the app's real
database. Every SQL statement the engine runs during a request is captured and
returned, so the pages can show exactly what the ORM did.

    GET  /lab/api/data/reset                         rebuild and reseed lab.db
    GET  /lab/api/data/account                       the shared row (locking demo)
    POST /lab/api/data/account                       {mode, balance, version?, holder?} update
    POST /lab/api/data/account/lock                  {holder} take / release the lease
    GET  /lab/api/data/authors?load=lazy|selectin|joined
    GET  /lab/api/data/items?mode=offset|cursor&page=&cursor=&size=
    POST /lab/api/data/items                         insert one at the top
    GET  /lab/api/data/schema                        PRAGMA table_info(lab_profile) + row sample
    POST /lab/api/data/migrate                       {step: add_column|backfill|make_required|reset}
    POST /lab/api/data/traffic                       one read+write against lab_profile (for the migration demo)
"""
import random
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from flask import current_app, g, jsonify, request
from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, String, create_engine, event, func, inspect, select, text, tuple_
)
from sqlalchemy.orm import DeclarativeBase, Session, joinedload, relationship, selectinload

from app.blueprints.lab import bp

# ---------------------------------------------------------------------------
# Engine with a per-request SQL recorder
# ---------------------------------------------------------------------------

_engine = None
_engine_lock = threading.Lock()


class Base(DeclarativeBase):
    pass


class Author(Base):
    __tablename__ = 'lab_author'
    id = Column(Integer, primary_key=True)
    name = Column(String(80), nullable=False)
    books = relationship('Book', back_populates='author', lazy='select')      # lazy on purpose: the N+1 lives here


class Book(Base):
    __tablename__ = 'lab_book'
    id = Column(Integer, primary_key=True)
    author_id = Column(ForeignKey('lab_author.id'), nullable=False, index=True)
    title = Column(String(120), nullable=False)
    year = Column(Integer)
    author = relationship('Author', back_populates='books')


class Account(Base):
    __tablename__ = 'lab_account'
    id = Column(Integer, primary_key=True)
    holder = Column(String(80), nullable=False)
    balance = Column(Integer, nullable=False, default=0)
    version = Column(Integer, nullable=False, default=1)         # optimistic locking
    locked_by = Column(String(40))                                # pessimistic lease (SQLite has no FOR UPDATE)
    locked_until = Column(DateTime)
    updated_by = Column(String(40))


class Item(Base):
    __tablename__ = 'lab_item'
    id = Column(Integer, primary_key=True)
    title = Column(String(120), nullable=False)
    created_at = Column(DateTime, nullable=False, index=True)


def engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            path = Path(current_app.config['DB_DIR']) / 'lab.db'
            path.parent.mkdir(parents=True, exist_ok=True)
            _engine = create_engine(f'sqlite:///{path}', future=True)

            @event.listens_for(_engine, 'after_cursor_execute')
            def record(conn, cursor, statement, parameters, context, executemany):
                log = getattr(g, 'sql_log', None)
                if log is not None:
                    log.append({'sql': ' '.join(statement.split()), 'params': _short_params(parameters)})

            if not inspect(_engine).has_table('lab_author'):
                _seed(_engine)
    return _engine


def _short_params(params):
    text_ = repr(params)
    return text_ if len(text_) < 120 else text_[:117] + '…'


def _seed(eng):
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    rng = random.Random(3)
    first = ['Ada', 'Grace', 'Alan', 'Edsger', 'Barbara', 'Donald', 'Margaret', 'Linus', 'Radia', 'Ken', 'Frances', 'Tim']
    last = ['Lovelace', 'Hopper', 'Turing', 'Dijkstra', 'Liskov', 'Knuth', 'Hamilton', 'Torvalds', 'Perlman', 'Thompson', 'Allen', 'Berners-Lee']
    words = ['Structures', 'Machines', 'Programs', 'Systems', 'Networks', 'Compilers', 'Proofs', 'Algorithms', 'Engines', 'Notes']
    with Session(eng) as s:
        for i in range(30):
            a = Author(name=f'{first[i % 12]} {last[(i * 7) % 12]}')
            for k in range(3):
                a.books.append(Book(title=f'{rng.choice(words)} of {rng.choice(words)} vol. {k + 1}', year=1950 + rng.randint(0, 74)))
            s.add(a)
        s.add(Account(id=1, holder='Shared savings', balance=1000, version=1))
        base = datetime(2026, 1, 1)
        for i in range(200):
            s.add(Item(title=f'Item #{i + 1}', created_at=base + timedelta(minutes=i * 7, seconds=rng.randint(0, 59))))
        s.commit()
    with eng.begin() as conn:
        conn.execute(text('CREATE TABLE IF NOT EXISTS lab_profile (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL)'))
        conn.execute(text("INSERT INTO lab_profile (name, email) VALUES ('Ada','ada@example.com'),('Grace','grace@example.com'),('Alan','alan@example.com')"))


def _begin_log():
    g.sql_log = []


def _with_sql(payload: dict, status: int = 200):
    payload['sql'] = g.get('sql_log', [])
    payload['sql_count'] = len(payload['sql'])
    return jsonify(payload), status


@bp.get('/api/data/reset', endpoint='api_data_reset')
def data_reset():
    _begin_log()
    _seed(engine())
    return _with_sql({'ok': True, 'message': 'lab.db rebuilt and reseeded'})


# ---------------------------------------------------------------------------
# 25. Locking
# ---------------------------------------------------------------------------

def _account_json(a: Account) -> dict:
    lease = a.locked_by if a.locked_until and a.locked_until > datetime.utcnow() else None
    return {'id': a.id, 'holder': a.holder, 'balance': a.balance, 'version': a.version, 'locked_by': lease,
            'lock_seconds_left': int((a.locked_until - datetime.utcnow()).total_seconds()) if lease else 0,
            'updated_by': a.updated_by}


@bp.get('/api/data/account', endpoint='api_data_account_get')
def account_get():
    _begin_log()
    with Session(engine()) as s:
        a = s.get(Account, 1)
        return _with_sql({'ok': True, 'account': _account_json(a)})


@bp.post('/api/data/account/lock', endpoint='api_data_account_lock')
def account_lock():
    _begin_log()
    data = request.get_json(silent=True) or {}
    holder = str(data.get('holder', 'A'))[:40]
    release = bool(data.get('release'))
    with Session(engine()) as s:
        a = s.get(Account, 1)
        now = datetime.utcnow()
        held = a.locked_by if a.locked_until and a.locked_until > now else None
        if release:
            if held == holder:
                a.locked_by = None; a.locked_until = None
                s.commit()
                return _with_sql({'ok': True, 'account': _account_json(a), 'message': f'{holder} released the lock'})
            return _with_sql({'ok': False, 'error': f'{holder} does not hold the lock', 'account': _account_json(a)}, 409)
        if held and held != holder:
            return _with_sql({'ok': False, 'error': f'row is locked by {held} for another {int((a.locked_until - now).total_seconds())} s',
                              'account': _account_json(a)}, 423)
        a.locked_by = holder; a.locked_until = now + timedelta(seconds=30)
        s.commit()
        return _with_sql({'ok': True, 'account': _account_json(a), 'message': f'{holder} holds the lock for 30 s'})


@bp.post('/api/data/account', endpoint='api_data_account_update')
def account_update():
    _begin_log()
    data = request.get_json(silent=True) or {}
    mode = data.get('mode', 'none')
    holder = str(data.get('holder', 'A'))[:40]
    try:
        balance = int(data.get('balance'))
    except (TypeError, ValueError):
        return _with_sql({'ok': False, 'error': 'balance must be a number'}, 400)

    with Session(engine()) as s:
        if mode == 'optimistic':
            expected = int(data.get('version', -1))
            # The whole trick: UPDATE ... WHERE version = <what I read>. Zero rows affected = someone got there first.
            result = s.execute(
                text('UPDATE lab_account SET balance=:b, version=version+1, updated_by=:u WHERE id=1 AND version=:v'),
                {'b': balance, 'u': holder, 'v': expected})
            s.commit()
            a = s.get(Account, 1)
            if result.rowcount == 0:
                return _with_sql({'ok': False, 'conflict': True, 'account': _account_json(a),
                                  'error': f'{holder} read version {expected} but the row is now version {a.version} — someone saved first. Reload and redo your change.'}, 409)
            return _with_sql({'ok': True, 'account': _account_json(a), 'message': f'{holder} saved; version {expected} → {a.version}'})

        a = s.get(Account, 1)
        if mode == 'pessimistic':
            now = datetime.utcnow()
            held = a.locked_by if a.locked_until and a.locked_until > now else None
            if held != holder:
                return _with_sql({'ok': False, 'error': f'{holder} must hold the lock to save' + (f' (held by {held})' if held else ' (nobody holds it — lock first)'),
                                  'account': _account_json(a)}, 423)
            a.balance = balance; a.version += 1; a.updated_by = holder
            a.locked_by = None; a.locked_until = None            # save releases the lock
            s.commit()
            return _with_sql({'ok': True, 'account': _account_json(a), 'message': f'{holder} saved and released the lock'})

        # mode 'none': last writer wins, silently.
        a.balance = balance; a.version += 1; a.updated_by = holder
        s.commit()
        return _with_sql({'ok': True, 'account': _account_json(a), 'message': f'{holder} saved (no check — whatever was there is gone)'})


# ---------------------------------------------------------------------------
# 26. N+1
# ---------------------------------------------------------------------------

@bp.get('/api/data/authors', endpoint='api_data_authors')
def authors():
    _begin_log()
    load = request.args.get('load', 'lazy')
    started = time.perf_counter()
    with Session(engine()) as s:
        stmt = select(Author).order_by(Author.id)
        if load == 'selectin':
            stmt = stmt.options(selectinload(Author.books))
        elif load == 'joined':
            stmt = stmt.options(joinedload(Author.books))
        rows = s.execute(stmt).unique().scalars().all()
        # Touching .books is what triggers the lazy loads — exactly as a template loop would.
        out = [{'id': a.id, 'name': a.name, 'books': [b.title for b in a.books]} for a in rows]
    ms = round((time.perf_counter() - started) * 1000, 1)
    return _with_sql({'ok': True, 'load': load, 'authors': out, 'ms': ms})


# ---------------------------------------------------------------------------
# 27. Pagination
# ---------------------------------------------------------------------------

@bp.get('/api/data/items', endpoint='api_data_items')
def items():
    _begin_log()
    mode = request.args.get('mode', 'offset')
    size = max(3, min(25, request.args.get('size', 10, type=int)))
    with Session(engine()) as s:
        total = s.scalar(select(func.count()).select_from(Item))
        if mode == 'cursor':
            cursor = request.args.get('cursor')
            stmt = select(Item).order_by(Item.created_at.desc(), Item.id.desc()).limit(size + 1)
            if cursor:
                ts, _, cid = cursor.partition('|')
                stmt = stmt.where(tuple_(Item.created_at, Item.id) < (datetime.fromisoformat(ts), int(cid)))
            rows = s.scalars(stmt).all()
            more = len(rows) > size
            rows = rows[:size]
            next_cursor = f'{rows[-1].created_at.isoformat()}|{rows[-1].id}' if rows and more else None
            payload = {'mode': 'cursor', 'next_cursor': next_cursor}
        else:
            page = max(1, request.args.get('page', 1, type=int))
            rows = s.scalars(select(Item).order_by(Item.created_at.desc(), Item.id.desc()).offset((page - 1) * size).limit(size)).all()
            payload = {'mode': 'offset', 'page': page, 'pages': -(-total // size)}
        payload.update(ok=True, total=total, items=[{'id': r.id, 'title': r.title, 'created_at': r.created_at.strftime('%Y-%m-%d %H:%M:%S')} for r in rows])
    return _with_sql(payload)


@bp.post('/api/data/items', endpoint='api_data_items_insert')
def items_insert():
    _begin_log()
    with Session(engine()) as s:
        newest = s.scalar(select(func.max(Item.created_at)))
        item = Item(title=f'Breaking news #{random.randint(100, 999)}', created_at=(newest or datetime.utcnow()) + timedelta(minutes=5))
        s.add(item); s.commit()
        return _with_sql({'ok': True, 'item': {'id': item.id, 'title': item.title}, 'message': 'a new row landed at the top of the list'})


# ---------------------------------------------------------------------------
# 28. Live migration (expand / contract)
# ---------------------------------------------------------------------------

def _schema(conn) -> dict:
    cols = [dict(r._mapping) for r in conn.execute(text('PRAGMA table_info(lab_profile)'))]
    rows = [dict(r._mapping) for r in conn.execute(text('SELECT * FROM lab_profile ORDER BY id LIMIT 5'))]
    count = conn.execute(text('SELECT COUNT(*) FROM lab_profile')).scalar()
    return {'columns': [{'name': c['name'], 'type': c['type'], 'nullable': not c['notnull'], 'default': c['dflt_value']} for c in cols],
            'rows': rows, 'count': count}


@bp.get('/api/data/schema', endpoint='api_data_schema')
def schema():
    _begin_log()
    with engine().begin() as conn:
        info = _schema(conn)
        applied = None
    # Read-only peek at the app's real Alembic state, for context.
    try:
        from app.extensions import db
        applied = db.session.execute(text('SELECT version_num FROM alembic_version')).scalar()
    except Exception:
        applied = None
    return _with_sql({'ok': True, **info, 'app_alembic_version': applied})


@bp.post('/api/data/migrate', endpoint='api_data_migrate')
def migrate():
    _begin_log()
    step = (request.get_json(silent=True) or {}).get('step', '')
    eng = engine()
    with eng.begin() as conn:
        cols = {c['name'] for c in _schema(conn)['columns']}
        if step == 'add_column':
            if 'phone' in cols:
                return _with_sql({'ok': False, 'error': 'phone already exists'}, 409)
            conn.execute(text('ALTER TABLE lab_profile ADD COLUMN phone TEXT'))           # nullable: instant, no rewrite
            note = 'EXPAND: added a nullable column. Old code ignores it; new code can start writing it. Zero downtime.'
        elif step == 'backfill':
            if 'phone' not in cols:
                return _with_sql({'ok': False, 'error': 'add the column first'}, 409)
            result = conn.execute(text("UPDATE lab_profile SET phone = '+63 900 000 ' || printf('%04d', id) WHERE phone IS NULL"))
            note = f'BACKFILL: filled {result.rowcount} existing row(s) in batches (one batch here). Reads and writes continue meanwhile.'
        elif step == 'make_required':
            if 'phone' not in cols:
                return _with_sql({'ok': False, 'error': 'add the column first'}, 409)
            nulls = conn.execute(text('SELECT COUNT(*) FROM lab_profile WHERE phone IS NULL')).scalar()
            if nulls:
                return _with_sql({'ok': False, 'error': f'{nulls} row(s) still have NULL phone — backfill first or the constraint fails'}, 409)
            # SQLite cannot ALTER a constraint: rebuild the table. This is what Alembic's batch_alter_table does.
            conn.execute(text('CREATE TABLE lab_profile_new (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL)'))
            conn.execute(text('INSERT INTO lab_profile_new SELECT id, name, email, phone FROM lab_profile'))
            conn.execute(text('DROP TABLE lab_profile'))
            conn.execute(text('ALTER TABLE lab_profile_new RENAME TO lab_profile'))
            note = 'CONTRACT: the column is NOT NULL now. On SQLite that is a copy-into-new-table, which Alembic hides behind batch_alter_table; on Postgres/MySQL it is a plain ALTER.'
        elif step == 'reset':
            conn.execute(text('DROP TABLE IF EXISTS lab_profile'))
            conn.execute(text('CREATE TABLE lab_profile (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL)'))
            conn.execute(text("INSERT INTO lab_profile (name, email) VALUES ('Ada','ada@example.com'),('Grace','grace@example.com'),('Alan','alan@example.com')"))
            note = 'Back to the original schema.'
        else:
            return _with_sql({'ok': False, 'error': 'unknown step'}, 400)
        info = _schema(conn)
    return _with_sql({'ok': True, 'note': note, **info})


@bp.post('/api/data/traffic', endpoint='api_data_traffic')
def traffic():
    """One read + one write, as the running application would do during a migration."""
    _begin_log()
    with engine().begin() as conn:
        cols = {c['name'] for c in _schema(conn)['columns']}
        row = conn.execute(text('SELECT id, name, email FROM lab_profile ORDER BY RANDOM() LIMIT 1')).mappings().first()
        # New code path: write the new column only once it exists (feature flag in real life).
        if 'phone' in cols:
            conn.execute(text("INSERT INTO lab_profile (name, email, phone) VALUES (:n, :e, :p)"),
                         {'n': f'User {random.randint(100, 999)}', 'e': f'u{random.randint(100, 999)}@example.com', 'p': '+63 917 000 0000'})
        else:
            conn.execute(text("INSERT INTO lab_profile (name, email) VALUES (:n, :e)"),
                         {'n': f'User {random.randint(100, 999)}', 'e': f'u{random.randint(100, 999)}@example.com'})
        count = conn.execute(text('SELECT COUNT(*) FROM lab_profile')).scalar()
    return _with_sql({'ok': True, 'read': dict(row) if row else None, 'count': count, 'columns': sorted(cols)})
