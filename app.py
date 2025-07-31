import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from collections import defaultdict
import time
import io
import base64
import math
import os # Pastikan ini diimpor untuk operasi file

# Set page configuration
st.set_page_config(
    page_title="Task Auto-Assignment System",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS to fix layout issues and add CRUD styling
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
    
    /* Ensure main content doesn't get cut off */
    .main {
        margin-left: 0;
    }
    
    /* Fix for wide layout */
    .stApp > div:first-child {
        margin-left: 0;
    }
    
    /* Specific fix for schedule tables */
    .stDataFrame, .stTable {
        width: 100% !important;
        overflow-x: auto !important;
    }
    
    /* Fix for tabs container */
    .stTabs [data-baseweb="tab-list"] {
        width: 100% !important;
    }
    
    /* Ensure schedule content is not cut off */
    .element-container {
        width: 100% !important;
    }
    
    /* Fix for dataframe display */
    div[data-testid="stDataFrame"] {
        width: 100% !important;
        overflow-x: auto !important;
    }
    
    /* Responsive adjustments */
    @media (max-width: 768px) {
        .main .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
        }
    }
    
    /* Force full width for schedule content */
    .stDataFrame > div {
        width: 100% !important;
        max_width: none !important;
    }
    
    /* Gaya Formulir CRUD */
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

# --- Data Models for Simulation ---
class TaskSimulationData:
    def __init__(self, product_row):
        self.product = product_row["Product"]
        self.description = product_row["Task"]
        self.task_id = product_row["Result"]
        # Handle NaN requirements gracefully
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
        self.duration_slot = product_row["DurationSlot"]

    def __repr__(self):
        return f"TaskSimData(ID={self.task_id}, Product={self.product}, Req={self.requirements})"

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
        # Handle potential NaN in favorite products
        self.favorite_products = [
            str(worker_row["FavoriteProduct1"]) if pd.notna(worker_row["FavoriteProduct1"]) else "",
            str(worker_row["FavoriteProduct2"]) if pd.notna(worker_row["FavoriteProduct2"]) else "",
            str(worker_row["FavoriteProduct3"]) if pd.notna(worker_row["FavoriteProduct3"]) else ""
        ]
        
        # Simulation state
        self.is_available = True
        self.current_task_instance = None
        self.time_remaining_on_task = 0
        self.expected_completion_time = 0
        self.task_history = []
        self.is_aggressive = False
        self.aggressiveness_factor = np.random.uniform(0.2, 0.8)
        self.progression_score = 0
        self.completed_products_count = defaultdict(int)
        self.total_tasks_completed_units = 0
        self.skill_utilization_score = 0
        self.time_spent_on_product = defaultdict(int)
        self.current_product_focus = None
        
    def __repr__(self):
        return f"WorkerSimData(Name={self.name}, Available={self.is_available})"

class TaskInstance:
    def __init__(self, task_sim_data, instance_idx):
        self.task_sim_data = task_sim_data
        self.instance_id = f"{task_sim_data.task_id}_U{instance_idx}"
        self.product = task_sim_data.product
        self.task_id = task_sim_data.task_id
        self.description = task_sim_data.description
        self.requirements = task_sim_data.requirements
        self.skill_requirements = task_sim_data.skill_requirements
        self.duration_slot = task_sim_data.duration_slot
        
        self.status = "pending"
        self.progress_percentage = 0.0
        self.assigned_worker_name = None
        self.start_time_minutes = None
        self.completion_time_minutes = None
        self.assigned_history = []
        
    def __repr__(self):
        return f"TaskInstance(ID={self.instance_id}, TaskType={self.task_id}, Status={self.status}, Progress={self.progress_percentage:.1f}%)"

# --- Data Loading (Diperbarui untuk membuat file jika tidak ada) ---
@st.cache_data
def load_data():
    """Memuat data dari file CSV di direktori yang sama.
    Akan membuat file CSV kosong jika tidak ditemukan.
    """
    try:
        # Muat data pekerja
        if os.path.exists("workers.csv"):
            workers_df = pd.read_csv("workers.csv")
        else:
            # Buat file pekerja default jika tidak ada
            workers_df = pd.DataFrame(columns=[
                "Worker", "Bending", "Gluing", "Assembling", "EdgeScrap",
                "OpenPaper", "QualityControl", "FavoriteProduct1",
                "FavoriteProduct2", "FavoriteProduct3"
            ])
            workers_df.to_csv("workers.csv", index=False)
        
        # Muat data produk
        if os.path.exists("products.csv"):
            products_df = pd.read_csv("products.csv")
        else:
            # Buat file produk default jika tidak ada
            products_df = pd.DataFrame(columns=[
                "Product", "Task", "Result", "Requirements", "Bending", 
                "Gluing", "Assembling", "EdgeScrap", "OpenPaper", 
                "QualityControl", "DurationSlot"
            ])
            products_df.to_csv("products.csv", index=False)
            
        return workers_df, products_df
    except Exception as e:
        st.error(f"Error memuat data: {e}")
        st.stop()

# --- Fungsi CRUD (Logika Data) ---
def save_workers_data(workers_df_to_save):
    """Menyimpan data pekerja ke CSV"""
    try:
        workers_df_to_save.to_csv("workers.csv", index=False)
        st.cache_data.clear() # Hapus cache data setelah perubahan
        return True
    except Exception as e:
        st.error(f"Error menyimpan data pekerja: {e}")
        return False

def save_products_data(products_df_to_save):
    """Menyimpan data produk ke CSV"""
    try:
        products_df_to_save.to_csv("products.csv", index=False)
        st.cache_data.clear() # Hapus cache data setelah perubahan
        return True
    except Exception as e:
        st.error(f"Error menyimpan data produk: {e}")
        return False

def add_worker(current_workers_df, worker_data):
    """Menambahkan pekerja baru ke dataframe"""
    try:
        # Periksa apakah pekerja sudah ada
        if worker_data["Worker"] in current_workers_df["Worker"].values:
            return False, "Pekerja dengan nama ini sudah ada!"
        
        # Tambahkan pekerja baru
        new_worker_df = pd.DataFrame([worker_data])
        updated_df = pd.concat([current_workers_df, new_worker_df], ignore_index=True)
        
        # Simpan ke CSV
        if save_workers_data(updated_df):
            return True, "Pekerja berhasil ditambahkan!"
        else:
            return False, "Gagal menyimpan data pekerja!"
            
    except Exception as e:
        return False, f"Error menambahkan pekerja: {e}"

def update_worker(current_workers_df, old_name, worker_data):
    """Memperbarui pekerja yang sudah ada"""
    try:
        # Temukan indeks pekerja
        worker_index = current_workers_df[current_workers_df["Worker"] == old_name].index
        
        if len(worker_index) == 0:
            return False, "Pekerja tidak ditemukan!"
        
        # Update worker data
        for col, value in worker_data.items():
            current_workers_df.loc[worker_index[0], col] = value
        
        # Simpan ke CSV
        if save_workers_data(current_workers_df):
            return True, "Pekerja berhasil diperbarui!"
        else:
            return False, "Gagal menyimpan data pekerja!"
            
    except Exception as e:
        return False, f"Error memperbarui pekerja: {e}"

def delete_worker(current_workers_df, worker_name):
    """Menghapus pekerja dari dataframe"""
    try:
        # Check if worker exists
        if worker_name not in current_workers_df["Worker"].values:
            return False, "Pekerja tidak ditemukan!"
        
        # Remove worker
        updated_df = current_workers_df[current_workers_df["Worker"] != worker_name].reset_index(drop=True)
        
        # Save to CSV
        if save_workers_data(updated_df):
            return True, "Pekerja berhasil dihapus!"
        else:
            return False, "Gagal menyimpan data pekerja!"
            
    except Exception as e:
        return False, f"Error menghapus pekerja: {e}"

def add_product(current_products_df, product_data):
    """Menambahkan produk baru ke dataframe"""
    try:
        # Periksa apakah ID hasil produk sudah ada
        if product_data["Result"] in current_products_df["Result"].values:
            return False, "Tugas produk dengan ID Hasil ini sudah ada!"
        
        # Tambahkan produk baru
        new_product_df = pd.DataFrame([product_data])
        updated_df = pd.concat([current_products_df, new_product_df], ignore_index=True)
        
        # Simpan ke CSV
        if save_products_data(updated_df):
            return True, "Tugas produk berhasil ditambahkan!"
        else:
            return False, "Gagal menyimpan data produk!"
            
    except Exception as e:
        return False, f"Error menambahkan produk: {e}"

def update_product(current_products_df, old_result_id, product_data):
    """Memperbarui produk yang sudah ada"""
    try:
        # Temukan indeks produk
        product_index = current_products_df[current_products_df["Result"] == old_result_id].index
        
        if len(product_index) == 0:
            return False, "Tugas produk tidak ditemukan!"
        
        # Perbarui data produk
        for col, value in product_data.items():
            current_products_df.loc[product_index[0], col] = value
        
        # Simpan ke CSV
        if save_products_data(current_products_df):
            return True, "Tugas produk berhasil diperbarui!"
        else:
            return False, "Gagal menyimpan data produk!"
            
    except Exception as e:
        return False, f"Error memperbarui produk: {e}"

def delete_product(current_products_df, result_id):
    """Menghapus produk dari dataframe"""
    try:
        # Periksa apakah produk ada
        if result_id not in current_products_df["Result"].values:
            return False, "Tugas produk tidak ditemukan!"
        
        # Hapus produk
        updated_df = current_products_df[current_products_df["Result"] != result_id].reset_index(drop=True)
        
        # Simpan ke CSV
        if save_products_data(updated_df):
            return True, "Tugas produk berhasil dihapus!"
        else:
            return False, "Gagal menyimpan data produk!"
            
    except Exception as e:
        return False, f"Error menghapus produk: {e}"

# Helper functions
def calculate_skill_match(worker_skills, task_skill_requirements):
    """Calculate skill match score between worker and task"""
    total_score = 0
    num_relevant_skills = 0
    
    for skill_type, required_ratio in task_skill_requirements.items():
        if required_ratio > 0:
            worker_skill = worker_skills.get(skill_type, 0)
            score = worker_skill / max(0.01, required_ratio)
            total_score += score
            num_relevant_skills += 1
            
    return total_score / num_relevant_skills if num_relevant_skills > 0 else 0.1

def format_time(minutes):
    """Convert simulation minutes to HH:MM format"""
    hours_from_start = minutes // 60
    mins_past_hour = minutes % 60
    display_hour = 8 + hours_from_start
    return f"{int(display_hour):02d}:{int(mins_past_hour):02d}"

def get_task_group(task_id):
    """Returns a generic task group ID (e.g., 'ST1' and 'SL1' both map to 'T1')"""
    if task_id.startswith("ST"):
        return f"T{task_id[2:]}"
    elif task_id.startswith("SL"):
        return f"T{task_id[2:]}"
    elif task_id.startswith("BH"):
        return f"T{task_id[2:]}"
    return task_id # Fallback for other task IDs

def check_requirements_met(task_instance, inventory, partial_completions):
    """Check if task requirements are met, considering interchangeable requirements"""
    # Tugas tanpa requirement (seperti ST1) langsung bisa dimulai
    if not task_instance.requirements:
        return True
    
    for req_task_id in task_instance.requirements:
        # Cek apakah ada task yang sama dalam grup requirement yang sudah selesai atau progres signifikan
        req_task_group = get_task_group(req_task_id)
        
        met_by_group = False
        for inv_task_id, completed_units in inventory.items():
            if get_task_group(inv_task_id) == req_task_group and completed_units >= 1:
                met_by_group = True
                break
        
        if not met_by_group:
            for pc in partial_completions:
                if get_task_group(pc["task_id"]) == req_task_group and pc["progress_percentage"] >= 50.0:
                    met_by_group = True
                    break
        
        if not met_by_group:
            return False
    return True


def get_earliest_available_tasks(all_task_instances, inventory, partial_completions):
    """Get earliest tasks that can be started (prioritizing tasks with no requirements)"""
    earliest_tasks = []
    for task_instance in all_task_instances:
        if task_instance.status == "pending" and not task_instance.requirements:
            earliest_tasks.append(task_instance)
    return earliest_tasks

def get_available_tasks(all_task_instances, inventory, partial_completions):
    """Get all tasks that can be started based on requirements"""
    available_tasks = []
    for task_instance in all_task_instances:
        if task_instance.status == "pending" and check_requirements_met(task_instance, inventory, partial_completions):
            available_tasks.append(task_instance)
    return available_tasks

def prioritize_tasks_for_flow(all_available_tasks, earliest_tasks, all_task_instances, inventory, partial_completions):
    """Prioritize tasks to optimize production flow and worker transitions"""
    prioritized_tasks = []
    
    # First prioritize all ST1 tasks since they have no requirements
    st1_tasks = [task for task in all_available_tasks if task.task_id == "ST1"]
    prioritized_tasks.extend(st1_tasks)
    
    # Then group remaining earliest tasks by task_id
    remaining_earliest = [task for task in earliest_tasks if task not in st1_tasks]
    earliest_tasks_by_id = {}
    for task in remaining_earliest:
        if task.task_id not in earliest_tasks_by_id:
            earliest_tasks_by_id[task.task_id] = []
        earliest_tasks_by_id[task.task_id].append(task)
    
    # Add remaining earliest tasks by type
    for task_id in sorted(earliest_tasks_by_id.keys()):
        prioritized_tasks.extend(earliest_tasks_by_id[task_id])

    # Add remaining available tasks
    other_tasks = [t for t in all_available_tasks if t not in prioritized_tasks]
    prioritized_tasks.extend(sorted(other_tasks, key=lambda t: (len(t.requirements), t.task_id)))  # Urutkan berdasarkan panjang requirements dan task_id

    
    return prioritized_tasks

def assign_worker_to_task(worker, task, current_time_minutes, slot_duration_minutes):
    """Assign a worker to a task"""
    worker.is_available = False
    worker.current_task_instance = task
    worker.time_remaining_on_task = task.duration_slot * slot_duration_minutes
    
    task.status = "in_progress"
    task.assigned_worker_name = worker.name
    task.start_time_minutes = current_time_minutes

# --- Core Scheduling Logic ---
def assign_tasks(products_to_produce, available_workers_df, products_df, slot_duration_minutes=30):
    """Enhanced task assignment with dynamic worker transitions and interchangeable requirements"""
    try:
        # Initialize simulation data structures
        task_sim_data_map = {row["Result"]: TaskSimulationData(row) for _, row in products_df.iterrows()}
        worker_sim_data_map = {row["Worker"]: WorkerSimulationData(row) for _, row in available_workers_df.iterrows()}
        
        # Generate unique TaskInstance objects
        all_task_instances = []
        instance_counter = defaultdict(int)
        
        for product_name, quantity in products_to_produce.items():
            product_tasks = products_df[products_df["Product"] == product_name].sort_values(by="Result")
            for unit_idx in range(quantity):
                for _, task_row in product_tasks.iterrows():
                    task_sim_data = task_sim_data_map[task_row["Result"]]
                    instance_counter[task_sim_data.task_id] += 1
                    task_instance = TaskInstance(task_sim_data, instance_counter[task_sim_data.task_id])
                    all_task_instances.append(task_instance)
        
        # Filter tasks for selected products
        all_task_instances = [ti for ti in all_task_instances if ti.product in products_to_produce]

        # Calculate simulation parameters
        total_task_slots = sum(ti.duration_slot for ti in all_task_instances)
        total_worker_slots_per_day = len(available_workers_df) * (8 * 60 / slot_duration_minutes)
        estimated_days = max(1, math.ceil(total_task_slots / total_worker_slots_per_day))
        
        # Simulation state
        current_time_minutes = 0
        max_simulation_time = estimated_days * 8 * 60  # 8 hours per day
        inventory = defaultdict(int)
        partial_completions = []
        
        # Schedule tracking
        schedule = defaultdict(lambda: defaultdict(lambda: defaultdict(str)))
        simulation_log = []
        
        # min_gap_minutes = 180
        # Main simulation loop
        while current_time_minutes < max_simulation_time:
            current_day = current_time_minutes // (8 * 60) + 1
            current_slot = (current_time_minutes % (8 * 60)) // slot_duration_minutes

            # if current_time_minutes < min_gap_minutes:
            #     current_time_minutes = min_gap_minutes
            
            # Update worker progress
            for worker_name, worker_data in worker_sim_data_map.items():
                if not worker_data.is_available and worker_data.current_task_instance:
                    worker_data.time_remaining_on_task -= slot_duration_minutes
                    
                    # Update task progress
                    task_instance = worker_data.current_task_instance
                    progress_increment = 100 / task_instance.duration_slot
                    task_instance.progress_percentage = min(100, task_instance.progress_percentage + progress_increment)
                    
                    # Check if task is completed
                    # Update worker progress
                    for worker_name, worker_data in worker_sim_data_map.items():
                        if not worker_data.is_available and worker_data.current_task_instance:
                            worker_data.time_remaining_on_task -= slot_duration_minutes
                            
                            # Update task progress
                            task_instance = worker_data.current_task_instance
                            progress_increment = 100 / task_instance.duration_slot
                            task_instance.progress_percentage = min(100, task_instance.progress_percentage + progress_increment)
                            
                            # Check if task is completed
                            if worker_data.time_remaining_on_task <= 0:
                                task_instance.status = "completed"  # Task sudah selesai
                                task_instance.completion_time_minutes = current_time_minutes
                                inventory[task_instance.task_id] += 1  # Menambah inventory dengan task yang selesai
                                
                                worker_data.is_available = True  # Worker siap untuk tugas lain
                                worker_data.current_task_instance = None  # Reset task saat ini
                                worker_data.time_remaining_on_task = 0  # Reset waktu yang tersisa

                        
                        simulation_log.append({
                            "time": format_time(current_time_minutes),
                            "event": f"Worker {worker_name} completed {task_instance.instance_id}"
                        })
            
            # Get available workers and tasks
            available_workers = [w for w in worker_sim_data_map.values() if w.is_available]
            
            # Get earliest tasks (no requirements) and all available tasks
            earliest_tasks = get_earliest_available_tasks(all_task_instances, inventory, partial_completions)
            all_available_tasks = get_available_tasks(all_task_instances, inventory, partial_completions)
            
            # Prioritize tasks for optimal flow
            prioritized_tasks = prioritize_tasks_for_flow(all_available_tasks, earliest_tasks, all_task_instances, inventory, partial_completions)
            
            # Enhanced assignment logic with smart worker distribution
            # Step 1: Identify task progression opportunities
            task_progression_map = {}
            for task in all_available_tasks:
                task_level = len(task.requirements)
                if task_level not in task_progression_map:
                    task_progression_map[task_level] = []
                task_progression_map[task_level].append(task)
            
            # Step 2: Smart worker assignment based on progression strategy
            assigned_workers = set()
            
            # Priority 1: Ensure earliest tasks (level 0) have sufficient workers
            level_0_tasks = task_progression_map.get(0, [])
            if level_0_tasks:
                workers_for_level_0 = max(1, len(available_workers) // 2)  # At least half workers on earliest tasks
                for i, task in enumerate(level_0_tasks[:workers_for_level_0]):
                    if i < len(available_workers):
                        worker = available_workers[i]
                        assign_worker_to_task(worker, task, current_time_minutes, slot_duration_minutes)
                        assigned_workers.add(worker.name)
                        
                        simulation_log.append({
                            "time": format_time(current_time_minutes),
                            "event": f"Worker {worker.name} started {task.instance_id} (earliest task priority)"
                        })
            
            # Priority 2: Assign remaining workers to highest available task level
            remaining_workers = [w for w in available_workers if w.name not in assigned_workers]
            
            # Find highest task level that has available tasks
            max_level = max(task_progression_map.keys()) if task_progression_map else 0
            
            for level in range(max_level, -1, -1):
                if level in task_progression_map and remaining_workers:
                    level_tasks = task_progression_map[level]
                    
                    # Assign workers to this level, but leave some for lower levels if needed
                    if level > 0:
                        # For higher levels, assign fewer workers to maintain balance
                        workers_for_this_level = min(len(remaining_workers) // 2, len(level_tasks))
                    else:
                        # For level 0, assign all remaining workers
                        workers_for_this_level = min(len(remaining_workers), len(level_tasks))
                    
                    for i in range(workers_for_this_level):
                        if i < len(level_tasks) and i < len(remaining_workers):
                            worker = remaining_workers[i]
                            task = level_tasks[i]
                            
                            # Check skill match
                            skill_score = calculate_skill_match(worker.skills, task.skill_requirements)
                            favorite_bonus = 1.2 if task.product in worker.favorite_products else 1.0
                            
                            assign_worker_to_task(worker, task, current_time_minutes, slot_duration_minutes)
                            assigned_workers.add(worker.name)
                            
                            simulation_log.append({
                                "time": format_time(current_time_minutes),
                                "event": f"Worker {worker.name} started {task.instance_id} (level {level}, skill: {skill_score:.2f})"
                            })
                    
                    # Remove assigned workers from remaining list
                    remaining_workers = [w for w in remaining_workers if w.name not in assigned_workers]
            
            # Priority 3: Assign any remaining workers to best available tasks
            remaining_tasks = [t for t in all_available_tasks if t.status == "pending"]
            for worker in remaining_workers:
                if not remaining_tasks:
                    break
                
                # Find best task for this worker based on priority first, then skill match
                best_task = None
                best_score = 0
                
                # First look for ST1 tasks
                st1_tasks = [t for t in remaining_tasks if t.task_id == "ST1"]
                if st1_tasks:
                    remaining_tasks = st1_tasks  # Only consider ST1 tasks if available
                
                for task in remaining_tasks:
                    skill_score = calculate_skill_match(worker.skills, task.skill_requirements)
                    favorite_bonus = 1.2 if task.product in worker.favorite_products else 1.0
                    priority_bonus = 2.0 if task.task_id == "ST1" else 1.0  # Give extra weight to ST1 tasks
                    total_score = skill_score * favorite_bonus * priority_bonus
                    
                    if total_score > best_score:
                        best_score = total_score
                        best_task = task
                
                if best_task:
                    assign_worker_to_task(worker, best_task, current_time_minutes, slot_duration_minutes)
                    remaining_tasks.remove(best_task)
                    
                    simulation_log.append({
                        "time": format_time(current_time_minutes),
                        "event": f"Worker {worker.name} started {best_task.instance_id} (fallback assignment)"
                    })
            
            # Record schedule and inventory
            inventory_str = ", ".join([f"{task_id} {count} pcs" for task_id, count in inventory.items() if count > 0])
            if not inventory_str:
                inventory_str = "None, just started"
            
            for worker_name, worker_data in worker_sim_data_map.items():
                if not worker_data.is_available and worker_data.current_task_instance:
                    task_desc = f"[{worker_data.current_task_instance.task_id}] {worker_data.current_task_instance.description}"
                    schedule[current_day][worker_name][current_slot] = task_desc
                else:
                    schedule[current_day][worker_name][current_slot] = "idle"
                    
            # Advance time
            current_time_minutes += slot_duration_minutes
            
            # Check if all tasks are completed
            if all(t.status == "completed" for t in all_task_instances):
                break
        
        return {
            "schedule": schedule,
            "inventory": dict(inventory),
            "simulation_log": simulation_log,
            "estimated_days": estimated_days,
            "all_task_instances": all_task_instances,
            "worker_sim_data_map": worker_sim_data_map
        }
    
    except Exception as e:
        st.error(f"Error in simulation: {str(e)}")
        return None

# --- Display Functions ---
def display_schedule_gantt(schedule_data, estimated_days):
    """Display schedule in simplified Gantt chart format with day tabs"""
    st.subheader("Tasks Schedule")
    
    # Create tabs for each day
    if estimated_days > 0:
        day_tabs = st.tabs([f"Day {day}" for day in range(1, estimated_days + 1)])
        
        for day_idx, day in enumerate(range(1, estimated_days + 1)):
            with day_tabs[day_idx]:
                if day in schedule_data:
                    # Create schedule table
                    day_schedule = schedule_data[day]
                    
                    # Get all time slots
                    all_slots = set()
                    for worker_schedule in day_schedule.values():
                        if isinstance(worker_schedule, dict):
                            all_slots.update(worker_schedule.keys())
                    
                    if all_slots:
                        max_slot = max(all_slots)
                        
                        # Create DataFrame for display
                        schedule_rows = []
                        for slot in range(max_slot + 1):
                            time_str = format_time(slot * 30)
                            row = {"TIME": time_str}
                            
                            # Add worker columns
                            for worker_name in sorted(day_schedule.keys()):
                                # Display "Available semi-finished tasks" as well
                                if isinstance(day_schedule[worker_name], dict):
                                    task_desc = day_schedule[worker_name].get(slot, "idle")
                                    row[f"{worker_name}"] = task_desc # Menggunakan worker_name langsung sebagai judul kolom
                            
                            schedule_rows.append(row)
                        
                        schedule_df = pd.DataFrame(schedule_rows)
                        
                        # Use container to ensure full width
                        with st.container():
                            st.dataframe(
                                schedule_df, 
                                use_container_width=True,
                                hide_index=True
                            )
                    else:
                        st.info("No schedule for today.")
                else:
                    st.info("No schedule for today.")
    else:
        st.info("No schedule data.")

def display_simulation_results(result):
    """Display simulation results in tabs"""
    if result is None:
        st.error("Simulation failed to be executed!")
        return
    
    st.success(f"Simulation successful! Estimated time: {result['estimated_days']} days")
    
    # Create tabs without Summary
    tab1, tab2, tab3 = st.tabs(["📅 Schedule", "👥 Worker Stats", "📝 Simulation Log"])
    
    with tab1:
        display_schedule_gantt(result["schedule"], result["estimated_days"])
    
    with tab2:
        st.subheader("Worker Statistics")
        
        worker_stats = []
        for worker_name, worker_data in result["worker_sim_data_map"].items():
            # Calculate completed tasks
            completed_tasks = sum(1 for ti in result["all_task_instances"] 
                                if ti.assigned_worker_name == worker_name and ti.status == "completed")
            
            # Calculate total working time
            total_working_time = sum(ti.duration_slot * 30 for ti in result["all_task_instances"] 
                                   if ti.assigned_worker_name == worker_name and ti.status == "completed")
            
            # Calculate average skill utilization
            relevant_tasks = [ti for ti in result["all_task_instances"] 
                            if ti.assigned_worker_name == worker_name and ti.status == "completed"]
            
            avg_skill_match = 0
            if relevant_tasks:
                skill_matches = [calculate_skill_match(worker_data.skills, ti.skill_requirements) 
                               for ti in relevant_tasks]
                avg_skill_match = sum(skill_matches) / len(skill_matches)
            
            worker_stats.append({
                "Worker": worker_name,
                "Tasks Completed": completed_tasks,
                "Working Time (min)": total_working_time,
                "Avg Skill Match": f"{avg_skill_match:.2f}",
                "Status": "Available" if worker_data.is_available else "Busy"
            })
        
        worker_stats_df = pd.DataFrame(worker_stats)
        st.dataframe(worker_stats_df, use_container_width=True, hide_index=True)
        
        # Worker skill utilization chart
        if worker_stats:
            chart_data = pd.DataFrame([
                {"Worker": ws["Worker"], "Skill Match": float(ws["Avg Skill Match"])} 
                for ws in worker_stats if float(ws["Avg Skill Match"]) > 0
            ])
            
            if not chart_data.empty:
                st.subheader("Worker Skill Utilization")
                skill_chart = alt.Chart(chart_data).mark_bar().encode(
                    x=alt.X('Worker:N', sort='-y'),
                    y=alt.Y('Skill Match:Q', scale=alt.Scale(domain=[0, 2])),
                    color=alt.condition(
                        alt.datum['Skill Match'] > 1.0,
                        alt.value('steelblue'),
                        alt.value('orange')
                    ),
                    tooltip=['Worker:N', 'Skill Match:Q']
                ).properties(
                    width=600,
                    height=300,
                    title="Average Skill Match Score by Worker"
                )
                st.altair_chart(skill_chart, use_container_width=True)
    
    with tab3:
        st.subheader("Simulation Log")
        if result["simulation_log"]:
            log_df = pd.DataFrame(result["simulation_log"])
            st.dataframe(log_df, use_container_width=True, hide_index=True)
        else:
            st.info("No simulation events recorded.")

def get_table_download_link(df, filename, text):
    """Generate a link to download the dataframe as a CSV file"""
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}" style="color:blue;">{text}</a>'
    return href

# --- Fungsi Antarmuka CRUD (Streamlit UI) ---
def render_workers_crud(workers_df_current):
    """Merender antarmuka CRUD untuk pekerja"""
    st.markdown('<div class="crud-section">', unsafe_allow_html=True)
    st.subheader("👥 Manajemen Pekerja")

    # Tampilkan pekerja saat ini
    st.write("**Pekerja Saat Ini:**")
    if not workers_df_current.empty:
        st.dataframe(workers_df_current, use_container_width=True, hide_index=True)
    else:
        st.info("Tidak ada pekerja ditemukan. Tambahkan pekerja di bawah.")

    # Operasi CRUD
    operation = st.selectbox("Pilih Operasi:", ["Tambah Pekerja", "Perbarui Pekerja", "Hapus Pekerja"])

    if operation == "Tambah Pekerja":
        with st.form("add_worker_form"):
            st.write("**Tambah Pekerja Baru**")

            col1, col2 = st.columns(2)
            with col1:
                worker_name = st.text_input("Nama Pekerja*")
                bending = st.slider("Kemampuan Bending", 0, 100, 50)
                gluing = st.slider("Kemampuan Gluing", 0, 100, 50)
                assembling = st.slider("Kemampuan Assembling", 0, 100, 50)

            with col2:
                edge_scrap = st.slider("Kemampuan EdgeScrap", 0, 100, 50)
                open_paper = st.slider("Kemampuan OpenPaper", 0, 100, 50)
                quality_control = st.slider("Kemampuan QualityControl", 0, 100, 50)

            st.write("**Produk Favorit (opsional):**")
            col3, col4, col5 = st.columns(3)
            with col3:
                fav1 = st.text_input("Produk Favorit 1")
            with col4:
                fav2 = st.text_input("Produk Favorit 2")
            with col5:
                fav3 = st.text_input("Produk Favorit 3")

            submitted = st.form_submit_button("Tambah Pekerja")

            if submitted:
                if worker_name.strip():
                    worker_data = {
                        "Worker": worker_name.strip(),
                        "Bending": bending,
                        "Gluing": gluing,
                        "Assembling": assembling,
                        "EdgeScrap": edge_scrap,
                        "OpenPaper": open_paper,
                        "QualityControl": quality_control,
                        "FavoriteProduct1": fav1.strip() if fav1.strip() else "",
                        "FavoriteProduct2": fav2.strip() if fav2.strip() else "",
                        "FavoriteProduct3": fav3.strip() if fav3.strip() else ""
                    }

                    success, message = add_worker(workers_df_current, worker_data)
                    if success:
                        st.markdown(f'<div class="success-box">{message}</div>', unsafe_allow_html=True)
                        st.rerun() # Memuat ulang aplikasi untuk melihat perubahan
                    else:
                        st.markdown(f'<div class="error-box">{message}</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="error-box">Nama pekerja wajib diisi!</div>', unsafe_allow_html=True)

    elif operation == "Perbarui Pekerja":
        if not workers_df_current.empty:
            selected_worker = st.selectbox("Pilih Pekerja untuk Diperbarui:", workers_df_current["Worker"].tolist())

            if selected_worker:
                # Dapatkan data pekerja saat ini
                current_data = workers_df_current[workers_df_current["Worker"] == selected_worker].iloc[0]

                with st.form("update_worker_form"):
                    st.write(f"**Perbarui Pekerja: {selected_worker}**")

                    col1, col2 = st.columns(2)
                    with col1:
                        new_name = st.text_input("Nama Pekerja*", value=current_data["Worker"])
                        bending = st.slider("Kemampuan Bending", 0, 100, int(current_data["Bending"]))
                        gluing = st.slider("Kemampuan Gluing", 0, 100, int(current_data["Gluing"]))
                        assembling = st.slider("Kemampuan Assembling", 0, 100, int(current_data["Assembling"]))

                    with col2:
                        edge_scrap = st.slider("Kemampuan EdgeScrap", 0, 100, int(current_data["EdgeScrap"]))
                        open_paper = st.slider("Kemampuan OpenPaper", 0, 100, int(current_data["OpenPaper"]))
                        quality_control = st.slider("Kemampuan QualityControl", 0, 100, int(current_data["QualityControl"]))

                    st.write("**Produk Favorit:**")
                    col3, col4, col5 = st.columns(3)
                    with col3:
                        fav1 = st.text_input("Produk Favorit 1", value=str(current_data["FavoriteProduct1"]) if pd.notna(current_data["FavoriteProduct1"]) else "")
                    with col4:
                        fav2 = st.text_input("Produk Favorit 2", value=str(current_data["FavoriteProduct2"]) if pd.notna(current_data["FavoriteProduct2"]) else "")
                    with col5:
                        fav3 = st.text_input("Produk Favorit 3", value=str(current_data["FavoriteProduct3"]) if pd.notna(current_data["FavoriteProduct3"]) else "")

                    submitted = st.form_submit_button("Perbarui Pekerja")

                    if submitted:
                        if new_name.strip():
                            worker_data = {
                                "Worker": new_name.strip(),
                                "Bending": bending,
                                "Gluing": gluing,
                                "Assembling": assembling,
                                "EdgeScrap": edge_scrap,
                                "OpenPaper": open_paper,
                                "QualityControl": quality_control,
                                "FavoriteProduct1": fav1.strip() if fav1.strip() else "",
                                "FavoriteProduct2": fav2.strip() if fav2.strip() else "",
                                "FavoriteProduct3": fav3.strip() if fav3.strip() else ""
                            }

                            success, message = update_worker(workers_df_current, selected_worker, worker_data)
                            if success:
                                st.markdown(f'<div class="success-box">{message}</div>', unsafe_allow_html=True)
                                st.rerun() # Memuat ulang aplikasi untuk melihat perubahan
                            else:
                                st.markdown(f'<div class="error-box">{message}</div>', unsafe_allow_html=True)
                        else:
                            st.markdown('<div class="error-box">Nama pekerja wajib diisi!</div>', unsafe_allow_html=True)
        else:
            st.info("Tidak ada pekerja yang tersedia untuk diperbarui.")

    elif operation == "Hapus Pekerja":
        if not workers_df_current.empty:
            selected_worker = st.selectbox("Pilih Pekerja untuk Dihapus:", workers_df_current["Worker"].tolist())

            if selected_worker:
                st.warning(f"Apakah Anda yakin ingin menghapus pekerja: **{selected_worker}**?")

                col1, col2 = st.columns([1, 4])
                with col1:
                    if st.button("🗑️ Hapus", type="secondary"):
                        success, message = delete_worker(workers_df_current, selected_worker)
                        if success:
                            st.markdown(f'<div class="success-box">{message}</div>', unsafe_allow_html=True)
                            st.rerun() # Memuat ulang aplikasi untuk melihat perubahan
                        else:
                            st.markdown(f'<div class="error-box">{message}</div>', unsafe_allow_html=True)
        else:
            st.info("Tidak ada pekerja yang tersedia untuk dihapus.")

    st.markdown('</div>', unsafe_allow_html=True)

def render_products_crud(products_df_current):
    """Merender antarmuka CRUD untuk produk"""
    st.markdown('<div class="crud-section">', unsafe_allow_html=True)
    st.subheader("📦 Manajemen Tugas Produk")

    # Tampilkan produk saat ini
    st.write("**Tugas Produk Saat Ini:**")
    if not products_df_current.empty:
        st.dataframe(products_df_current, use_container_width=True, hide_index=True)
    else:
        st.info("Tidak ada tugas produk ditemukan. Tambahkan tugas produk di bawah.")

    # Operasi CRUD
    operation = st.selectbox("Pilih Operasi:", ["Tambah Tugas Produk", "Perbarui Tugas Produk", "Hapus Tugas Produk"], key="product_operation")

    if operation == "Tambah Tugas Produk":
        with st.form("add_product_form"):
            st.write("**Tambah Tugas Produk Baru**")

            col1, col2 = st.columns(2)
            with col1:
                product = st.text_input("Nama Produk*")
                task = st.text_input("Deskripsi Tugas*")
                result_id = st.text_input("ID Hasil*")
                requirements = st.text_input("Persyaratan (dipisahkan koma)")
                duration_slot = st.number_input("Durasi Slot", min_value=1, value=1)

            with col2:
                st.write("**Persyaratan Kemampuan (0-100):**")
                bending = st.slider("Bending", 0, 100, 0, key="add_bending")
                gluing = st.slider("Gluing", 0, 100, 0, key="add_gluing")
                assembling = st.slider("Assembling", 0, 100, 0, key="add_assembling")
                edge_scrap = st.slider("EdgeScrap", 0, 100, 0, key="add_edge")
                open_paper = st.slider("OpenPaper", 0, 100, 0, key="add_paper")
                quality_control = st.slider("QualityControl", 0, 100, 0, key="add_qc")

            submitted = st.form_submit_button("Tambah Tugas Produk")

            if submitted:
                if product.strip() and task.strip() and result_id.strip():
                    product_data = {
                        "Product": product.strip(),
                        "Task": task.strip(),
                        "Result": result_id.strip(),
                        "Requirements": requirements.strip() if requirements.strip() else "",
                        "Bending": bending,
                        "Gluing": gluing,
                        "Assembling": assembling,
                        "EdgeScrap": edge_scrap,
                        "OpenPaper": open_paper,
                        "QualityControl": quality_control,
                        "DurationSlot": duration_slot
                    }

                    success, message = add_product(products_df_current, product_data)
                    if success:
                        st.markdown(f'<div class="success-box">{message}</div>', unsafe_allow_html=True)
                        st.rerun() # Memuat ulang aplikasi untuk melihat perubahan
                    else:
                        st.markdown(f'<div class="error-box">{message}</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="error-box">Nama produk, deskripsi tugas, dan ID hasil wajib diisi!</div>', unsafe_allow_html=True)

    elif operation == "Perbarui Tugas Produk":
        if not products_df_current.empty:
            selected_product = st.selectbox("Pilih Tugas Produk untuk Diperbarui:", products_df_current["Result"].tolist(), key="update_product_select")

            if selected_product:
                # Dapatkan data produk saat ini
                current_data = products_df_current[products_df_current["Result"] == selected_product].iloc[0]

                with st.form("update_product_form"):
                    st.write(f"**Perbarui Tugas Produk: {selected_product}**")

                    col1, col2 = st.columns(2)
                    with col1:
                        product = st.text_input("Nama Produk*", value=current_data["Product"])
                        task = st.text_input("Deskripsi Tugas*", value=current_data["Task"])
                        result_id = st.text_input("ID Hasil*", value=current_data["Result"])
                        requirements = st.text_input("Persyaratan (dipisahkan koma)",
                                                   value=str(current_data["Requirements"]) if pd.notna(current_data["Requirements"]) else "")
                        duration_slot = st.number_input("Durasi Slot", min_value=1, value=int(current_data["DurationSlot"]))

                    with col2:
                        st.write("**Persyaratan Kemampuan (0-100):**")
                        bending = st.slider("Bending", 0, 100, int(current_data["Bending"]), key="upd_bending")
                        gluing = st.slider("Gluing", 0, 100, int(current_data["Gluing"]), key="upd_gluing")
                        assembling = st.slider("Assembling", 0, 100, int(current_data["Assembling"]), key="upd_assembling")
                        edge_scrap = st.slider("EdgeScrap", 0, 100, int(current_data["EdgeScrap"]), key="upd_edge")
                        open_paper = st.slider("OpenPaper", 0, 100, int(current_data["OpenPaper"]), key="upd_paper")
                        quality_control = st.slider("QualityControl", 0, 100, int(current_data["QualityControl"]), key="upd_qc")

                    submitted = st.form_submit_button("Perbarui Tugas Produk")

                    if submitted:
                        if product.strip() and task.strip() and result_id.strip():
                            product_data = {
                                "Product": product.strip(),
                                "Task": task.strip(),
                                "Result": result_id.strip(),
                                "Requirements": requirements.strip() if requirements.strip() else "",
                                "Bending": bending,
                                "Gluing": gluing,
                                "Assembling": assembling,
                                "EdgeScrap": edge_scrap,
                                "OpenPaper": open_paper,
                                "QualityControl": quality_control,
                                "DurationSlot": duration_slot
                            }

                            success, message = update_product(products_df_current, selected_product, product_data)
                            if success:
                                st.markdown(f'<div class="success-box">{message}</div>', unsafe_allow_html=True)
                                st.rerun() # Memuat ulang aplikasi untuk melihat perubahan
                            else:
                                st.markdown(f'<div class="error-box">{message}</div>', unsafe_allow_html=True)
                        else:
                            st.markdown('<div class="error-box">Nama produk, deskripsi tugas, dan ID hasil wajib diisi!</div>', unsafe_allow_html=True)
        else:
            st.info("Tidak ada tugas produk yang tersedia untuk diperbarui.")

    elif operation == "Hapus Tugas Produk":
        if not products_df_current.empty:
            selected_product = st.selectbox("Pilih Tugas Produk untuk Dihapus:", products_df_current["Result"].tolist(), key="delete_product_select")

            if selected_product:
                st.warning(f"Apakah Anda yakin ingin menghapus tugas produk: **{selected_product}**?")

                col1, col2 = st.columns([1, 4])
                with col1:
                    if st.button("🗑️ Hapus", type="secondary", key="delete_product_btn"):
                        success, message = delete_product(products_df_current, selected_product)
                        if success:
                            st.markdown(f'<div class="success-box">{message}</div>', unsafe_allow_html=True)
                            st.rerun() # Memuat ulang aplikasi untuk melihat perubahan
                        else:
                            st.markdown(f'<div class="error-box">{message}</div>', unsafe_allow_html=True)
        else:
            st.info("Tidak ada tugas produk yang tersedia untuk dihapus.")

    st.markdown('</div>', unsafe_allow_html=True)


# --- Main Application ---
def main():
    # Load data
    try:
        workers_df, products_df = load_data()
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        return
    
    # Sidebar navigation
    with st.sidebar:
        st.header("Navigation")
        # Menambahkan opsi navigasi untuk CRUD
        page = st.radio("Go to", ["Home", "Product Database", "Worker Database", "Production Order", "Manage Workers", "Manage Products", "About"])
    
    if page == "Home":
        st.header("Welcome to Worker Task Autoassign System")
        
        st.write("This system helps you organize employee assignments automatically based on:")
        
        st.write("• **Employee expertise** in different type of tasks")
        st.write("• **Dependencies between tasks** in the production process")
        st.write("• **Product preferences** of each employee")
        st.write("• **Dynamic assignment strategies** to maximize efficiency")
        
        # Display summary statistics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Product(s)", len(products_df["Product"].unique()))
        
        with col2:
            st.metric("Total Worker(s)", len(workers_df))
        
        with col3:
            st.metric("Total Type of Task(s)", len(products_df))
        
        st.subheader("Main Features")
        
        st.write("📊 **Product and Worker Database**: View and manage master data")
        st.write("🎯 **Production Order**: Create and manage production orders")
        st.write("📈 **Real-Time Analysis**: View assignment results and performance statistics")
        st.write("🔄 **Dynamic Assignment**: Employees can switch tasks optimally")
        st.write("👥 **Manage Workers**: Add, update, or delete worker profiles (new!)")
        st.write("📦 **Manage Products**: Add, update, or delete product tasks (new!)")
    
    elif page == "Product Database":
        st.header("📦 Product Database")
        st.dataframe(products_df, use_container_width=True)
        # Add flow diagram and attribute distribution if desired (from previous versions)
        # For simplicity, keeping it basic as per the provided app.py's Product Database section

        # As per the provided `app.py`, this section was simplified,
        # but if you need the detailed charts back, let me know.
        # For now, just showing the dataframe.

        # Example of how to add the detailed charts back:
        # # Group products and show their tasks
        # for product in products_df['Product'].unique():
        #     with st.expander(f"**{product}**"):
        #         product_tasks = products_df[products_df['Product'] == product]
        #         st.dataframe(product_tasks)
        #         # ... (add Altair chart logic for tasks and dependencies here) ...
        
        # # Show skill attribute distribution
        # st.markdown('<div class="sub-header">Distribusi Atribut Tugas</div>', unsafe_allow_html=True)
        # # ... (add Altair chart logic for attribute distribution here) ...
    
    elif page == "Worker Database":
        st.header("👥 Worker Database")
        st.dataframe(workers_df, use_container_width=True)
        # Add worker skill charts and preferences if desired (from previous versions)
        # For simplicity, keeping it basic as per the provided app.py's Worker Database section

        # Example of how to add the detailed charts back:
        # for _, worker in workers_df.iterrows():
        #     with st.expander(f"**{worker['Worker']}**"):
        #         col1, col2 = st.columns([3, 2])
        #         with col1:
        #             # Display worker skills chart
        #             # ... (add Altair chart logic for worker skills here) ...
        #         with col2:
        #             # Display worker preferences
        #             # ... (add worker preferences display here) ...
    
    elif page == "Production Order":
        st.header("🎯 Production Order")
        
        # Product selection and quantity input
        st.subheader("Make a Production Order")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Choose Product and Quantity:**")
            
            products_to_produce = {}
            # Re-load unique_products here to ensure it's up-to-date with any CRUD changes
            current_products_df = load_data()[1] 
            unique_products_for_order = current_products_df["Product"].unique()
            
            for product in unique_products_for_order:
                quantity = st.number_input(
                    product, 
                    min_value=0, 
                    max_value=1000, 
                    value=0, 
                    step=1,
                    key=f"qty_{product}"
                )
                if quantity > 0:
                    products_to_produce[product] = quantity
        
        with col2:
            st.write("**Choose Worker(s):**")
            # Re-load workers_df here to ensure it's up-to-date with any CRUD changes
            current_workers_df = load_data()[0]
            selected_workers = st.multiselect(
                "Choose Worker(s)",
                current_workers_df["Worker"].tolist(),
                default=current_workers_df["Worker"].tolist()
            )
        
        # Order summary
        if products_to_produce:
            st.subheader("Order Summary")
            
            for product, qty in products_to_produce.items():
                st.write(f"• **{product}**: {qty} unit(s)")
            
            st.write(f"• **Available worker(s)**: {len(selected_workers)} person(s)")
            
            # Run simulation button
            if st.button("🚀 Run Simulation"):
                if not selected_workers:
                    st.error("Select at least one worker!")
                else:
                    with st.spinner("Running Simulation..."):
                        available_workers_df = current_workers_df[current_workers_df["Worker"].isin(selected_workers)]
                        
                        result = assign_tasks(
                            products_to_produce=products_to_produce,
                            available_workers_df=available_workers_df,
                            products_df=current_products_df, # Pastikan menggunakan products_df terbaru
                            slot_duration_minutes=30
                        )
                        
                        if result:
                            display_simulation_results(result)
        
    elif page == "Manage Workers":
        # Muat ulang data untuk mendapatkan perubahan terbaru
        workers_df_latest, _ = load_data()
        render_workers_crud(workers_df_latest)
    
    elif page == "Manage Products":
        # Muat ulang data untuk mendapatkan perubahan terbaru
        _, products_df_latest = load_data()
        render_products_crud(products_df_latest)

    elif page == "About":
        st.header("About the System")
        
        st.write("**Task Auto-Assignment System** is an application designed to optimize employee assignments in the production process.")
        
        st.subheader("Key Features:")
        st.write("• Auto-assignment based on skills")
        st.write("• Dependency management between tasks")
        st.write("• Real-time simulation")
        st.write("• Worker performance analysis")
        st.write("• CRUD for Workers and Products") # Tambahkan fitur baru
        
        st.subheader("Technology:")
        st.write("• Python & Streamlit")
        st.write("• Pandas for data manipulation")
        st.write("• Assignment optimization algorithm")

if __name__ == "__main__":
    main()
