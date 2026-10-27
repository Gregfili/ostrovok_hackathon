"""Таблицы SQLite. Схема меняется только миграцией Alembic."""

from __future__ import annotations

from sqlalchemy import Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class FactRow(Base):
    __tablename__ = "facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hotel_id: Mapped[str] = mapped_column(Text, nullable=False)
    feature: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    hotel_id: Mapped[str | None] = mapped_column(Text)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hotel_id: Mapped[str] = mapped_column(Text, nullable=False)
    guest_id: Mapped[str | None] = mapped_column(Text)
    author_role: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    hidden_for_guest: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    hidden_for_hotelier: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)


class HotelRegistration(Base):
    __tablename__ = "hotel_registrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    hotel_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guest_id: Mapped[str] = mapped_column(Text, nullable=False)
    hotel_id: Mapped[str] = mapped_column(Text, nullable=False)
    check_in: Mapped[str] = mapped_column(Text, nullable=False)
    check_out: Mapped[str] = mapped_column(Text, nullable=False)
    nights: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_rub: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class HotelFaqConfig(Base):
    __tablename__ = "hotel_faq_config"

    hotel_id: Mapped[str] = mapped_column(Text, primary_key=True)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    sections_json: Mapped[str] = mapped_column(Text, nullable=False, server_default="'{}'")
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class HotelFaqDocument(Base):
    __tablename__ = "hotel_faq_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hotel_id: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_at: Mapped[str] = mapped_column(Text, nullable=False)


class HotelFaqChunk(Base):
    __tablename__ = "hotel_faq_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hotel_id: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
