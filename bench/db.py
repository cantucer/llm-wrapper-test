from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from bench.schemas import (
    BenchmarkRunConfig,
    CapabilityResult,
    LoggingAssessment,
    RequestResult,
    StreamEventModel,
)
from bench.utils import ensure_parent_dir, json_dumps, utc_now


class Base(DeclarativeBase):
    pass


class BenchmarkRunORM(Base):
    __tablename__ = "benchmark_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    profile_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)


class RequestResultORM(Base):
    __tablename__ = "request_results"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("benchmark_runs.id"), index=True)
    target_id: Mapped[str] = mapped_column(String, index=True)
    target_name: Mapped[str] = mapped_column(String)
    prompt_id: Mapped[str] = mapped_column(String, index=True)
    prompt_category: Mapped[str] = mapped_column(String)
    concurrency_level: Mapped[int] = mapped_column(Integer)
    repetition_index: Mapped[int] = mapped_column(Integer)

    request_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    status: Mapped[str] = mapped_column(String, index=True)
    error_type: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    http_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String, nullable=True)
    client_request_id: Mapped[str] = mapped_column(String, index=True)

    model: Mapped[str] = mapped_column(String)
    base_url: Mapped[str] = mapped_column(Text)

    stream: Mapped[bool] = mapped_column(Boolean)
    temperature: Mapped[float] = mapped_column(Float)
    top_p: Mapped[float] = mapped_column(Float)
    max_tokens: Mapped[int] = mapped_column(Integer)

    ttft_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_to_last_token_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    first_chunk_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_content_chunk_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    content_chunk_count: Mapped[int] = mapped_column(Integer, default=0)

    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_chars: Mapped[int] = mapped_column(Integer, default=0)
    prompt_chars: Mapped[int] = mapped_column(Integer, default=0)

    prompt_tokens_reported: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens_reported: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens_reported: Mapped[int | None] = mapped_column(Integer, nullable=True)

    approx_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_per_second_reported: Mapped[float | None] = mapped_column(Float, nullable=True)
    tokens_per_second_approx: Mapped[float | None] = mapped_column(Float, nullable=True)

    mean_inter_content_chunk_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    p50_inter_content_chunk_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    p95_inter_content_chunk_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    response_headers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_usage_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class StreamEventORM(Base):
    __tablename__ = "stream_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    request_result_id: Mapped[str] = mapped_column(
        String, ForeignKey("request_results.id"), index=True
    )
    event_index: Mapped[int] = mapped_column(Integer)
    elapsed_ms: Mapped[float] = mapped_column(Float)
    event_type: Mapped[str] = mapped_column(String)
    delta_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_event_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class CapabilityResultORM(Base):
    __tablename__ = "capability_results"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    target_id: Mapped[str] = mapped_column(String, index=True)
    capability_name: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LoggingAssessmentORM(Base):
    __tablename__ = "logging_assessments"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    target_id: Mapped[str] = mapped_column(String, index=True)
    feature_name: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def get_db_path(db_path: str | Path | None = None) -> Path:
    return Path(db_path or os.getenv("BENCH_DB_PATH", "data/app.db"))


def get_engine(db_path: str | Path | None = None):
    path = ensure_parent_dir(get_db_path(db_path))
    return create_engine(f"sqlite:///{path}", future=True)


def init_db(db_path: str | Path | None = None) -> None:
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)


def create_benchmark_run(
    run_config: BenchmarkRunConfig, db_path: str | Path | None = None
) -> str:
    init_db(db_path)
    run_id = str(uuid4())
    config_json = json_dumps(run_config.model_dump(mode="json"))
    with Session(get_engine(db_path)) as session:
        session.add(
            BenchmarkRunORM(
                id=run_id,
                created_at=utc_now(),
                name=run_config.name,
                profile_name=run_config.profile_name,
                status="created",
                started_at=None,
                finished_at=None,
                notes=run_config.notes,
                config_json=config_json,
            )
        )
        session.commit()
    return run_id


def update_run_status(
    run_id: str,
    status: str,
    db_path: str | Path | None = None,
    *,
    started: bool = False,
    finished: bool = False,
) -> None:
    with Session(get_engine(db_path)) as session:
        row = session.get(BenchmarkRunORM, run_id)
        if row is None:
            raise KeyError(f"benchmark run not found: {run_id}")
        row.status = status
        now = utc_now()
        if started:
            row.started_at = now
        if finished:
            row.finished_at = now
        session.commit()


def insert_request_result(
    result: RequestResult,
    stream_events: list[StreamEventModel] | None = None,
    db_path: str | Path | None = None,
) -> None:
    init_db(db_path)
    with Session(get_engine(db_path)) as session:
        session.add(RequestResultORM(**result.model_dump()))
        for event in stream_events or []:
            session.add(StreamEventORM(**event.model_dump()))
        session.commit()


def insert_capability_result(
    result: CapabilityResult, db_path: str | Path | None = None
) -> None:
    init_db(db_path)
    with Session(get_engine(db_path)) as session:
        session.add(CapabilityResultORM(**result.model_dump()))
        session.commit()


def upsert_logging_assessment(
    assessment: LoggingAssessment, db_path: str | Path | None = None
) -> None:
    init_db(db_path)
    with Session(get_engine(db_path)) as session:
        existing = session.execute(
            select(LoggingAssessmentORM).where(
                LoggingAssessmentORM.target_id == assessment.target_id,
                LoggingAssessmentORM.feature_name == assessment.feature_name,
            )
        ).scalar_one_or_none()
        if existing:
            existing.status = assessment.status
            existing.evidence = assessment.evidence
            existing.notes = assessment.notes
            existing.updated_at = utc_now()
        else:
            session.add(LoggingAssessmentORM(**assessment.model_dump()))
        session.commit()


def list_runs(db_path: str | Path | None = None) -> pd.DataFrame:
    init_db(db_path)
    with get_engine(db_path).connect() as connection:
        return pd.read_sql_query(
            select(BenchmarkRunORM).order_by(BenchmarkRunORM.created_at.desc()),
            connection,
        )


def latest_run_id(db_path: str | Path | None = None) -> str | None:
    runs = list_runs(db_path)
    if runs.empty:
        return None
    return str(runs.iloc[0]["id"])


def load_request_results(
    db_path: str | Path | None = None, run_id: str | None = None
) -> pd.DataFrame:
    init_db(db_path)
    statement = select(RequestResultORM)
    if run_id:
        statement = statement.where(RequestResultORM.run_id == run_id)
    with get_engine(db_path).connect() as connection:
        return pd.read_sql_query(statement, connection)


def load_stream_events(
    db_path: str | Path | None = None, request_result_id: str | None = None
) -> pd.DataFrame:
    init_db(db_path)
    statement = select(StreamEventORM)
    if request_result_id:
        statement = statement.where(StreamEventORM.request_result_id == request_result_id)
    with get_engine(db_path).connect() as connection:
        return pd.read_sql_query(statement, connection)


def load_capability_results(
    db_path: str | Path | None = None, run_id: str | None = None
) -> pd.DataFrame:
    init_db(db_path)
    statement = select(CapabilityResultORM)
    if run_id:
        statement = statement.where(CapabilityResultORM.run_id == run_id)
    with get_engine(db_path).connect() as connection:
        return pd.read_sql_query(statement, connection)


def load_logging_assessments(db_path: str | Path | None = None) -> pd.DataFrame:
    init_db(db_path)
    with get_engine(db_path).connect() as connection:
        return pd.read_sql_query(select(LoggingAssessmentORM), connection)
