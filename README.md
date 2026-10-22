# AI Question Generator (PDF RAG)

A full-stack app for teachers: upload a textbook PDF, find a chapter, let a free AI agent write questions from it, keep them in a question bank, and print shuffled multi-set question papers.

## Features

1. **Upload a PDF.** The text is split into chunks and chapters. Chunks are embedded into **pgvector** and indexed in **Elasticsearch**.
   - Chapters are detected from the PDF's bookmarks, or from "Chapter N / Unit N / Lesson N" headings. You can also add a chapter by page range.
2. **Search for a chapter.** Hybrid search combines Elasticsearch BM25 keyword search with pgvector semantic search, using Reciprocal Rank Fusion. For example, both "Photosynthesis" and "how plants make food" find the right chapter.
3. **AI Question Chat (RAG).** Choose a scope (all documents, one PDF, or one chapter) and chat with the AI. Examples: "Give me 5 MCQ on the Calvin cycle", "make Q2 harder", "summarize this chapter", or ask in Bangla.
   - Every message retrieves the relevant chunks (pgvector + Elasticsearch, fused with RRF) and the AI answers only from them, citing sources like [1] with page numbers.
   - In chapter scope, chunks spread across the whole chapter are added too, so a request like "5 MCQ from this chapter" covers all of it.
   - Questions appear as cards in the chat. Tick the ones you want and save them to the question bank.
   - The chat history is kept in the browser and sent with each request, so follow-ups work.
4. **Question bank.**
   - Add questions by hand, bulk upload them from CSV or JSON, or save AI-generated ones.
   - View them with full-text search (Elasticsearch, typo-tolerant) and filters for type, topic, difficulty, source and document.
   - Edit or delete questions.
5. **Question paper PDF.** Build a paper in one of two ways:
   - pick specific questions from the bank, or
   - ask for "N MCQ + N short + N broad" picked at random, with optional filters.

   You can then:
   - generate **several sets (A, B, C...)**, with question order and MCQ options shuffled per set;
   - add an answer key for each set;
   - give a seed so the same paper can be rebuilt.

## Tech Stack

| Part | Technology |
|---|---|
| Frontend | React 19, Vite, Tailwind CSS 4 |
| API | FastAPI, SQLAlchemy, Alembic |
| Database + vector DB | PostgreSQL + **pgvector** |
| Keyword search | **Elasticsearch 8** (optional; falls back to Postgres search if it's not running) |
| Embeddings | **fastembed** `BAAI/bge-small-en-v1.5`. It runs locally on CPU, is free, and needs no API key |
| AI agent | **Groq** free API (`openai/gpt-oss-120b`), called through the OpenAI SDK. Any OpenAI-compatible API works, e.g. Google Gemini's free tier |
| PDF | PyMuPDF (reading), ReportLab (question papers) |

## Setup

### 1. Get a free AI API key

Create a free key at https://console.groq.com/keys. Then put it in `Backend/backend/.env`:

```env
DATABASE_URL=postgresql+psycopg2://postgres:your_password@localhost:5432/AI_ML_project
LLM_API_KEY=gsk_your_groq_key
ELASTICSEARCH_URL=http://localhost:9200
```

To use **Google Gemini** (also free) instead, add these lines. Get the key at https://aistudio.google.com/apikey.

```env
LLM_API_KEY=your_gemini_key
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_MODEL=gemini-2.5-flash
```

### 2. Start Elasticsearch (optional but recommended)

**Windows (no Docker):**
1. Download the Elasticsearch 8 zip from https://www.elastic.co/downloads/elasticsearch and extract it.
2. Add these lines to `config/elasticsearch.yml`:

   ```yaml
   xpack.security.enabled: false
   discovery.type: single-node
   network.host: 127.0.0.1
   ```
3. Run `bin\elasticsearch.bat`.

**Docker:**

```bash
docker run -d --name es -p 9200:9200 -e discovery.type=single-node -e xpack.security.enabled=false -e ES_JAVA_OPTS="-Xms1g -Xmx1g" docker.elastic.co/elasticsearch/elasticsearch:8.19.3
```

If you start Elasticsearch after data already exists, copy that data in with `POST /api/v1/search/sync`.

### 3. Backend

```bash
cd Backend
myenv\Scripts\activate
pip install -r backend/requirements.txt
cd backend
alembic upgrade head
python -m uvicorn app.main:app --port 8000 --reload
```

The first upload downloads the embedding model (~70 MB), once.

API docs: http://localhost:8000/docs

### 4. Frontend

```bash
cd Frontend
npm install
npm run dev
```

Open http://localhost:5173. The header shows whether the API, Elasticsearch and the AI key are working.

## API Overview

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/health` | Status of the API, Elasticsearch and the AI agent |
| POST | `/api/v1/search/sync` | Copy all data from Postgres into Elasticsearch |
| POST | `/api/v1/documents/upload` | Upload a PDF. It is chunked and chapter-split, then embedded and indexed |
| GET | `/api/v1/documents` | List documents |
| POST | `/api/v1/documents/{id}/reindex` | Rebuild embeddings, chapters and indexes |
| DELETE | `/api/v1/documents/{id}` | Delete a document |
| GET | `/api/v1/documents/search?q=` | Semantic chunk search (pgvector) |
| GET/POST | `/api/v1/documents/{id}/chapters` | List chapters, or add one by page range |
| GET | `/api/v1/chapters/search?q=&document_id=` | Hybrid chapter search |
| GET/DELETE | `/api/v1/chapters/{id}` | Chapter text, or delete the chapter |
| POST | `/api/v1/chat` | RAG chat: `{messages, chapter_id?, document_id?}` returns `{reply, questions, sources}` |
| POST | `/api/v1/chapters/{id}/generate-questions` | One-shot question generation, without chat |
| GET | `/api/v1/questions` | List questions, with search and filters |
| POST | `/api/v1/questions` · `/questions/bulk` | Add one question · add many |
| POST | `/api/v1/questions/upload` | Bulk import from CSV or JSON |
| GET | `/api/v1/questions/template.csv` | CSV template |
| PUT/DELETE | `/api/v1/questions/{id}` | Edit or delete a question |
| POST | `/api/v1/questions/paper` | Build the multi-set shuffled question paper PDF |

### CSV format for question upload

```csv
text,qtype,options,answer,marks,difficulty,topic
What is the powerhouse of the cell?,mcq,Nucleus|Mitochondria|Ribosome|Golgi body,Mitochondria,1,easy,Cell Biology
Plants make food by photosynthesis.,true_false,,True,1,easy,Plants
Define osmosis.,short,,Movement of water across a membrane...,2,medium,Cell Biology
```

`qtype` is one of `mcq`, `true_false`, `short` or `broad`. A JSON upload is a list of objects with the same fields, where `options` is an array.

## Notes

- Scanned (image-only) PDFs have no extractable text. Run OCR on them first.
- Free AI tiers have rate limits. `LLM_CONTEXT_CHARS` (default 12000) caps how much chapter text is sent per request.
