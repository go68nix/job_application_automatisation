GEO_CHECK_PROMPT = """You are checking if a job location is compatible with user preferences.
Given user base location, max commute preference, and job location/remote option,
return JSON with:
{
  "verdict": "green" | "yellow" | "red",
  "reason": "short reason"
}
Rules:
- green = local or remote-friendly
- yellow = different city but remote possible
- red = onsite only, different country
Respond with valid JSON only. No markdown, no backticks, no explanation.
"""

PROFILE_MATCH_PROMPT = """Score CV fit against the job description from 0-100 and provide one short reason.
Return JSON with:
{
  "match_score": 0,
  "verdict": "strong" | "partial" | "mismatch",
  "reason": "one sentence"
}
Verdict mapping:
- strong: 65+
- partial: 40-64
- mismatch: below 40
Respond with valid JSON only. No markdown, no backticks, no explanation.
"""

REQUIREMENTS_EXTRACT_PROMPT = """Extract 5-7 most critical requirements from the job description and check each against the CV.
Return strict JSON in this exact shape:
{
  "requirements": [
    { "skill": "string", "in_cv": true, "gap": false }
  ]
}
Mark gap=true only when requirement is not found in CV.
Respond with valid JSON only. No markdown, no backticks, no explanation.
"""

CV_GENERATION_PROMPT = """Generate a tailored CV summary with these rules:
- Use ONLY facts from CV, never invent anything.
- No buzzwords: leverage, passionate, dynamic, delve, spearhead, honed, pivotal, thrilled, keen, synergy, innovative, game-changer.
- Keep the output clean and PDF-ready as plain text only.
- Use this exact section order:
  1) Profile Summary
  2) Work Experience
  3) Personal Projects
  4) Technical Skills
  5) Education
- Under Work Experience, list roles in reverse chronological order.
- Under Personal Projects, include only the most relevant projects from the CV.
- Make sections concise, ATS-friendly, and easy to convert to PDF.
- Integrate gap answers:
  - yes: include as real experience with user detail
  - somewhat: mention briefly with softer language
  - no: omit
Return plain text with simple markdown-style headings and bullets.
"""

COVER_LETTER_PROMPT = """Generate cover letter with these rules:
- Use ONLY facts from CV + gap answers.
- Tone: warm and enthusiastic, sounds like a real person.
- NEVER open with: "I am writing to apply", "I am passionate about", "I have always been".
- Open with something specific about the company or role.
- Structure exactly 3 paragraphs:
  1) Why this company/role specifically
  2) Most relevant experience connected to their needs
  3) What you bring + confident call to action
- Same forbidden words as CV prompt: leverage, passionate, dynamic, delve, spearhead, honed, pivotal, thrilled, keen, synergy, innovative, game-changer.
- Length: 260-320 words strictly.
Return plain text only.
"""
