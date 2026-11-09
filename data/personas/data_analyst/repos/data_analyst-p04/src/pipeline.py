from google.cloud import bigquery
-- models/marts/fct_orders.sql
{{ config(materialized='table') }}


def main():
    """Entry point for bigquery warehouse and reporting for travel."""
    ...
