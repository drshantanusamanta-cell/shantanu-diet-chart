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
            submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)

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


def diet_chart_prompts(patient: dict) -> tuple[str, str]:
    local_lang = STATES.get(patient["state"], "Hindi")

    system_prompt = f"""You are Dr. Shantanu Samanta, a highly skilled nutritionist and dietitian with 30 years of experience in India.
Your task is to create a highly personalized, culturally appropriate diet chart based on Indian Dietetic Association (IDA) guidelines.

CRITICAL INSTRUCTIONS:
1. Analyze the patient's details and any lab report images/PDFs provided.
2. Calculate the estimated Total Daily Energy Expenditure (TDEE) and set a target caloric intake.
3. Create a diet chart with 4 meals: Breakfast, Lunch, Evening Snack, Dinner.
4. For EACH meal, provide 4 distinct options.
5. Each option MUST include: Item Name (English), Item Name (Local Language: {local_lang}), Portion Size, and Approx Calories.
6. Focus on local cuisine from {patient['state']} but keep it healthy.
7. Provide a "Clinical Summary" interpreting their BMI and any lab data if visible.
8. Provide a specific "Do's and Don'ts" list. IMPORTANT: These must be BILINGUAL. Write the point in English followed by the translation in {local_lang} in parentheses.
9. Cite references (e.g., "NIN Guidelines 2020").

OUTPUT FORMAT:
Return ONLY a JSON object with this structure (no markdown code blocks):
{{
  "patientSummary": "String describing BMI status and health overview",
  "caloricNeeds": "String (e.g., '1800 kcal/day')",
  "macronutrientSplit": "String (e.g., '55% Carbs, 20% Protein, 25% Fat')",
  "meals": {{
    "breakfast": [{{ "item": "String", "localName": "String", "portion": "String", "cals": Number }}],
    "lunch": [],
    "snack": [],
    "dinner": []
  }},
  "dos": ["String (Bilingual)"],
  "donts": ["String (Bilingual)"],
  "references": ["String"]
}}"""

    user_prompt = f"""Patient Details:
Name: {patient['name']}
Age: {patient['age']}
Gender: {patient['gender']}
Height: {patient['height']} cm
Weight: {patient['weight']} kg
Location: {patient['state']} (Prefer local cuisine)
Activity: {patient['activity']}
Medical Conditions: {patient['conditions'] or 'None reported'}
Dietary Preference: {patient['preferences']}

There are {patient['report_count']} lab report files attached. Please analyze values if legible."""

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

def page_diet_chart() -> None:
    st.subheader("Patient Intake")

    with st.form("intake"):
        c1, c2, c3 = st.columns(3)
        with c1:
            name = st.text_input("Patient name *", placeholder="e.g. Ramesh Kumar")
            height = st.number_input("Height (cm)", 50, 250, 165)
        with c2:
            age = st.number_input("Age *", 1, 120, 40)
            weight = st.number_input("Weight (kg)", 10, 300, 70)
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
            "Medical conditions / history",
            placeholder="e.g. Type 2 Diabetes, Hypertension, Hypothyroidism…",
            height=80,
        )

        reports = st.file_uploader(
            "Lab reports (optional) — photos or PDFs",
            type=["png", "jpg", "jpeg", "webp", "pdf"],
            accept_multiple_files=True,
            help="Photos are compressed automatically before upload.",
        )

        submitted = st.form_submit_button(
            "Generate diet chart", type="primary", use_container_width=True
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
        "preferences": preferences, "report_count": len(files),
    }

    system_prompt, user_prompt = diet_chart_prompts(patient)

    with st.spinner("Analysing and building the chart… this usually takes 20–40 seconds."):
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

    st.session_state.plan = plan
    st.session_state.patient = patient
    st.success("Diet chart ready.")


def show_plan() -> None:
    plan = st.session_state.get("plan")
    patient = st.session_state.get("patient")
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
                use_container_width=True,
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

    if plan.get("references"):
        with st.expander("References & guidelines"):
            for ref in plan["references"]:
                st.markdown(f"- {ref}")

    # --- Downloads ---
    st.divider()
    st.markdown("#### Give it to the patient")

    html = render.build_html(patient, plan)
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
                use_container_width=True,
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
            use_container_width=True,
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
        use_container_width=True,
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
        if st.button("Sign out", use_container_width=True):
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
