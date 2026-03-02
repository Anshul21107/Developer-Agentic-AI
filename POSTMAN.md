Postman API usage

Base URL: http://localhost:8000

1) Create session
   POST /sessions

2) List sessions
   GET /sessions

3) Get session messages
   GET /sessions/{session_id}/messages

4) Stream chat
   POST /chat/{session_id}/stream
   Body (JSON): { "message": "Hello there" }

Streaming notes:
- Use an SSE-capable client. Postman can receive the stream but will show it as raw event lines.
- Each SSE event includes JSON with a token: { "token": "..." }
- Stream ends with: data: [DONE]
