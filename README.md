# QOTD Backend (Python / FastAPI)

A lightweight Question-of-the-Day backend implemented with FastAPI. Designed for demonstration and easy deployment to platforms like Render or Railway.

## Features ✅
- Get today's question (deterministic by day) `GET /api/qotd/today`
- Fetch question details `GET /api/qotd/{q_id}`
- Submit solutions (simple evaluation) `POST /api/qotd/submit`
  - Two modes supported: `output` (compare with expected output) and `python` (executes code against test cases — demo only)
- Hints `GET /api/qotd/hints/{q_id}`
- Stats `GET /api/qotd/stats/{q_id}`
- Leaderboard `GET /api/leaderboard`
- Add question (admin, no auth) `POST /api/qotd`

## Run locally

1. Create virtual env and install:

```bash
python -m venv .venv
.venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

2. Run:

```bash
uvicorn main:app --reload
```

3. Open docs: http://127.0.0.1:8000/docs

## Notes & Safety ⚠️
- The `python` execution mode runs user code in a subprocess for demo/test purposes. This is UNSAFE for production — use proper sandboxing or avoid executing user code.
- Data is persisted in `data/` as simple JSON files for ease of use. Switch to a DB for production.

## Example curl

Submit expected output:
```bash
curl -X POST "http://127.0.0.1:8000/api/qotd/submit" -H "Content-Type: application/json" -d "{\"user\":\"alice\",\"q_id\":\"q1\",\"language\":\"output\",\"answer\":\"5\"}"
```

Submit python code (demo):

```bash
curl -X POST "http://127.0.0.1:8000/api/qotd/submit" -H "Content-Type: application/json" -d @- <<'JSON'
{"user":"bob","q_id":"q1","language":"python","answer":"def solve(input_str):\n    a,b=map(int,input_str.split())\n    return str(a+b)"}
JSON
```

