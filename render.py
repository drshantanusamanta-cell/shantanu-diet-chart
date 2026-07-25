"""Builds the printable diet chart.

Two outputs from one HTML source:
  * `build_html()`  — a standalone file that opens in any browser and prints to A4.
                      Always works, and the browser shapes Indic scripts perfectly.
  * `build_pdf()`   — the same document as a real PDF, via WeasyPrint.
                      Needs Noto fonts installed (see packages.txt) for local-language text.
"""

from datetime import date
from html import escape

CLINIC_NAME = "Dr Shantanu Samanta©️"
CLINIC_TAGLINE = "Smart Diet Clinic · Senior Clinical Nutritionist & Dietitian"
CLINIC_ADDRESS = "New Town, Kolkata"
CLINIC_PHONE = "+91 87775 68960"

MEAL_ORDER = ["breakfast", "lunch", "snack", "dinner"]
MEAL_LABEL = {
    "breakfast": "Breakfast",
    "lunch": "Lunch",
    "snack": "Evening Snack",
    "dinner": "Dinner",
}

# Noto covers every Indian script. The browser or WeasyPrint picks whichever
# family it needs per character, so one stack handles all 33 states.
FONT_STACK = (
    "'Noto Sans', 'Noto Sans Bengali', 'Noto Sans Devanagari', 'Noto Sans Gujarati', "
    "'Noto Sans Gurmukhi', 'Noto Sans Kannada', 'Noto Sans Malayalam', "
    "'Noto Sans Oriya', 'Noto Sans Tamil', 'Noto Sans Telugu', "
    "'Nirmala UI', 'Arial Unicode MS', Arial, sans-serif"
)

CSS = f"""
@page {{ size: A4; margin: 14mm 12mm; }}

* {{ box-sizing: border-box; }}

body {{
  font-family: {FONT_STACK};
  color: #1f2937;
  margin: 0;
  font-size: 11pt;
  line-height: 1.45;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}}

.header {{ text-align: center; border-bottom: 3px solid #0284c7; padding-bottom: 10px; margin-bottom: 14px; }}
.header h1 {{ margin: 0; font-size: 20pt; color: #075985; letter-spacing: 0.5px; }}
.header .tagline {{ color: #0284c7; font-size: 9pt; font-weight: 600; margin-top: 3px; }}
.header .contact {{ color: #6b7280; font-size: 8.5pt; margin-top: 4px; }}
.doc-title {{
  display: inline-block; margin-top: 8px; padding: 3px 16px;
  border: 2px solid #0284c7; border-radius: 20px;
  color: #0284c7; font-weight: 700; font-size: 10pt;
  text-transform: uppercase; letter-spacing: 2px;
}}

.patient {{ background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 6px; padding: 10px 12px; margin-bottom: 14px; }}
.patient table {{ width: 100%; border-collapse: collapse; }}
.patient td {{ padding: 2px 6px; vertical-align: top; width: 25%; }}
.label {{ display: block; color: #0284c7; font-size: 7.5pt; font-weight: 700; text-transform: uppercase; letter-spacing: 0.6px; }}
.value {{ font-weight: 700; font-size: 10.5pt; color: #111827; }}

.assessment {{ margin-top: 9px; padding-top: 8px; border-top: 1px solid #bae6fd; }}
.assessment p {{ margin: 3px 0 6px; font-size: 9.5pt; }}
.pill {{
  display: inline-block; background: #fff; border: 1px solid #bae6fd;
  border-radius: 20px; padding: 2px 10px; font-size: 8.5pt;
  font-weight: 700; color: #0369a1; margin-right: 6px;
}}

.meal {{ border: 1px solid #bae6fd; border-radius: 6px; margin-bottom: 10px; overflow: hidden; page-break-inside: avoid; }}
.meal-head {{
  background: #e0f2fe; padding: 6px 10px; font-weight: 700; color: #0c4a6e;
  font-size: 10pt; display: flex; justify-content: space-between;
}}
.meal-head .hint {{ font-size: 7.5pt; font-weight: 600; color: #0284c7; text-transform: uppercase; letter-spacing: 1px; }}

table.items {{ width: 100%; border-collapse: collapse; font-size: 9.5pt; }}
table.items th {{
  background: #f8fafc; color: #0284c7; font-size: 7.5pt; text-transform: uppercase;
  letter-spacing: 0.5px; text-align: left; padding: 5px 10px; border-bottom: 1px solid #e0f2fe;
}}
table.items td {{ padding: 6px 10px; border-bottom: 1px solid #f1f5f9; vertical-align: top; }}
table.items tr:last-child td {{ border-bottom: none; }}
.opt {{ color: #0284c7; font-weight: 700; width: 8%; }}
.item-en {{ font-weight: 700; color: #111827; }}
.item-local {{ color: #6b7280; font-size: 9pt; font-style: italic; }}
.cals {{ text-align: right; font-weight: 700; white-space: nowrap; }}

.guides {{ display: flex; gap: 10px; margin-top: 14px; page-break-inside: avoid; }}
.guide {{ flex: 1; padding: 10px 12px; border-radius: 6px; }}
.guide h3 {{ margin: 0 0 6px; font-size: 10pt; padding-bottom: 4px; border-bottom: 1px solid rgba(0,0,0,0.08); }}
.guide ul {{ margin: 0; padding-left: 15px; }}
.guide li {{ font-size: 9pt; margin-bottom: 4px; line-height: 1.4; }}
.dos {{ background: #f0fdf4; border: 1px solid #bbf7d0; }}
.dos h3 {{ color: #15803d; }}
.donts {{ background: #fef2f2; border: 1px solid #fecaca; }}
.donts h3 {{ color: #b91c1c; }}

.footer {{ margin-top: 16px; padding-top: 10px; border-top: 2px solid #e0f2fe; font-size: 8pt; color: #6b7280; page-break-inside: avoid; }}
.footer .refs {{ color: #075985; font-weight: 700; margin-bottom: 3px; }}
.footer ul {{ margin: 0 0 10px; padding-left: 15px; }}
.sign {{ text-align: center; margin-top: 10px; padding-top: 8px; border-top: 1px solid #e0f2fe; }}
.sign .name {{ font-weight: 700; color: #075985; font-size: 9.5pt; }}
.sign .disclaimer {{ font-style: italic; color: #9ca3af; font-size: 8pt; margin-top: 2px; }}
"""


def _meal_block(meal_key: str, options: list) -> str:
    if not options:
        return ""
    rows = []
    for i, opt in enumerate(options, start=1):
        rows.append(
            f"""<tr>
  <td class="opt">{i}</td>
  <td>
    <div class="item-en">{escape(str(opt.get('item', '')))}</div>
    <div class="item-local">{escape(str(opt.get('localName', '')))}</div>
  </td>
  <td>{escape(str(opt.get('portion', '')))}</td>
  <td class="cals">{escape(str(opt.get('cals', '')))}</td>
</tr>"""
        )
    return f"""<div class="meal">
  <div class="meal-head"><span>{MEAL_LABEL.get(meal_key, meal_key.title())}</span><span class="hint">Choose any one</span></div>
  <table class="items">
    <thead><tr><th style="width:8%">Opt</th><th style="width:47%">Item (English / Local)</th><th style="width:30%">Portion</th><th style="width:15%" class="cals">Kcal</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>"""


def build_html(patient: dict, plan: dict) -> str:
    """Return a complete, standalone HTML document for the diet chart."""
    meals_html = "".join(
        _meal_block(key, (plan.get("meals") or {}).get(key) or []) for key in MEAL_ORDER
    )

    dos = "".join(f"<li>{escape(str(d))}</li>" for d in plan.get("dos") or [])
    donts = "".join(f"<li>{escape(str(d))}</li>" for d in plan.get("donts") or [])
    refs = "".join(f"<li>{escape(str(r))}</li>" for r in plan.get("references") or [])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Diet Chart — {escape(patient.get('name', 'Patient'))}</title>
<style>{CSS}</style>
</head>
<body>

<div class="header">
  <h1>{escape(CLINIC_NAME)}</h1>
  <div class="tagline">{escape(CLINIC_TAGLINE)}</div>
  <div class="contact">{escape(CLINIC_ADDRESS)} &nbsp;|&nbsp; {escape(CLINIC_PHONE)}</div>
  <div class="doc-title">Diet Chart</div>
</div>

<div class="patient">
  <table>
    <tr>
      <td><span class="label">Patient Name</span><span class="value">{escape(str(patient.get('name', '')))}</span></td>
      <td><span class="label">Age / Gender</span><span class="value">{escape(str(patient.get('age', '')))} yrs / {escape(str(patient.get('gender', '')))}</span></td>
      <td><span class="label">Location</span><span class="value">{escape(str(patient.get('state', '')))}</span></td>
      <td><span class="label">Date</span><span class="value">{date.today().strftime('%d %b %Y')}</span></td>
    </tr>
    <tr>
      <td><span class="label">Height</span><span class="value">{escape(str(patient.get('height', '—')))} cm</span></td>
      <td><span class="label">Weight</span><span class="value">{escape(str(patient.get('weight', '—')))} kg</span></td>
      <td><span class="label">Diet</span><span class="value">{escape(str(patient.get('preferences', '')))}</span></td>
      <td><span class="label">Activity</span><span class="value" style="font-size:9pt">{escape(str(patient.get('activity', '')).split('(')[0].strip())}</span></td>
    </tr>
  </table>

  <div class="assessment">
    <span class="label">Clinical Assessment</span>
    <p>{escape(str(plan.get('patientSummary', '')))}</p>
    <span class="pill">Target: {escape(str(plan.get('caloricNeeds', '')))}</span>
    <span class="pill">{escape(str(plan.get('macronutrientSplit', '')))}</span>
  </div>
</div>

{meals_html}

<div class="guides">
  <div class="guide dos"><h3>&#10003; DO's</h3><ul>{dos}</ul></div>
  <div class="guide donts"><h3>&#10007; DON'Ts</h3><ul>{donts}</ul></div>
</div>

<div class="footer">
  <div class="refs">References &amp; Guidelines</div>
  <ul>{refs}</ul>
  <div class="sign">
    <div class="name">{escape(CLINIC_NAME)}</div>
    <div class="disclaimer">This is an indicative chart. Please consult a nutritionist for further advice.</div>
  </div>
</div>

</body>
</html>"""


def build_pdf(html: str) -> bytes:
    """Convert the chart HTML to PDF bytes.

    Raises RuntimeError if WeasyPrint or its system libraries (Pango, HarfBuzz)
    are unavailable. The caller should fall back to the HTML download, which
    needs nothing installed and renders every Indian script correctly.
    """
    unavailable = RuntimeError(
        "PDF generation isn't available on this server. "
        "Use the HTML download instead — it opens in any browser and prints to A4."
    )

    try:
        from weasyprint import HTML
    except Exception as exc:  # ImportError, or OSError when Pango is missing
        raise unavailable from exc

    try:
        return HTML(string=html).write_pdf()
    except Exception as exc:  # noqa: BLE001 — any rendering failure
        raise RuntimeError(
            f"The PDF could not be generated ({type(exc).__name__}). "
            "Use the HTML download instead — it prints to A4 from any browser."
        ) from exc
