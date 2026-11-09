"""Skill tagging used for chunk metadata and the heuristic (no-LLM) requirement extractor.

Deliberately matches canonical skill *names* only (word-boundary, case-insensitive). Aliases
such as "a background task queue" for Celery are NOT matched here; recovering implied skills
is the job of the LLM extractor, dense retrieval, HyDE and the corrective loop. Matching
aliases here would leak the generator's vocabulary into the retriever.
"""
from __future__ import annotations

import re
from functools import lru_cache

from gigsim.world import SKILLS

GENERIC = {"Python", "SQL", "JavaScript", "Docker", "REST API", "Excel", "TypeScript"}
# Code-level names that imply a canonical skill (import names, file conventions).
CODE_HINTS = {
    "torch": "PyTorch", "sklearn": "scikit-learn", "xgboost": "XGBoost", "langchain": "LangChain",
    "langgraph": "LangGraph", "peft": "LLM fine-tuning", "transformers": "Hugging Face Transformers",
    "openai": "OpenAI API", "pinecone": "Pinecone", "faiss": "FAISS", "pgvector": "pgvector",
    "cv2": "OpenCV", "ultralytics": "YOLO", "spacy": "spaCy", "mlflow": "MLflow", "fastapi": "FastAPI",
    "sagemaker": "AWS SageMaker", "airflow": "Airflow", "celery": "Celery", "onnxruntime": "ONNX",
    "react": "React", "next/link": "Next.js", "vue": "Vue", "express": "Express", "@nestjs": "NestJS",
    "django": "Django", "flask": "Flask", "psycopg": "PostgreSQL", "mongodb": "MongoDB", "redis": "Redis",
    "apollo": "GraphQL", "tailwind": "Tailwind CSS", "stripe": "Stripe", "next-auth": "OAuth",
    "'ws'": "WebSockets", "@playwright": "Playwright", "@jest": "Jest", "react-native": "React Native",
    "pandas": "pandas", "materialized=": "dbt", "snowflake": "Snowflake", "bigquery": "BigQuery",
    "scipy": "statistics", "tidyverse": "R", "metabase": "Metabase", "gspread": "Google Sheets",
}


@lru_cache(maxsize=1)
def _patterns() -> list[tuple[str, re.Pattern]]:
    out = []
    for name in SKILLS:
        if name == "R":
            pat = re.compile(r"(?<![\w-])R(?![\w-])")  # case-sensitive for the language R
        else:
            pat = re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", re.I)
        out.append((name, pat))
    return out


def tag_skills(text: str, code: bool = False) -> list[str]:
    found = [name for name, pat in _patterns() if pat.search(text)]
    if code:
        low = text.lower()
        found += [s for h, s in CODE_HINTS.items() if h in low]
    seen, out = set(), []
    for s in found:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def all_skill_names() -> list[str]:
    return list(SKILLS)
