# Trustworthy Model Registry

A registry for ML artifacts with trust metrics and lineage tracking.

## Features

- **Artifact Management**: CRUD operations for models, datasets, and notebooks
- **Trust Metrics**: Automated rating with reproducibility, reviewedness, and treescore
- **HuggingFace Ingest**: Import models directly from HuggingFace
- **Lineage Tracking**: Track parent-child relationships between artifacts
- **Search**: Regex-based artifact search
- **Health Monitoring**: System health endpoints with component status
- **S3 Storage**: Artifact blob storage with presigned URLs

## Quick Start

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd Software-Engineering-Project

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Server

```bash
# Development mode
python run.py

# Or with uvicorn directly
uvicorn src.api.main:app --reload

# Production mode
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

The server will start at http://localhost:8000

### API Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## API Endpoints

### Artifacts

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/artifacts/{type}` | Create artifact |
| GET | `/artifacts` | List artifacts |
| GET | `/artifacts/{type}/{id}` | Get artifact |
| DELETE | `/artifacts/{type}/{id}` | Delete artifact |
| GET | `/artifacts/{type}/{id}/download` | Download artifact |
| POST | `/reset` | Reset registry |

### Rating

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/artifacts/{type}/{id}/rating` | Rate artifact |
| GET | `/artifacts/{type}/{id}/rating` | Get latest rating |

### Ingest & Search

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ingest` | Ingest from HuggingFace |
| GET | `/artifacts/search?query={regex}` | Search artifacts |

### Lineage & Cost

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/artifacts/{id}/lineage` | Get lineage graph |
| POST | `/artifacts/{id}/lineage` | Add lineage edge |
| GET | `/artifacts/{id}/cost` | Get storage cost |
| POST | `/license-check` | Check license compatibility |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Aggregate health stats |
| GET | `/health/components` | Component status |

## Configuration

Environment variables:

```bash
# Database (default: SQLite)
DATABASE_URL=sqlite:///./registry.db

# AWS S3
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_REGION=us-east-1
S3_BUCKET=your-bucket

# Server
HOST=0.0.0.0
PORT=8000
```

## Testing

```bash
# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run smoke test (requires server running)
python scripts/autograder-smoke-test.py
```

## Project Structure

```
├── src/
│   ├── api/
│   │   ├── main.py           # FastAPI application
│   │   ├── routes/           # API endpoints
│   │   ├── models/           # Pydantic schemas
│   │   ├── db/               # Database layer
│   │   ├── storage/          # S3 adapter
│   │   └── services/         # Business logic
│   ├── cli.py                # Phase 1 CLI (legacy)
│   └── metrics.py            # Phase 1 metrics (legacy)
├── static/                   # Frontend files
├── tests/                    # Test suite
├── docs/                     # Documentation
└── .github/workflows/        # CI/CD
```

## Frontend

Access the web UI at http://localhost:8000/static/index.html

Pages:
- **Artifacts**: Browse and search artifacts
- **Upload**: Create new artifacts or ingest from HuggingFace
- **Health**: System health dashboard

## Deployment

See [docs/deploy-aws-ec2.md](docs/deploy-aws-ec2.md) for AWS EC2 deployment instructions.

## Development

```bash
# Install dev dependencies
pip install -r requirements.txt

# Run linter
ruff check .

# Format code
ruff format .

# Run tests with coverage
pytest tests/ --cov=src --cov-report=term-missing
```

## License

MIT License
