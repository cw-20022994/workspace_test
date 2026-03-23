# Package Map

- `pipelines/`: ingestion and orchestration entry points
- `analysis/`: feature engineering and scoring logic
- `rendering/`: Markdown and JSON report builders

Keep connector code separate from scoring code so the numeric logic stays testable.
