# Aura Intelligence — RAG AI Assistant

A full-stack **Retrieval-Augmented Generation (RAG)** application that lets you upload documents (PDF, TXT, MD, CSV, JSON), automatically extracts and indexes their content, and answers questions about them using an LLM powered by the Groq API.

---

## Features

- **Document Upload** — Drag-and-drop or click to upload PDFs, text files, and more
- **Automatic Text Extraction** — PDFs are parsed with `pdfplumber`; text files are read directly
- **Chunking & Indexing** — Documents are split into overlapping chunks and stored in SQLite for fast keyword-based retrieval
- **RAG-Powered Chat** — Ask questions in natural language; the system retrieves relevant document chunks and sends them as context to the Groq LLM
- **Source Citations** — Every AI response includes the source document name and page number
- **Conversation History** — Chat threads are persisted in SQLite with full message history
- **Apple-Inspired UI** — Clean, glassmorphic frontend built with Tailwind CSS

---

## Project Structure

```
Rag_AI/
├── .env                        # Environment variables (API keys, DB path)
├── requirements.txt            # Python dependencies
├── backend/
│   ├── main.py                 # Flask server — API routes, RAG pipeline, document processing
│   └── uploads/                # Uploaded documents stored here
├── database/
│   └── data.db                 # SQLite database (auto-created on first run)
├── frontend/
│   └── index.html              # Single-page frontend (Tailwind CSS + vanilla JS)
└── venv/                       # Python virtual environment
```

---

## Prerequisites

- **Python 3.10+**
- **Groq API Key** — Get one free at [console.groq.com](https://console.groq.com)

---

## Setup & Installation

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd Rag_AI
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

Activate it:

| OS | Command |
|---|---|
| **Windows** | `venv\Scripts\activate` |
| **macOS / Linux** | `source venv/bin/activate` |

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `Flask` + `flask-cors` — Web server
- `pdfplumber` — PDF text extraction
- `python-dotenv` — Environment variable loading
- `requests` — HTTP client for Groq API calls

### 4. Configure environment variables

Create or edit the `.env` file in the project root:

```env
DATABASE_PATH=database/data.db
GROQ_API_KEY=your_groq_api_key_here
```

> Replace `your_groq_api_key_here` with your actual Groq API key.

---

## Running the Application

### Start the server

```bash
cd backend
python main.py
```

The server starts at **http://127.0.0.1:5000**

### Open the frontend

Navigate to **http://127.0.0.1:5000** in your browser.

---

## How It Works

### Upload Flow

1. User uploads a document via the UI
2. File is saved to `backend/uploads/`
3. Text is extracted (PDF via `pdfplumber`, text files directly)
4. Extracted text is split into ~800-character overlapping chunks
5. Chunks are stored in the `document_chunks` SQLite table with page numbers
6. Document status is set to `indexed`

### Chat Flow

1. User sends a message
2. System searches `document_chunks` for chunks matching query keywords
3. Top 5 most relevant chunks are retrieved
4. Chunks + conversation history + system prompt are sent to the Groq LLM
5. LLM responds with source citations (document name + page number)
6. Response and sources are saved to the conversation history

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serve frontend |
| `GET` | `/api/health` | Health check (returns doc count, chunk count, Groq status) |
| `POST` | `/api/upload` | Upload documents (multipart form, field: `files`) |
| `GET` | `/api/documents` | List all uploaded documents |
| `DELETE` | `/api/documents/<id>` | Delete a document and its chunks |
| `POST` | `/api/chat` | Send a chat message (JSON: `message`, optional `conversation_id`) |
| `GET` | `/api/conversations` | List all conversations |
| `POST` | `/api/conversations` | Create a new conversation |
| `DELETE` | `/api/conversations/<id>` | Delete a conversation and its messages |
| `GET` | `/api/conversations/<id>/messages` | Get messages for a conversation |

---

## Supported File Types

| Extension | Type |
|-----------|------|
| `.pdf` | PDF document (full text extraction via `pdfplumber`) |
| `.txt` | Plain text |
| `.md` | Markdown |
| `.csv` | CSV data |
| `.json` | JSON data |
| `.docx` / `.doc` | Word document (saved but text extraction limited) |

---

## Configuration

All configuration is via environment variables in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_PATH` | `database/data.db` | Path to SQLite database |
| `GROQ_API_KEY` | *(empty)* | **Required** — Groq API key for LLM responses |

---

## Troubleshooting

### "AI service error" or no response
- Verify `GROQ_API_KEY` is set correctly in `.env`
- Check your Groq API key is active at [console.groq.com](https://console.groq.com)

### Document uploads but chat says "no documents indexed"
- Check `/api/health` — if `chunks_indexed` is 0, the file may be empty or an unsupported format
- Restart the server — it auto-indexes unindexed documents on startup

### Port already in use
- Kill any process using port 5000:
  ```bash
  # Windows
  netstat -ano | findstr :5000
  taskkill /PID <pid> /F
  ```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | HTML, Tailwind CSS, Vanilla JS |
| Backend | Python, Flask |
| Database | SQLite3 |
| PDF Parsing | pdfplumber |
| LLM | Groq API (OpenAI-compatible) |
| Styling | Apple-inspired glassmorphism UI |
