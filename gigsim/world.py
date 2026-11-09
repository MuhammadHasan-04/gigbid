"""GigSim stand-in: the synthetic world (skill ontology, personas, archetypes).

NOTE: The instructor-provided GigSim was not available when this repo was built, so this
package is a student-built stand-in that follows the behaviour described in the assignment
(jobs with client histories, Connects, proposals, messages, rate limits, occasional errors,
simulated clients with hidden preferences). If the official GigSim is supplied, drop it in
`gigsim/` and point GIGSIM_BASE_URL at it; nothing outside the adapter depends on this code.
"""
from __future__ import annotations

# skill -> list of aliases / implied phrasings (used to make corpora and job posts "messy")
SKILLS: dict[str, list[str]] = {
    # ---------- AI / ML ----------
    "Python": ["python 3", "pythonic tooling"],
    "PyTorch": ["torch", "a torch training loop"],
    "TensorFlow": ["keras", "tf.keras models"],
    "scikit-learn": ["sklearn", "classical ML pipelines"],
    "XGBoost": ["gradient boosted trees", "boosted tree ensembles"],
    "LangChain": ["LLM chains", "chain-of-tools orchestration"],
    "LangGraph": ["stateful agent graphs", "multi-step agent workflows"],
    "RAG": ["retrieval-augmented generation", "grounding an LLM on company documents"],
    "LLM fine-tuning": ["LoRA adapters", "instruction tuning an open model"],
    "Hugging Face Transformers": ["transformer checkpoints", "HF model hub models"],
    "OpenAI API": ["GPT function calling", "chat completion endpoints"],
    "Pinecone": ["a managed vector index", "hosted vector search"],
    "FAISS": ["approximate nearest neighbour search", "an in-memory ANN index"],
    "pgvector": ["vector columns in Postgres", "embedding search inside Postgres"],
    "computer vision": ["image understanding", "visual inspection models"],
    "OpenCV": ["cv2", "classic image processing"],
    "YOLO": ["real-time object detection", "bounding-box detectors"],
    "NLP": ["text classification", "language understanding"],
    "spaCy": ["named entity recognition pipelines", "rule-plus-statistical NER"],
    "time series forecasting": ["demand forecasting", "predicting next month's numbers"],
    "MLOps": ["model deployment pipelines", "keeping models healthy in production"],
    "MLflow": ["experiment tracking", "a model registry"],
    "Docker": ["containerised services", "container images"],
    "FastAPI": ["an async Python API", "typed Python endpoints"],
    "AWS SageMaker": ["managed training jobs on AWS", "SageMaker endpoints"],
    "Airflow": ["DAG-based scheduling", "orchestrated nightly pipelines"],
    "Celery": ["a background task queue", "asynchronous workers with a broker"],
    "prompt engineering": ["prompt design", "careful system prompts"],
    "recommendation systems": ["personalised ranking", "you-may-also-like suggestions"],
    "ONNX": ["portable model export", "optimised inference graphs"],
    # ---------- Full-stack ----------
    "JavaScript": ["vanilla JS", "ES2022"],
    "TypeScript": ["typed JavaScript", "strict TS"],
    "React": ["component-based SPA", "hooks-based frontend"],
    "Next.js": ["server-rendered React", "the app router"],
    "Vue": ["Vue 3", "composition API frontend"],
    "Node.js": ["a JavaScript backend", "server-side JS"],
    "Express": ["express middleware", "a minimal Node HTTP server"],
    "NestJS": ["opinionated Node framework", "decorator-based Node services"],
    "Django": ["Django ORM", "batteries-included Python web framework"],
    "Flask": ["a lightweight Python web app", "flask blueprints"],
    "PostgreSQL": ["Postgres", "a relational database"],
    "MongoDB": ["a document database", "Mongo collections"],
    "Redis": ["an in-memory cache", "a key-value store"],
    "GraphQL": ["a typed query API", "Apollo schema"],
    "REST API": ["RESTful endpoints", "JSON over HTTP"],
    "Tailwind CSS": ["utility-first CSS", "tailwind classes"],
    "Stripe": ["card payments", "subscription billing"],
    "OAuth": ["social login", "single sign-on"],
    "AWS": ["Amazon cloud", "EC2 and S3"],
    "Vercel": ["edge deployment", "preview deployments"],
    "WebSockets": ["real-time updates", "live push to the browser"],
    "Playwright": ["browser end-to-end tests", "automated UI tests"],
    "Jest": ["JS unit tests", "snapshot testing"],
    "Shopify": ["a Shopify storefront", "Liquid theme work"],
    "WordPress": ["a WP site", "custom WP plugins"],
    "React Native": ["a cross-platform mobile app", "Expo app"],
    # ---------- Data analyst ----------
    "SQL": ["complex queries", "window functions"],
    "Excel": ["spreadsheets", "pivot tables"],
    "Power BI": ["DAX dashboards", "Microsoft BI reports"],
    "Tableau": ["Tableau workbooks", "interactive viz dashboards"],
    "Looker": ["LookML models", "governed BI layer"],
    "pandas": ["dataframes", "python data wrangling"],
    "dbt": ["a SQL transformation layer with tests", "modular data models"],
    "Snowflake": ["a cloud data warehouse", "warehouse credits"],
    "BigQuery": ["Google's warehouse", "serverless SQL on GCP"],
    "Google Analytics 4": ["GA4", "web analytics events"],
    "A/B testing": ["split tests", "controlled experiments"],
    "statistics": ["hypothesis testing", "confidence intervals"],
    "R": ["tidyverse", "ggplot2"],
    "ETL": ["data pipelines", "extract-transform-load jobs"],
    "Fivetran": ["managed connectors", "automated ingestion"],
    "data cleaning": ["messy data", "deduplicating records"],
    "dashboard design": ["executive dashboards", "KPI reporting"],
    "cohort analysis": ["retention curves", "customer cohorts"],
    "Google Sheets": ["shared sheets", "Apps Script automations"],
    "Metabase": ["self-serve BI", "open-source BI"],
    # ---------- out-of-domain (no persona has these) ----------
    "Swift": ["native iOS", "SwiftUI"],
    "Unity": ["a 3D game engine", "C# game scripting"],
    "Solidity": ["smart contracts", "EVM contracts"],
    "video editing": ["Premiere Pro cuts", "YouTube edits"],
    "logo design": ["brand marks", "Illustrator vectors"],
    "SEO copywriting": ["keyword-rich blog posts", "content marketing"],
    "Salesforce Apex": ["Salesforce triggers", "Apex classes"],
    "embedded C": ["microcontroller firmware", "bare-metal C"],
    "Laravel": ["PHP Laravel", "Eloquent ORM"],
    "Flutter": ["Dart mobile app", "Flutter widgets"],
}

OUT_OF_DOMAIN = ["Swift", "Unity", "Solidity", "video editing", "logo design", "SEO copywriting",
                 "Salesforce Apex", "embedded C", "Laravel", "Flutter"]

INDUSTRIES = ["fintech", "healthcare", "e-commerce", "logistics", "edtech", "real estate",
              "media", "SaaS", "manufacturing", "travel", "insurance", "non-profit"]

# Archetypes: (category, title template, core skills, optional skills, base_hours)
ARCHETYPES: dict[str, list[tuple[str, str, list[str], list[str], int]]] = {
    "ai_ml": [
        ("llm_apps", "RAG chatbot over {industry} documents", ["Python", "RAG", "LangChain"], ["Pinecone", "FAISS", "pgvector", "OpenAI API", "FastAPI", "prompt engineering"], 60),
        ("llm_apps", "Multi-agent workflow for {industry} operations", ["Python", "LangGraph", "OpenAI API"], ["LangChain", "FastAPI", "Docker", "prompt engineering", "Celery"], 70),
        ("llm_apps", "Fine-tune an open LLM for {industry} support tickets", ["Python", "LLM fine-tuning", "Hugging Face Transformers"], ["PyTorch", "MLflow", "AWS SageMaker", "ONNX"], 55),
        ("classical_ml", "Churn / risk prediction model for a {industry} company", ["Python", "scikit-learn", "XGBoost"], ["pandas", "MLflow", "FastAPI", "Docker"], 35),
        ("classical_ml", "Demand forecasting for {industry}", ["Python", "time series forecasting"], ["XGBoost", "Airflow", "pandas", "MLflow"], 40),
        ("vision", "Defect detection with computer vision for {industry}", ["Python", "computer vision", "YOLO"], ["OpenCV", "PyTorch", "ONNX", "Docker"], 60),
        ("vision", "Document image classification for {industry}", ["Python", "computer vision", "PyTorch"], ["OpenCV", "TensorFlow", "FastAPI"], 45),
        ("nlp", "Entity extraction from {industry} contracts", ["Python", "NLP", "spaCy"], ["Hugging Face Transformers", "FastAPI", "Docker"], 40),
        ("mlops", "Productionise ML models for a {industry} team", ["MLOps", "Docker", "MLflow"], ["AWS SageMaker", "Airflow", "FastAPI", "Celery"], 50),
        ("recsys", "Recommendation engine for a {industry} platform", ["Python", "recommendation systems"], ["PyTorch", "FAISS", "Redis", "FastAPI"], 55),
    ],
    "fullstack": [
        ("web_app", "SaaS dashboard for a {industry} startup", ["React", "TypeScript", "Node.js"], ["PostgreSQL", "Tailwind CSS", "Stripe", "OAuth", "Next.js"], 70),
        ("web_app", "Marketing site and CMS for a {industry} brand", ["Next.js", "React"], ["Tailwind CSS", "Vercel", "TypeScript"], 30),
        ("backend", "REST API backend for {industry} mobile app", ["Node.js", "REST API", "PostgreSQL"], ["Express", "NestJS", "Redis", "Docker", "AWS"], 50),
        ("backend", "Django platform for {industry} bookings", ["Django", "PostgreSQL", "Python"], ["Celery", "Redis", "Stripe", "Docker"], 60),
        ("realtime", "Real-time collaboration feature for {industry}", ["WebSockets", "Node.js", "React"], ["Redis", "TypeScript", "MongoDB"], 45),
        ("ecommerce", "Shopify store customisation for {industry}", ["Shopify", "JavaScript"], ["Stripe", "React"], 25),
        ("ecommerce", "Checkout and subscriptions for a {industry} site", ["Stripe", "React", "Node.js"], ["PostgreSQL", "TypeScript", "OAuth"], 35),
        ("api", "GraphQL API for a {industry} product", ["GraphQL", "Node.js", "TypeScript"], ["PostgreSQL", "MongoDB", "Jest"], 45),
        ("testing", "End-to-end test suite for a {industry} web app", ["Playwright", "TypeScript"], ["Jest", "React", "Docker"], 25),
        ("mobile", "Cross-platform mobile app for {industry}", ["React Native", "TypeScript"], ["Node.js", "REST API", "OAuth"], 70),
    ],
    "data_analyst": [
        ("bi", "Executive KPI dashboard in Power BI for {industry}", ["Power BI", "SQL", "dashboard design"], ["Excel", "data cleaning", "ETL"], 30),
        ("bi", "Tableau sales dashboards for a {industry} company", ["Tableau", "SQL", "dashboard design"], ["Snowflake", "data cleaning"], 30),
        ("analytics_eng", "dbt models on Snowflake for {industry}", ["dbt", "SQL", "Snowflake"], ["Fivetran", "ETL", "Looker"], 45),
        ("analytics_eng", "BigQuery warehouse and reporting for {industry}", ["BigQuery", "SQL", "ETL"], ["dbt", "Looker", "Google Analytics 4"], 40),
        ("product_analytics", "Retention and cohort analysis for a {industry} app", ["cohort analysis", "SQL", "Python"], ["pandas", "statistics", "Metabase"], 25),
        ("product_analytics", "A/B test analysis for {industry} growth team", ["A/B testing", "statistics"], ["Python", "R", "SQL"], 20),
        ("web_analytics", "GA4 tracking audit for a {industry} website", ["Google Analytics 4"], ["BigQuery", "Google Sheets", "dashboard design"], 15),
        ("spreadsheet", "Excel financial model clean-up for {industry}", ["Excel", "data cleaning"], ["Google Sheets", "Power BI"], 15),
        ("forecasting", "Sales forecasting in Python for {industry}", ["Python", "pandas", "statistics"], ["R", "Excel"], 25),
        ("research", "Survey data analysis in R for a {industry} study", ["R", "statistics"], ["data cleaning", "Excel"], 20),
    ],
}

OUT_ARCHETYPES = [
    ("out_of_domain", "iOS app for a {industry} brand", ["Swift"], ["Flutter"], 80),
    ("out_of_domain", "Unity mini-game for {industry} marketing", ["Unity"], [], 60),
    ("out_of_domain", "NFT smart contract for a {industry} community", ["Solidity"], [], 30),
    ("out_of_domain", "YouTube video editing for a {industry} channel", ["video editing"], [], 10),
    ("out_of_domain", "Logo and brand kit for a {industry} startup", ["logo design"], [], 10),
    ("out_of_domain", "SEO blog posts for a {industry} site", ["SEO copywriting"], [], 10),
    ("out_of_domain", "Salesforce automation for {industry} sales team", ["Salesforce Apex"], [], 40),
    ("out_of_domain", "Firmware for a {industry} IoT sensor", ["embedded C"], [], 50),
    ("out_of_domain", "Laravel admin panel for {industry}", ["Laravel"], ["PostgreSQL"], 40),
]

PERSONAS = {
    "ai_ml": {
        "freelancer_id": "fl-ai-ml",
        "name": "Ayesha Raza",
        "title": "AI/ML Engineer - LLM apps, RAG and production ML",
        "hourly_floor": 45,
        "years": 6,
        "location": "Lahore, Pakistan",
    },
    "fullstack": {
        "freelancer_id": "fl-fullstack",
        "name": "Bilal Khan",
        "title": "Full-stack Web Developer - React, Node and Django",
        "hourly_floor": 35,
        "years": 7,
        "location": "Islamabad, Pakistan",
    },
    "data_analyst": {
        "freelancer_id": "fl-data",
        "name": "Sana Malik",
        "title": "Data Analyst - BI dashboards, SQL and experimentation",
        "hourly_floor": 30,
        "years": 5,
        "location": "Karachi, Pakistan",
    },
}

GENERIC_OPENINGS = [
    "dear sir", "dear hiring manager", "i am excited to apply", "i have read your job",
    "i am the perfect fit", "hello, i am interested", "i can do this job", "greetings",
    "i am passionate", "to whom it may concern",
]
