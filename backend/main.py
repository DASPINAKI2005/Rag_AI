import os
import re
import sqlite3
import json
import datetime
import logging
import requests as http_requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app, origins=["*"])

# ─── Configuration ──────────────────────────────────────
DATABASE_PATH = os.getenv('DATABASE_PATH', 'database/data.db')
db_dir = os.path.dirname(os.path.abspath(DATABASE_PATH))
if db_dir:
    os.makedirs(db_dir, exist_ok=True)

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024

ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc', 'txt', 'md', 'csv', 'json'}

GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')
GROQ_MODEL = 'openai/gpt-oss-120b'
GROQ_API_URL = 'https://api.groq.com/openai/v1/chat/completions'

CHUNK_SIZE = 800
CHUNK_OVERLAP = 150

# ─── Per-User API Key Resolution ──────────────────────────
def get_groq_key():
    return request.headers.get('X-Groq-Api-Key', '').strip() or GROQ_API_KEY

# ─── Database ────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                sources TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                size INTEGER DEFAULT 0,
                status TEXT DEFAULT 'uploaded',
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS document_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                page INTEGER DEFAULT 1,
                content TEXT NOT NULL,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            )
        ''')

        cols = {row[1] for row in conn.execute('PRAGMA table_info(documents)').fetchall()}
        if 'size' not in cols:
            conn.execute('ALTER TABLE documents ADD COLUMN size INTEGER DEFAULT 0')

        conn.commit()

init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ─── Document Processing ─────────────────────────────────
def extract_text_from_pdf(file_path):
    try:
        import pdfplumber
        pages = []
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text and text.strip():
                    pages.append({'page': i + 1, 'text': text.strip()})
        return pages
    except Exception as e:
        logger.error("PDF extraction failed for %s: %s", file_path, e)
        return []

def extract_text_from_txt(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
        if text.strip():
            return [{'page': 1, 'text': text.strip()}]
    except Exception as e:
        logger.error("Text extraction failed for %s: %s", file_path, e)
    return []

def extract_text(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.pdf':
        return extract_text_from_pdf(file_path)
    elif ext in ('.txt', '.md', '.csv', '.json'):
        return extract_text_from_txt(file_path)
    return []

def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start += chunk_size - overlap
    return chunks

def process_document(doc_id, file_path):
    pages = extract_text(file_path)
    if not pages:
        logger.warning("No text extracted from %s", file_path)
        return 0

    total_chunks = 0
    with get_db() as conn:
        for page_data in pages:
            chunks = chunk_text(page_data['text'])
            for i, chunk in enumerate(chunks):
                conn.execute(
                    'INSERT INTO document_chunks (document_id, chunk_index, page, content) VALUES (?, ?, ?, ?)',
                    (doc_id, total_chunks, page_data['page'], chunk)
                )
                total_chunks += 1

        status = 'indexed' if total_chunks > 0 else 'empty'
        conn.execute('UPDATE documents SET status = ? WHERE id = ?', (status, doc_id))
        conn.commit()

    logger.info("Indexed %d chunks from %s", total_chunks, os.path.basename(file_path))
    return total_chunks

def search_relevant_chunks(query, limit=5, document_id=None):
    query_lower = query.lower()
    query_words = set(re.findall(r'\w+', query_lower))
    query_words = {w for w in query_words if len(w) > 2}

    if not query_words:
        return []

    with get_db() as conn:
        if document_id:
            rows = conn.execute('''
                SELECT dc.id, dc.document_id, dc.page, dc.content, d.name
                FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.id
                WHERE d.status = 'indexed' AND d.id = ?
            ''', (document_id,)).fetchall()
        else:
            rows = conn.execute('''
                SELECT dc.id, dc.document_id, dc.page, dc.content, d.name
                FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.id
                WHERE d.status = 'indexed'
            ''').fetchall()

    scored = []
    for row in rows:
        content_lower = row['content'].lower()
        score = sum(1 for w in query_words if w in content_lower)
        if score > 0:
            scored.append({
                'chunk_id': row['id'],
                'document_id': row['document_id'],
                'document_name': row['name'],
                'page': row['page'],
                'content': row['content'],
                'score': score
            })

    scored.sort(key=lambda x: x['score'], reverse=True)
    return scored[:limit]

# ─── AI Response (Groq API) ──────────────────────────────
def get_document_context():
    try:
        with get_db() as conn:
            rows = conn.execute('SELECT name FROM documents ORDER BY uploaded_at DESC').fetchall()
            return [row['name'] for row in rows]
    except Exception as e:
        logger.warning("Failed to fetch document context: %s", e)
        return []

def get_conversation_history(conv_id, limit=10):
    try:
        with get_db() as conn:
            rows = conn.execute(
                'SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at ASC LIMIT ?',
                (conv_id, limit)
            ).fetchall()
            return [{'role': row['role'], 'content': row['content']} for row in rows]
    except Exception as e:
        logger.warning("Failed to fetch conversation history: %s", e)
        return []

def generate_response(user_message, conversation_id=None, document_id=None, mode=None, section_context=None, style=None):
    if document_id:
        with get_db() as conn:
            row = conn.execute('SELECT name FROM documents WHERE id = ?', (document_id,)).fetchone()
            doc_names = [row['name']] if row else []
    else:
        doc_names = get_document_context()
    doc_list = ', '.join(doc_names) if doc_names else 'No documents currently indexed.'

    search_query = user_message
    if section_context:
        search_query = user_message + ' ' + section_context[:300]

    relevant_chunks = search_relevant_chunks(search_query, limit=5, document_id=document_id)

    if relevant_chunks:
        context_parts = []
        for i, chunk in enumerate(relevant_chunks, 1):
            context_parts.append(
                f"[Source {i}: {chunk['document_name']}, page {chunk['page']}]\n{chunk['content']}"
            )
        rag_context = "\n\n".join(context_parts)
    else:
        rag_context = "No relevant document content found for this query."

    mode_instructions = {
        'summarize': (
            "Provide a concise but comprehensive summary of the relevant document content. "
            "Organize by main themes. Use bullet points for key takeaways. "
            "Include an executive summary at the top."
        ),
        'compare': (
            "Compare and contrast the provided content. Identify: "
            "(1) Key similarities, (2) Key differences, (3) Contradictions or conflicts, "
            "(4) Missing information in one source vs the other. "
            "Use a structured comparison format with clear sections."
        ),
        'extract': (
            "Extract and list all important data points, facts, figures, dates, names, "
            "requirements, and specifications from the document content. "
            "Organize extracted data in a structured format (lists, tables where appropriate)."
        ),
        'explain': (
            "Provide a clear, thorough explanation of the concepts and topics in the documents. "
            "Break down complex ideas into simple terms. Use analogies where helpful. "
            "Structure the explanation from basic to advanced concepts."
        ),
        'quiz': (
            "Generate a quiz based on the document content. Create 5-8 questions of varying "
            "difficulty (multiple choice and short answer). After each question, provide the "
            "answer and which source it came from. End with a scoring guide."
        )
    }

    mode_key = (mode or '').lower().strip()
    system_parts = [
        "You are Aura Intelligence, an enterprise-grade RAG assistant. "
        "You help users analyze and query their uploaded documents.\n\n"
        "AVAILABLE DOCUMENTS: " + doc_list + "\n\n"
        "RELEVANT DOCUMENT CONTENT (retrieved for this query):\n"
        "--------------------------------------\n"
        + rag_context + "\n"
        "--------------------------------------\n"
    ]

    if mode_key in mode_instructions:
        system_parts.append(
            "MODE INSTRUCTIONS — The user has selected the \"" + mode_key.upper() + "\" mode:\n"
            + mode_instructions[mode_key] + "\n\n"
        )
    else:
        system_parts.append(
            "MODE: Standard Q&A — Answer the user's question directly and thoroughly.\n\n"
        )

    if section_context:
        trimmed_ctx = section_context[:500]
        system_parts.append(
            "SECTION CONTEXT — The user is asking about this specific section/passage from a previous response:\n"
            '"' + trimmed_ctx + '"\n'
            "Focus your answer on this specific context. Reference it explicitly.\n\n"
        )

    system_parts.append(
        "INSTRUCTIONS:\n"
        "- Use the document content above to answer the user's question accurately.\n"
        "- When referencing information, cite the document name and page number.\n"
        "- If the document content doesn't contain enough information to answer, "
        "say so honestly.\n"
        "- Format your response using clear markdown structure:\n"
        "  - Use ## or ### for headings and subheadings to organize sections.\n"
        "  - Use **bold** for key terms and important findings.\n"
        "  - Use numbered lists (1. 2. 3.) for sequential steps or ranked items.\n"
        "  - Use bullet points (- or *) for non-sequential items.\n"
        "  - Use paragraph breaks to separate distinct ideas.\n"
        "  - Use ``` code blocks for any code, commands, or structured data.\n"
        "  - Use > blockquotes for important callouts or citations.\n"
        "- Present the answer in a clean, structured, professional format.\n"
        "- Group related information under descriptive subheadings."
    )

    system_prompt = ''.join(system_parts)

    if style:
        style_map = {
            'shorter': '\n\nKeep your response brief and concise. Use bullet points. Max 3-4 paragraphs.',
            'detailed': '\n\nProvide an extremely detailed and comprehensive response. Cover every aspect thoroughly.',
            'simplify': '\n\nExplain using simple, everyday language. Avoid jargon. Assume the reader is a beginner.',
            'professional': '\n\nWrite in a formal, professional tone suitable for a business document or report.',
            'technical': '\n\nWrite in a highly technical manner with precise terminology. Assume an expert audience.'
        }
        style_lower = style.lower().strip()
        if style_lower in style_map:
            system_prompt += style_map[style_lower]

    messages = [{'role': 'system', 'content': system_prompt}]

    if conversation_id:
        history = get_conversation_history(conversation_id, limit=10)
        messages.extend(history)

    messages.append({'role': 'user', 'content': user_message})

    sources = []
    for chunk in relevant_chunks:
        sources.append({
            'name': chunk['document_name'],
            'page': chunk['page'],
            'match': min(99, 50 + chunk['score'] * 10),
            'excerpt': chunk['content'][:200]
        })

    active_key = get_groq_key()
    if not active_key:
        logger.warning("GROQ_API_KEY not set — returning fallback response")
        fallback = (
            "I'm Aura Intelligence. Your Groq API key is not configured, "
            "so I cannot process AI requests. Please set your Groq API key in the app."
        )
        return fallback, []

    try:
        response = http_requests.post(
            GROQ_API_URL,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {active_key}'
            },
            json={
                'model': GROQ_MODEL,
                'messages': messages,
                'temperature': 0.7,
                'max_tokens': 1024
            },
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        ai_text = data['choices'][0]['message']['content']
        return ai_text, sources
    except http_requests.exceptions.Timeout:
        logger.error("Groq API request timed out")
        return "The AI service timed out. Please try again.", []
    except http_requests.exceptions.HTTPError as e:
        logger.error("Groq API HTTP error: %s — %s", e.response.status_code, e.response.text[:200])
        return f"AI service error (HTTP {e.response.status_code}). Please try again.", []
    except (KeyError, IndexError) as e:
        logger.error("Unexpected Groq API response structure: %s", e)
        return "Received an unexpected response from the AI service. Please try again.", []
    except Exception as e:
        logger.error("Groq API call failed: %s", e)
        return "An unexpected error occurred. Please try again.", []

# ─── API Routes ──────────────────────────────────────────

@app.route('/')
def serve_frontend():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/conversations', methods=['GET', 'POST'])
def handle_conversations():
    if request.method == 'GET':
        try:
            with get_db() as conn:
                rows = conn.execute('SELECT * FROM conversations ORDER BY created_at DESC').fetchall()
                return jsonify([dict(row) for row in rows])
        except Exception as e:
            logger.error("Failed to fetch conversations: %s", e)
            return jsonify({'error': 'Failed to fetch conversations'}), 500
    else:
        data = request.get_json(silent=True) or {}
        title = (data.get('title') or 'New Conversation').strip() or 'New Conversation'
        try:
            with get_db() as conn:
                cur = conn.execute('INSERT INTO conversations (title) VALUES (?)', (title,))
                conv_id = cur.lastrowid
                conn.commit()
                row = conn.execute('SELECT created_at FROM conversations WHERE id = ?', (conv_id,)).fetchone()
                return jsonify({
                    'id': conv_id,
                    'title': title,
                    'created_at': row['created_at'] if row else datetime.datetime.now().isoformat()
                }), 201
        except Exception as e:
            logger.error("Failed to create conversation: %s", e)
            return jsonify({'error': 'Failed to create conversation'}), 500

@app.route('/api/conversations/<int:conv_id>', methods=['DELETE'])
def delete_conversation(conv_id):
    try:
        with get_db() as conn:
            conn.execute('DELETE FROM messages WHERE conversation_id = ?', (conv_id,))
            conn.execute('DELETE FROM conversations WHERE id = ?', (conv_id,))
            conn.commit()
        return jsonify({'success': True, 'id': conv_id})
    except Exception as e:
        logger.error("Failed to delete conversation %s: %s", conv_id, e)
        return jsonify({'error': 'Failed to delete conversation'}), 500

@app.route('/api/conversations/<int:conv_id>/messages', methods=['GET'])
def get_messages(conv_id):
    try:
        with get_db() as conn:
            rows = conn.execute(
                'SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC',
                (conv_id,)
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                if item.get('sources'):
                    try:
                        item['sources'] = json.loads(item['sources'])
                    except (json.JSONDecodeError, TypeError):
                        item['sources'] = []
                else:
                    item['sources'] = []
                result.append(item)
            return jsonify(result)
    except Exception as e:
        logger.error("Failed to fetch messages for conversation %s: %s", conv_id, e)
        return jsonify({'error': 'Failed to fetch messages'}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json(silent=True) or {}
    user_message = (data.get('message') or '').strip()

    if not user_message:
        return jsonify({'error': 'Message content cannot be empty'}), 400

    conv_id = data.get('conversation_id')
    document_id = data.get('document_id')
    mode = data.get('mode')
    section_context = data.get('section_context')
    style = data.get('style')
    branch_from = data.get('branch_from')

    try:
        with get_db() as conn:
            if not conv_id:
                title = user_message[:35] + ('...' if len(user_message) > 35 else '')
                cur = conn.execute('INSERT INTO conversations (title) VALUES (?)', (title,))
                conv_id = cur.lastrowid
                conn.commit()
            else:
                exists = conn.execute('SELECT id FROM conversations WHERE id = ?', (conv_id,)).fetchone()
                if not exists:
                    return jsonify({'error': 'Conversation not found'}), 404

            conn.execute(
                'INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)',
                (conv_id, 'user', user_message)
            )
            conn.commit()

            response_text, sources = generate_response(
                user_message, conv_id, document_id=document_id,
                mode=mode, section_context=section_context, style=style
            )

            conn.execute(
                'INSERT INTO messages (conversation_id, role, content, sources) VALUES (?, ?, ?, ?)',
                (conv_id, 'assistant', response_text, json.dumps(sources))
            )
            conn.commit()

            followups = generate_followups(user_message, response_text, sources, mode)

            return jsonify({
                'conversation_id': conv_id,
                'response': response_text,
                'sources': sources,
                'followups': followups,
                'mode': mode
            })
    except Exception as e:
        logger.error("Chat processing failed: %s", e)
        return jsonify({'error': 'Chat processing failed'}), 500

@app.route('/api/documents', methods=['GET'])
def list_documents():
    try:
        with get_db() as conn:
            rows = conn.execute('SELECT * FROM documents ORDER BY uploaded_at DESC').fetchall()
            return jsonify({'documents': [dict(row) for row in rows]})
    except Exception as e:
        logger.error("Failed to list documents: %s", e)
        return jsonify({'error': 'Failed to list documents'}), 500

@app.route('/api/documents/<int:doc_id>', methods=['DELETE'])
def delete_document(doc_id):
    try:
        with get_db() as conn:
            row = conn.execute('SELECT name FROM documents WHERE id = ?', (doc_id,)).fetchone()
            if not row:
                return jsonify({'error': 'Document not found'}), 404
            filename = row['name']
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                except OSError as e:
                    logger.warning("Failed to remove file %s: %s", file_path, e)
            conn.execute('DELETE FROM document_chunks WHERE document_id = ?', (doc_id,))
            conn.execute('DELETE FROM documents WHERE id = ?', (doc_id,))
            conn.commit()
            return jsonify({'success': True, 'id': doc_id})
    except Exception as e:
        logger.error("Failed to delete document %s: %s", doc_id, e)
        return jsonify({'error': 'Failed to delete document'}), 500

@app.route('/api/upload', methods=['POST'])
def upload_files():
    if 'files' not in request.files:
        return jsonify({'error': 'No file payload provided'}), 400

    files = request.files.getlist('files')
    uploaded_records = []
    errors = []

    with get_db() as conn:
        for file in files:
            if not file or file.filename == '':
                continue
            original_name = file.filename
            filename = secure_filename(original_name)
            if not filename or not allowed_file(filename):
                errors.append(f"Rejected: {original_name} (unsupported file type)")
                continue
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            try:
                file.save(save_path)
                file_size = os.path.getsize(save_path)
            except Exception as e:
                logger.error("Failed to save file %s: %s", filename, e)
                errors.append(f"Failed to save: {original_name}")
                continue

            cur = conn.execute(
                'INSERT INTO documents (name, size, status) VALUES (?, ?, ?)',
                (filename, file_size, 'uploaded')
            )
            doc_id = cur.lastrowid
            conn.commit()

            num_chunks = process_document(doc_id, save_path)

            uploaded_records.append({
                'id': doc_id,
                'name': filename,
                'size': file_size,
                'status': 'indexed' if num_chunks > 0 else 'empty',
                'chunks': num_chunks
            })

    result = {'uploaded': len(uploaded_records), 'documents': uploaded_records}
    if errors:
        result['errors'] = errors
    return jsonify(result), 201

@app.route('/api/health', methods=['GET'])
def health_check():
    try:
        with get_db() as conn:
            chunk_count = conn.execute('SELECT COUNT(*) as c FROM document_chunks').fetchone()['c']
            doc_count = conn.execute('SELECT COUNT(*) as c FROM documents').fetchone()['c']
    except Exception:
        chunk_count = 0
        doc_count = 0
    return jsonify({
        'status': 'ok',
        'groq_configured': bool(get_groq_key()),
        'documents': doc_count,
        'chunks_indexed': chunk_count
    })

@app.route('/api/config/groq-key', methods=['GET'])
def get_groq_key_status():
    return jsonify({'configured': bool(get_groq_key()), 'masked_key': ''})

@app.route('/api/config/groq-key/validate', methods=['POST'])
def validate_groq_key():
    key = request.headers.get('X-Groq-Api-Key', '').strip()
    if not key:
        return jsonify({'valid': False, 'error': 'No API key provided.'}), 400
    try:
        resp = http_requests.post(
            GROQ_API_URL,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {key}'
            },
            json={
                'model': GROQ_MODEL,
                'messages': [{'role': 'user', 'content': 'hi'}],
                'max_tokens': 5
            },
            timeout=10
        )
        if resp.status_code == 200:
            return jsonify({'valid': True})
        elif resp.status_code in (401, 403):
            return jsonify({'valid': False, 'error': 'Invalid API key. Please check your Groq API key and try again.'}), 401
        else:
            return jsonify({'valid': False, 'error': f'Unexpected response from Groq (HTTP {resp.status_code}).'}), 502
    except http_requests.exceptions.Timeout:
        return jsonify({'valid': False, 'error': 'Validation request timed out. Please try again.'}), 504
    except Exception as e:
        return jsonify({'valid': False, 'error': f'Connection error: {str(e)}'}), 500

# ─── Follow-Up Suggestions Generator ──────────────────────
def generate_followups(user_message, response_text, sources, mode=None):
    followups = []
    if sources:
        followups.append("Show me the evidence for that")
        followups.append("Summarize this response")
    followups.append("Explain this further")
    if len(sources) > 1:
        followups.append("Compare the sources")
    followups.append("Ask a deeper question")
    if not mode:
        followups.append("Extract key points")
    return followups[:5]

# ─── Document Compare Endpoint ────────────────────────────
@app.route('/api/compare', methods=['POST'])
def compare_documents():
    data = request.get_json(silent=True) or {}
    doc_id_a = data.get('document_a')
    doc_id_b = data.get('document_b')

    if not doc_id_a or not doc_id_b:
        return jsonify({'error': 'Two document IDs required'}), 400

    try:
        with get_db() as conn:
            doc_a = conn.execute('SELECT * FROM documents WHERE id = ?', (doc_id_a,)).fetchone()
            doc_b = conn.execute('SELECT * FROM documents WHERE id = ?', (doc_id_b,)).fetchone()

            if not doc_a or not doc_b:
                return jsonify({'error': 'One or both documents not found'}), 404

            chunks_a = conn.execute(
                'SELECT content FROM document_chunks WHERE document_id = ? ORDER BY chunk_index',
                (doc_id_a,)
            ).fetchall()
            chunks_b = conn.execute(
                'SELECT content FROM document_chunks WHERE document_id = ? ORDER BY chunk_index',
                (doc_id_b,)
            ).fetchall()

            text_a = ' '.join(c['content'] for c in chunks_a)
            text_b = ' '.join(c['content'] for c in chunks_b)

            words_a = set(re.findall(r'\w+', text_a.lower()))
            words_b = set(re.findall(r'\w+', text_b.lower()))
            common = words_a & words_b
            total = words_a | words_b
            similarity = round((len(common) / max(len(total), 1)) * 100, 1)

            key_a = list(words_a - words_b)[:20]
            key_b = list(words_b - words_a)[:20]

            groq_key = get_groq_key()
            comparison_result = None
            if groq_key:
                try:
                    sys_prompt = (
                        "You are comparing two documents. Provide a structured comparison with these sections:\n"
                        "## Similarities\n## Key Differences\n## Changed Requirements\n## Missing Information\n"
                        "## Contradictions\n\n"
                        "DOCUMENT A (" + doc_a['name'] + "):\n" + text_a[:3000] + "\n\n"
                        "DOCUMENT B (" + doc_b['name'] + "):\n" + text_b[:3000]
                    )
                    resp = http_requests.post(
                        GROQ_API_URL,
                        headers={
                            'Content-Type': 'application/json',
                            'Authorization': f'Bearer {groq_key}'
                        },
                        json={
                            'model': GROQ_MODEL,
                            'messages': [
                                {'role': 'system', 'content': sys_prompt},
                                {'role': 'user', 'content': 'Compare these two documents comprehensively.'}
                            ],
                            'temperature': 0.3,
                            'max_tokens': 2048
                        },
                        timeout=30
                    )
                    resp.raise_for_status()
                    comparison_result = resp.json()['choices'][0]['message']['content']
                except Exception as e:
                    logger.error("Comparison AI error: %s", e)

            return jsonify({
                'document_a': {'id': doc_a['id'], 'name': doc_a['name']},
                'document_b': {'id': doc_b['id'], 'name': doc_b['name']},
                'similarity': similarity,
                'unique_to_a': key_a,
                'unique_to_b': key_b,
                'comparison': comparison_result
            })
    except Exception as e:
        logger.error("Compare failed: %s", e)
        return jsonify({'error': 'Comparison failed'}), 500

# ─── Document Health Endpoint ─────────────────────────────
@app.route('/api/documents/<int:doc_id>/health', methods=['GET'])
def document_health(doc_id):
    try:
        with get_db() as conn:
            doc = conn.execute('SELECT * FROM documents WHERE id = ?', (doc_id,)).fetchone()
            if not doc:
                return jsonify({'error': 'Document not found'}), 404

            chunk_count = conn.execute(
                'SELECT COUNT(*) as c FROM document_chunks WHERE document_id = ?', (doc_id,)
            ).fetchone()['c']

            page_info = conn.execute(
                'SELECT MIN(page) as min_page, MAX(page) as max_page FROM document_chunks WHERE document_id = ?',
                (doc_id,)
            ).fetchone()

            total_chars = conn.execute(
                'SELECT COALESCE(SUM(LENGTH(content)), 0) as total FROM document_chunks WHERE document_id = ?',
                (doc_id,)
            ).fetchone()['total']

            file_path = os.path.join(UPLOAD_FOLDER, doc['name'])
            exists_on_disk = os.path.isfile(file_path)

            ext = os.path.splitext(doc['name'])[1].lower()
            content_type_map = {
                '.pdf': 'PDF Document',
                '.txt': 'Text File',
                '.md': 'Markdown File',
                '.csv': 'CSV Data',
                '.json': 'JSON Data',
                '.docx': 'Word Document',
                '.doc': 'Word Document'
            }

            return jsonify({
                'id': doc['id'],
                'name': doc['name'],
                'size': doc['size'],
                'status': doc['status'],
                'uploaded_at': doc['uploaded_at'],
                'chunks': chunk_count,
                'pages': page_info['max_page'] if page_info['max_page'] else 0,
                'total_characters': total_chars,
                'content_type': content_type_map.get(ext, 'Unknown'),
                'indexed': doc['status'] == 'indexed',
                'file_on_disk': exists_on_disk,
                'retrievable': doc['status'] == 'indexed' and chunk_count > 0
            })
    except Exception as e:
        logger.error("Document health failed: %s", e)
        return jsonify({'error': 'Health check failed'}), 500

# ─── Branch Conversation Endpoint ─────────────────────────
@app.route('/api/conversations/<int:conv_id>/branch', methods=['POST'])
def branch_conversation(conv_id):
    data = request.get_json(silent=True) or {}
    message_id = data.get('message_id')

    if not message_id:
        return jsonify({'error': 'message_id is required'}), 400

    try:
        with get_db() as conn:
            conv = conn.execute('SELECT * FROM conversations WHERE id = ?', (conv_id,)).fetchone()
            if not conv:
                return jsonify({'error': 'Conversation not found'}), 404

            msg = conn.execute(
                'SELECT * FROM messages WHERE id = ? AND conversation_id = ?',
                (message_id, conv_id)
            ).fetchone()
            if not msg:
                return jsonify({'error': 'Message not found'}), 404

            new_title = conv['title'] + ' (Branch)'
            cur = conn.execute('INSERT INTO conversations (title) VALUES (?)', (new_title,))
            new_conv_id = cur.lastrowid

            messages_to_copy = conn.execute(
                'SELECT * FROM messages WHERE conversation_id = ? AND id <= ? ORDER BY created_at ASC',
                (conv_id, message_id)
            ).fetchall()

            for m in messages_to_copy:
                conn.execute(
                    'INSERT INTO messages (conversation_id, role, content, sources) VALUES (?, ?, ?, ?)',
                    (new_conv_id, m['role'], m['content'], m['sources'])
                )

            conn.commit()

            return jsonify({
                'id': new_conv_id,
                'title': new_title,
                'message_count': len(messages_to_copy)
            }), 201
    except Exception as e:
        logger.error("Branch failed: %s", e)
        return jsonify({'error': 'Branching failed'}), 500

# ─── Startup: index any unindexed documents ──────────────
def index_existing_documents():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, name FROM documents WHERE status != 'indexed' OR status IS NULL"
        ).fetchall()

    for row in rows:
        file_path = os.path.join(UPLOAD_FOLDER, row['name'])
        if os.path.isfile(file_path):
            num_chunks = process_document(row['id'], file_path)
            if num_chunks > 0:
                logger.info("Auto-indexed %s: %d chunks", row['name'], num_chunks)
        else:
            logger.warning("File not found on disk: %s", row['name'])

if __name__ == '__main__':
    index_existing_documents()
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
