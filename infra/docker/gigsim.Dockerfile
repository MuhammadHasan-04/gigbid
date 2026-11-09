# GigSim marketplace simulator (stand-in; see gigsim/README.md).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
RUN pip install --no-cache-dir fastapi==0.162.2 "uvicorn[standard]==0.54.0" pyyaml==6.0.3 pydantic==2.14.3 reportlab==5.1.0
COPY gigsim gigsim
COPY data/gigsim data/gigsim
COPY data/policy_pack data/policy_pack
EXPOSE 8081
CMD ["uvicorn", "gigsim.server:app", "--host", "0.0.0.0", "--port", "8081"]
