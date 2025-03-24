import time
from collections import deque
import random
import threading
import queue
import tkinter as tk
from tkinter import ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

# Simulated CPU frequency levels (in GHz) and power consumption (relative units)
FREQUENCY_LEVELS = {
    "low": {"freq": 0.8, "power": 0.5},
    "mid": {"freq": 1.2, "power": 1.0},
    "high": {"freq": 2.0, "power": 2.0}
}

# Task class
class Task:
    def __init__(self, task_id, priority, est_exec_time, deadline=None, arrival_time=None):
        self.task_id = task_id
        self.priority = priority
        self.est_exec_time = est_exec_time
        self.deadline = deadline if deadline else float('inf')
        self.arrival_time = arrival_time if arrival_time else time.time() * 1000
        self.actual_exec_time = None
        self.start_time = None
        self.finish_time = None

# Core class
class Core:
    def __init__(self, core_id, gui):
        self.core_id = core_id
        self.task_queue = deque()
        self.load_history = []
        self.current_freq = "low"
        self.energy_consumed = 0
        self.running = False
        self.lock = threading.Lock()
        self.gui = gui
        self.deadline_misses = 0

    def moving_average(self, window=10):
        with self.lock:
            if not self.load_history:
                return 0
            recent = self.load_history[-window:] if len(self.load_history) > window else self.load_history
            return sum(recent) / len(recent)

    def set_cpu_frequency(self, task, current_time):
        load = self.moving_average() / 100
        slack = task.deadline - (current_time + task.est_exec_time)
        with self.lock:
            if task.priority == 1:
                self.current_freq = "high"
            else:
                if slack > 200:
                    self.current_freq = "low" if load < 40 else "mid"
                else:
                    self.current_freq = "high" if slack < 50 else "mid"

    def execute_task(self, task, current_time):
        with self.lock:
            freq = FREQUENCY_LEVELS[self.current_freq]["freq"]
            base_time = task.est_exec_time * (2.0 / freq)
            task.actual_exec_time = base_time + random.uniform(-5, 5)
            task.start_time = current_time
            time.sleep(task.actual_exec_time / 1000)
            task.finish_time = time.time() * 1000

            power = FREQUENCY_LEVELS[self.current_freq]["power"]
            energy = power * (task.actual_exec_time / 1000)
            self.energy_consumed += energy
            self.load_history.append(task.actual_exec_time)
            if task.finish_time > task.deadline:
                self.deadline_misses += 1
        
        latency = task.finish_time - task.arrival_time
        log_msg = (f"Core {self.core_id} | Task {task.task_id}: Freq={self.current_freq}, "
                   f"ExecTime={task.actual_exec_time:.2f}ms, Energy={energy:.2f}J, "
                   f"Latency={latency:.2f}ms, DeadlineMet={task.finish_time <= task.deadline}")
        self.gui.update_log(log_msg)
        self.gui.update_graphs(self.core_id, self.energy_consumed, len(self.load_history), self.deadline_misses)

    def run(self):
        while self.running and (self.task_queue or not self.gui.task_pool.empty()):
            if not self.task_queue:
                time.sleep(0.1)
                continue
            task = self.task_queue.popleft()
            current_time = time.time() * 1000
            self.set_cpu_frequency(task, current_time)
            self.execute_task(task, current_time)
            self.gui.update_metrics()

# Multi-core scheduler with GUI
class EOTS:
    def __init__(self, root):
        self.root = root
        self.root.title("Energy-Optimized Task Scheduler")
        self.cores = []
        self.task_pool = queue.Queue()
        self.total_energy = 0
        self.tasks_completed = 0
        self.deadline_misses = 0
        self.start_time = None
        self.running = False
        self.energy_data = {}
        self.task_data = {}
        self.miss_data = {}

        # GUI elements
        self.setup_gui()

    def setup_gui(self):
        # Configuration frame
        config_frame = ttk.LabelFrame(self.root, text="Configuration")
        config_frame.pack(padx=10, pady=5, fill="x")

        ttk.Label(config_frame, text="Number of Cores:").grid(row=0, column=0, padx=5, pady=5)
        self.num_cores_var = tk.IntVar(value=4)
        ttk.Entry(config_frame, textvariable=self.num_cores_var).grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(config_frame, text="Number of Tasks:").grid(row=1, column=0, padx=5, pady=5)
        self.num_tasks_var = tk.IntVar(value=200)
        ttk.Entry(config_frame, textvariable=self.num_tasks_var).grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(config_frame, text="Scheduling Type:").grid(row=2, column=0, padx=5, pady=5)
        self.scheduling_label = ttk.Label(config_frame, text="Hybrid Energy-Aware Priority Scheduling")
        self.scheduling_label.grid(row=2, column=1, padx=5, pady=5)

        ttk.Button(config_frame, text="Start", command=self.start_simulation).grid(row=3, column=0, pady=5)
        ttk.Button(config_frame, text="Stop", command=self.stop_simulation).grid(row=3, column=1, pady=5)

        # Metrics frame
        metrics_frame = ttk.LabelFrame(self.root, text="Metrics")
        metrics_frame.pack(padx=10, pady=5, fill="x")

        self.energy_label = ttk.Label(metrics_frame, text="Total Energy: 0.00 J")
        self.energy_label.pack()
        self.tasks_label = ttk.Label(metrics_frame, text="Tasks Completed: 0")
        self.tasks_label.pack()
        self.misses_label = ttk.Label(metrics_frame, text="Deadline Misses: 0")
        self.misses_label.pack()

        self.progress = ttk.Progressbar(metrics_frame, maximum=200, mode="determinate")
        self.progress.pack(fill="x", padx=5, pady=5)

        # Graphs frame
        graphs_frame = ttk.LabelFrame(self.root, text="Scheduling Graphs")
        graphs_frame.pack(padx=10, pady=5, fill="both", expand=True)

        self.fig, (self.ax1, self.ax2, self.ax3) = plt.subplots(3, 1, figsize=(8, 6))
        self.canvas = FigureCanvasTkAgg(self.fig, master=graphs_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        self.ax1.set_title("Energy Consumption (J)")
        self.ax1.set_xlabel("Time (s)")
        self.ax2.set_title("Tasks Completed")
        self.ax2.set_xlabel("Time (s)")
        self.ax3.set_title("Deadline Misses")
        self.ax3.set_xlabel("Time (s)")

        # Log frame
        log_frame = ttk.LabelFrame(self.root, text="Execution Log")
        log_frame.pack(padx=10, pady=5, fill="both", expand=True)

        self.log_text = tk.Text(log_frame, height=5, width=80)
        self.log_text.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text["yscrollcommand"] = scrollbar.set

    def generate_tasks(self):
        num_tasks = self.num_tasks_var.get()
        for i in range(num_tasks):
            priority = random.choice([0, 1])
            est_exec_time = random.randint(10, 100)
            deadline = (time.time() * 1000) + random.randint(50, 500) if priority == 0 else None
            task = Task(i, priority, est_exec_time, deadline)
            self.task_pool.put(task)

    def assign_tasks(self):
        while not self.task_pool.empty():
            task = self.task_pool.get()
            core = min(self.cores, key=lambda c: len(c.task_queue))
            core.task_queue.append(task)

    def start_simulation(self):
        if self.running:
            return
        self.running = True
        self.start_time = time.time()
        self.total_energy = 0
        self.tasks_completed = 0
        self.deadline_misses = 0
        self.progress["value"] = 0
        self.energy_data = {i: [] for i in range(self.num_cores_var.get())}
        self.task_data = {i: [] for i in range(self.num_cores_var.get())}
        self.miss_data = {i: [] for i in range(self.num_cores_var.get())}

        num_cores = self.num_cores_var.get()
        self.cores = [Core(i, self) for i in range(num_cores)]
        self.generate_tasks()
        self.assign_tasks()

        for core in self.cores:
            core.running = True
            threading.Thread(target=core.run, daemon=True).start()

    def stop_simulation(self):
        self.running = False
        for core in self.cores:
            core.running = False
        self.update_metrics()

    def update_log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def update_metrics(self):
        self.total_energy = sum(core.energy_consumed for core in self.cores)
        self.tasks_completed = sum(len(core.load_history) for core in self.cores)
        self.deadline_misses = sum(core.deadline_misses for core in self.cores)

        self.energy_label.config(text=f"Total Energy: {self.total_energy:.2f} J")
        self.tasks_label.config(text=f"Tasks Completed: {self.tasks_completed}")
        self.misses_label.config(text=f"Deadline Misses: {self.deadline_misses}")
        self.progress["value"] = self.tasks_completed
        self.progress["maximum"] = self.num_tasks_var.get()
        self.root.update_idletasks()

    def update_graphs(self, core_id, energy, tasks, misses):
        elapsed_time = time.time() - self.start_time
        self.energy_data[core_id].append((elapsed_time, energy))
        self.task_data[core_id].append((elapsed_time, tasks))
        self.miss_data[core_id].append((elapsed_time, misses))

        self.ax1.clear()
        self.ax2.clear()
        self.ax3.clear()
        for i in range(len(self.cores)):
            if self.energy_data[i]:
                x, y = zip(*self.energy_data[i])
                self.ax1.plot(x, y, label=f"Core {i}")
            if self.task_data[i]:
                x, y = zip(*self.task_data[i])
                self.ax2.plot(x, y, label=f"Core {i}")
            if self.miss_data[i]:
                x, y = zip(*self.miss_data[i])
                self.ax3.plot(x, y, label=f"Core {i}")

        self.ax1.set_title("Energy Consumption (J)")
        self.ax1.legend()
        self.ax2.set_title("Tasks Completed")
        self.ax2.legend()
        self.ax3.set_title("Deadline Misses")
        self.ax3.legend()
        self.canvas.draw()

def main():
    root = tk.Tk()
    app = EOTS(root)
    root.mainloop()

if __name__ == "__main__":
    main()