"""Checked numbers from the patient's details and reports.

Everything here is computed in Python, never by the AI, so the figures on the chart
are reproducible. The AI only receives the results as facts to tune the chart.

Ported from the drshantanu website's diet-chart tool (netlify/lib/diet-profile.mts),
Nov 2026.

Sources
  BMI cut-offs   Misra A, et al. Diabetes Metab Syndr 2025 (Asian Indians: healthy 18.5–22.9,
                 overweight 23–24.9, obesity ≥25)
  eGFR           2021 CKD-EPI creatinine equation, race-free (Inker LA, et al. NEJM 2021)
  Protein (CKD)  KDIGO 2024: 0.8 g/kg/day for G3–G5 not on dialysis;
                 KDOQI 2020: 1.0–1.2 g/kg/day on dialysis
  Energy         Mifflin-St Jeor resting energy (Am J Clin Nutr 1990) × activity factor
  Thyroxine      ATA 2014: levothyroxine ~60 minutes before breakfast, consistently
"""

from __future__ import annotations

import math
import re

# Condition choices shown in the app → reference topic.
CONDITIONS = {
    "Healthy eating": "general",
    "Type 2 diabetes": "diabetes",
    "High blood pressure": "hypertension",
    "Heart / high cholesterol": "heart",
    "Weight loss (adult)": "weight",
    "Kidney disease (CKD)": "kidney",
    "Hypothyroid (low thyroid)": "thyroid",
}

# Which report fields to show for each topic.
LAB_GROUPS = {
    "diabetes": "diabetes",
    "hypertension": "bp",
    "heart": "heart",
    "kidney": "kidney",
    "thyroid": "thyroid",
}

ACTIVITY_FACTOR = [1.2, 1.375, 1.55, 1.725, 1.9]  # same order as app.ACTIVITY_LEVELS

# Fixed, verified references. Attached by the app; the AI never writes citations.
REFS = {
    "icmr": ("ICMR–National Institute of Nutrition. Dietary Guidelines for Indians, revised edition. "
             "Hyderabad: ICMR-NIN; 2024.",
             "https://www.nin.res.in/dietaryguidelines/pdfjs/locale/DGI24thJune2024fin.pdf"),
    "rssdi": ("Makkar BM, et al. RSSDI Clinical Practice Recommendations for the Management of Type 2 "
              "Diabetes Mellitus 2022. Int J Diabetes Dev Ctries. 2022;42(Suppl 1):S1–S143.",
              "https://doi.org/10.1007/s13410-022-01129-5"),
    "ada": ("American Diabetes Association. 5. Facilitating Positive Health Behaviors and Well-being: "
            "Standards of Care in Diabetes—2026. Diabetes Care. 2026;49(Suppl 1):S89–S131.",
            "https://doi.org/10.2337/dc26-S005"),
    "dash": ("National Heart, Lung, and Blood Institute (NIH). DASH Eating Plan: Healthy Eating, "
             "Proven Results. 2020.",
             "https://www.nhlbi.nih.gov/resources/dash-eating-plan-healthy-eating-proven-results"),
    "aha": ("Lichtenstein AH, Appel LJ, et al. 2021 Dietary Guidance to Improve Cardiovascular Health: "
            "A Scientific Statement From the American Heart Association. Circulation. 2021;144:e472–e487.",
            "https://doi.org/10.1161/CIR.0000000000001031"),
    "kdigo": ("KDIGO CKD Work Group. KDIGO 2024 Clinical Practice Guideline for the Evaluation and "
              "Management of Chronic Kidney Disease. Kidney Int. 2024;105(4S):S117–S314.",
              "https://doi.org/10.1016/j.kint.2023.10.018"),
    "kdoqi": ("Ikizler TA, Burrowes JD, Byham-Gray LD, et al. KDOQI Clinical Practice Guideline for "
              "Nutrition in CKD: 2020 Update. Am J Kidney Dis. 2020;76(3 Suppl 1):S1–S107.",
              "https://doi.org/10.1053/j.ajkd.2020.05.006"),
    "inker": ("Inker LA, Eneanya ND, Coresh J, et al. New Creatinine- and Cystatin C–Based Equations to "
              "Estimate GFR without Race. N Engl J Med. 2021;385(19):1737–1749.",
              "https://doi.org/10.1056/NEJMoa2102953"),
    "ata": ("Jonklaas J, Bianco AC, Bauer AJ, et al. Guidelines for the Treatment of Hypothyroidism: "
            "American Thyroid Association Task Force on Thyroid Hormone Replacement. "
            "Thyroid. 2014;24(12):1670–1751.",
            "https://doi.org/10.1089/thy.2014.0028"),
    "misra": ("Misra A, Vikram NK, et al. Revised definition of obesity in Asian Indians living in India. "
              "Diabetes Metab Syndr. 2025;19:102989.",
              "https://doi.org/10.1016/j.dsx.2024.102989"),
    "mifflin": ("Mifflin MD, St Jeor ST, Hill LA, et al. A new predictive equation for resting energy "
                "expenditure in healthy individuals. Am J Clin Nutr. 1990;51(2):241–247.",
                "https://doi.org/10.1093/ajcn/51.2.241"),
}

TOPIC_REFS = {
    "general": ["icmr"],
    "weight": ["icmr"],
    "diabetes": ["icmr", "rssdi", "ada"],
    "hypertension": ["icmr", "dash"],
    "heart": ["icmr", "aha"],
    "kidney": ["icmr", "kdigo", "kdoqi"],
    "egfr": ["inker"],
    "bmi": ["misra"],
    "thyroid": ["icmr", "ata"],
    "energy": ["mifflin"],
}


def references(topics: list[str]) -> list[tuple[str, str]]:
    keys: list[str] = []
    for t in ["general", *topics]:
        for k in TOPIC_REFS.get(t, []):
            if k not in keys:
                keys.append(k)
    return [REFS[k] for k in keys]


def _num(v, lo: float, hi: float) -> float | None:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) and lo <= n <= hi else None


def _r1(n: float) -> str:
    return f"{round(n, 1):g}"


def egfr_ckd_epi_2021(scr: float, age: float, female: bool) -> float:
    k = 0.7 if female else 0.9
    a = -0.241 if female else -0.302
    ratio = scr / k
    return (142 * min(ratio, 1) ** a * max(ratio, 1) ** -1.2 * 0.9938 ** age
            * (1.012 if female else 1))


def ckd_stage(egfr: float) -> str:
    for cut, st in ((90, "G1"), (60, "G2"), (45, "G3a"), (30, "G3b"), (15, "G4")):
        if egfr >= cut:
            return st
    return "G5"


def analyze(p: dict, conditions: list[str], other_conditions: str = "") -> dict:
    """Return {facts, lines, urgent, topics, child, energy_kcal, thyroxine}.

    `p` keys: age, sex ('Female'/'Male'/other), weight, height, activity_index (0-4),
    fbs, ppbs, hba1c, insulin, sbp, dbp, ldl, tg, urea, creatinine, potassium,
    dialysis, tsh, thyroxine. Missing values may be None.
    """
    topics = [CONDITIONS[c] for c in conditions if c in CONDITIONS]
    text = " ".join(conditions) + " " + (other_conditions or "")
    if re.search(r"diabet|t2dm|dm\b", text, re.I):
        topics.append("diabetes")
    if re.search(r"hypertens|high bp|\bbp\b", text, re.I):
        topics.append("hypertension")
    if re.search(r"kidney|ckd|renal", text, re.I):
        topics.append("kidney")
    if re.search(r"thyroid", text, re.I):
        topics.append("thyroid")
    if re.search(r"cholesterol|lipid|heart|cardiac|cad\b", text, re.I):
        topics.append("heart")

    age = _num(p.get("age"), 1, 120)
    sex = {"female": "female", "male": "male"}.get(str(p.get("sex", "")).lower())
    weight = _num(p.get("weight"), 10, 300)
    height = _num(p.get("height"), 50, 250)
    act = p.get("activity_index")
    fbs = _num(p.get("fbs"), 20, 800)
    ppbs = _num(p.get("ppbs"), 20, 900)
    hba1c = _num(p.get("hba1c"), 3, 20)
    insulin = bool(p.get("insulin"))
    sbp = _num(p.get("sbp"), 60, 300)
    dbp = _num(p.get("dbp"), 30, 200)
    ldl = _num(p.get("ldl"), 10, 500)
    tg = _num(p.get("tg"), 10, 5000)
    urea = _num(p.get("urea"), 2, 500)
    creat = _num(p.get("creatinine"), 0.1, 25)
    k = _num(p.get("potassium"), 1.5, 10)
    dialysis = bool(p.get("dialysis"))
    tsh = _num(p.get("tsh"), 0.005, 200)
    thyroxine = bool(p.get("thyroxine"))

    facts: list[str] = []
    lines: list[str] = []
    urgent: list[str] = []
    child = age is not None and age < 18

    if child:
        facts.append("The patient is under 18: give only general healthy-eating options for a child, "
                     "no weight-loss chart, no calorie restriction; say a paediatric plan must come "
                     "from the doctor.")

    # BMI (Asian Indian cut-offs)
    bmi = None
    ref_weight = weight
    if weight is not None and height is not None:
        bmi = weight / (height / 100) ** 2
        if child:
            lines.append(f"BMI {_r1(bmi)} — adult cut-offs do not apply under 18")
        else:
            if bmi < 18.5:
                cat, adv = "below the healthy range", "underweight: slightly larger portions and protein-rich snacks; no weight loss"
            elif bmi < 23:
                cat, adv = "healthy range for Indians", "healthy weight: moderate portions to maintain weight"
            elif bmi < 25:
                cat, adv = "overweight range for Indians", "overweight: slightly smaller cereal/rice portions for gentle weight loss"
            else:
                cat, adv = "obesity range for Indians", "obesity: smaller cereal/rice portions, more vegetables and salad, no fried snacks, gradual loss of about 0.5 kg a week"
                ref_weight = 23 * (height / 100) ** 2
            lines.append(f"**BMI {_r1(bmi)}** — {cat} (Indian cut-offs: healthy 18.5–22.9)")
            facts.append(f"BMI {_r1(bmi)} ({cat}). Tune portions for {adv}.")
            topics.append("bmi")

    # Energy target (Mifflin-St Jeor × activity), adults only
    energy = None
    if (not child and weight is not None and height is not None and age is not None
            and sex and isinstance(act, int) and 0 <= act < len(ACTIVITY_FACTOR)):
        ree = 10 * weight + 6.25 * height - 5 * age + (5 if sex == "male" else -161)
        tdee = ree * ACTIVITY_FACTOR[act]
        target = tdee
        note = "to maintain weight"
        if bmi is not None and bmi >= 23:
            target = tdee - 500
            note = "for gradual weight loss (500 kcal below maintenance)"
        elif bmi is not None and bmi < 18.5:
            target = tdee + 300
            note = "for gradual weight gain"
        floor = 1500 if sex == "male" else 1200
        if target < floor:
            target = floor
            note = f"kept at the safe minimum of {floor} kcal"
        energy = int(round(target / 50) * 50)
        lines.append(f"**Energy target about {energy} kcal/day** {note} "
                     f"(maintenance ≈ {int(round(tdee / 50) * 50)} kcal; Mifflin-St Jeor)")
        facts.append(f"Daily energy target about {energy} kcal ({note}). Make the options in each meal add up "
                     f"to roughly this total for the day (one option per meal); write each option's kcal.")
        topics.append("energy")

    # Diabetes
    if hba1c is not None:
        if hba1c < 5.7:
            t = "in the normal range"
        elif hba1c < 6.5:
            t = "in the prediabetes range"
        elif hba1c < 7:
            t = "in the diabetes range, near the usual target of under 7%"
        elif hba1c <= 8:
            t = "above the usual target of under 7%"
        else:
            t = "well above the usual target of under 7%"
        lines.append(f"HbA1c {_r1(hba1c)}% — {t}")
        facts.append(f"HbA1c {_r1(hba1c)}% ({t})." + (
            " Keep carbohydrate portions small and steady, no sugar, prefer high-fibre whole grains and millets."
            if hba1c >= 7 else ""))
        topics.append("diabetes")
    if fbs is not None:
        t = ("low" if fbs < 70 else "normal" if fbs < 100 else "in the prediabetes range" if fbs < 126
             else "in the diabetes range" if fbs < 250 else "very high")
        lines.append(f"Fasting sugar {_r1(fbs)} mg/dL — {t}")
        facts.append(f"Fasting blood sugar {_r1(fbs)} mg/dL ({t}).")
        topics.append("diabetes")
        if fbs < 70:
            urgent.append(f"Fasting sugar ({_r1(fbs)} mg/dL) is **low**. If shaky, sweaty or confused, take "
                          "3 teaspoons of sugar or glucose in water now, recheck after 15 minutes, and "
                          "review with the doctor today.")
        elif fbs >= 300:
            urgent.append(f"Fasting sugar ({_r1(fbs)} mg/dL) is **very high**. Needs review today; if drowsy, "
                          "vomiting or breathing fast, go to the nearest emergency or call 112.")
    if ppbs is not None:
        t = "low" if ppbs < 70 else "normal" if ppbs < 140 else "high" if ppbs < 200 else "in the diabetes range"
        lines.append(f"After-meal sugar {_r1(ppbs)} mg/dL — {t}")
        facts.append(f"Post-meal blood sugar {_r1(ppbs)} mg/dL ({t})." + (
            " Keep lunch and dinner cereal portions small; vegetables and protein first." if ppbs >= 180 else ""))
        topics.append("diabetes")
        if ppbs < 70 and not any("low" in u for u in urgent):
            urgent.append(f"After-meal sugar ({_r1(ppbs)} mg/dL) is **low**. Take 3 teaspoons of sugar or "
                          "glucose in water now if symptomatic, and review with the doctor today.")
        elif ppbs >= 400:
            urgent.append(f"After-meal sugar ({_r1(ppbs)} mg/dL) is **very high**. Needs review today.")
    if insulin:
        facts.append("On insulin: same meal times every day, never skip meals, steady carbohydrate at each "
                     "meal, include a small bedtime snack, carry sugar for lows. Say insulin doses must "
                     "only be changed by the doctor.")
        lines.append("On insulin — meal times and carbohydrate kept steady, bedtime snack included")
        topics.append("diabetes")

    # Blood pressure
    if sbp is not None or dbp is not None:
        s, d = sbp or 0, dbp or 0
        if s >= 180 or d >= 120:
            t = "very high"
        elif s >= 140 or d >= 90:
            t = "high"
        elif s >= 130 or d >= 80:
            t = "raised"
        else:
            t = "in the normal range"
        bp = f"{_r1(sbp) if sbp else '–'}/{_r1(dbp) if dbp else '–'}"
        lines.append(f"BP {bp} mmHg — {t}")
        facts.append(f"Blood pressure {bp} mmHg ({t}). Strict low-salt DASH-style choices.")
        topics.append("hypertension")
        if t == "very high":
            urgent.append(f"BP ({bp}) is **very high**. With chest pain, breathlessness, severe headache, "
                          "weakness or confusion, call 112 or go to emergency now; otherwise review today.")

    # Lipids
    if ldl is not None:
        t = ("very high" if ldl >= 190 else "high" if ldl >= 160 else "borderline high" if ldl >= 130
             else "above optimal" if ldl >= 100 else "optimal")
        lines.append(f"LDL cholesterol {_r1(ldl)} mg/dL — {t}")
        facts.append(f"LDL cholesterol {_r1(ldl)} mg/dL ({t}). Limit ghee, butter, red meat, fried and bakery "
                     "foods; more fibre (oats, dal, vegetables), fish, nuts.")
        topics.append("heart")
    if tg is not None:
        t = "very high" if tg >= 500 else "high" if tg >= 200 else "borderline high" if tg >= 150 else "normal"
        lines.append(f"Triglycerides {_r1(tg)} mg/dL — {t}")
        facts.append(f"Triglycerides {_r1(tg)} mg/dL ({t}). Cut sugar, sweets, refined flour, large rice "
                     "portions and alcohol." + (" Very low fat as well." if tg >= 500 else ""))
        topics.append("heart")
        if tg >= 1000:
            urgent.append(f"Triglycerides ({_r1(tg)} mg/dL) are **extremely high** (pancreatitis risk). "
                          "Review soon; emergency if severe abdominal pain.")

    # Thyroid
    thyroid = "thyroid" in topics or thyroxine or tsh is not None
    if tsh is not None:
        t = "low" if tsh < 0.4 else "within the usual range" if tsh <= 4.5 else "raised" if tsh <= 10 else "high"
        lines.append(f"TSH {tsh:g} mIU/L — {t}" + (
            " (review the thyroid dose with the doctor; never change it yourself)" if tsh > 4.5 or tsh < 0.4 else ""))
        facts.append(f"TSH {tsh:g} mIU/L ({t})." + (
            " Thyroid under-treated or untreated: weight-control portions, high-fibre foods for constipation, "
            "advise dose review with the doctor (do not suggest a dose)." if tsh > 4.5 else
            " TSH low: advise dose review with the doctor (do not suggest a dose)." if tsh < 0.4 else ""))
    if thyroid:
        topics.append("thyroid")
        facts.append(
            "Hypothyroidism" + (", on thyroxine (levothyroxine)" if thyroxine else "") + ": " +
            ("the Early morning options must come after the thyroid tablet, which is taken with plain water "
             "on an empty stomach, waiting about 60 minutes before tea, milk or breakfast; keep calcium or "
             "iron tablets and soy foods a few hours away from it. " if thyroxine else "") +
            "Use iodised salt but within 5 g a day. Normal cooked cabbage, cauliflower and broccoli are fine; "
            "no raw-goitrogen or 'thyroid cure' diets, no selenium/iodine supplements unless the doctor "
            "advises. Weight-control portions and fibre for constipation.")
        if thyroxine:
            lines.append("On thyroxine — take the tablet with plain water on an empty stomach, about "
                         "60 minutes before tea, milk or breakfast")

    # Kidney
    egfr = None
    if creat is not None:
        if dialysis:
            lines.append(f"Creatinine {creat:g} mg/dL (on dialysis — kidney function not estimated from it)")
            facts.append(f"Serum creatinine {creat:g} mg/dL (on dialysis).")
        elif age is not None and age >= 18 and sex:
            egfr = egfr_ckd_epi_2021(creat, age, sex == "female")
            st = ckd_stage(egfr)
            lines.append(f"Creatinine {creat:g} mg/dL → **eGFR about {round(egfr)}** mL/min/1.73m² "
                         f"(CKD-EPI 2021) — stage {st}")
            facts.append(f"Serum creatinine {creat:g} mg/dL, estimated GFR {round(egfr)} mL/min/1.73m² "
                         f"(CKD stage {st}).")
            topics.append("egfr")
        else:
            lines.append(f"Creatinine {creat:g} mg/dL (age ≥18 and male/female sex needed to estimate eGFR)")
            facts.append(f"Serum creatinine {creat:g} mg/dL" + (" (raised)." if creat > 1.3 else "."))
    if urea is not None:
        t = "raised" if urea > 45 else "within the usual range"
        lines.append(f"Urea {_r1(urea)} mg/dL — {t}")
        facts.append(f"Blood urea {_r1(urea)} mg/dL ({t}).")
    if k is not None:
        t = "low" if k < 3.5 else "normal" if k <= 5.0 else "high" if k < 6 else "dangerously high"
        lines.append(f"Potassium {k:g} mmol/L — {t}" + (": low-potassium foods used" if k > 5 else ""))
        facts.append(f"Serum potassium {k:g} mmol/L ({t})." + (
            " Low-potassium foods only: avoid coconut water, banana, orange/mosambi juice, dry fruits, potato, "
            "tomato-heavy gravies and salt substitutes (low-sodium salt contains potassium). Leach vegetables: "
            "cut, soak in warm water, boil and discard the water." if k > 5 else
            " Potassium low: discuss with the doctor; do not suggest supplements." if k < 3.5 else ""))
        if k >= 6:
            urgent.append(f"Potassium ({k:g} mmol/L) is **dangerously high** and can affect the heart. "
                          "Needs urgent review or emergency care **today**.")
    if dialysis:
        facts.append("On dialysis: higher protein (about 1.0–1.2 g/kg/day: egg white, fish, chicken, paneer in "
                     "measured amounts); strict salt limit; follow the nephrologist's fluid limit; limit "
                     "high-potassium and high-phosphorus foods (colas, packaged and processed foods).")

    if dialysis or "kidney" in topics or (egfr is not None and egfr < 60):
        topics.append("kidney")
        lo_f, hi_f = (1.0, 1.2) if dialysis else (0.8, 0.8)
        basis = "1.0–1.2 g/kg, KDOQI 2020, on dialysis" if dialysis else "0.8 g/kg, KDIGO 2024"
        if ref_weight is not None:
            lo, hi = round(ref_weight * lo_f), round(ref_weight * hi_f)
            g = f"{lo} g" if lo == hi else f"{lo}–{hi} g"
            lines.append(f"**Protein target about {g} a day** ({basis}"
                         + (", using a healthy reference weight" if ref_weight != weight else "") + ")")
            facts.append(f"Daily protein target about {g} ({basis}). Divide protein between meals, keep "
                         "dal/meat/fish/egg/paneer portions within this; no high-protein options (never above "
                         "1.3 g/kg). Salt under 5 g a day. Limit phosphorus: colas, packaged/processed foods, "
                         "processed cheese.")
        else:
            lines.append(f"Protein target: {'1.0–1.2' if dialysis else '0.8'} g per kg body weight a day ({basis})")
            facts.append(f"Protein about {'1.0–1.2' if dialysis else '0.8'} g/kg/day ({basis}); moderate protein "
                         "portions. Salt under 5 g a day. Limit phosphorus: colas, packaged/processed foods.")
        if not dialysis and egfr is not None and egfr < 15:
            urgent.append(f"Estimated kidney function (eGFR about {round(egfr)}) is **very low**. This chart "
                          "cannot replace the nephrologist's plan.")

    # de-duplicate, keep order
    seen: set = set()
    topics = [t for t in topics if not (t in seen or seen.add(t))]
    return {
        "facts": facts,
        "lines": lines,
        "urgent": urgent,
        "topics": topics,
        "child": child,
        "energy_kcal": energy,
        "thyroxine": thyroxine,
    }
