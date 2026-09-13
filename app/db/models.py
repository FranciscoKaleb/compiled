"""Database schema for face identification.

Replaces the single `users` table that held one pickled numpy array per row.
Three deliberate changes:

1. Vectors are stored as raw float32 bytes, not pickle. The old code called
   pickle.loads() on data straight out of the database, which is an arbitrary
   code execution path if that database is ever tampered with. Raw bytes are
   also about a quarter of the size.
2. Vectors are L2-normalised on the way in, so a cosine similarity is a plain
   dot product and matching all enrolled people is one matrix multiply.
3. A person can have several embeddings. One photograph of a face is a poor
   template; several (different angles, lighting) is what makes 1:N matching
   work in practice.
"""
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Person(db.Model):
    __tablename__ = 'person'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    embeddings: Mapped[list['FaceEmbedding']] = relationship(
        back_populates='person', cascade='all, delete-orphan', lazy='selectin'
    )
    sightings: Mapped[list['RecognitionLog']] = relationship(
        back_populates='person', cascade='all, delete-orphan'
    )

    def __repr__(self) -> str:
        return f'<Person {self.id} {self.name!r}>'


class FaceEmbedding(db.Model):
    __tablename__ = 'face_embedding'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey('person.id', ondelete='CASCADE'), nullable=False, index=True
    )
    vector: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False, default='buffalo_l')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    person: Mapped[Person] = relationship(back_populates='embeddings')

    # -- serialisation ------------------------------------------------------

    @staticmethod
    def normalise(vector) -> np.ndarray:
        """Unit-length float32, so similarity is a dot product."""
        array = np.asarray(vector, dtype=np.float32).ravel()
        norm = float(np.linalg.norm(array))
        if norm == 0.0:
            raise ValueError('refusing to store a zero-length embedding')
        return array / norm

    @classmethod
    def from_vector(cls, vector, *, model_name: str = 'buffalo_l') -> 'FaceEmbedding':
        array = cls.normalise(vector)
        return cls(vector=array.tobytes(), dim=array.size, model_name=model_name)

    def to_array(self) -> np.ndarray:
        return np.frombuffer(self.vector, dtype=np.float32, count=self.dim)


class RecognitionLog(db.Model):
    """One row per identification attempt — what the old 'attendance system'
    claimed to record but never did."""

    __tablename__ = 'recognition_log'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int | None] = mapped_column(
        ForeignKey('person.id', ondelete='CASCADE'), nullable=True, index=True
    )
    similarity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    matched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default='still')
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, server_default=func.now(), nullable=False, index=True
    )

    person: Mapped[Person | None] = relationship(back_populates='sightings')
