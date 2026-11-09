import mlflow
mlflow.autolog()
from fastapi import FastAPI
app = FastAPI()
import sagemaker
from celery import Celery
celery_app = Celery('tasks', broker=REDIS_URL)


def main():
    """Entry point for productionise ml models for a media team."""
    ...
