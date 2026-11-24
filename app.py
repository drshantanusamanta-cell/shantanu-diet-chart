"""Dr Shantanu Samanta©️ — Smart Diet Clinic

A private clinical tool that generates personalised, regionally appropriate diet
charts from patient details and lab reports, and analyses meal photos.

Run locally:  streamlit run app.py
"""

import io
import os
import re
from datetime import date

import streamlit as st
from dotenv import load_dotenv

import ai
import diet_profile as dp
import render

load_dotenv()

# --- 1. Page config (must be the first Streamlit call) ---------------------

st.set_page_config(
    page_title="Dr Shantanu Samanta — Smart Diet Clinic",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- 2. Constants ----------------------------------------------------------

CLINIC_NAME = "Dr Shantanu Samanta©️"

STATES = {
    "Andhra Pradesh": "Telugu", "Arunachal Pradesh": "English", "Assam": "Assamese",
    "Bihar": "Hindi", "Chhattisgarh": "Hindi", "Goa": "Konkani", "Gujarat": "Gujarati",
    "Haryana": "Hindi", "Himachal Pradesh": "Hindi", "Jharkhand": "Hindi",
    "Karnataka": "Kannada", "Kerala": "Malayalam", "Madhya Pradesh": "Hindi",
    "Maharashtra": "Marathi", "Manipur": "Manipuri", "Meghalaya": "English",
    "Mizoram": "Mizo", "Nagaland": "English", "Odisha": "Odia", "Punjab": "Punjabi",
    "Rajasthan": "Hindi", "Sikkim": "Nepali", "Tamil Nadu": "Tamil",
    "Telangana": "Telugu", "Tripura": "Bengali", "Uttar Pradesh": "Hindi",
    "Uttarakhand": "Hindi", "West Bengal": "Bengali", "Delhi": "Hindi",
    "Jammu and Kashmir": "Urdu", "Ladakh": "Ladakhi", "Puducherry": "Tamil",
}

ACTIVITY_LEVELS = [
    "Sedentary (Little or no exercise)",
    "Lightly active (Light exercise/sports 1-3 days/week)",
    "Moderately active (Moderate exercise/sports 3-5 days/week)",
    "Very active (Hard exercise/sports 6-7 days/week)",
    "Extra active (Very hard exercise & physical job)",
]

DIET_PREFERENCES = ["Vegetarian", "Non-Vegetarian", "Eggetarian", "Vegan", "Jain"]

TRACKER_GOALS = [
    "General Healthy Diet", "Diabetic (Low GI)", "Weight Loss (Low Calorie)",
    "High Protein", "Keto", "Renal (Low Sodium/Potassium)",
]

MAX_IMAGE_DIMENSION = 1600
MAX_PDF_BYTES = 4 * 1024 * 1024

# --- 3. Styling ------------------------------------------------------------

st.markdown(
    """
<style>
  .block-container { padding-top: 2rem; max-width: 1100px; }
  .clinic-header {
    background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
    color: #fff; padding: 1.4rem 1.8rem; border-radius: 14px; margin-bottom: 1.5rem;
  }
  .clinic-header h1 { margin: 0; font-size: 1.75rem; font-weight: 700; letter-spacing: -0.3px; }
  .clinic-header p { margin: 0.3rem 0 0; opacity: 0.9; font-size: 0.9rem; }
  .metric-pill {
    display: inline-block; background: #f0f9ff; border: 1px solid #bae6fd;
    color: #0369a1; padding: 0.35rem 0.9rem; border-radius: 20px;
    font-weight: 600; font-size: 0.85rem; margin-right: 0.5rem;
  }
  div[data-testid="stMetricValue"] { font-size: 1.4rem; }
  .stButton>button { border-radius: 8px; font-weight: 600; }
</style>
""",
    unsafe_allow_html=True,
)


def clinic_header(subtitle: str) -> None:
    st.markdown(
        f"""<div class="clinic-header">
              <h1>{CLINIC_NAME}</h1>
              <p>{subtitle}</p>
            </div>""",
        unsafe_allow_html=True,
    )


# --- 4. Password gate ------------------------------------------------------

def get_expected_password() -> str:
    try:
        pw = st.secrets.get("APP_PASSWORD", "")
    except Exception:
        pw = ""
    return (pw or os.getenv("APP_PASSWORD", "")).strip()


def check_password() -> bool:
    """Show a sign-in screen until the correct password is entered."""
    if st.session_state.get("authenticated"):
        return True

    expected = get_expected_password()

    clinic_header("Smart Diet Clinic · Private access")

    if not expected:
        st.error(
            "**Not configured yet.** `APP_PASSWORD` is missing.\n\n"
            "On Streamlit Cloud, open **Manage app → Settings → Secrets** and add:\n\n"
            "```toml\nAPP_PASSWORD = \"your-password-here\"\nGEMINI_API_KEY = \"your-key-here\"\n```"
        )
        return False

    left, _ = st.columns([1, 1])
    with left:
        with st.form("signin"):
            st.markdown("#### 🔒 Sign in")
            st.caption("Enter the clinic password to continue.")
            entered = st.text_input("Password", type="password", label_visibility="collapsed")
            submitted = st.form_submit_button("Sign in", type="primary", width="stretch")

        if submitted:
            attempts = st.session_state.get("failed_attempts", 0)
            if attempts >= 10:
                st.error("Too many failed attempts. Please reload the page and try again.")
            elif entered == expected:
                st.session_state.authenticated = True
                st.session_state.failed_attempts = 0
                st.rerun()
            else:
                st.session_state.failed_attempts = attempts + 1
                st.error("Incorrect password.")

        st.caption("Authorised clinic use only.")

    return False


# --- 5. Helpers ------------------------------------------------------------

def prepare_upload(uploaded_file) -> dict | None:
    """Downscale images and return {'mime_type', 'data', 'name'} for the API.

    Phone photos are often 5-8 MB; 1600px is plenty to read a lab report and
    keeps requests fast and inside API limits.
    """
    raw = uploaded_file.getvalue()
    mime = uploaded_file.type or ""

    if mime == "application/pdf":
        if len(raw) > MAX_PDF_BYTES:
            st.warning(f"Skipped **{uploaded_file.name}** — PDF is larger than 4 MB.")
            return None
        return {"mime_type": "application/pdf", "data": raw, "name": uploaded_file.name}

    if not mime.startswith("image/"):
        st.warning(f"Skipped **{uploaded_file.name}** — unsupported file type.")
        return None

    try:
        from PIL import Image

        img = Image.open(io.BytesIO(raw))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        if max(img.size) > MAX_IMAGE_DIMENSION:
            ratio = MAX_IMAGE_DIMENSION / max(img.size)
            img = img.resize(
                (int(img.width * ratio), int(img.height * ratio)),
                Image.LANCZOS,
            )

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=82, optimize=True)
        return {
            "mime_type": "image/jpeg",
            "data": buffer.getvalue(),
            "name": uploaded_file.name,
        }
    except Exception:
        # If Pillow can't decode it, send the original bytes and let Gemini try.
        return {"mime_type": mime, "data": raw, "name": uploaded_file.name}


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", (name or "patient")).strip("-")
    return cleaned or "patient"


def diet_chart_prompts(patient: dict, analysis: dict) -> tuple[str, str]:
    local_lang = STATES.get(patient["state"], "Hindi")

    system_prompt = f"""You are the diet-chart assistant of Dr. Shantanu Samanta, a Consultant General Physician in Kolkata with special interest in Cardiology, Diabetes and Critical Care.
Create a personalised, culturally appropriate Indian diet chart for an adult patient, tuned to their details and reports.

RULES:
1. Follow the "Checked patient details" exactly. They were calculated by the clinic software. Do NOT recalculate or contradict BMI, eGFR, energy target, protein target or lab interpretations.
2. Meals: early_morning, breakfast, mid_morning, lunch, snack (evening), dinner, bedtime. Give EXACTLY 4 distinct, interchangeable options for every meal (similar carbohydrate and protein, so any one can be chosen). Bedtime may be an empty list unless the patient is on insulin or underweight.
3. Each option: Item Name (English), Item Name (Local Language: {local_lang}), Portion in household measures (katori/bowl, roti, cup, glass, teaspoon, fist-size, plus grams where useful), and approximate kcal.
4. If an energy target is given, one option from each meal should add up to roughly that daily total. Never plan below 1200 kcal a day, and no crash, fad or fasting diets, no supplements.
5. Lunch and dinner options are full plates (rice/roti + dal or fish/egg/chicken/paneer + sabzi/shak + salad) in sensible amounts. Focus on local cuisine from {patient['state']}, kept healthy.
6. Follow the ICMR-NIN Dietary Guidelines for Indians (2024): salt not more than 5 g a day (about 1 level teaspoon); added sugar avoided or within 20–25 g a day; about 400 g of vegetables incl. green leafy vegetables plus a fruit; whole grains and millets instead of refined flour; pulses, curd/milk, nuts and seeds daily; about 5–6 teaspoons of cooking oil a day in total; no ultra-processed or fried foods.
7. Condition rules:
   - Diabetes: steady carbohydrate at each meal; half plate vegetables, quarter whole grains, quarter protein; no juices or sweets. High sugars or HbA1c above 7% → smaller rice/roti portions, more vegetables, millets. On insulin: fixed meal times, never skip meals, bedtime snack; insulin doses only changed by the doctor.
   - High blood pressure: DASH-style; low salt; avoid pickles, papad, chips, packaged foods.
   - Heart / cholesterol: less ghee, butter, red meat, fried and bakery food; more fish, nuts, oats, whole grains, fibre.
   - Kidney disease (CKD): keep protein within the stated daily target, spread across meals; salt under 5 g; no salt substitutes; limit phosphorus (colas, packaged/processed foods, processed cheese); if potassium is high use only low-potassium vegetables and fruits and explain leaching (cut, soak, boil, discard water). No fluid limit unless on dialysis, then follow the nephrologist's fluid advice.
   - Hypothyroidism: if on thyroxine, the early_morning options come after the tablet (plain water, empty stomach, wait about 60 minutes before tea/milk/breakfast); keep calcium/iron tablets and soy a few hours away. Iodised salt within 5 g. Cooked cabbage/cauliflower are fine. Never suggest a thyroid dose or selenium/iodine supplements.
8. If the patient is under 18, pregnant, or has liver disease: give gentle general healthy-eating options only (no restriction or weight loss), and say in the summary that an individual plan must come from the doctor.
9. If the notes mention an eating disorder, extreme restriction or binge-purge behaviour: do not restrict calories; use a normal balanced plan and say in the summary that the patient needs a doctor's review first.
10. Never prescribe or change medicines.
11. "patientSummary": 2–4 sentences on what the chart is tuned for, using the checked details (no new numbers).
12. "dos" and "donts": up to 6 each, specific to this patient's conditions and reports, BILINGUAL: the point in English followed by the translation in {local_lang} in parentheses.
13. Do NOT write references; the clinic attaches verified ones.

OUTPUT FORMAT:
Return ONLY a JSON object with this structure (no markdown code blocks):
{{
  "patientSummary": "String",
  "caloricNeeds": "String (e.g., '1600 kcal/day')",
  "macronutrientSplit": "String (e.g., '55% Carbs, 20% Protein, 25% Fat')",
  "meals": {{
    "early_morning": [{{ "item": "String", "localName": "String", "portion": "String", "cals": Number }}],
    "breakfast": [], "mid_morning": [], "lunch": [], "snack": [], "dinner": [], "bedtime": []
  }},
  "dos": ["String (Bilingual)"],
  "donts": ["String (Bilingual)"]
}}"""

    facts = "\n".join(f"- {f}" for f in analysis["facts"]) or "- (none beyond the basic details)"
    user_prompt = f"""Patient Details:
Name: {patient['name']}
Age: {patient['age']}
Gender: {patient['gender']}
Height: {patient['height']} cm
Weight: {patient['weight']} kg
Location: {patient['state']} (Prefer local cuisine)
Activity: {patient['activity']}
Chart for: {', '.join(patient['condition_list']) or 'Healthy eating'}
Other conditions / notes: {patient['conditions'] or 'None reported'}
Dietary Preference: {patient['preferences']}

Checked patient details (calculated by the clinic software; use them, do not recalculate):
{facts}

There are {patient['report_count']} lab report files attached. Read any legible values to tune food choices, but the checked details above take priority."""

    return system_prompt, user_prompt


TRACKER_SYSTEM_PROMPT = """You are an AI Clinical Nutritionist. Analyze the food image provided.
Return a VALID JSON object with the following structure:
{
  "items": [
    {"name": "Food Item Name", "qty": "Estimated Quantity (e.g. 1 cup, 150g)", "cals": 120, "protein": "5g", "carbs": "20g", "fat": "3g"}
  ],
  "total_calories": 500,
  "health_score": 8,
  "verdict": "Brief one sentence verdict.",
  "breakdown": "Brief nutritional breakdown explanation."
}
Do not include markdown code blocks. Return only raw JSON."""


# --- 6. Pages --------------------------------------------------------------

def _num_input(label: str, key: str, help_text: str | None = None):
    """Optional decimal field: blank means 'not known'. Accepts any decimal (e.g. TSH 7.8)."""
    return st.number_input(label, min_value=0.0, value=None, step=None, format="%g",
                           key=key, placeholder="—", help=help_text)


def page_diet_chart() -> None:
    st.subheader("Patient Intake")

    condition_list = st.multiselect(
        "Chart for (choose one or more)",
        list(dp.CONDITIONS),
        default=["Healthy eating"],
        help="Picking a condition shows its report fields below.",
    )
    topics = {dp.CONDITIONS[c] for c in condition_list}

    with st.form("intake"):
        c1, c2, c3 = st.columns(3)
        with c1:
            name = st.text_input("Patient name *", placeholder="e.g. Ramesh Kumar")
            height = st.number_input("Height (cm)", 50.0, 250.0, 165.0, step=0.5, format="%g")
        with c2:
            age = st.number_input("Age *", 1, 120, 40)
            weight = st.number_input("Weight (kg)", 10.0, 300.0, 70.0, step=0.5, format="%g")
        with c3:
            gender = st.selectbox("Gender", ["Female", "Male", "Other"])
            preferences = st.selectbox("Dietary preference", DIET_PREFERENCES)

        c4, c5 = st.columns(2)
        with c4:
            state = st.selectbox(
                "State / location",
                list(STATES),
                index=list(STATES).index("West Bengal"),
                format_func=lambda s: f"{s}  ({STATES[s]})",
            )
        with c5:
            activity = st.selectbox("Activity level", ACTIVITY_LEVELS)

        conditions = st.text_area(
            "Other conditions / history / notes",
            placeholder="e.g. Fatty liver, gout, on metformin, works night shifts…",
            height=80,
        )

        vals: dict = {}
        if topics & {"diabetes", "hypertension", "heart", "kidney", "thyroid"}:
            st.markdown("**Reports (optional)** — leave blank anything not known. "
                        "The software reads these numbers itself; the AI never does the maths.")
        if "diabetes" in topics:
            st.caption("Sugar reports")
            r = st.columns(4)
            with r[0]: vals["fbs"] = _num_input("Fasting sugar (mg/dL)", "fbs")
            with r[1]: vals["ppbs"] = _num_input("After-meal sugar (mg/dL)", "ppbs")
            with r[2]: vals["hba1c"] = _num_input("HbA1c (%)", "hba1c")
            with r[3]: vals["insulin"] = st.checkbox("On insulin", key="insulin")
        if "hypertension" in topics:
            st.caption("Blood pressure")
            r = st.columns(4)
            with r[0]: vals["sbp"] = _num_input("Systolic (upper)", "sbp")
            with r[1]: vals["dbp"] = _num_input("Diastolic (lower)", "dbp")
        if "heart" in topics:
            st.caption("Cholesterol report")
            r = st.columns(4)
            with r[0]: vals["ldl"] = _num_input("LDL (mg/dL)", "ldl")
            with r[1]: vals["tg"] = _num_input("Triglycerides (mg/dL)", "tg")
        if "kidney" in topics:
            st.caption("Kidney reports — eGFR is estimated from creatinine, age and sex (CKD-EPI 2021)")
            r = st.columns(4)
            with r[0]: vals["urea"] = _num_input("Urea (mg/dL)", "urea")
            with r[1]: vals["creatinine"] = _num_input("Creatinine (mg/dL)", "creatinine")
            with r[2]: vals["potassium"] = _num_input("Potassium (mmol/L)", "potassium")
            with r[3]: vals["dialysis"] = st.checkbox("On dialysis", key="dialysis")
        if "thyroid" in topics:
            st.caption("Thyroid report")
            r = st.columns(4)
            with r[0]: vals["tsh"] = _num_input("TSH (mIU/L)", "tsh")
            with r[1]: vals["thyroxine"] = st.checkbox("Takes thyroxine", key="thyroxine")

        reports = st.file_uploader(
            "Lab report files (optional) — photos or PDFs",
            type=["png", "jpg", "jpeg", "webp", "pdf"],
            accept_multiple_files=True,
            help="Photos are compressed automatically before upload.",
        )

        submitted = st.form_submit_button(
            "Generate diet chart", type="primary", width="stretch"
        )

    if not submitted:
        return

    if not name.strip():
        st.error("Please enter the patient's name.")
        return

    files = [f for f in (prepare_upload(r) for r in reports or []) if f]

    patient = {
        "name": name.strip(), "age": age, "gender": gender,
        "height": height, "weight": weight, "state": state,
        "activity": activity, "conditions": conditions.strip(),
        "condition_list": condition_list,
        "preferences": preferences, "report_count": len(files),
    }

    analysis = dp.analyze(
        {
            "age": age, "sex": gender, "weight": weight, "height": height,
            "activity_index": ACTIVITY_LEVELS.index(activity),
            **{k: v for k, v in vals.items() if v not in (None, False)},
        },
        condition_list,
        conditions,
    )
    analysis["references"] = dp.references(analysis["topics"])

    system_prompt, user_prompt = diet_chart_prompts(patient, analysis)

    with st.spinner("Analysing and building the chart (7 meals × 4 options)… this usually takes 30–60 seconds."):
        try:
            plan = ai.call_gemini(user_prompt, system_prompt, files)
        except ai.ConfigError as exc:
            st.error(str(exc))
            return
        except ai.GeminiError as exc:
            st.error(f"Could not generate the chart. {exc}")
            return

    if not plan.get("meals"):
        st.error("The chart came back incomplete. Please try generating again.")
        return

    if analysis.get("energy_kcal"):
        plan["caloricNeeds"] = f"{analysis['energy_kcal']} kcal/day"

    st.session_state.plan = plan
    st.session_state.patient = patient
    st.session_state.analysis = analysis
    st.success("Diet chart ready.")


def show_plan() -> None:
    plan = st.session_state.get("plan")
    patient = st.session_state.get("patient")
    analysis = st.session_state.get("analysis") or {}
    if not plan or not patient:
        return

    st.divider()
    st.subheader(f"Diet chart — {patient['name']}")

    bmi = None
    try:
        bmi = round(patient["weight"] / ((patient["height"] / 100) ** 2), 1)
    except (ZeroDivisionError, TypeError):
        pass

    m1, m2, m3 = st.columns(3)
    m1.metric("Target intake", plan.get("caloricNeeds", "—"))
    m2.metric("Macro split", plan.get("macronutrientSplit", "—"))
    m3.metric("BMI", bmi if bmi else "—")

    for u in analysis.get("urgent") or []:
        st.error(f"⚠️ {u}")

    if analysis.get("lines"):
        with st.container(border=True):
            st.markdown("**Checked details used** (calculated by the software, not the AI)")
            for line in analysis["lines"]:
                st.markdown(f"- {line}")

    st.info(f"**Clinical assessment** — {plan.get('patientSummary', '')}")

    for key in render.MEAL_ORDER:
        options = (plan.get("meals") or {}).get(key) or []
        if not options:
            continue
        with st.expander(f"**{render.MEAL_LABEL[key]}** — {len(options)} options", expanded=True):
            st.dataframe(
                [
                    {
                        "#": i,
                        "Item": o.get("item", ""),
                        "Local name": o.get("localName", ""),
                        "Portion": o.get("portion", ""),
                        "Kcal": o.get("cals", ""),
                    }
                    for i, o in enumerate(options, start=1)
                ],
                hide_index=True,
                width="stretch",
            )

    g1, g2 = st.columns(2)
    with g1:
        st.markdown("#### ✅ DO's")
        for item in plan.get("dos") or []:
            st.markdown(f"- {item}")
    with g2:
        st.markdown("#### ❌ DON'Ts")
        for item in plan.get("donts") or []:
            st.markdown(f"- {item}")

    refs = analysis.get("references") or dp.references([])
    with st.expander("References (verified, attached by the clinic software)"):
        for text, url in refs:
            st.markdown(f"- [{text}]({url})")

    # --- Downloads ---
    st.divider()
    st.markdown("#### Give it to the patient")

    html = render.build_html(patient, plan, analysis)
    stem = f"DietChart-{safe_filename(patient['name'])}-{date.today():%Y%m%d}"

    d1, d2 = st.columns(2)

    with d1:
        try:
            pdf_bytes = render.build_pdf(html)
            st.download_button(
                "⬇️  Download PDF (A4)",
                data=pdf_bytes,
                file_name=f"{stem}.pdf",
                mime="application/pdf",
                type="primary",
                width="stretch",
            )
            st.caption("Ready to print or send on WhatsApp.")
        except RuntimeError as exc:
            st.warning(str(exc))

    with d2:
        st.download_button(
            "⬇️  Download HTML",
            data=html.encode("utf-8"),
            file_name=f"{stem}.html",
            mime="text/html",
            width="stretch",
        )
        st.caption("Opens in any browser; print to A4 from there.")

    with st.expander("Preview the printable chart"):
        st.components.v1.html(html, height=800, scrolling=True)


def page_tracker() -> None:
    st.subheader("Snap & Check — meal analysis")

    goal = st.selectbox("Dietary goal (for context)", TRACKER_GOALS)
    source = st.radio(
        "Meal photo", ["Upload a photo", "Use camera"], horizontal=True,
        label_visibility="collapsed",
    )

    photo = (
        st.camera_input("Take a photo of the meal")
        if source == "Use camera"
        else st.file_uploader("Meal photo", type=["png", "jpg", "jpeg", "webp"])
    )

    if not photo:
        return

    st.image(photo, width=380)

    if not st.button("Analyse this meal", type="primary"):
        return

    prepared = prepare_upload(photo)
    if not prepared:
        return

    with st.spinner("Analysing the meal…"):
        try:
            result = ai.call_gemini(
                f"Analyze this meal. Context: The user is following a {goal}.",
                TRACKER_SYSTEM_PROMPT,
                [prepared],
            )
        except ai.ConfigError as exc:
            st.error(str(exc))
            return
        except ai.GeminiError as exc:
            st.error(f"Analysis failed. {exc}")
            return

    items = result.get("items") or []
    if not items:
        st.error("Nothing recognisable in that photo. Try a clearer, well-lit shot.")
        return

    score = result.get("health_score", 0)
    c1, c2 = st.columns(2)
    c1.metric("Total calories", result.get("total_calories", "—"))
    c2.metric("Health score", f"{score}/10")

    if isinstance(score, (int, float)):
        if score >= 7:
            st.success(result.get("verdict", ""))
        elif score >= 4:
            st.warning(result.get("verdict", ""))
        else:
            st.error(result.get("verdict", ""))

    st.dataframe(
        [
            {
                "Item": i.get("name", ""), "Qty": i.get("qty", ""),
                "Kcal": i.get("cals", ""), "Protein": i.get("protein", ""),
                "Carbs": i.get("carbs", ""), "Fat": i.get("fat", ""),
            }
            for i in items
        ],
        hide_index=True,
        width="stretch",
    )

    if result.get("breakdown"):
        st.caption(result["breakdown"])


# --- 7. Main ---------------------------------------------------------------

def main() -> None:
    if not check_password():
        return

    clinic_header("Smart Diet Clinic · Senior Clinical Nutritionist & Dietitian")

    with st.sidebar:
        st.markdown(f"**{CLINIC_NAME}**")
        st.caption("New Town, Kolkata · +91 87775 68960")
        st.divider()
        if st.button("Sign out", width="stretch"):
            st.session_state.clear()
            st.rerun()
        st.divider()
        st.caption(
            "Nothing is saved. Patient details exist only while this page is open — "
            "download each chart before you leave."
        )

    chart_tab, tracker_tab = st.tabs(["📋  Diet Chart", "📷  Snap & Check"])

    with chart_tab:
        page_diet_chart()
        show_plan()

    with tracker_tab:
        page_tracker()


if __name__ == "__main__":
    main()
