"""Face enrolment and matching against the database.

Kept separate from the HTTP layer so the live video stream and the still-image
endpoints share exactly one implementation of "who is this?".
"""
import threading

import numpy as np
from sqlalchemy import select

from app.db.models import FaceEmbedding, Person, RecognitionLog
from app.extensions import db

# The matcher keeps enrolled vectors in memory as one (N, dim) matrix. `_version`
# is bumped by every write, so a stream that enrolled someone a second ago
# notices immediately — the old code only reloaded when the stream restarted.
_lock = threading.RLock()
_version = 0
_cache: tuple[int, np.ndarray, list[tuple[int, str]]] | None = None


def invalidate() -> None:
    global _version
    with _lock:
        _version += 1


def _matrix() -> tuple[np.ndarray, list[tuple[int, str]]]:
    """(vectors, [(person_id, name), ...]) for every enrolled embedding."""
    global _cache
    with _lock:
        if _cache is not None and _cache[0] == _version:
            return _cache[1], _cache[2]

        rows = db.session.execute(
            select(FaceEmbedding.vector, FaceEmbedding.dim, Person.id, Person.name)
            .join(Person, Person.id == FaceEmbedding.person_id)
            .order_by(Person.name)
        ).all()

        if rows:
            vectors = np.vstack([
                np.frombuffer(blob, dtype=np.float32, count=dim) for blob, dim, _, _ in rows
            ])
            owners = [(pid, name) for _, _, pid, name in rows]
        else:
            vectors = np.zeros((0, 512), dtype=np.float32)
            owners = []

        _cache = (_version, vectors, owners)
        return vectors, owners


def enrol(name: str, embedding) -> Person:
    """Add an embedding for `name`, creating the person if they are new."""
    name = name.strip()
    person = db.session.scalar(select(Person).where(Person.name == name))
    if person is None:
        person = Person(name=name)
        db.session.add(person)
        db.session.flush()

    person.embeddings.append(FaceEmbedding.from_vector(embedding))
    db.session.commit()
    invalidate()
    return person


def identify(embedding, threshold: float, *, source: str = 'still', log: bool = True):
    """Best match for one embedding.

    Returns (person_id, name, similarity) with name None when nothing clears
    the threshold. One dot product against every enrolled vector at once.
    """
    vectors, owners = _matrix()
    if not owners:
        return None, None, 0.0

    query = FaceEmbedding.normalise(embedding)
    similarities = vectors @ query           # both sides are unit-length
    best = int(np.argmax(similarities))
    score = float(similarities[best])
    person_id, name = owners[best]

    matched = score >= threshold
    if log:
        db.session.add(RecognitionLog(
            person_id=person_id if matched else None,
            similarity=score, matched=matched, source=source,
        ))
        db.session.commit()

    return (person_id, name, score) if matched else (None, None, score)


def roster() -> list[dict]:
    """Everyone enrolled, with how many embeddings each has."""
    rows = db.session.execute(
        select(Person.id, Person.name, Person.created_at,
               db.func.count(FaceEmbedding.id))
        .outerjoin(FaceEmbedding, FaceEmbedding.person_id == Person.id)
        .group_by(Person.id, Person.name, Person.created_at)
        .order_by(Person.name)
    ).all()
    return [
        {'id': pid, 'name': name, 'enrolled_at': created.isoformat(), 'samples': count}
        for pid, name, created, count in rows
    ]


def forget(person_id: int) -> bool:
    """Delete a person and everything recorded about them."""
    person = db.session.get(Person, person_id)
    if person is None:
        return False
    db.session.delete(person)
    db.session.commit()
    invalidate()
    return True
