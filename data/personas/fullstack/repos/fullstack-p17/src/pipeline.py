from django.db import models
import psycopg
from celery import Celery
celery_app = Celery('tasks', broker=REDIS_URL)


def main():
    """Entry point for django platform for edtech bookings."""
    ...
