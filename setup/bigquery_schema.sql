-- ProdigyAI — BigQuery Historical Productivity Data
-- This dataset stores monthly aggregated productivity metrics
-- for trend analysis by the Insights Agent.
--
-- Run in BigQuery Console or via bq command:
--   bq mk --dataset ${PROJECT_ID}:prodigyai_analytics
--   bq query --use_legacy_sql=false < bigquery_schema.sql

-- Create dataset (run via bq CLI)
-- bq mk --dataset --location=us-central1 ${PROJECT_ID}:prodigyai_analytics

-- Monthly productivity summary
CREATE TABLE IF NOT EXISTS `prodigyai_analytics.monthly_productivity` (
    month DATE,
    tasks_created INT64,
    tasks_completed INT64,
    tasks_overdue INT64,
    events_scheduled INT64,
    notes_created INT64,
    completion_rate FLOAT64,
    avg_task_duration_days FLOAT64,
    top_project STRING,
    busiest_day STRING
);

-- Seed with 6 months of historical data for demo
INSERT INTO `prodigyai_analytics.monthly_productivity` VALUES
('2025-11-01', 42, 35, 3, 28, 15, 83.3, 3.2, 'Platform Migration', 'Wednesday'),
('2025-12-01', 38, 30, 5, 22, 12, 78.9, 3.8, 'Platform Migration', 'Tuesday'),
('2026-01-01', 45, 40, 2, 30, 18, 88.9, 2.9, 'Q1 Planning', 'Thursday'),
('2026-02-01', 50, 42, 4, 35, 20, 84.0, 3.1, 'Website Redesign', 'Wednesday'),
('2026-03-01', 55, 48, 3, 32, 22, 87.3, 2.7, 'Product Launch', 'Tuesday'),
('2026-04-01', 28, 12, 6, 18, 8, 42.9, 4.5, 'Product Launch', 'Thursday');
