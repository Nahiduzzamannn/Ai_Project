# AI PDF RAG Project

A full-stack document intelligence application that lets users upload PDF files, extract text, generate embeddings, store the content in a database, and perform semantic search over the uploaded documents.

This project combines a FastAPI backend with a React + Vite frontend, and is designed around a PDF retrieval workflow powered by OpenAI embeddings and PostgreSQL with pgvector support.

## Project Overview

The application is structured around a simple but practical AI workflow:

1. A user uploads a PDF file from the frontend.
2. The backend validates and saves the PDF.
3. The PDF is parsed page by page using PyMuPDF.
4. Text is split into manageable chunks.
5. Each chunk is converted into an embedding via the OpenAI embeddings API.
6. Chunks and embeddings are stored in a database.
7. A semantic search query generates an embedding and returns the most relevant document chunks.

## Tech Stack

### Frontend
- React 19
- Vite
- JavaScript
- Tailwind CSS

### Backend
- Python 3.12
- FastAPI
- SQLAlchemy
- PostgreSQL + pgvector
- PyMuPDF
- OpenAI Python SDK
- Alembic for database migrations

## Repository Structure

```text
AI_ML_Project/
├── Backend/
│   ├── backend/
│   │   ├── alembic.ini
│   │   ├── app/
│   │   │   ├── api/
│   │   │   │   └── v1/
│   │   │   │       ├── documents.py
│   │   │   │       ├── health.py
│   │   │   │       └── router.py
│   │   │   ├── core/
│   │   │   │   ├── config.py
│   │   │   │   └── deps.py
│   │   │   ├── db/
│   │   │   │   ├── base.py
│   │   │   │   ├── base_imports.py
│   │   │   │   ├── session.py
│   │   │   │   └── migrations/
│   │   │   ├── models/
│   │   │   │   ├── document.py
│   │   │   │   └── document_chunk.py
│   │   │   ├── schemas/
│   │   │   │   └── document.py
│   │   │   ├── services/
│   │   │   │   ├── embedding_service.py
│   │   │   │   └── pdf_parser.py
│   │   │   └── main.py
│   │   └── uploaded_pdfs/
│   └── myenv/
├── Frontend/
│   ├── src/
│   ├── package.json
│   ├── vite.config.js
│   └── index.html
├── .gitignore
├── README.md
└── package-lock.json
```

## Backend Architecture

The backend is organized around a clean FastAPI structure:

- app/main.py: application entry point and CORS setup
- app/core/config.py: environment configuration and app settings
- app/core/deps.py: dependency injection for database access
- app/api/v1/router.py: API routing entry
- app/api/v1/documents.py: document upload and search endpoints
- app/services/pdf_parser.py: PDF text extraction and chunking
- app/services/embedding_service.py: OpenAI embedding generation
- app/models/document.py and document_chunk.py: SQLAlchemy models
- app/db/session.py: database session setup

## API Endpoints

### Health
- GET /api/v1/health

### Document Upload
- POST /api/v1/documents/upload
- Accepts a PDF file
- Saves the file on disk
- Extracts text
- Splits into chunks
- Generates embeddings
- Stores the document and chunks in the database

### Document Search
- GET /api/v1/documents/search
- Accepts a query string and optional top_k value
- Generates an embedding for the query
- Uses pgvector similarity to return the nearest document chunks

## Frontend Features

The frontend is a simple React interface for uploading PDFs and showing upload responses or errors. It uses a file input that validates PDF files before sending them to the backend.

Key features:
- PDF upload form
- Validation for file type
- Loading states
- Error and success feedback
- API base URL configuration through environment variables

## Environment Configuration

Before running the project, configure the required environment variables.

### Backend environment
Create a .env file in the Backend/backend directory with values similar to:

```env
OPENAI_API_KEY=your_openai_api_key
DATABASE_URL=postgresql+psycopg2://postgres:your_password@localhost:5432/AI_ML_project
```

### Frontend environment
The app reads the API base URL from Vite environment variables. For example:

```env
VITE_API_BASE_URL=http://localhost:8000
```

## Run the Project

### 1. Start the backend

```bash
cd Backend/backend
..
```

Then activate the virtual environment and run:

```bash
..\myenv\Scripts\activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Start the frontend

```bash
cd Frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Then open:
- http://localhost:5173

The backend should be available at:
- http://localhost:8000

## Notes

- The backend currently expects PostgreSQL with pgvector enabled.
- The embedding generation depends on a valid OpenAI API key.
- Uploaded PDF files are stored under the uploaded_pdfs directory in the backend project.
- The project is designed as a lightweight AI document search prototype and can be extended with authentication, file metadata, user-level documents, and richer search UX.

## Potential Enhancements

- Add authentication and authorization
- Support document deletion and listing
- Add full-text search fallback
- Improve chunk overlap and preprocessing strategies
- Add vector index tuning for production workloads
- Add a conversational AI layer on top of retrieved chunks
- Build a more advanced dashboard for document management

## Summary

This project demonstrates a practical AI document retrieval workflow using modern Python and React technologies. It is a strong starting point for building document intelligence, enterprise knowledge search, or PDF-based Q&A systems.
