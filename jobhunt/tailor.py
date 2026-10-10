"""Truthful CV tailoring, cover letters and a short report per job.

Rules that keep it honest:
* Bullets are copied verbatim from profile.toml. Tailoring only reorders and selects them.
* Generated text (summary, cover letter) passes a truth guard: every number and every known
  tool it mentions must already appear in the profile. If not, it falls back to safe text.
Method credit: inspired by varunr89/resume-tailoring-skill (MIT), see NOTICE.md.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

from .score import RE_CACHE, _mentioned, profile_text

# ---------------------------------------------------------------- truth guard

_NUM = re.compile(r"\d+(?:[.,]\d+)?\s*%?|\b\d+[kKmM]\b")


def unsupported_claims(text: str, profile: dict, job: dict | None = None) -> list[str]:
    """Numbers or tools in `text` that the profile does not contain. Empty list means safe.
    Tools named by the job ad are allowed only when the text frames them as learning or a gap."""
    source = profile_text(profile)
    src_nums = {n.strip().rstrip("%") for n in _NUM.findall(source)}
    bad = [n for n in _NUM.findall(text) if n.strip().rstrip("%") not in src_nums]
    have = _mentioned(source)
    for tool in _mentioned(text) - have:
        # allow "eager to learn dbt" style mentions of tools the job asks for
        near = re.search(rf"(learn\w*|new to|not yet|currently studying|gap)[^.]{{0,60}}{re.escape(tool)}|{re.escape(tool)}[^.]{{0,40}}(next|to learn|not yet)", text, re.I)
        if not near:
            bad.append(tool)
    return bad


# ---------------------------------------------------------------- planning

PLAN_SYSTEM = """You tailor a CV to a job ad WITHOUT inventing anything.
You may only: choose a headline from the given list, write a 2 to 3 sentence summary that uses ONLY facts from the candidate profile, and reorder or drop items.
Do not use hyphens or dashes as punctuation in the summary. No numbers or tools that are not in the profile.
Return JSON with keys:
headline_index (int),
summary (string),
skill_groups (list of skill group names, most relevant first; keep all groups),
experience (list, same length as the profile's experience list, each a list of bullet indexes to keep in the new order, at least one),
projects (list of project indexes in the new order; drop clearly irrelevant ones, keep at least one),
coverage (integer 0 to 100: share of the ad's main requirements the tailored CV shows evidence for),
covered (list of the ad's requirements the CV covers), missing (list of requirements it does not cover)."""


def _indexed_profile(profile: dict) -> str:
    out = [f"HEADLINES: {[(i, h) for i, h in enumerate(profile.get('person', {}).get('headlines', []))]}",
           f"SKILL GROUPS: {list(profile.get('skills', {}).keys())}"]
    for i, e in enumerate(profile.get("experience", [])):
        out.append(f"EXPERIENCE {i}: {e['title']} at {e['company']}")
        out += [f"  bullet {j}: {b}" for j, b in enumerate(e.get("bullets", []))]
    for i, p in enumerate(profile.get("projects", [])):
        out.append(f"PROJECT {i}: {p['name']}: " + " ".join(p.get("bullets", [])))
    return "\n".join(out)


def _relevance(text: str, wanted: set[str]) -> int:
    return sum(1 for t in wanted if RE_CACHE[t].search(text))


def keyword_plan(job: dict, profile: dict) -> dict:
    """No-LLM plan: sort everything by how many of the ad's tools it mentions."""
    wanted = _mentioned(job["title"] + "\n" + job["description"])
    person = profile.get("person", {})
    heads = person.get("headlines", [""])
    skills = profile.get("skills", {})
    exp = profile.get("experience", [])
    projs = profile.get("projects", [])
    have = _mentioned(profile_text(profile))
    return {
        "headline_index": max(range(len(heads)), key=lambda i: _relevance(heads[i], wanted)) if heads else 0,
        "summary": profile.get("summary") or person.get("summary", ""),
        "skill_groups": sorted(skills, key=lambda g: -_relevance(" ".join(skills[g]), wanted)),
        "experience": [sorted(range(len(e.get("bullets", []))), key=lambda j: -_relevance(e["bullets"][j], wanted)) for e in exp],
        "projects": sorted(range(len(projs)), key=lambda i: -_relevance(" ".join(projs[i].get("bullets", [])), wanted)),
        "coverage": int(100 * len(wanted & have) / len(wanted)) if wanted else 0,
        "covered": sorted(wanted & have), "missing": sorted(wanted - have),
    }


def _valid_plan(plan: dict, profile: dict) -> dict:
    """Clamp indexes so a sloppy LLM answer can never reference facts that do not exist."""
    heads = profile.get("person", {}).get("headlines", [""])
    exp = profile.get("experience", [])
    projs = profile.get("projects", [])
    groups = list(profile.get("skills", {}))
    hi = plan.get("headline_index", 0)
    plan["headline_index"] = hi if isinstance(hi, int) and 0 <= hi < len(heads) else 0
    order = [g for g in plan.get("skill_groups", []) if g in groups]
    plan["skill_groups"] = order + [g for g in groups if g not in order]
    exp_plan = plan.get("experience") or []
    fixed = []
    for i, e in enumerate(exp):
        n = len(e.get("bullets", []))
        idx = exp_plan[i] if i < len(exp_plan) and isinstance(exp_plan[i], list) else []
        idx = [j for j in dict.fromkeys(idx) if isinstance(j, int) and 0 <= j < n]
        fixed.append(idx or list(range(n)))
    plan["experience"] = fixed
    pidx = [i for i in dict.fromkeys(plan.get("projects") or []) if isinstance(i, int) and 0 <= i < len(projs)]
    plan["projects"] = pidx or list(range(len(projs)))
    return plan


def make_plan(job: dict, profile: dict, llm=None) -> dict:
    plan = keyword_plan(job, profile)
    if llm and llm.enabled:
        user = f"CANDIDATE PROFILE\n{profile_text(profile)}\n\nINDEXED ITEMS\n{_indexed_profile(profile)}\n\nJOB AD\n{job['title']} at {job['company']}\n{job['description'][:6000]}"
        try:
            plan = {**plan, **llm.complete_json(PLAN_SYSTEM, user, max_tokens=1200)}
        except Exception as e:  # fall back to the keyword plan, never block the run
            plan["note"] = f"LLM plan failed, used keyword plan: {e}"
    plan = _valid_plan(plan, profile)
    bad = unsupported_claims(plan.get("summary", ""), profile)
    if bad:
        plan["summary"] = profile.get("summary") or profile.get("person", {}).get("summary", "")
        plan["guard"] = f"Generated summary mentioned {bad}, not in your profile, so the default summary was used."
    return plan


# ---------------------------------------------------------------- documents

def _heading(doc, text):
    p = doc.add_paragraph()
    r = p.add_run(text.upper())
    r.bold = True
    r.font.size = Pt(10.5)
    r.font.color.rgb = RGBColor(0x1E, 0x3A, 0x8A)
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)


def _base_doc() -> Document:
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10.5)
    for s in doc.sections:
        s.left_margin = s.right_margin = s.top_margin = s.bottom_margin = Pt(50)
    return doc


def build_cv(profile: dict, plan: dict, path: Path) -> None:
    person = profile.get("person", {})
    doc = _base_doc()
    t = doc.add_paragraph()
    r = t.add_run(person.get("name", ""))
    r.bold = True
    r.font.size = Pt(20)
    head = person.get("headlines", [""])[plan["headline_index"]] if person.get("headlines") else ""
    if head:
        doc.add_paragraph(head).runs[0].font.size = Pt(11.5)
    contact = " | ".join(x for x in [person.get("location"), person.get("email"), person.get("phone"), *person.get("links", [])] if x)
    doc.add_paragraph(contact).runs[0].font.size = Pt(9.5)

    _heading(doc, "Professional Summary")
    doc.add_paragraph(plan["summary"])

    _heading(doc, "Skills")
    skills = profile.get("skills", {})
    for g in plan["skill_groups"]:
        p = doc.add_paragraph()
        p.add_run(f"{g}: ").bold = True
        p.add_run(", ".join(skills[g]))
        p.paragraph_format.space_after = Pt(0)

    exp = profile.get("experience", [])
    if exp:
        _heading(doc, "Experience")
        for e, idx in zip(exp, plan["experience"]):
            p = doc.add_paragraph()
            p.add_run(f"{e['title']}, {e['company']}").bold = True
            p.add_run(f"    {e.get('dates', '')}").italic = True
            p.paragraph_format.space_after = Pt(0)
            for j in idx:
                doc.add_paragraph(e["bullets"][j], style="List Bullet")

    projs = profile.get("projects", [])
    if projs:
        _heading(doc, "Projects")
        for i in plan["projects"]:
            pr = projs[i]
            p = doc.add_paragraph()
            p.add_run(pr["name"]).bold = True
            if pr.get("link"):
                p.add_run(f"    {pr['link']}").italic = True
            p.paragraph_format.space_after = Pt(0)
            for b in pr.get("bullets", []):
                doc.add_paragraph(b, style="List Bullet")

    if profile.get("education"):
        _heading(doc, "Education")
        for ed in profile["education"]:
            p = doc.add_paragraph()
            p.add_run(ed["degree"]).bold = True
            p.add_run(f", {ed.get('school', '')}    {ed.get('dates', '')}")
            p.paragraph_format.space_after = Pt(0)
    if person.get("languages"):
        _heading(doc, "Languages")
        doc.add_paragraph(", ".join(person["languages"]))
    doc.save(path)


LETTER_SYSTEM = """Write a short, warm, specific cover letter body (3 short paragraphs, under 230 words) for the candidate.
Use ONLY facts from the candidate profile. No new numbers, tools, employers or achievements.
Be honest about one gap and say the candidate is learning it, if a gap exists.
Write like a person, not a template. Do not use hyphens or dashes as punctuation. No greeting line and no sign off.
Return JSON: {"body": "..."}"""


def letter_body(job: dict, profile: dict, plan: dict, llm=None) -> tuple[str, str]:
    """Returns (body, note). Falls back to a plain template when the guard rejects the draft."""
    name = profile.get("person", {}).get("name", "")
    template = (f"I am applying for the {job['title']} role at {job['company']}. {plan['summary']}\n\n"
                f"The role asks for {', '.join(plan.get('covered', [])[:4]) or 'skills I use every day'}, which match what I have done in my work and projects. "
                f"{'I am still building experience in ' + ', '.join(plan.get('missing', [])[:2]) + ' and I am glad to learn it on the job. ' if plan.get('missing') else ''}\n\n"
                f"I would be happy to talk about how I can help your team. Thank you for your time.")
    if not (llm and llm.enabled):
        return template, "Template letter (no LLM configured)."
    user = f"CANDIDATE PROFILE\n{profile_text(profile)}\n\nJOB\n{job['title']} at {job['company']}\n{job['description'][:5000]}\n\nCandidate name: {name}"
    for attempt in range(2):
        try:
            body = str(llm.complete_json(LETTER_SYSTEM, user, max_tokens=900).get("body", ""))
        except Exception as e:
            return template, f"LLM letter failed ({e}), template used."
        bad = unsupported_claims(body, profile, job)
        if body and not bad:
            return body, ""
        user += f"\n\nYour previous draft mentioned {bad}, which are not in the profile. Remove them."
    return template, f"LLM drafts mentioned facts not in your profile ({bad}), so a template letter was used."


def build_letter(job: dict, profile: dict, body: str, path: Path) -> None:
    person = profile.get("person", {})
    doc = _base_doc()
    doc.add_paragraph(person.get("name", "")).runs[0].bold = True
    doc.add_paragraph(" | ".join(x for x in [person.get("location"), person.get("email"), person.get("phone")] if x))
    doc.add_paragraph(date.today().strftime("%d %B %Y")).alignment = WD_ALIGN_PARAGRAPH.RIGHT
    doc.add_paragraph(f"{job['company']}\nRe: {job['title']}")
    doc.add_paragraph("Dear Hiring Team,")
    for para in [p.strip() for p in body.split("\n") if p.strip()]:
        doc.add_paragraph(para)
    doc.add_paragraph("Kind regards,")
    doc.add_paragraph(person.get("name", ""))
    doc.save(path)


def to_pdf(paths: list[Path]) -> list[Path]:
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe:
        return []
    outdir = paths[0].parent
    subprocess.run([exe, "--headless", "--convert-to", "pdf", "--outdir", str(outdir), *map(str, paths)],
                   check=False, capture_output=True, timeout=180)
    return [p.with_suffix(".pdf") for p in paths if p.with_suffix(".pdf").exists()]


def slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:40] or "job"


def tailor_job(job: dict, profile: dict, out_root: Path, llm=None, make_pdf: bool = True) -> dict:
    person = profile.get("person", {})
    folder = out_root / date.today().isoformat() / slug(job["company"])
    folder.mkdir(parents=True, exist_ok=True)
    plan = make_plan(job, profile, llm)
    who = slug(person.get("name", "CV"))
    cv = folder / f"{who}_CV_{slug(job['company'])}.docx"
    build_cv(profile, plan, cv)
    body, note = letter_body(job, profile, plan, llm)
    letter = folder / f"{who}_Cover_Letter_{slug(job['company'])}.docx"
    build_letter(job, profile, body, letter)
    report = folder / "report.md"
    report.write_text("\n".join([
        f"# {job['title']} at {job['company']}",
        f"Match: {job.get('match')}  |  Coverage of the ad's requirements: {plan.get('coverage', 0)}%",
        f"Link: {job.get('url', '')}", "",
        "## Covered", *[f"* {c}" for c in plan.get("covered", [])], "",
        "## Missing (say so honestly if asked)", *[f"* {m}" for m in plan.get("missing", [])], "",
        "## Notes", *[f"* {n}" for n in (plan.get("note"), plan.get("guard"), note) if n],
    ]) + "\n", encoding="utf-8")
    pdfs = to_pdf([cv, letter]) if make_pdf else []
    return {"folder": str(folder), "files": [str(p) for p in (cv, letter, report, *pdfs)],
            "coverage": plan.get("coverage", 0)}
