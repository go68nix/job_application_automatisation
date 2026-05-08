# job-applier

Local web app for automating job application document generation.

## Project structure

```
job-applier/
├── backend/
│   ├── main.py
│   ├── scraper.py
│   ├── fit_check.py
│   ├── generator.py
│   ├── pdf_builder.py
│   ├── tracker.py
│   └── prompts.py
├── frontend/
│   └── index.html
├── data/
│   ├── master_cv.pdf
│   ├── user_config.json
│   ├── applications.db
│   └── outputs/
├── .env
└── requirements.txt
```

## Windows setup

1. `pip install -r requirements.txt`
2. `playwright install chromium`
3. Create `.env` with `GEMINI_API_KEY=your_key_here`
4. `python -m uvicorn backend.main:app --reload --port 8000`
5. Open `frontend/index.html` in your browser

## WeasyPrint note for Windows

WeasyPrint may require the GTK runtime on Windows. If PDF generation fails, install GTK3 runtime for Windows and restart your terminal.
