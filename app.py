import streamlit as st
import pandas as pd
from datetime import datetime
import os

st.set_page_config(page_title="Planner de Treinos", layout="wide")

# ---------- GIFs (FitnessProgramer) ----------
GIFS = {
    "hip_thrust": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Barbell-Hip-Thrust.gif",
    "abdutora": "https://fitnessprogramer.com/wp-content/uploads/2021/02/HiP-ABDUCTION-MACHINE.gif",

    # puxada alta aberta (barra no peito)
    "lat_pulldown_open": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Lat-Pulldown.gif",

    # pulldown com braço estendido
    "straight_pulldown": "https://fitnessprogramer.com/wp-content/uploads/2021/05/Cable-Straight-Arm-Pulldown.gif",

    "seated_row": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Seated-Cable-Row.gif",
    "leg_press": "https://fitnessprogramer.com/wp-content/uploads/2015/11/Leg-Press.gif",
    "stiff": "https://fitnessprogramer.com/wp-content/uploads/2022/01/Stiff-Leg-Deadlift.gif",
    "squat": "https://fitnessprogramer.com/wp-content/uploads/2021/02/BARBELL-SQUAT.gif",
    "bulgaro": "https://fitnessprogramer.com/wp-content/uploads/2021/05/Barbell-Bulgarian-Split-Squat.gif",
    "lateral_raise": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Dumbbell-Lateral-Raise.gif",
    "shoulder_press": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Dumbbell-Shoulder-Press.gif",
    "plank": "https://fitnessprogramer.com/wp-content/uploads/2021/02/plank.gif",
    "leg_raise": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Lying-Leg-Raise.gif",
    "cable_kickback": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Cable-Hip-Extension.gif",

    # flexoras
    "leg_curl_lying": "https://fitnessprogramer.com/wp-content/uploads/2015/11/Leg-Curl.gif",
    "leg_curl_seated": "https://fitnessprogramer.com/wp-content/uploads/2015/11/Seated-Leg-Curl.gif",

    # rosca alternada - link que você mandou
    "alt_db_curl": "https://fitnessprogramer.com/wp-content/uploads/2022/06/Seated-dumbbell-alternating-curl.gif",

    # panturrilha sentada - link que você mandou
    "seated_calf": "https://fitnessprogramer.com/wp-content/uploads/2021/06/Lever-Seated-Calf-Raise.gif",

    # outros
    "barbell_curl": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Barbell-Curl.gif",
    "leg_extension": "https://fitnessprogramer.com/wp-content/uploads/2021/02/LEG-EXTENSION.gif",  # atualizado
    "triceps_bar": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Cable-Triceps-Pushdown.gif",
    "triceps_rope": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Rope-Triceps-Pushdown.gif",
    "standing_calf": "https://fitnessprogramer.com/wp-content/uploads/2021/02/Standing-Calf-Raise.gif",

    # Afundo / Split Squat e variações
    "split_squat": "https://fitnessprogramer.com/wp-content/uploads/2022/12/ATG-Split-Squat.gif",
    "split_squat_db": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQMfPUcNXe8VtsptiC6de4ICwID4x17hXMcyQ&s",
    "split_squat_bb": "https://fitnessprogramer.com/wp-content/uploads/2022/04/Barbell-Split-Squat.gif",
    "split_squat_band": "https://fitnessprogramer.com/wp-content/uploads/2022/10/Banded-Split-Squat.gif",
}

# ---------- Treino por dia ----------
WORKOUTS = {
    "Segunda": [
        ("Glúteo e Posterior", "Cadeira abdutora", "4x15", GIFS["abdutora"]),
        ("Glúteo e Posterior", "Elevação pélvica (Hip Thrust)", "4x12", GIFS["hip_thrust"]),
        ("Glúteo e Posterior", "Coice e abdução na polia", "3x10", GIFS["cable_kickback"]),
        ("Glúteo e Posterior", "Búlgaro", "3x12", GIFS["bulgaro"]),
        ("Glúteo e Posterior", "Agachamento livre", "3x12", GIFS["squat"]),
        ("Glúteo e Posterior", "Stiff unilateral", "4x12", GIFS["stiff"]),
        ("Glúteo e Posterior", "Mesa flexora", "4x12", GIFS["leg_curl_lying"]),
    ],
    "Terça": [
        ("Costas / Bíceps / ABS / Panturrilha", "Puxada alta aberta", "3x12", GIFS["lat_pulldown_open"]),
        ("Costas / Bíceps / ABS / Panturrilha", "Pulldown", "3x12", GIFS["straight_pulldown"]),
        ("Costas / Bíceps / ABS / Panturrilha", "Remada baixa", "4x12", GIFS["seated_row"]),
        ("Costas / Bíceps / ABS / Panturrilha", "Rosca direta com barra", "3x12", GIFS["barbell_curl"]),
        ("Costas / Bíceps / ABS / Panturrilha", "Rosca alternada com halteres", "3x12", GIFS["alt_db_curl"]),
        ("Costas / Bíceps / ABS / Panturrilha", "Prancha", "3x30–45s", GIFS["plank"]),
        ("Costas / Bíceps / ABS / Panturrilha", "Abdominal infra (elevação de pernas)", "4x20", GIFS["leg_raise"]),
        ("Costas / Bíceps / ABS / Panturrilha", "Elevação de panturrilha sentado", "3x15–20", GIFS["seated_calf"]),
    ],
    "Quarta": [
        ("Quadríceps e Glúteo", "Cadeira extensora", "5x15", GIFS["leg_extension"]),
        ("Quadríceps e Glúteo", "Agachamento livre", "4x12", GIFS["squat"]),
        ("Quadríceps e Glúteo", "Búlgaro", "3x12", GIFS["bulgaro"]),
        ("Quadríceps e Glúteo", "Afundo (Split Squat)", "3x12", GIFS["split_squat"]),
        ("Quadríceps e Glúteo", "Leg press", "3x12", GIFS["leg_press"]),
        ("Quadríceps e Glúteo", "Cadeira abdutora", "4x12", GIFS["abdutora"]),
        ("Quadríceps e Glúteo", "Coice na polia", "3x12", GIFS["cable_kickback"]),
    ],
    "Quinta": [
        ("Ombro / Tríceps / ABS / Panturrilha", "Desenvolvimento com halteres", "3x12", GIFS["shoulder_press"]),
        ("Ombro / Tríceps / ABS / Panturrilha", "Elevação lateral com halteres", "3x12", GIFS["lateral_raise"]),
        ("Ombro / Tríceps / ABS / Panturrilha", "Elevação frontal com halteres", "3x12", GIFS["lateral_raise"]),
        ("Ombro / Tríceps / ABS / Panturrilha", "Tríceps na polia (corda)", "3x12", GIFS["triceps_rope"]),
        ("Ombro / Tríceps / ABS / Panturrilha", "Tríceps na polia (barra)", "3x12", GIFS["triceps_bar"]),
        ("Ombro / Tríceps / ABS / Panturrilha", "Prancha", "3x30–45s", GIFS["plank"]),
        ("Ombro / Tríceps / ABS / Panturrilha", "Abdominal infra (elevação de pernas)", "4x20", GIFS["leg_raise"]),
        ("Ombro / Tríceps / ABS / Panturrilha", "Elevação de panturrilha em pé", "3x15–20", GIFS["standing_calf"]),
    ],
    "Sexta": [
        ("Glúteo", "Elevação pélvica (Hip Thrust)", "4x12", GIFS["hip_thrust"]),
        ("Glúteo", "Cadeira abdutora", "4x15", GIFS["abdutora"]),
        ("Glúteo", "Coice na polia", "3x12", GIFS["cable_kickback"]),
        ("Glúteo", "Agachamento sumô", "4x12", GIFS["squat"]),
        ("Glúteo", "Búlgaro", "3x12", GIFS["bulgaro"]),
        ("Glúteo", "Stiff", "4x12", GIFS["stiff"]),
    ],
}

# ---------- Variações (Mesa flexora e Afundo) ----------
ALT_EXERCISES = {
    "Mesa flexora": [
        ("Mesa flexora", GIFS["leg_curl_lying"]),
        ("Cadeira flexora", GIFS["leg_curl_seated"]),
    ],
    "Afundo (Split Squat)": [
        ("Afundo (Split Squat)", GIFS["split_squat"]),
        ("Afundo com Halteres (Dumbbell Split Squat)", GIFS["split_squat_db"]),
        ("Afundo com Barra (Barbell Split Squat)", GIFS["split_squat_bb"]),
        ("Afundo com Elástico (Banded Split Squat)", GIFS["split_squat_band"]),
    ],
}

# (continua com a lógica completa de interface e gravação)
