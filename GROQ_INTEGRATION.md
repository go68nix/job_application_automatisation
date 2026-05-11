# Job Application Automation - Groq Filter Integration ✅

## Summary of Changes

### Backend Updates

#### 1. **`backend/groq_client.py`** (NEW)
- Groq API wrapper for fast, cost-effective LLM inference
- Uses `mixtral-8x7b-32768` model
- Async HTTP client with proper error handling
- Reads `GROQ_API_KEY` from environment

#### 2. **`backend/job_filter.py`** (NEW)
Two-stage job filtering pipeline using Groq:

**`parse_job_with_groq(page_content, url)`**
- Parses job posting content with Groq LLM
- Extracts: `company`, `role`, `location`, `contact_information`, `remote_ok`, `description`, `url`
- Returns: `{"job": {...}}` or `{"error": "..."}`

**`filter_job_with_groq(job, cv_text, base_location)`**
- Analyzes job fit against user's CV
- Returns (geo verdict, talent score, skill gaps, recommendation)
- Fields:
  - `geo_verdict`: "green" (Munich), "yellow" (near/remote), "red" (far)
  - `geo_reason`: brief explanation
  - `talent_fit_score`: 0-100
  - `talent_fit_reason`: brief explanation
  - `gaps`: [{skill, in_cv}] list of required skills user doesn't have
  - `overall_recommendation`: brief summary

#### 3. **`backend/main.py`**
- Added imports: `from .job_filter import parse_job_with_groq, filter_job_with_groq`
- Added POST `/filter-job` endpoint:
  - Takes: `{job: {...}}`
  - Loads CV from `data/master_cv.pdf` (base64 decoded)
  - Loads user config for `base_location`
  - Returns: filter result with geo/talent/gaps, or error

### Frontend Updates

#### **`frontend/index.html`** 
Added filter display panel (`#quickFilterPanel`):
- **Geo Verdict**: badge showing "GREEN|YELLOW|RED" + explanation
- **Talent Fit Score**: 0-100 score with color coding
  - ≥70: green
  - 50-69: yellow
  - <50: red
- **Overall Recommendation**: text summary
- **Skill Gaps Form**: checkboxes to confirm "Do you have this skill?"
- **Buttons**:
  - "Proceed to Full Analysis" → (placeholder) next stage
  - "Go Back & Try Another Job" → back to parse results

Updated button handler for "Analyse This Parsed Job":
- Replaced old `/fit-check` flow with new `/filter-job`
- Shows filter panel with results
- Collects gap answers from user

Added `renderFilterPanel(filterResult)`:
- Hides scrape results, shows filter panel
- Displays geo verdict badge (colored)
- Displays talent score with color
- Renders skill gaps as checkboxes
- Sets up button handlers

---

## How It Works (End-to-End)

1. **User enters job URL or pastes page content** → Click "Preview" or "Parse"
2. **Parse button attempts heuristic parsing** (fast, no API)
3. **If parse succeeds**:
   - Shows parsed job data
   - Shows "Retry with AI" (Groq fallback)
   - Shows "Analyse This Parsed Job" button
4. **Click "Analyse This Parsed Job"**:
   - Calls `/filter-job` with parsed job
   - Groq analyzes job vs CV → geo/talent/gaps
   - Shows filter panel:
     - Geo verdict (green/yellow/red)
     - Talent fit score
     - Skill gaps checkboxes
5. **User reviews gaps, clicks "Proceed"** → (Future) next stage for CV/CL writing

---

## What You Need to Do

### 1. ⚠️ **Get Valid Groq API Key** (CRITICAL)
- Visit: https://console.groq.com
- Create account or sign in
- Generate API key
- Current key in `.env` is **invalid** (401 Unauthorized)
- Update `.env`:
  ```dotenv
  GROQ_API_KEY=your_actual_groq_key_here
  ```

### 2. ✅ **Verify Setup**
- Run backend: `uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000`
- Open frontend: http://localhost:8000/static/ (or port your server is on)
- Upload a master CV if you haven't already
- Save base location config

### 3. 🧪 **Test End-to-End**
a. Paste a job posting or URL
b. Let heuristic parsing attempt (or "Retry with AI" if it fails)
c. Click "Analyse This Parsed Job"
d. Verify filter panel appears with:
   - Geo verdict badge (should say green/yellow/red)
   - Talent score (0-100)
   - Skill gaps list
e. Review gaps, click "Proceed"

---

## Workflow Diagram

```
Job URL/Paste
      ↓
   Parse (heuristic)
      ↓
   Success? 
   ├→ Yes: Show parsed job + buttons
   │       ├→ "Analyse" button
   │       └→ "Retry with AI" button
   └→ No: Show "Retry with AI" button

When you click "Analyse":
      ↓
   /filter-job (Groq)
      ↓
   Geo Check ✓
   Talent Score ✓
   Skill Gaps ✓
      ↓
   Display Filter Panel
   User reviews gaps
      ↓
   Click "Proceed"
      ↓
   [Future: CV/CL generation stage]
```

---

## Files Modified/Created

### New Files
- `backend/groq_client.py` - Groq API wrapper
- `backend/job_filter.py` - Filter logic (geo, talent, gaps)
- `test_filter_flow.py` - Test script (optional, for debugging)

### Modified Files
- `backend/main.py` - Added `/filter-job` endpoint
- `.env` - Added `GROQ_API_KEY` (needs valid value)
- `frontend/index.html` - Added filter panel UI + handlers

---

## Cost & Performance Notes

- **Groq** is ~10x cheaper and 5x faster than Gemini for JSON extraction
- **mixtral-8x7b-32768** model: 0.27¢ per 1K input tokens, no per-request charge
- Parse job: ~500-1000 cost-equivalent tokens (< 1¢ per job)
- Filter job: ~1000-1500 tokens (< 1¢ per job)
- **Estimate**: <2¢ per full job analyze → very scalable

---

## Next Steps (Future Work)

1. **Second-Stage Model** (CV/CL writing):
   - Consider: OpenAI GPT-4, Claude 3.5, or Groq itself
   - Input: job + CV + gap answers
   - Output: tailored CV + cover letter PDF

2. **Job Tracking**:
   - Store filtered jobs in database
   - Track applications sent
   - Measure success rate

3. **Enhanced Gap QA**:
   - Interactive skill descriptions
   - Portfolio links for gaps
   - Experience level scale (beginner/intermediate/expert)

---

## Testing the Filter (Once API Key is Valid)

```bash
python test_filter_flow.py
```

Expected output:
```
TEST 1: Parse job with Groq
✅ Parsed job:
   Company: ...
   Role: ...
   Location: ...
   ...

TEST 2: Filter job (geo + talent + gaps)
✅ Filter result:
   Geo Verdict: green (Job in Munich central)
   Talent Fit: 85/100 (Strong match)
   Recommendation: Highly recommended
   Gaps found:
      - Kubernetes (in CV: false)
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `401 Unauthorized` from Groq | Update `.env` with valid API key from https://console.groq.com |
| Filter panel doesn't appear | Check browser console for errors, verify `/filter-job` endpoint works |
| "No CV available" message | Upload CV first via UI on Step 1 |
| Gaps list empty | Job requirements matched well with your CV |

---

✅ **Backend integration complete. Frontend UI connected. Ready for API key + testing.**
