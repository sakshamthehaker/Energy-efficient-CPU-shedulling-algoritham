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
    "low": {"freq": 0.8, "power": 0.5, "color": "#A2D9A2"},  # Soft green
    "mid": {"freq": 1.2, "power": 1.0, "color": "#FFFFB3"},  # Pale yellow
    "high": {"freq": 2.0, "power": 2.0, "color": "#FF9999"}  # Soft red
}

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
        self.efficient_energy = self.calculate_efficient_energy()

    def calculate_efficient_energy(self):
        if self.priority == 1:
            freq = FREQUENCY_LEVELS["high"]["freq"]
            power = FREQUENCY_LEVELS["high"]["power"]
        else:
            slack = self.deadline - (self.arrival_time + self.est_exec_time)
            if slack > 200:
                freq = FREQUENCY_LEVELS["low"]["freq"]
                power = FREQUENCY_LEVELS["low"]["power"]
            elif slack > 50:
                freq = FREQUENCY_LEVELS["mid"]["freq"]
                power = FREQUENCY_LEVELS["mid"]["power"]
            else:
                freq = FREQUENCY_LEVELS["high"]["freq"]
                power = FREQUENCY_LEVELS["high"]["power"]
        exec_time = self.est_exec_time * (2.0 / freq)
        return power * (exec_time / 1000)

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
        self.current_task = None  # Track currently running task

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
            self.current_task = task  # Set current task
            self.gui.update_running_processes()  # Update GUI
            freq = FREQUENCY_LEVELS[self.current_freq]["freq"]
            base_time = task.est_exec_time * (2.0 / freq)
            task.actual_exec_time = base_time + random.uniform(-2, 2)
            task.start_time = current_time
        
        # Simulate execution while updating remaining time
        start_real_time = time.time()
        exec_duration = task.actual_exec_time / 1000
        while time.time() - start_real_time < exec_duration:
            time.sleep(0.01)  # Small sleep to allow GUI updates
            self.gui.update_running_processes()
        
        with self.lock:
            task.finish_time = time.time() * 1000
            power = FREQUENCY_LEVELS[self.current_freq]["power"]
            energy = power * (task.actual_exec_time / 1000)
            self.energy_consumed += energy
            self.load_history.append(task.actual_exec_time)
            if task.finish_time > task.deadline:
                self.deadline_misses += 1
            self.current_task = None  # Clear current task
        
        latency = task.finish_time - task.arrival_time
        log_msg = (f"Core {self.core_id} | Task {task.task_id}: Freq={self.current_freq}, "
                   f"ExecTime={task.actual_exec_time:.2f}ms, Energy={energy:.2f}J, "
                   f"Latency={latency:.2f}ms, DeadlineMet={task.finish_time <= task.deadline}")
        self.gui.update_log(log_msg)
        self.gui.queue_gantt_update(self.core_id, task.task_id, task.priority, task.start_time, task.finish_time, self.current_freq)
        self.gui.update_running_processes()  # Update after completion

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

class EOTS:
    def __init__(self, root):
        self.root = root
        self.root.title("Energy-Optimized Task Scheduler")
        self.cores = []
        self.task_pool = queue.Queue()
        self.total_energy = 0
        self.total_efficient_energy = 0
        self.tasks_completed = 0
        self.deadline_misses = 0
        self.start_time = None
        self.running = False
        self.gantt_data = {}
        self.gui_lock = threading.Lock()
        self.gantt_update_queue = queue.Queue()
        self.setup_gui()

    def setup_gui(self):
        config_frame = ttk.LabelFrame(self.root, text="Configuration")
        config_frame.pack(padx=10, pady=5, fill="x")

        ttk.Label(config_frame, text="Number of Cores:").grid(row=0, column=0, padx=5, pady=5)
        self.num_cores_var = tk.IntVar(value=4)
        ttk.Entry(config_frame, textvariable=self.num_cores_var).grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(config_frame, text="Number of Tasks:").grid(row=1, column=0, padx=5, pady=5)
        self.num_tasks_var = tk.IntVar(value=100)
        ttk.Entry(config_frame, textvariable=self.num_tasks_var).grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(config_frame, text="Scheduling Type:").grid(row=2, column=0, padx=5, pady=5)
        self.scheduling_label = ttk.Label(config_frame, text="Hybrid Energy-Aware Priority Scheduling")
        self.scheduling_label.grid(row=2, column=1, padx=5, pady=5)

        ttk.Button(config_frame, text="Start", command=self.start_simulation).grid(row=3, column=0, pady=5)
        ttk.Button(config_frame, text="Stop", command=self.stop_simulation).grid(row=3, column=1, pady=5)

        metrics_frame = ttk.LabelFrame(self.root, text="Metrics")
        metrics_frame.pack(padx=10, pady=5, fill="x")

        self.energy_label = ttk.Label(metrics_frame, text="Total Energy: 0.00 J")
        self.energy_label.pack()
        self.efficient_energy_label = ttk.Label(metrics_frame, text="Efficient Energy: 0.00 J")
        self.efficient_energy_label.pack()
        self.efficiency_label = ttk.Label(metrics_frame, text="Energy Efficiency: 0%")
        self.efficiency_label.pack()
        self.tasks_label = ttk.Label(metrics_frame, text="Tasks Completed: 0")
        self.tasks_label.pack()
        self.misses_label = ttk.Label(metrics_frame, text="Deadline Misses: 0")
        self.misses_label.pack()

        self.progress = ttk.Progressbar(metrics_frame, maximum=100, mode="determinate")
        self.progress.pack(fill="x", padx=5, pady=5)

        # New Running Process Information Section
        running_frame = ttk.LabelFrame(self.root, text="Running Process Information")
        running_frame.pack(padx=10, pady=5, fill="x")
        self.running_text = tk.Text(running_frame, height=4, width=80, state='disabled')
        self.running_text.pack(fill="x", padx=5, pady=5)
        scrollbar = ttk.Scrollbar(running_frame, orient="vertical", command=self.running_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.running_text["yscrollcommand"] = scrollbar.set

        gantt_frame = ttk.LabelFrame(self.root, text="Gantt Chart")
        gantt_frame.pack(padx=10, pady=5, fill="both", expand=True)

        self.fig = Figure(figsize=(12, 6))
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=gantt_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        self.legend_patches = [
            plt.Rectangle((0, 0), 1, 1, facecolor=FREQUENCY_LEVELS["low"]["color"], label="Low Freq (P0)"),
            plt.Rectangle((0, 0), 1, 1, facecolor=FREQUENCY_LEVELS["mid"]["color"], label="Mid Freq (P0)"),
            plt.Rectangle((0, 0), 1, 1, facecolor=FREQUENCY_LEVELS["high"]["color"], label="High Freq (P1/P0)")
        ]

        log_frame = ttk.LabelFrame(self.root, text="Execution Log")
        log_frame.pack(padx=10, pady=5, fill="both", expand=True)

        self.log_text = tk.Text(log_frame, height=5, width=80)
        self.log_text.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text["yscrollcommand"] = scrollbar.set

        self.gantt_thread = threading.Thread(target=self.process_gantt_updates, daemon=True)
        self.gantt_thread.start()

    def generate_tasks(self):
        num_tasks = self.num_tasks_var.get()
        self.total_efficient_energy = 0
        for i in range(num_tasks):
            priority = random.choice([0, 1])
            est_exec_time = random.randint(10, 20)
            deadline = (time.time() * 1000) + random.randint(50, 150) if priority == 0 else None
            task = Task(i, priority, est_exec_time, deadline)
            self.task_pool.put(task)
            self.total_efficient_energy += task.efficient_energy

    def assign_tasks(self):
        with self.gui_lock:
            while not self.task_pool.empty():
                task = self.task_pool.get()
                core = min(self.cores, key=lambda c: len(c.task_queue))
                core.task_queue.append(task)

    def start_simulation(self):
        if self.running:
            return
        self.running = True
        self.start_time = time.time() * 1000
        self.total_energy = 0
        self.total_efficient_energy = 0
        self.tasks_completed = 0
        self.deadline_misses = 0
        self.progress["value"] = 0
        self.gantt_data = {i: [] for i in range(self.num_cores_var.get())}
        self.ax.clear()
        self.canvas.draw()

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
        self.update_running_processes()

    def update_log(self, message):
        with self.gui_lock:
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
            self.root.update_idletasks()

    def update_metrics(self):
        with self.gui_lock:
            self.total_energy = sum(core.energy_consumed for core in self.cores)
            self.tasks_completed = sum(len(core.load_history) for core in self.cores)
            self.deadline_misses = sum(core.deadline_misses for core in self.cores)

            self.energy_label.config(text=f"Total Energy: {self.total_energy:.2f} J")
            self.efficient_energy_label.config(text=f"Efficient Energy: {self.total_efficient_energy:.2f} J")
            efficiency = (self.total_efficient_energy / self.total_energy * 100) if self.total_energy > 0 else 0
            self.efficiency_label.config(text=f"Energy Efficiency: {efficiency:.1f}%")
            self.tasks_label.config(text=f"Tasks Completed: {self.tasks_completed}")
            self.misses_label.config(text=f"Deadline Misses: {self.deadline_misses}")
            self.progress["value"] = self.tasks_completed
            self.progress["maximum"] = self.num_tasks_var.get()
            self.root.update_idletasks()

    def update_running_processes(self):
        with self.gui_lock:
            self.running_text.config(state='normal')
            self.running_text.delete(1.0, tk.END)
            header = "Core | Task ID | Priority | Frequency | Remaining Time (ms)\n"
            self.running_text.insert(tk.END, header)
            for core in self.cores:
                if core.current_task:
                    task = core.current_task
                    elapsed = (time.time() * 1000 - task.start_time) if task.start_time else 0
                    remaining = max(0, task.actual_exec_time - elapsed) if task.actual_exec_time else task.est_exec_time
                    line = (f"C{core.core_id:<2} | T{task.task_id:<6} | P{task.priority:<7} | "
                            f"{core.current_freq:<9} | {remaining:.1f}\n")
                    self.running_text.insert(tk.END, line)
                else:
                    line = f"C{core.core_id:<2} | Idle    | -       | -         | -\n"
                    self.running_text.insert(tk.END, line)
            self.running_text.config(state='disabled')
            self.root.update_idletasks()

    def queue_gantt_update(self, core_id, task_id, priority, start_time, finish_time, freq):
        self.gantt_update_queue.put((core_id, task_id, priority, start_time, finish_time, freq))

    def process_gantt_updates(self):
        while True:
            try:
                updates = []
                while not self.gantt_update_queue.empty():
                    updates.append(self.gantt_update_queue.get())
                
                if updates:
                    with self.gui_lock:
                        max_time = 0
                        for core_id, task_id, priority, start_time, finish_time, freq in updates:
                            label = f"T{task_id}"
                            start = max(0, start_time - self.start_time)
                            finish = finish_time - self.start_time
                            self.gantt_data[core_id].append((label, start, finish, freq))
                            max_time = max(max_time, finish)

                        self.ax.clear()
                        time_window = max(1000, max_time * 1.1)
                        self.ax.set_xlim(0, time_window)
                        self.ax.set_ylim(-0.5, len(self.cores) - 0.5)

                        for cid in range(len(self.cores)):
                            for task_label, start, finish, freq in self.gantt_data[cid]:
                                if finish > start:
                                    duration = finish - start
                                    color = FREQUENCY_LEVELS[freq]["color"]
                                    bar_height = 0.8
                                    self.ax.broken_barh(
                                        [(start, duration)],
                                        (cid - bar_height/2, bar_height),
                                        facecolors=color,
                                        edgecolor="black",
                                        alpha=0.7
                                    )
                                    if duration > 20 or int(task_label[1:]) % 5 == 0:
                                        text_x = start + duration / 2
                                        if duration < 15:
                                            self.ax.text(text_x, cid + 0.4, task_label, 
                                                       ha='center', va='bottom', fontsize=6)
                                        else:
                                            self.ax.text(text_x, cid, task_label, 
                                                       ha='center', va='center', fontsize=6)

                        self.ax.set_title("Task Execution Timeline", fontsize=12, pad=20)
                        self.ax.set_xlabel("Time (ms)", fontsize=10)
                        self.ax.set_ylabel("Cores", fontsize=10)
                        self.ax.set_yticks(range(len(self.cores)))
                        self.ax.set_yticklabels([f"C{cid}" for cid in range(len(self.cores))])
                        self.ax.grid(True, linestyle='--', alpha=0.3)
                        self.ax.legend(handles=self.legend_patches, loc="upper center", 
                                     fontsize=8, bbox_to_anchor=(0.5, 1.15), ncol=3)
                        self.fig.tight_layout()
                        self.canvas.draw()
                
                time.sleep(0.1)
            except Exception as e:
                print(f"Gantt update error: {e}")

def main():
    root = tk.Tk()
    app = EOTS(root)
    root.mainloop()

if __name__ == "__main__":
    main()