from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from pathlib import Path
import json
import time
import subprocess

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
QUESTIONS_FILE = DATA_DIR / "questions.json"
STORE_FILE = DATA_DIR / "store.json"

app = FastAPI(title="QOTD Backend - TechLearn Demo")

# ---------- Models ----------
class TestCase(BaseModel):
    input: Optional[str] = None
    expected_output: str

class Question(BaseModel):
    id: str
    title: str
    difficulty: str
    statement: str
    sample_input: Optional[str] = None
    sample_output: Optional[str] = None
    test_cases: List[TestCase] = []
    hints: List[str] = []
    expected_solution: Optional[str] = None  # hidden by default

class QuestionOut(Question):
    expected_solution: Optional[str] = Field(None, description="Hidden by default")

class SubmissionRequest(BaseModel):
    user: str
    q_id: str
    language: Optional[str] = "output"  # "output" or "python"
    answer: str  # for "output", the expected output string; for "python", the source code

class TestResult(BaseModel):
    input: Optional[str]
    expected_output: str
    actual_output: Optional[str]
    passed: bool
    error: Optional[str]

class SubmissionResponse(BaseModel):
    correct: bool
    passed_count: int
    total: int
    results: List[TestResult]
    time_ms: float
    message: Optional[str] = None

class Stats(BaseModel):
    attempts: int = 0
    successes: int = 0
    average_time_ms: float = 0.0

class LeaderboardEntry(BaseModel):
    user: str
    q_id: str
    correct: bool
    time_ms: float

# ---------- Simple JSON-backed datastore ----------
class DataStore:
    def __init__(self, questions_file: Path, store_file: Path):
        self.questions_file = questions_file
        self.store_file = store_file
        self._ensure_files()
        self._load()

    def _ensure_files(self):
        if not self.questions_file.exists():
            # create with sample data
            sample = [
                {
                    "id": "q1",
                    "title": "Sum of Two Numbers",
                    "difficulty": "Easy",
                    "statement": "Given two integers separated by space, output their sum.",
                    "sample_input": "2 3",
                    "sample_output": "5",
                    "test_cases": [
                        {"input": "2 3", "expected_output": "5"},
                        {"input": "10 5", "expected_output": "15"}
                    ],
                    "hints": ["Split the input by space and convert to integers", "Return a+b"],
                    "expected_solution": "def solve(input_str):\n    a,b=map(int,input_str.split())\n    return str(a+b)"
                },
                {
                    "id": "q2",
                    "title": "Reverse String",
                    "difficulty": "Easy",
                    "statement": "Given a string, return the string reversed.",
                    "sample_input": "hello",
                    "sample_output": "olleh",
                    "test_cases": [
                        {"input": "hello", "expected_output": "olleh"},
                        {"input": "abc", "expected_output": "cba"}
                    ],
                    "hints": ["Use slicing s[::-1]"],
                    "expected_solution": "def solve(input_str):\n    return input_str[::-1]"
                }
            ]
            self.questions_file.write_text(json.dumps(sample, indent=2))
        if not self.store_file.exists():
            store = {"stats": {}, "leaderboard": []}
            self.store_file.write_text(json.dumps(store, indent=2))

    def _load(self):
        with open(self.questions_file, "r", encoding="utf-8") as f:
            self.questions = {q["id"]: q for q in json.load(f)}
        with open(self.store_file, "r", encoding="utf-8") as f:
            self.store = json.load(f)

    def save_store(self):
        with open(self.store_file, "w", encoding="utf-8") as f:
            json.dump(self.store, f, indent=2)

    def get_today(self) -> Question:
        # Simple deterministic "today" selector: pick by day number
        qids = sorted(self.questions.keys())
        idx = int(time.time() // 86400) % len(qids)
        return Question(**self.questions[qids[idx]])

    def get_question(self, q_id: str) -> Question:
        q = self.questions.get(q_id)
        if not q:
            raise KeyError("Question not found")
        return Question(**q)

    def add_question(self, q: Dict[str, Any]):
        if q["id"] in self.questions:
            raise KeyError("Question already exists")
        self.questions[q["id"]] = q
        # persist to file
        with open(self.questions_file, "w", encoding="utf-8") as f:
            json.dump(list(self.questions.values()), f, indent=2)

    def update_stats(self, q_id: str, user: str, correct: bool, time_ms: float):
        stats = self.store.setdefault("stats", {}).setdefault(q_id, {"attempts": 0, "successes": 0, "total_time_ms": 0.0})
        stats["attempts"] += 1
        if correct:
            stats["successes"] += 1
        stats["total_time_ms"] += time_ms
        # update leaderboard (simple: append and sort by correct desc then time)
        self.store.setdefault("leaderboard", []).append({"user": user, "q_id": q_id, "correct": correct, "time_ms": time_ms})
        # keep top 100
        self.store["leaderboard"] = sorted(self.store["leaderboard"], key=lambda x: (not x["correct"], x["time_ms"]))[:100]
        self.save_store()

    def get_stats(self, q_id: str) -> Stats:
        s = self.store.setdefault("stats", {}).get(q_id, {"attempts": 0, "successes": 0, "total_time_ms": 0.0})
        avg = (s["total_time_ms"] / s["attempts"]) if s["attempts"] else 0.0
        return Stats(attempts=s["attempts"], successes=s["successes"], average_time_ms=avg)

    def get_leaderboard(self, top: int = 10) -> List[LeaderboardEntry]:
        lb = [LeaderboardEntry(**e) for e in self.store.get("leaderboard", [])][:top]
        return lb

store = DataStore(QUESTIONS_FILE, STORE_FILE)

# ---------- Evaluation helpers ----------

def _compare_outputs(expected: str, actual: str) -> bool:
    # basic normalization
    return expected.strip() == (actual or "").strip()


def evaluate_output_submission(q: Question, answer: str) -> SubmissionResponse:
    results = []
    passed = 0
    start = time.time()
    for tc in q.test_cases:
        ok = _compare_outputs(tc["expected_output"], answer)
        results.append(TestResult(input=tc.get("input"), expected_output=tc["expected_output"], actual_output=answer, passed=ok, error=None))
        if ok:
            passed += 1
    end = time.time()
    return SubmissionResponse(correct=(passed == len(q.test_cases)), passed_count=passed, total=len(q.test_cases), results=results, time_ms=(end - start) * 1000)


def evaluate_python_submission(q: Question, source: str, timeout_sec: int = 2) -> SubmissionResponse:
    results = []
    passed = 0
    start = time.time()
    # We'll attempt to run the code for each test case by piping input to `python -c "<source>\nprint(solve(sys.stdin.read()))"`.
    # WARNING: executing arbitrary code is unsafe. This is for demo/testing only.
    wrapper = (
        "import sys\n"
        "def _run():\n"
        "    import sys\n"
        "    data = sys.stdin.read()\n"
        "    try:\n"
        "        # the user code can define solve(input_str) to return answer string\n"
        "        globals_dict = {}\n"
        "        locals_dict = {}\n"
        "        exec(source_code, globals_dict, locals_dict)\n"
        "        if 'solve' in locals_dict:\n"
        "            out = locals_dict['solve'](data.strip())\n"
        "        elif 'solve' in globals_dict:\n"
        "            out = globals_dict['solve'](data.strip())\n"
        "        else:\n"
        "            out = ''\n"
        "        print(out, end='')\n"
        "    except Exception as e:\n"
        "        print('__ERROR__:' + str(e), end='')\n"
        "if __name__ == '__main__':\n"
        "    _run()\n"
    )
    for tc in q.test_cases:
        try:
            # assemble full code
            full = f"source_code = '''{source}'''\n" + wrapper
            proc = subprocess.run(["python", "-c", full], input=(tc.get("input") or '').encode('utf-8'), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_sec)
            out = proc.stdout.decode('utf-8')
            err = proc.stderr.decode('utf-8')
            if out.startswith("__ERROR__:"):
                res = TestResult(input=tc.get("input"), expected_output=tc["expected_output"], actual_output=None, passed=False, error=out)
            else:
                ok = _compare_outputs(tc["expected_output"], out)
                res = TestResult(input=tc.get("input"), expected_output=tc["expected_output"], actual_output=out, passed=ok, error=(err if err else None))
                if ok:
                    passed += 1
        except subprocess.TimeoutExpired:
            res = TestResult(input=tc.get("input"), expected_output=tc["expected_output"], actual_output=None, passed=False, error="timeout")
        except Exception as e:
            res = TestResult(input=tc.get("input"), expected_output=tc["expected_output"], actual_output=None, passed=False, error=str(e))
        results.append(res)
    end = time.time()
    return SubmissionResponse(correct=(passed == len(q.test_cases)), passed_count=passed, total=len(q.test_cases), results=results, time_ms=(end - start) * 1000)

# ---------- API Routes ----------

@app.get("/api/qotd/today", response_model=QuestionOut)
def get_today(reveal: bool = False):
    q = store.get_today()
    out = q.dict()
    if not reveal:
        out.pop("expected_solution", None)
    return out

@app.get("/api/qotd/{q_id}", response_model=QuestionOut)
def get_question(q_id: str, reveal: bool = False):
    try:
        q = store.get_question(q_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Question not found")
    out = q.dict()
    if not reveal:
        out.pop("expected_solution", None)
    return out

@app.post("/api/qotd/submit", response_model=SubmissionResponse)
def submit(sub: SubmissionRequest):
    try:
        q = store.get_question(sub.q_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Question not found")

    if sub.language == "output":
        res = evaluate_output_submission(Question(**q.dict()), sub.answer)
    elif sub.language == "python":
        res = evaluate_python_submission(q, sub.answer)
    else:
        raise HTTPException(status_code=400, detail="Unsupported submission language/type")

    # update stats and leaderboard
    store.update_stats(sub.q_id, sub.user, res.correct, res.time_ms)
    res.message = "Submission evaluated"
    return res

@app.get("/api/qotd/hints/{q_id}")
def get_hints(q_id: str):
    try:
        q = store.get_question(q_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Question not found")
    return {"hints": q.hints}

@app.get("/api/qotd/stats/{q_id}", response_model=Stats)
def get_stats(q_id: str):
    try:
        _ = store.get_question(q_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Question not found")
    return store.get_stats(q_id)

@app.get("/api/leaderboard")
def leaderboard(top: int = 10):
    return [e.dict() for e in store.get_leaderboard(top=top)]

@app.post("/api/qotd")
def add_question(q: Question):
    try:
        store.add_question(q.dict())
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}

@app.get("/")
def root():
    return {"msg": "QOTD Backend - visit /docs for API docs"}
