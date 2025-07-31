import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from collections import defaultdict
import math
import os

# -----------------------------
# Page Config
# -----------------------------
st.set_page_config(page_title="Task Auto-Assignment System", page_icon="📋", layout="wide")

# -----------------------------
# Data Models
# -----------------------------
class TaskSimulationData:
    def __init__(self, row):
        self.product = row["Product"]
        self.description = row["Task"]
        self.task_id = row["Result"]
        # Parse requirements
        requirements_str = str(row["Requirements"])
        if pd.isna(row["Requirements"]) or requirements_str.lower() == "nan":
            self.requirements = []
        else:
            self.requirements = [r.strip() for r in requirements_str.split(",") if r.strip()]
        # Skills
        self.skill_requirements = {
            "Bending": row["Bending"] / 100,
            "Gluing": row["Gluing"] / 100,
            "Assembling": row["Assembling"] / 100,
            "EdgeScrap": row["EdgeScrap"] / 100,
            "OpenPaper": row["OpenPaper"] / 100,
            "QualityControl": row["QualityControl"] / 100,
        }
        self.time_per_piece_seconds = int(row.get("TimePerPieceSeconds", 60))

class WorkerSimulationData:
    def __init__(self, row):
        self.name = row["Worker"]
        self.skills = {
            "Bending": row["Bending"],
            "Gluing": row["Gluing"],
            "Assembling": row["Assembling"],
            "EdgeScrap": row["EdgeScrap"],
            "OpenPaper": row["OpenPaper"],
            "QualityControl": row["QualityControl"],
        }

# -----------------------------
# Load & Save Data
# -----------------------------
@st.cache_data
def load_data():
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

def save_workers_data(df):
    df.to_csv("workers.csv", index=False)
    st.cache_data.clear()

def save_products_data(df):
    df.to_csv("products.csv", index=False)
    st.cache_data.clear()

# -----------------------------
# Helper Functions
# -----------------------------
def calculate_skill_match(worker_skills, task_skill_requirements):
    total_score, count = 0, 0
    for skill, req_ratio in task_skill_requirements.items():
        if req_ratio > 0:
            total_score += worker_skills.get(skill, 0) / max(0.01, req_ratio)
            count += 1
    return total_score / count if count > 0 else 0.1

def format_time(minutes):
    hour = 8 + (minutes // 60)
    minute = minutes % 60
    return f"{hour:02d}:{minute:02d}"

def check_requirements_met(task, inventory, required_qty):
    if not task["requirements"]:
        return True
    for req in task["requirements"]:
        # Strict rule: prerequisite must be fully complete for the entire product qty
        if inventory[req] < required_qty:
            return False
    return True

# -----------------------------
# Simulation Logic
# -----------------------------
def assign_tasks(products_to_produce, available_workers_df, products_df, slot_duration_minutes=30):
    try:
        slot_duration_seconds = slot_duration_minutes * 60
        workday_minutes = 8 * 60
        task_sim_data_map = {row["Result"]: TaskSimulationData(row) for _, row in products_df.iterrows()}
        worker_sim_data_map = {row["Worker"]: WorkerSimulationData(row) for _, row in available_workers_df.iterrows()}

        # Expand tasks
        all_task_instances = []
        for product, qty in products_to_produce.items():
            tasks = products_df[products_df["Product"] == product].sort_values(by="Result")
            for _, row in tasks.iterrows():
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

            available_tasks = []
            for t in all_task_instances:
                if t["remaining_qty"] > 0:
                    product_qty = products_to_produce[t["product"]]
                    if check_requirements_met(t, inventory, product_qty):
                        available_tasks.append(t)

            if not available_tasks:
                current_time_minutes += slot_duration_minutes
                continue

            worker_assignments = {}
            for worker in worker_sim_data_map.values():
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
        }

    except Exception as e:
        st.error(f"Simulation error: {e}")
        return None

# -----------------------------
# Display Functions
# -----------------------------
def display_schedule_gantt(schedule_data, estimated_days):
    st.subheader("Schedule")
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
                            row = {"TIME": format_time(slot * 30)}
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
    tab1, tab2 = st.tabs(["📅 Schedule", "📝 Simulation Log"])
    with tab1:
        display_schedule_gantt(result["schedule"], result["estimated_days"])
    with tab2:
        st.dataframe(pd.DataFrame(result["simulation_log"]), use_container_width=True, hide_index=True)

# -----------------------------
# Main App
# -----------------------------
def main():
    workers_df, products_df = load_data()
    with st.sidebar:
        page = st.radio("Navigate", ["Home","Product Database","Worker Database","Production Order","About"])
    if page == "Home":
        st.header("Welcome")
        st.write("Auto-assign tasks based on skills and requirements.")
    elif page == "Product Database":
        st.header("📦 Product Database")
        st.dataframe(products_df, use_container_width=True)
    elif page == "Worker Database":
        st.header("👥 Worker Database")
        st.dataframe(workers_df, use_container_width=True)
    elif page == "Production Order":
        st.header("🎯 Production Order")
        products_to_produce = {}
        for product in products_df["Product"].unique():
            qty = st.number_input(f"{product}", min_value=0, max_value=1000, value=0, step=1)
            if qty > 0:
                products_to_produce[product] = qty
        selected_workers = st.multiselect("Choose Workers", workers_df["Worker"].tolist(), default=workers_df["Worker"].tolist())
        if products_to_produce and st.button("🚀 Run Simulation"):
            available_workers_df = workers_df[workers_df["Worker"].isin(selected_workers)]
            result = assign_tasks(products_to_produce, available_workers_df, products_df)
            if result:
                display_simulation_results(result)
    elif page == "About":
        st.write("This app assigns tasks respecting prerequisites and production constraints.")

if __name__ == "__main__":
    main()
