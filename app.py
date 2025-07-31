import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from collections import defaultdict
import time
import io
import base64
import math
import os

# -----------------------------
# Page Configuration
# -----------------------------
st.set_page_config(
    page_title="Task Auto-Assignment System",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------
# Custom CSS for Layout & Styling
# -----------------------------
st.markdown("""
<style>
    .main .block-container {
        padding-left: 2rem;
        padding-right: 2rem;
        max-width: none;
    }
    .sidebar .sidebar-content {
        width: 21rem;
    }
    .main {
        margin-left: 0;
    }
    .stApp > div:first-child {
        margin-left: 0;
    }
    .stDataFrame, .stTable {
        width: 100% !important;
        overflow-x: auto !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        width: 100% !important;
    }
    .element-container {
        width: 100% !important;
    }
    div[data-testid="stDataFrame"] {
        width: 100% !important;
        overflow-x: auto !important;
    }
    @media (max-width: 768px) {
        .main .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
        }
    }
    .stDataFrame > div {
        width: 100% !important;
        max_width: none !important;
    }
    .crud-section {
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 20px;
        margin: 10px 0;
        background-color: #f8f9fa;
    }
    .success-box {
        padding: 10px;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 5px;
        color: #155724;
        margin: 10px 0;
    }
    .error-box {
        padding: 10px;
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        border-radius: 5px;
        color: #721c24;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------
# Data Models
# -----------------------------
class TaskSimulationData:
    def __init__(self, product_row):
        self.product = product_row["Product"]
        self.description = product_row["Task"]
        self.task_id = product_row["Result"]
        # Handle NaN requirements
        requirements_str = str(product_row["Requirements"])
        if pd.isna(product_row["Requirements"]) or requirements_str.lower() == "nan":
            self.requirements = []
        else:
            self.requirements = [req.strip() for req in requirements_str.split(",") if req.strip()]
        
        self.skill_requirements = {
            "Bending": product_row["Bending"] / 100,
            "Gluing": product_row["Gluing"] / 100,
            "Assembling": product_row["Assembling"] / 100,
            "EdgeScrap": product_row["EdgeScrap"] / 100,
            "OpenPaper": product_row["OpenPaper"] / 100,
            "QualityControl": product_row["QualityControl"] / 100,
        }
        self.time_per_piece_seconds = int(product_row.get("TimePerPieceSeconds", 60))  # Default 60s if missing

class WorkerSimulationData:
    def __init__(self, worker_row):
        self.name = worker_row["Worker"]
        self.skills = {
            "Bending": worker_row["Bending"],
            "Gluing": worker_row["Gluing"],
            "Assembling": worker_row["Assembling"],
            "EdgeScrap": worker_row["EdgeScrap"],
            "OpenPaper": worker_row["OpenPaper"],
            "QualityControl": worker_row["QualityControl"],
        }
        self.favorite_products = [
            str(worker_row["FavoriteProduct1"]) if pd.notna(worker_row["FavoriteProduct1"]) else "",
            str(worker_row["FavoriteProduct2"]) if pd.notna(worker_row["FavoriteProduct2"]) else "",
            str(worker_row["FavoriteProduct3"]) if pd.notna(worker_row["FavoriteProduct3"]) else ""
        ]

# -----------------------------
# Data Loading & Saving
# -----------------------------
@st.cache_data
def load_data():
    try:
        if os.path.exists("workers.csv"):
            workers_df = pd.read_csv("workers.csv")
        else:
            workers_df = pd.DataFrame(columns=[
                "Worker","Bending","Gluing","Assembling","EdgeScrap","OpenPaper","QualityControl",
                "FavoriteProduct1","FavoriteProduct2","FavoriteProduct3"
            ])
            workers_df.to_csv("workers.csv", index=False)
        
        if os.path.exists("products.csv"):
            products_df = pd.read_csv("products.csv")
        else:
            products_df = pd.DataFrame(columns=[
                "Product","Task","Result","Requirements","Bending","Gluing","Assembling",
                "EdgeScrap","OpenPaper","QualityControl","TimePerPieceSeconds"
            ])
            products_df.to_csv("products.csv", index=False)

        return workers_df, products_df
    except Exception as e:
        st.error(f"Error loading data: {e}")
        st.stop()

def save_workers_data(df):
    try:
        df.to_csv("workers.csv", index=False)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error saving workers: {e}")
        return False

def save_products_data(df):
    try:
        df.to_csv("products.csv", index=False)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error saving products: {e}")
        return False

# -----------------------------
# Helper Functions
# -----------------------------
def calculate_skill_match(worker_skills, task_skill_requirements):
    total_score = 0
    count = 0
    for skill, required_ratio in task_skill_requirements.items():
        if required_ratio > 0:
            score = worker_skills.get(skill, 0) / max(0.01, required_ratio)
            total_score += score
            count += 1
    return total_score / count if count > 0 else 0.1

def format_time(minutes):
    hours_from_start = minutes // 60
    mins_past_hour = minutes % 60
    display_hour = 8 + hours_from_start
    return f"{int(display_hour):02d}:{int(mins_past_hour):02d}"

def check_requirements_met_for_qty(task, inventory):
    if not task["requirements"]:
        return True
    for req in task["requirements"]:
        if inventory[req] <= 0:
            return False
    return True

# -----------------------------
# Core Simulation (Quantity-Based)
# -----------------------------
def assign_tasks(products_to_produce, available_workers_df, products_df, slot_duration_minutes=30):
    try:
        slot_duration_seconds = slot_duration_minutes * 60
        workday_minutes = 8 * 60
        workday_slots = workday_minutes // slot_duration_minutes

        task_sim_data_map = {row["Result"]: TaskSimulationData(row) for _, row in products_df.iterrows()}
        worker_sim_data_map = {row["Worker"]: WorkerSimulationData(row) for _, row in available_workers_df.iterrows()}

        all_task_instances = []
        for product_name, qty in products_to_produce.items():
            product_tasks = products_df[products_df["Product"] == product_name].sort_values(by="Result")
            for _, row in product_tasks.iterrows():
                sim = task_sim_data_map[row["Result"]]
                all_task_instances.append({
                    "task_id": sim.task_id,
                    "description": sim.description,
                    "product": sim.product,
                    "requirements": sim.requirements,
                    "skill_requirements": sim.skill_requirements,
                    "time_per_piece": sim.time_per_piece_seconds,
                    "remaining_qty": qty
                })

        total_seconds = sum(t["time_per_piece"] * t["remaining_qty"] for t in all_task_instances)
        total_worker_seconds_per_day = len(available_workers_df) * workday_minutes * 60
        estimated_days = max(1, math.ceil(total_seconds / total_worker_seconds_per_day))

        current_time_minutes = 0
        current_day = 1
        inventory = defaultdict(int)
        schedule = defaultdict(lambda: defaultdict(lambda: defaultdict(str)))
        simulation_log = []

        while True:
            if all(t["remaining_qty"] <= 0 for t in all_task_instances):
                break

            current_day = (current_time_minutes // workday_minutes) + 1
            current_slot = (current_time_minutes % workday_minutes) // slot_duration_minutes
            available_workers = list(worker_sim_data_map.values())

            available_tasks = [t for t in all_task_instances if t["remaining_qty"] > 0 and check_requirements_met_for_qty(t, inventory)]
            if not available_tasks:
                current_time_minutes += slot_duration_minutes
                continue

            worker_assignments = {}
            for worker in available_workers:
                if not available_tasks:
                    break
                best_task = max(
                    available_tasks,
                    key=lambda task: (calculate_skill_match(worker.skills, task["skill_requirements"]), task["remaining_qty"])
                )
                worker_assignments[worker.name] = best_task

            for worker_name, task in worker_assignments.items():
                time_remaining = slot_duration_seconds
                dominant_task = task["task_id"]
                pieces_total = 0

                while time_remaining > 0 and task:
                    if task["remaining_qty"] <= 0:
                        available_tasks = [t for t in available_tasks if t["remaining_qty"] > 0]
                        if not available_tasks:
                            break
                        task = max(available_tasks, key=lambda t: t["remaining_qty"])
                        continue

                    tpp = task["time_per_piece"]
                    max_pieces = min(task["remaining_qty"], time_remaining // tpp)
                    if max_pieces > 0:
                        task["remaining_qty"] -= max_pieces
                        inventory[task["task_id"]] += max_pieces
                        pieces_total += max_pieces
                        time_spent = max_pieces * tpp
                        time_remaining -= time_spent

                        simulation_log.append({
                            "time": format_time(current_time_minutes),
                            "event": f"Worker {worker_name} produced {max_pieces} pcs of {task['task_id']} ({task['description']})"
                        })
                    else:
                        break

                schedule[current_day][worker_name][current_slot] = f"[{dominant_task}] {task['description']} ({pieces_total} pcs)"

            current_time_minutes += slot_duration_minutes
            if current_time_minutes > estimated_days * workday_minutes * 2:
                break

        return {
            "schedule": schedule,
            "inventory": dict(inventory),
            "simulation_log": simulation_log,
            "estimated_days": current_day,
            "all_task_instances": all_task_instances,
            "worker_sim_data_map": worker_sim_data_map
        }

    except Exception as e:
        st.error(f"Error in simulation: {e}")
        return None

# -----------------------------
# Display Functions
# -----------------------------
def display_schedule_gantt(schedule_data, estimated_days):
    st.subheader("Tasks Schedule")
    if estimated_days > 0:
        day_tabs = st.tabs([f"Day {d}" for d in range(1, estimated_days + 1)])
        for idx, day in enumerate(range(1, estimated_days + 1)):
            with day_tabs[idx]:
                if day in schedule_data:
                    day_schedule = schedule_data[day]
                    all_slots = set()
                    for ws in day_schedule.values():
                        all_slots.update(ws.keys())
                    if all_slots:
                        max_slot = max(all_slots)
                        rows = []
                        for slot in range(max_slot + 1):
                            time_str = format_time(slot * 30)
                            row = {"TIME": time_str}
                            for worker in sorted(day_schedule.keys()):
                                row[worker] = day_schedule[worker].get(slot, "idle")
                            rows.append(row)
                        df = pd.DataFrame(rows)
                        st.dataframe(df, use_container_width=True, hide_index=True)
                    else:
                        st.info("No schedule for this day.")
                else:
                    st.info("No schedule for this day.")
    else:
        st.info("No schedule data.")

def display_simulation_results(result):
    if result is None:
        st.error("Simulation failed!")
        return
    st.success(f"Simulation completed! Estimated {result['estimated_days']} day(s).")
    tab1, tab2, tab3 = st.tabs(["📅 Schedule", "👥 Worker Stats", "📝 Simulation Log"])
    with tab1:
        display_schedule_gantt(result["schedule"], result["estimated_days"])
    with tab2:
        st.subheader("Worker Statistics")
        st.write("Currently simplified stats")
    with tab3:
        log_df = pd.DataFrame(result["simulation_log"])
        st.dataframe(log_df, use_container_width=True, hide_index=True)

# -----------------------------
# CRUD for Workers
# -----------------------------
def render_workers_crud(df):
    st.markdown('<div class="crud-section">', unsafe_allow_html=True)
    st.subheader("👥 Manage Workers")
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)

# -----------------------------
# CRUD for Products
# -----------------------------
def render_products_crud(df):
    st.markdown('<div class="crud-section">', unsafe_allow_html=True)
    st.subheader("📦 Manage Products")
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)

# -----------------------------
# Main Application
# -----------------------------
def main():
    workers_df, products_df = load_data()
    with st.sidebar:
        page = st.radio("Navigate", ["Home","Product Database","Worker Database","Production Order","Manage Workers","Manage Products","About"])
    if page == "Home":
        st.header("Welcome to Worker Task Autoassign System")
        st.write("Automatically assigns tasks based on skills and requirements.")
    elif page == "Product Database":
        st.header("📦 Product Database")
        st.dataframe(products_df, use_container_width=True)
    elif page == "Worker Database":
        st.header("👥 Worker Database")
        st.dataframe(workers_df, use_container_width=True)
    elif page == "Production Order":
        st.header("🎯 Production Order")
        products_to_produce = {}
        col1, col2 = st.columns(2)
        with col1:
            for product in products_df["Product"].unique():
                qty = st.number_input(f"{product}", min_value=0, max_value=1000, value=0, step=1)
                if qty > 0:
                    products_to_produce[product] = qty
        with col2:
            selected_workers = st.multiselect("Choose Worker(s)", workers_df["Worker"].tolist(), default=workers_df["Worker"].tolist())
        if products_to_produce:
            st.subheader("Order Summary")
            st.write(products_to_produce)
            if st.button("🚀 Run Simulation"):
                available_workers_df = workers_df[workers_df["Worker"].isin(selected_workers)]
                result = assign_tasks(products_to_produce, available_workers_df, products_df)
                if result:
                    display_simulation_results(result)
    elif page == "Manage Workers":
        render_workers_crud(workers_df)
    elif page == "Manage Products":
        render_products_crud(products_df)
    elif page == "About":
        st.header("About")
        st.write("This app assigns tasks based on skills, requirements, and production constraints.")

if __name__ == "__main__":
    main()
