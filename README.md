# Aura Intelligence — RAG AI Assistant

A full-stack **Retrieval-Augmented Generation (RAG)** application that lets you upload documents, automatically extracts and indexes their content into a local SQLite database, and answers natural-language questions about them using an LLM via the **Groq API** (`openai/gpt-oss-120b`).

---

## 🎥 Project Demo

Watch the full demonstration below to see Aura Intelligence in action, including document upload, RAG chat, analysis modes, document comparison, and the overall workflow.

> **[▶ Click here to watch the full demo video](https://github.com/DASPINAKI2005/Rag_AI/blob/master/Video%20Project%203.mp4)** — opens GitHub's built-in video player.

---

## Overview

Aura Intelligence is a self-contained document Q&A system. Users upload files through a glassmorphic Apple-inspired web interface; the backend extracts text, chunks it, and stores it in SQLite. When the user asks a question, the system retrieves the most relevant chunks using keyword-based scoring, injects them as context into an LLM prompt, and returns a cited, structured answer.

The entire application runs on a single Flask server — no external databases, no Docker, no build step.

---

## Key Features

- **Document Upload & Indexing** — Upload PDFs, text files, Markdown, CSV, and JSON. Text is extracted, chunked into ~800-character overlapping segments, and stored in SQLite for retrieval.
- **RAG-Powered Chat** — Ask questions in natural language. The system retrieves the top-5 most relevant document chunks and sends them as context to the Groq LLM.
- **Source Citations** — Every AI response includes the source document name, page number, and a relevance match percentage.
- **6 Analysis Modes** — Ask (default Q&A), Summarize, Compare, Extract, Explain, and Quiz Me — each tailoring the LLM system prompt differently.
- **Response Style Controls** — Adjust response tone: Shorter, Detailed, Simplify, Professional, Technical.
- **Document Comparison** — Side-by-side comparison of two documents with AI-generated similarity analysis, unique keywords, and structured difference report.
- **Document Health Panel** — Per-document metadata: chunk count, page count, content type, file size, and retrieval status.
- **Voice Input** — Browser-native speech-to-text via the Web Speech API, with real-time transcript, pause/resume, and accept/cancel controls.
- **Conversation Branching** — Fork a conversation from any point to explore alternative follow-up paths.
- **Follow-Up Suggestions** — Contextual post-response chips (Explain further, Show evidence, Compare sources, Summarize, Deeper question).
- **"Ask This Section"** — Select a portion of an AI response and ask a follow-up scoped to that passage.
- **Prompt Library** — Save, reuse, and manage frequently used prompts (persisted in `localStorage`).
- **Export / Import** — Export conversations as Markdown, plain text, JSON, or print-friendly HTML. Import from JSON.
- **Share Modal** — Share responses via clipboard, email, WhatsApp, Twitter/X, or LinkedIn.
- **Smart Draft Recovery** — Unsent input is automatically saved to `localStorage` and restored on reload.
- **API Key Management** — Runtime Groq API key configuration through a modal UI; key is persisted in `backend/config.json`.
- **Mobile-Responsive** — Desktop sidebar + mobile slide-out overlay; voice controls and file selector adapt to smaller screens.

---

## Architecture

```
User (Browser)
│
├── Frontend (index.html — single-page app)
│   ├── Tailwind CSS + vanilla JS
│   ├── Voice input (Web Speech API)
│   └── localStorage (drafts, prompt library)
│
└── Backend (Flask — main.py)
    ├── REST API (Flask routes)
    ├── Document Processing (pdfplumber / text read)
    ├── Chunking & Indexing (SQLite)
    ├── Keyword Retrieval (word-match scoring)
    ├── Groq LLM Integration (openai/gpt-oss-120b)
    └── SQLite Database (data.db)
```

### Request Flow

```
User sends message
  → Frontend POST /api/chat
    → Backend creates/retrieves conversation
    → Backend runs keyword search on document_chunks
    → Top-5 chunks retrieved
    → System prompt built: persona + available docs + retrieved chunks + mode + style
    → POST to Groq API (openai/gpt-oss-120b, temperature 0.7, max 1024 tokens)
    → AI response + source metadata returned
    → Response saved to messages table
    → Frontend renders markdown + source chips + confidence badge + follow-ups
```

### Document Ingestion Flow

```
User uploads file(s)
  → Frontend POST /api/upload (multipart/form-data)
    → File saved to backend/uploads/
    → Text extracted (pdfplumber for PDFs, direct read for text files)
    → Text split into ~800-char chunks (150-char overlap)
    → Chunks stored in document_chunks table
    → Document status set to 'indexed'
    → On server startup, any un-indexed documents are auto-re-indexed
```

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Frontend** | HTML5, Tailwind CSS (CDN), Vanilla JavaScript | Single-page UI with glassmorphic design |
| **Fonts** | Google Fonts — Plus Jakarta Sans, Material Symbols Outlined | Typography and iconography |
| **Backend** | Python 3.10+, Flask 2.3.3 | HTTP server and REST API |
| **CORS** | flask-cors 4.0.0 | Cross-origin request handling |
| **PDF Parsing** | pdfplumber 0.11.4 | Page-level text extraction from PDFs |
| **Text Files** | Python built-in (`open`) | Direct UTF-8 read for .txt, .md, .csv, .json |
| **Database** | SQLite3 (built-in) | Conversation/message/document/chunk storage |
| **LLM** | Groq API — `openai/gpt-oss-120b` (120B MoE, Apache 2.0) | RAG response generation |
| **HTTP Client** | requests 2.34.2 | Groq API calls |
| **Config** | python-dotenv 1.0.0 | `.env` file loading |
| **Runtime Config** | `backend/config.json` | Persistent API key storage (runtime) |

---

## Project Structure

```
Rag_AI/
├── .env                        # Environment variables (API keys, DB path)
├── .gitignore                  # Git ignore rules
├── requirements.txt            # Python dependencies (5 packages)
├── README.md                   # This file
├── backend/
│   ├── main.py                 # Flask server — all API routes, RAG pipeline, document processing
│   ├── config.json             # Runtime config — persisted Groq API key (auto-created, gitignored)
│   ├── uploads/                # Uploaded documents stored here (gitignored)
│   ├── database/
│   │   └── data.db             # SQLite database (auto-created on first run, gitignored)
│   └── __pycache__/            # Python bytecode cache
├── database/                   # Alternate DB path (used if DATABASE_PATH points here)
├── frontend/
│   └── index.html              # Single-page frontend (~2300 lines: HTML + CSS + JS)
└── venv/                       # Python virtual environment (gitignored)
```

---

## Backend — `backend/main.py`

The entire backend is a single 887-line Python file organized into clearly separated sections.

### Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `DATABASE_PATH` | `database/data.db` | SQLite database file path (from `.env`) |
| `UPLOAD_FOLDER` | `backend/uploads/` | Where uploaded files are saved |
| `MAX_CONTENT_LENGTH` | 32 MB | Maximum upload file size |
| `CHUNK_SIZE` | 800 characters | Target size for each text chunk |
| `CHUNK_OVERLAP` | 150 characters | Overlap between consecutive chunks |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | LLM model identifier |
| `GROQ_API_URL` | `https://api.groq.com/openai/v1/chat/completions` | Groq API endpoint |

### Database Schema (SQLite)

**`conversations`** — Chat sessions

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-incrementing ID |
| `title` | TEXT | Conversation title (truncated user message) |
| `created_at` | TIMESTAMP | Creation time |

**`messages`** — Individual chat messages

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-incrementing ID |
| `conversation_id` | INTEGER FK | References `conversations.id` (CASCADE DELETE) |
| `role` | TEXT | `user` or `assistant` |
| `content` | TEXT | Message text |
| `sources` | TEXT | JSON-encoded source metadata (for assistant messages) |
| `created_at` | TIMESTAMP | Creation time |

**`documents`** — Uploaded files

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-incrementing ID |
| `name` | TEXT | Original filename (sanitized via `secure_filename`) |
| `size` | INTEGER | File size in bytes |
| `status` | TEXT | `uploaded`, `indexed`, or `empty` |
| `uploaded_at` | TIMESTAMP | Upload time |

**`document_chunks`** — Indexed text segments

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-incrementing ID |
| `document_id` | INTEGER FK | References `documents.id` (CASCADE DELETE) |
| `chunk_index` | INTEGER | Sequential position within the document |
| `page` | INTEGER | Source page number (1 for text files) |
| `content` | TEXT | The chunk text |

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serve `frontend/index.html` |
| `GET` | `/api/health` | Health check — returns Groq config status, document count, chunk count |
| `POST` | `/api/upload` | Upload documents (multipart, field: `files`) — extracts text, chunks, indexes |
| `GET` | `/api/documents` | List all uploaded documents |
| `DELETE` | `/api/documents/<id>` | Delete a document, its chunks, and the uploaded file |
| `GET` | `/api/documents/<id>/health` | Per-document health: chunk count, page count, content type, retrievability |
| `POST` | `/api/chat` | Send a chat message — triggers RAG pipeline and returns AI response |
| `GET` | `/api/conversations` | List all conversations (sorted by creation time, descending) |
| `POST` | `/api/conversations` | Create a new conversation |
| `DELETE` | `/api/conversations/<id>` | Delete a conversation and all its messages |
| `GET` | `/api/conversations/<id>/messages` | Get all messages for a conversation |
| `POST` | `/api/conversations/<id>/branch` | Fork a conversation from a specific message |
| `POST` | `/api/compare` | Compare two documents (Jaccard similarity + optional AI analysis) |
| `GET` | `/api/config/groq-key` | Check if Groq API key is configured (returns masked key) |
| `POST` | `/api/config/groq-key` | Save a new Groq API key to `backend/config.json` |

### Chat Request Body (`POST /api/chat`)

```json
{
  "message": "What are the key constraints?",
  "conversation_id": 5,
  "document_id": 3,
  "mode": "summarize",
  "style": "detailed",
  "section_context": "The user selected this passage: ...",
  "branch_from": null
}
```

All fields except `message` are optional. If `conversation_id` is omitted, a new conversation is created automatically.

### Chat Response

```json
{
  "conversation_id": 5,
  "response": "Based on the architecture document...",
  "sources": [
    {
      "name": "architecture.pdf",
      "page": 3,
      "match": 80,
      "excerpt": "Key constraints include..."
    }
  ],
  "followups": ["Show me the evidence for that", "Summarize this response"],
  "mode": "summarize"
}
```

### Analysis Modes

Each mode modifies the LLM system prompt:

| Mode | Behavior |
|------|----------|
| *(none/ask)* | Standard Q&A — answer the question directly and thoroughly |
| `summarize` | Concise summary organized by themes, with bullet points and executive summary |
| `compare` | Structured comparison identifying similarities, differences, contradictions, and gaps |
| `extract` | Structured extraction of data points, facts, figures, dates, and specifications |
| `explain` | Concept explanation from basic to advanced, using analogies and simple language |
| `quiz` | Generate 5-8 quiz questions (MC + short answer) with answers and source citations |

### Response Styles

Each style appends additional instructions to the system prompt:

| Style | Effect |
|-------|--------|
| `shorter` | Brief and concise, bullet points, max 3-4 paragraphs |
| `detailed` | Extremely comprehensive, covering every aspect |
| `simplify` | Simple everyday language, no jargon, beginner-friendly |
| `professional` | Formal tone suitable for business documents |
| `technical` | Precise terminology, expert audience assumed |

### Retrieval Algorithm

The retrieval system uses **keyword-based scoring** (not semantic/embedding search):

1. The user query is tokenized into words (lowercased, filtered to >2 characters)
2. All chunks from indexed documents are fetched from SQLite
3. Each chunk is scored by counting how many query words appear in it
4. Chunks are sorted by score (descending), top 5 returned
5. A relevance match percentage is calculated: `min(99, 50 + score × 10)`

This is a simple but effective approach for exact-match retrieval. It does not use vector embeddings or semantic similarity.

---

## Frontend — `frontend/index.html`

A single 2,298-line HTML file containing all markup, styles, and JavaScript. No build step, no bundler, no framework — pure vanilla JS with Tailwind CSS via CDN.

### External Dependencies (CDN)

| Resource | Purpose |
|----------|---------|
| `tailwindcss.com` (script) | Utility-first CSS framework |
| Google Fonts — Plus Jakarta Sans | Primary typeface |
| Google Fonts — Material Symbols Outlined | Icon system |

### UI Sections

| Section | Description |
|---------|-------------|
| **Desktop Sidebar** | Brand, new chat, navigation tabs, conversation history, document list with upload |
| **Mobile Sidebar** | Slide-out overlay version of the desktop sidebar |
| **Main Header** | View badge, header title, action buttons (prompt library, compare, export, clear) |
| **Chat Workspace** | Welcome screen, message container, mode selector bar, input area with file selector and voice button |
| **Knowledge Base Tab** | Document grid with health panels and quick-action buttons |
| **Settings Tab** | Preferences (citation verification, response speed, API key management) |
| **Modals** | API key setup, document compare, prompt library, export/import, share |

### JavaScript State

The frontend maintains minimal global state:

```javascript
currentConversationId  // Active conversation ID (null = new)
isProcessing           // Prevents duplicate sends
selectedDocumentId     // Filter to a specific document (null = all)
documentsList          // Cached document list
currentStyle           // Active response style modifier
pendingSectionContext  // Text from "Ask This Section" feature
```

### Key Frontend Features

- **Markdown Rendering** — Client-side markdown-to-HTML conversion (code blocks with copy buttons, headings, bold/italic, lists, blockquotes, tables, links, horizontal rules)
- **XSS Protection** — All user-facing content is escaped via `escapeHtml()` before rendering; only the AI response uses `formatContent()` which operates on escaped HTML
- **Voice Input** — Web Speech API integration with continuous recognition, interim results, pause/resume, and accept/cancel workflow
- **Draft Persistence** — Unsent input saved to `localStorage` key `aura_chat_draft`, restored on page load
- **Prompt Library** — Saved prompts stored in `localStorage` key `aura_prompt_library`
- **File Source Selector** — Dropdown to filter chat context to a specific document

---

## Configuration

### Environment Variables (`.env`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_PATH` | No | `database/data.db` | Path to SQLite database file |
| `GROQ_API_KEY` | Yes | *(empty)* | Groq API key for LLM access |

Example:

```env
DATABASE_PATH=database/data.db
GROQ_API_KEY=YOUR_GROQ_API_KEY
```

### Runtime Configuration (`backend/config.json`)

The Groq API key can also be set at runtime through the UI. This persists the key to `backend/config.json` (gitignored). The runtime config takes precedence over the `.env` value.

```json
{
  "groq_api_key": "gsk_..."
}
```

### API Key Priority

1. `backend/config.json` (set via UI) — highest priority
2. `.env` `GROQ_API_KEY` — fallback

---

## Installation

### Prerequisites

- **Python 3.10+**
- **Groq API Key** — Get one free at [console.groq.com/keys](https://console.groq.com/keys)

### Setup

```bash
# 1. Clone the repository
git clone <your-repo-url>
cd Rag_AI

# 2. Create a virtual environment
python -m venv venv

# 3. Activate it
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Configure environment variables
# Edit .env and set GROQ_API_KEY (or configure it via the UI after starting)
```

### Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| Flask | 2.3.3 | Web framework |
| flask-cors | 4.0.0 | CORS handling |
| python-dotenv | 1.0.0 | `.env` file loading |
| requests | 2.34.2 | HTTP client for Groq API |
| pdfplumber | 0.11.4 | PDF text extraction |

---

## Running the Application

```bash
cd backend
python main.py
```

The server starts at **http://127.0.0.1:5000** (all interfaces: `0.0.0.0:5000`).

On first launch:
1. SQLite database and tables are created automatically
2. `backend/uploads/` directory is created
3. Any previously uploaded but un-indexed documents are auto-re-indexed
4. If no Groq API key is configured, an API key setup modal appears in the frontend

Navigate to **http://127.0.0.1:5000** in your browser.

---

## Supported File Types

| Extension | Type | Text Extraction |
|-----------|------|-----------------|
| `.pdf` | PDF document | Full extraction via `pdfplumber` (page-level) |
| `.txt` | Plain text | Direct UTF-8 read |
| `.md` | Markdown | Direct UTF-8 read |
| `.csv` | CSV data | Direct UTF-8 read |
| `.json` | JSON data | Direct UTF-8 read |
| `.docx` | Word document | Saved to disk, **text extraction not implemented** |
| `.doc` | Word document (legacy) | Saved to disk, **text extraction not implemented** |

> **Note:** `.docx` and `.doc` files are accepted and stored but cannot be indexed for retrieval because text extraction for these formats is not implemented. They will show as status `empty`.

---

## Security

### Authentication & Authorization

This application has **no authentication or authorization system**. It is designed for local/personal use. Anyone with network access to port 5000 can:
- Upload and delete documents
- Read and manage conversations
- Configure the Groq API key
- Access all indexed content

### CORS

CORS is restricted to `http://127.0.0.1:5000` and `http://localhost:5000` via Flask-CORS configuration.

### API Key Storage

- The Groq API key is stored in plaintext in either `.env` or `backend/config.json`
- Both files are gitignored to prevent accidental commits
- The `/api/config/groq-key` GET endpoint returns only a masked version of the key (e.g., `gsk_****XYZW`)
- The key is transmitted to the Groq API over HTTPS

### SQL Injection

All database queries use parameterized placeholders (`?`), preventing SQL injection.

### XSS (Cross-Site Scripting)

- User-provided content is escaped via `escapeHtml()` before DOM insertion
- AI responses are escaped before markdown rendering via `formatContent()`
- The `formatContent()` function operates on already-escaped HTML and only wraps content in safe structural elements (`<h2>`, `<p>`, `<ul>`, `<code>`, etc.)
- The `onclick` handler on code block copy buttons uses a global function rather than inline HTML event handlers with unsanitized content

### File Upload Security

- Filenames are sanitized via Werkzeug's `secure_filename()`
- File extensions are validated against a whitelist
- Maximum upload size is enforced at 32 MB
- Uploaded files are stored in a dedicated `uploads/` directory

### Known Security Concerns

1. **No authentication** — The application is fully open to anyone on the network. Not suitable for shared or production environments without adding auth.
2. **Plaintext API key storage** — The Groq API key is stored in plaintext on disk. Consider environment-variable-only configuration for production.
3. **No rate limiting** — API endpoints have no rate limiting. The Groq API itself enforces its own rate limits.
4. **`backend/config.json` stores API key** — This file is created by the runtime and gitignored, but could be read by any process with filesystem access.
5. **Word document text extraction** — `.docx`/`.doc` files are accepted but not processed, potentially misleading users about index coverage.

---

## Privacy Considerations

- **No user accounts** — The application does not collect user identity information
- **Local data only** — All documents, conversations, and chunks are stored locally in SQLite
- **Third-party API** — Document content and user queries are sent to the Groq API for LLM inference. Groq's data usage policies apply.
- **No analytics or tracking** — The frontend does not include any analytics, tracking, or external telemetry scripts
- **Browser storage** — Drafts and prompt library are stored in the browser's `localStorage`

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| No Groq API key configured | Frontend shows mandatory setup modal; backend returns fallback message |
| Groq API timeout (30s) | Returns "The AI service timed out. Please try again." |
| Groq API HTTP error | Returns "AI service error (HTTP <status>). Please try again." |
| Unexpected Groq response | Returns "Received an unexpected response from the AI service." |
| Empty message sent | Returns 400 error: "Message content cannot be empty" |
| Invalid conversation ID | Returns 404: "Conversation not found" |
| Unsupported file type | File is rejected with error message in upload response |
| Empty/unreadable document | Document saved, status set to `empty`, zero chunks indexed |
| Database unavailable | Returns 500 with error message |
| File not found on disk | Warning logged, document remains in DB |

---

## Troubleshooting

### "AI service error" or no response
- Verify your Groq API key is set correctly (Settings tab or `.env`)
- Check your key is active at [console.groq.com](https://console.groq.com)
- The application falls back to a message saying the key is not configured if empty

### Document uploads but chat says "no documents indexed"
- Check `/api/health` — if `chunks_indexed` is 0, the file may be empty or an unsupported format
- Restart the server — it auto-indexes unindexed documents on startup
- For `.docx`/`.doc` files: text extraction is not implemented; the file is stored but not indexed

### Port already in use
```bash
# Windows
netstat -ano | findstr :5000
taskkill /PID <pid> /F

# macOS/Linux
lsof -ti:5000 | xargs kill -9
```

### Voice input not working
- Ensure microphone permission is granted in the browser
- Voice input requires HTTPS or localhost (Chrome restriction)
- Not supported in all browsers — falls back gracefully with a toast notification

### Database issues
- The SQLite database is auto-created on first run
- To reset: delete `backend/database/data.db` and restart the server
- The database directory is auto-created if missing

---

## Known Issues

### Confirmed

- **`.docx`/`.doc` files not indexed** — Files are accepted and stored but text extraction is not implemented for Word documents. The document shows status `empty` and contributes nothing to retrieval.
- **No authentication** — The application is fully open. Not suitable for shared or production environments without modification.
- **Keyword-only retrieval** — The retrieval algorithm uses word-match counting, not semantic search. Synonyms and paraphrases will not match.
- **Single-server architecture** — The application cannot be scaled horizontally (SQLite is file-based, not network-accessible).

### Potential

- **Memory usage with large documents** — Very large PDFs (hundreds of pages) will generate many chunks. The `search_relevant_chunks` function loads all indexed chunks into memory for scoring, which may become slow with thousands of chunks.
- **Conversation history limit** — Only the last 10 messages are included in the LLM context window, regardless of conversation length.
- **No conversation context isolation** — Branching copies messages but the branch and original can diverge without affecting each other.

---

## Future Improvements

### High Priority

- **Add authentication** — Implement user accounts or API key-based access control for networked use
- **Implement `.docx` text extraction** — Add `python-docx` dependency to extract text from Word documents
- **Semantic retrieval** — Replace keyword scoring with vector embeddings (e.g., sentence-transformers + FAISS or ChromaDB) for meaning-aware retrieval

### Medium Priority

- **Streaming responses** — Implement SSE (Server-Sent Events) for real-time token-by-token response display
- **Rate limiting** — Add Flask-Limiter or similar to prevent abuse
- **Document versioning** — Track re-uploads and allow comparing versions of the same document
- **Conversation search** — Add full-text search across all conversations
- **User settings persistence** — Move "Strict Citation Verification" and "Response Speed" toggles from decorative to functional, with backend integration

### Low Priority

- **Multi-file comparison** — Extend compare to support 3+ documents
- **Conversation tags/labels** — Organize conversations with tags or folders
- **Dark mode** — Implement a dark theme variant of the Apple-inspired UI
- **API documentation** — Add OpenAPI/Swagger spec for the REST API
- **Tests** — Add unit and integration tests for the backend

---

## License

This project is for personal/educational use. No license file is included.
