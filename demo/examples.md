# Demo Examples

Real outputs from the Manus autonomous agent system.

---

## Example 1: URL Shortener with Analytics

**Input:**
```
Build a URL shortener with analytics
```

**Manus Plan (8 steps):**
1. `research` — Research existing URL shorteners and best practices
2. `research` — Research analytics tracking patterns
3. `coding`   — Design database schema
4. `coding`   — Implement URL shortening backend
5. `coding`   — Implement analytics tracking
6. `test`     — Generate and run test suite
7. `coding`   — Add error handling and validation
8. `test`     — Final test pass

**Generated Files:**
```
main.py           # FastAPI application
models.py         # SQLAlchemy database models
database.py       # DB connection and session management
analytics.py      # Click tracking and analytics aggregation
test_solution.py  # pytest test suite (12 tests)
requirements.txt  # Dependencies
```

**Sample Generated Code — `main.py`:**
```python
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
import string, random

app = FastAPI(title="URL Shortener with Analytics")

def generate_short_code(length=6):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))

@app.post("/shorten")
async def shorten_url(url: str, db: Session = Depends(get_db)):
    short_code = generate_short_code()
    url_entry = URL(original_url=url, short_code=short_code)
    db.add(url_entry); db.commit()
    return {"short_url": f"http://localhost/{short_code}"}

@app.get("/{short_code}")
async def redirect_url(short_code: str, db: Session = Depends(get_db)):
    url = db.query(URL).filter(URL.short_code == short_code).first()
    if not url: raise HTTPException(status_code=404)
    url.click_count += 1; db.commit()
    return RedirectResponse(url.original_url)

@app.get("/analytics/{short_code}")
async def get_analytics(short_code: str, db: Session = Depends(get_db)):
    url = db.query(URL).filter(URL.short_code == short_code).first()
    return {"clicks": url.click_count, "created_at": url.created_at}
```

**Evaluation:**
| Metric | Score |
|--------|-------|
| Correctness | 8.5/10 |
| Quality | 7.5/10 |
| Completeness | 8.0/10 |
| **Overall** | **8.0/10** ✅ |

**Test Results:** 9/12 passed (75% pass rate)
**Execution time:** 3m 42s (including research, coding, debug, test)
**Debug retries:** 1 (auto-fixed an import error)

---

## Example 2: FastAPI Todo App with JWT Auth

**Input:**
```
Build a FastAPI todo app with JWT authentication
```

**Generated Files:**
```
main.py       # FastAPI app with auth middleware
auth.py       # JWT token creation and validation
models.py     # User + Todo SQLAlchemy models
schemas.py    # Pydantic request/response schemas
database.py   # DB setup
test_solution.py
requirements.txt
```

**Evaluation:**
| Metric | Score |
|--------|-------|
| Correctness | 9.0/10 |
| Quality | 8.0/10 |
| Completeness | 8.5/10 |
| **Overall** | **8.5/10** ✅ |

**Debug retries:** 0 (passed first time)

---

## Example 3: Binary Search Tree

**Input:**
```
Implement a binary search tree with insert, search, delete, and traversal
```

**Evaluation:**
| Metric | Score |
|--------|-------|
| Correctness | 9.5/10 |
| Quality | 9.0/10 |
| Test pass rate | 100% |
| **Overall** | **9.0/10** ✅ |

---

## Self-Healing Loop in Action

```
15:14:57 › Starting: coding — Implement URL shortening backend
15:14:59 › 🐛 Debug loop triggered — error detected
           TypeError: 'NoneType' has no attribute 'short_code'
15:15:18 › Groq fixing error... (attempt 1/3)
15:15:35 › ✓ Fixed — added null check before attribute access
15:15:36 › ✓ coding completed (38.2s total, 1 retry)
```

The system identified a null reference bug, fixed it, re-ran the code, and continued — zero human intervention.

---

## Memory in Action

After fixing the null reference bug above, ChromaDB stored:

```
ERROR: TypeError: 'NoneType' has no attribute 'short_code'
FIX:   Add db.query(...).first() null check before accessing attributes
```

On the next task with a similar pattern, the ResearchAgent pulls this from memory and the CodingAgent avoids the bug entirely.
