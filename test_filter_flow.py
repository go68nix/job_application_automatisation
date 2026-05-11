#!/usr/bin/env python3
"""Test the new Groq filter flow (geo + talent + gaps)."""
import asyncio
import json
from backend.job_filter import parse_job_with_groq, filter_job_with_groq

# Sample job content and CV text for testing
SAMPLE_JOB_CONTENT = """
Senior Python Backend Engineer
Location: Munich, Germany
Remote: Hybrid (2 days office)
Salary: €70-80k

Company: TechCorp GmbH
We're looking for a Python expert to build scalable APIs using FastAPI and PostgreSQL.
Required:
- 5+ years Python
- FastAPI or Django
- PostgreSQL
- Docker/Kubernetes
- AWS or GCP

Nice to have:
- Microservices architecture
- Redis
- GraphQL
Contact: jobs@techcorp.de
"""

SAMPLE_CV = """
John Doe
Senior Software Engineer

Skills:
- Python (7 years)
- FastAPI, Django, Flask
- PostgreSQL, MongoDB
- Docker, Docker Compose
- AWS (EC2, Lambda, RDS)
- Git, GitHub, GitLab
- CI/CD (GitHub Actions)

Experience:
- Senior Backend Engineer at StartupXYZ (3 years) - Python, FastAPI, PostgreSQL
- Backend Engineer at OtherCorp (2 years) - Python, Django
- Junior Developer at TechStartup (2 years) - Python, Flask

Languages: English, German
"""

async def test_filter_flow():
    print("=" * 60)
    print("TEST 1: Parse job with Groq")
    print("=" * 60)
    
    # Test parse
    parse_result = await parse_job_with_groq(SAMPLE_JOB_CONTENT, url="test_job")
    if "error" in parse_result:
        print(f"❌ Parse error: {parse_result['error']}")
        return
    
    job = parse_result.get("job", {})
    print(f"✅ Parsed job:")
    print(f"   Company: {job.get('company')}")
    print(f"   Role: {job.get('role')}")
    print(f"   Location: {job.get('location')}")
    print(f"   Remote: {job.get('remote_ok')}")
    print(f"   Contact: {job.get('contact_information')}")
    print()
    
    print("=" * 60)
    print("TEST 2: Filter job (geo + talent + gaps)")
    print("=" * 60)
    
    filter_result = await filter_job_with_groq(job, SAMPLE_CV, base_location="Munich, Germany")
    if "error" in filter_result:
        print(f"❌ Filter error: {filter_result['error']}")
        return
    
    print(f"✅ Filter result:")
    print(f"   Geo Verdict: {filter_result.get('geo_verdict')} ({filter_result.get('geo_reason')})")
    print(f"   Talent Fit: {filter_result.get('talent_fit_score')}/100 ({filter_result.get('talent_fit_reason')})")
    print(f"   Recommendation: {filter_result.get('overall_recommendation')}")
    
    gaps = filter_result.get('gaps', [])
    if gaps:
        print(f"   Gaps found:")
        for gap in gaps:
            print(f"      - {gap.get('skill')} (in CV: {gap.get('in_cv', False)})")
    else:
        print(f"   No major gaps identified")
    print()
    
    print("=" * 60)
    print("✅ All tests passed! Filter flow is working.")
    print("=" * 60)

if __name__ == '__main__':
    asyncio.run(test_filter_flow())
