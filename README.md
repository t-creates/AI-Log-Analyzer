# AI Log Analyzer

AI Log Analyzer is a full-stack web application for ingesting, analyzing, and querying system logs using **semantic search and AI-generated insights powered by Gemini 2.5 Flash**. It allows users to upload log files, browse historical events, and ask natural-language questions to quickly identify incidents, patterns, and recommended actions.

The system follows a **retrieval-augmented generation (RAG)** approach: logs are retrieved locally using vector similarity search (FAISS), and Gemini is used only for reasoning and natural-language generation.

---

## What This App Does

- Ingests structured log files (CSV or TXT)
- Stores logs locally and indexes them for semantic search
- Generates AI-assisted summaries of incidents and patterns
- Answers natural-language questions about log data
- Provides a clean web UI for upload, browsing, summary, and search

---

## Features

### Log Ingestion
- Upload CSV or TXT log files
- Automatic validation and parsing
- Tracks ingestion metadata:
  - File ID
  - Number of entries parsed
  - Date range
  - Severity breakdown

### Log Browsing
- List and browse stored log entries
- Filter by source and severity
- Inspect timestamps and messages

### AI Summary
- AI-generated summary of recent incidents
- Highlights:
  - Top incidents
  - Detected patterns
  - Recommended actions
- Designed to surface correlated events across logs

### Semantic Search
- Ask natural-language questions (e.g. *“Were there any pressure drops last week?”*)
- Uses embeddings + FAISS for similarity search
- Returns:
  - AI-generated answer
  - Relevant logs with relevance scores
  - Suggested follow-up actions

### Frontend
- Clean React UI
- Tab-based navigation (Upload, Logs, Summary, Search)
- Loading states and error handling
- Styled with Tailwind CSS

---

## Tech Stack

### Backend
- Python
- FastAPI
- SQLAlchemy (Async)
- SQLite (local database)
- FAISS (vector similarity search)
- Sentence Transformers (`all-MiniLM-L6-v2`)
- **Gemini 2.5 Flash (LLM for summaries and answers)**

### Frontend
- React (Vite, no TypeScript)
- Tailwind CSS
- Fetch API

### AI / Search Architecture
- Local embeddings for deterministic retrieval
- FAISS in-memory index with persistence
- Gemini used only for generation and reasoning
- Clear separation between retrieval and AI generation

---

## Running Locally

### Prerequisites
- Python 3.11+ (recommended for FAISS stability)
- Node.js 18+
- npm

---

## Backend Setup

### 1) Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Create `.env` file

Create a file named `.env` in the backend root directory with the following contents:

```env
ENV=dev
LOG_LEVEL=INFO

DATABASE_URL=sqlite+aiosqlite:///./data/app.db

MAX_UPLOAD_MB=25

EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
FAISS_INDEX_PATH=./data/faiss.index
FAISS_IDMAP_PATH=./data/faiss_idmap.json

GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

> ⚠️ Do not commit your `.env` file.  
> Make sure `.env` is included in `.gitignore`.

---

### 4) Run the backend

```bash
uvicorn app.main:app --workers 1
```

> Note: Use a single worker for FAISS stability during development.

---

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The web app will be available at:

```
http://localhost:5173
```

---

## API Overview

| Endpoint   | Method | Description |
|-----------|--------|-------------|
| `/upload` | POST   | Upload log file (CSV or TXT) |
| `/logs`   | GET    | List and filter stored log entries |
| `/summary`| GET    | Get AI-generated summary of incidents |
| `/query`  | POST   | Natural-language semantic search |

---

## Project Goals

- Demonstrate practical AI-assisted log analysis
- Show safe integration of FAISS and embeddings in a web app
- Provide a stable baseline for RAG-style applications
- Serve as a foundation for observability and monitoring tools

---

## Future Enhancements

- Authentication and multi-tenant support
- Background re-indexing jobs
- Alerting and anomaly detection
- Time-series visualizations
- Cloud deployment and scalable storage

---

## Notes

- FAISS runs locally and persists to disk
- Embeddings and search are deterministic
- Gemini is used only after retrieval to generate grounded responses
- The architecture is intentionally modular to allow future LLM or embedding swaps
