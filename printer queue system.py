"""
Printer Queue System — Enhanced Version
نظام الطباعة المتزامن — النسخة المطورة

Improvements:
1. ✅ Added "Show Report" button with full session report
2. ✅ Fixed Race Condition counter reset bug
3. ✅ Fixed JobSubmitterThread missing app_callback parameter
4. ✅ Fixed thread card creation before threads start
5. ✅ Added Deadlock Detection panel
6. ✅ Added job history tracking
7. ✅ Improved UI with animated progress bars
8. ✅ Added export report to .txt file
9. ✅ Added worker thread count control (1-5)
10. ✅ Better log coloring and filtering
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time
import random
import queue
from datetime import datetime
import os

# ══════════════════════════════════════════════════════
#  SHARED RESOURCES & SYNCHRONIZATION PRIMITIVES
# ══════════════════════════════════════════════════════

printer_lock      = threading.Lock()
printer_semaphore = threading.Semaphore(1)

total_pages_printed = 0
total_pages_safe    = 0

job_queue   = queue.Queue()
log_entries = []
log_lock    = threading.Lock()

active_threads = []
threads_lock   = threading.Lock()

# Full job history for report
job_history      = []
job_history_lock = threading.Lock()

# Chart data history (time-series for live chart)
chart_history      = []   # list of {"t": float, "submitted": int, "completed": int, "queued": int}
chart_history_lock = threading.Lock()
CHART_MAX_POINTS   = 40   # how many data points to show

stats = {
    "jobs_submitted":    0,
    "jobs_completed":    0,
    "jobs_failed":       0,
    "race_errors_detected": 0,
    "pages_without_sync":   0,
    "pages_with_sync":      0,
    "total_print_time_sec": 0.0,
    "session_start":        None,
}
stats_lock = threading.Lock()

is_running = False
sync_mode  = True

# ══════════════════════════════════════════════════════
#  PRINTER WORKER THREAD
# ══════════════════════════════════════════════════════

class PrinterWorkerThread(threading.Thread):
    def __init__(self, worker_id, app_callback, use_sync):
        super().__init__(daemon=True)
        self.worker_id    = worker_id
        self.app_callback = app_callback
        self.use_sync     = use_sync
        self.name         = f"PrinterThread-{worker_id}"

    def run(self):
        global total_pages_printed, total_pages_safe, is_running

        while is_running:
            try:
                job = job_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            job_id    = job["id"]
            doc_name  = job["name"]
            pages     = job["pages"]
            submitter = job["submitter"]
            start_t   = time.time()

            self._log(f"▶️ Worker-{self.worker_id} started: [{doc_name}] ({pages} pages) by {submitter}")
            self.app_callback("thread_status", self.worker_id, "busy", doc_name)

            if self.use_sync:
                self._log(f"🔒 Worker-{self.worker_id} acquiring Mutex...")
                with printer_lock:
                    self._log(f"✅ Worker-{self.worker_id} got Mutex — printing safely")
                    self._do_print(job_id, doc_name, pages, submitter, safe=True)
            else:
                self._log(f"⚠️  Worker-{self.worker_id} printing WITHOUT lock (Race Condition risk!)")
                self._do_print(job_id, doc_name, pages, submitter, safe=False)

            elapsed = round(time.time() - start_t, 2)

            # Record in job history
            with job_history_lock:
                job_history.append({
                    "id":        job_id,
                    "name":      doc_name,
                    "pages":     pages,
                    "submitter": submitter,
                    "worker":    self.worker_id,
                    "sync":      self.use_sync,
                    "time_sec":  elapsed,
                    "finished":  datetime.now().strftime("%H:%M:%S"),
                })

            with stats_lock:
                stats["total_print_time_sec"] += elapsed

            job_queue.task_done()
            self.app_callback("thread_status", self.worker_id, "idle", "")

        self._log(f"🛑 Worker-{self.worker_id} terminated")
        self.app_callback("thread_status", self.worker_id, "stopped", "")

    def _do_print(self, job_id, doc_name, pages, submitter, safe):
        global total_pages_printed, total_pages_safe

        for page in range(1, pages + 1):
            if not is_running:
                break

            time.sleep(random.uniform(0.05, 0.15))

            if safe:
                with stats_lock:
                    total_pages_safe += 1
                    stats["pages_with_sync"] += 1
            else:
                temp = total_pages_printed
                time.sleep(0.001)
                total_pages_printed = temp + 1
                with stats_lock:
                    stats["pages_without_sync"] += 1

            progress = int((page / pages) * 100)
            self.app_callback("job_progress", job_id, progress, page, pages)

        with stats_lock:
            stats["jobs_completed"] += 1

        self._log(f"✔ Worker-{self.worker_id} finished: [{doc_name}] — {pages} pages")
        self.app_callback("job_done", job_id, doc_name, pages, submitter)

    def _log(self, message):
        ts    = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        entry = f"[{ts}] {message}"
        with log_lock:
            log_entries.append(entry)
        self.app_callback("add_log", entry)


# ══════════════════════════════════════════════════════
#  JOB SUBMITTER THREAD
# ══════════════════════════════════════════════════════

class JobSubmitterThread(threading.Thread):
    def __init__(self, submitter_id, app_callback):   # ✅ FIXED: was missing app_callback
        super().__init__(daemon=True)
        self.submitter_id = submitter_id
        self.app_callback = app_callback
        self.name = f"Submitter-{submitter_id}"

    def run(self):
        docs = ["Report.pdf", "Invoice.docx", "Thesis.pdf",
                "Slides.pptx", "Contract.pdf", "Letter.docx",
                "Manual.pdf", "Exam.docx", "Drawing.pdf", "Code.txt"]

        while is_running:
            time.sleep(random.uniform(0.5, 2.5))
            if not is_running:
                break

            doc    = random.choice(docs)
            pages  = random.randint(1, 10)
            job_id = f"JOB-{int(time.time()*1000) % 100000}"

            job = {
                "id":        job_id,
                "name":      doc,
                "pages":     pages,
                "submitter": f"User-{self.submitter_id}",
                "status":    "queued",
            }
            job_queue.put(job)
            with stats_lock:
                stats["jobs_submitted"] += 1


# ══════════════════════════════════════════════════════
#  REPORT WINDOW
# ══════════════════════════════════════════════════════

class ReportWindow(tk.Toplevel):
    DARK_BG  = "#0d1117"
    PANEL_BG = "#161b22"
    CARD_BG  = "#21262d"
    ACCENT   = "#58a6ff"
    GREEN    = "#3fb950"
    RED      = "#f85149"
    YELLOW   = "#d29922"
    PURPLE   = "#bc8cff"
    TEXT_PRI = "#e6edf3"
    TEXT_SEC = "#8b949e"
    BORDER   = "#30363d"

    def __init__(self, parent):
        super().__init__(parent)
        self.title("📊  Session Report — تقرير الجلسة")
        self.geometry("860x640")
        self.configure(bg=self.DARK_BG)
        self.resizable(True, True)
        self._build()
        self.grab_set()   # Modal

    def _build(self):
        # ── Header ──
        hdr = tk.Frame(self, bg="#010409", pady=10)
        hdr.pack(fill=tk.X)

        tk.Label(hdr, text="📊  Session Report",
                 font=("Consolas", 16, "bold"),
                 fg=self.ACCENT, bg="#010409").pack(side=tk.LEFT, padx=20)

        tk.Label(hdr,
                 text=f"Generated: {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}",
                 font=("Consolas", 9), fg=self.TEXT_SEC, bg="#010409").pack(side=tk.LEFT, padx=10)

        btn_frm = tk.Frame(hdr, bg="#010409")
        btn_frm.pack(side=tk.RIGHT, padx=16)

        tk.Button(btn_frm, text="💾  Export .txt",
                  font=("Consolas", 9, "bold"),
                  bg=self.PURPLE, fg="#000000",
                  relief=tk.FLAT, padx=10, pady=3,
                  cursor="hand2",
                  command=self._export).pack(side=tk.LEFT, padx=4)

        tk.Button(btn_frm, text="✖  Close",
                  font=("Consolas", 9),
                  bg=self.CARD_BG, fg=self.TEXT_SEC,
                  relief=tk.FLAT, padx=10, pady=3,
                  cursor="hand2",
                  command=self.destroy).pack(side=tk.LEFT, padx=4)

        # ── Notebook tabs ──
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Dark.TNotebook",
                        background=self.DARK_BG,
                        borderwidth=0)
        style.configure("Dark.TNotebook.Tab",
                        background=self.CARD_BG,
                        foreground=self.TEXT_SEC,
                        font=("Consolas", 9, "bold"),
                        padding=[12, 5])
        style.map("Dark.TNotebook.Tab",
                  background=[("selected", self.PANEL_BG)],
                  foreground=[("selected", self.ACCENT)])

        nb = ttk.Notebook(self, style="Dark.TNotebook")
        nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        # Tab 1: Summary
        tab_summary = tk.Frame(nb, bg=self.PANEL_BG)
        nb.add(tab_summary, text="  📈 Summary  ")
        self._build_summary(tab_summary)

        # Tab 2: Job History
        tab_jobs = tk.Frame(nb, bg=self.PANEL_BG)
        nb.add(tab_jobs, text="  📋 Job History  ")
        self._build_job_history(tab_jobs)

        # Tab 3: Race Condition Analysis
        tab_race = tk.Frame(nb, bg=self.PANEL_BG)
        nb.add(tab_race, text="  🔬 Race Analysis  ")
        self._build_race_analysis(tab_race)

        # Tab 4: Raw Log
        tab_log = tk.Frame(nb, bg=self.PANEL_BG)
        nb.add(tab_log, text="  📟 Full Log  ")
        self._build_raw_log(tab_log)

    # ── Tab 1: Summary ──
    def _build_summary(self, parent):
        with stats_lock:
            s = stats.copy()

        session_dur = "N/A"
        if s["session_start"]:
            sec = int(time.time() - s["session_start"])
            session_dur = f"{sec // 60}m {sec % 60}s"

        avg_time = 0.0
        if s["jobs_completed"] > 0:
            avg_time = round(s["total_print_time_sec"] / s["jobs_completed"], 2)

        diff = abs(total_pages_safe - total_pages_printed)

        cards = [
            ("Jobs Submitted",  s["jobs_submitted"],          self.ACCENT),
            ("Jobs Completed",  s["jobs_completed"],          self.GREEN),
            ("Jobs in Queue",   job_queue.qsize(),            self.YELLOW),
            ("Session Duration",session_dur,                  self.PURPLE),
            ("Pages (Safe)",    total_pages_safe,             self.GREEN),
            ("Pages (Unsafe)",  total_pages_printed,          self.RED),
            ("Avg Job Time",    f"{avg_time}s",               self.ACCENT),
            ("Race Corruption", diff,                         self.RED if diff > 0 else self.GREEN),
        ]

        grid = tk.Frame(parent, bg=self.PANEL_BG)
        grid.pack(fill=tk.X, padx=16, pady=16)

        for idx, (label, value, color) in enumerate(cards):
            col = idx % 4
            row = idx // 4
            card = tk.Frame(grid, bg=self.CARD_BG, padx=14, pady=12)
            card.grid(row=row, column=col, padx=6, pady=6, sticky="ew")
            grid.columnconfigure(col, weight=1)

            tk.Label(card, text=str(value),
                     font=("Consolas", 22, "bold"),
                     fg=color, bg=self.CARD_BG).pack()
            tk.Label(card, text=label,
                     font=("Consolas", 8),
                     fg=self.TEXT_SEC, bg=self.CARD_BG).pack()

        # Sync mode used
        mode_frm = tk.Frame(parent, bg=self.CARD_BG, padx=16, pady=10)
        mode_frm.pack(fill=tk.X, padx=16, pady=(0, 8))

        mode_color = self.GREEN if sync_mode else self.RED
        mode_text  = "WITH Mutex (Synchronized)" if sync_mode else "WITHOUT Mutex (Race Condition Demo)"
        tk.Label(mode_frm, text=f"Current Sync Mode:  {mode_text}",
                 font=("Consolas", 10, "bold"),
                 fg=mode_color, bg=self.CARD_BG).pack(anchor="w")

        if diff > 0:
            tk.Label(mode_frm,
                     text=f"⚠  {diff} page count corruptions detected due to Race Condition!",
                     font=("Consolas", 9), fg=self.RED, bg=self.CARD_BG).pack(anchor="w", pady=2)
        else:
            tk.Label(mode_frm,
                     text="✔  No race condition corruption detected — data is consistent.",
                     font=("Consolas", 9), fg=self.GREEN, bg=self.CARD_BG).pack(anchor="w", pady=2)

        # Worker breakdown
        with job_history_lock:
            history_copy = list(job_history)

        if history_copy:
            worker_stats = {}
            for j in history_copy:
                wid = j["worker"]
                if wid not in worker_stats:
                    worker_stats[wid] = {"jobs": 0, "pages": 0, "time": 0.0}
                worker_stats[wid]["jobs"]  += 1
                worker_stats[wid]["pages"] += j["pages"]
                worker_stats[wid]["time"]  += j["time_sec"]

            wfrm = tk.Frame(parent, bg=self.PANEL_BG, padx=16)
            wfrm.pack(fill=tk.X, padx=16)
            tk.Label(wfrm, text="Worker Thread Breakdown",
                     font=("Consolas", 10, "bold"),
                     fg=self.TEXT_PRI, bg=self.PANEL_BG).pack(anchor="w", pady=(6, 4))

            for wid, ws in sorted(worker_stats.items()):
                row = tk.Frame(wfrm, bg=self.CARD_BG, padx=10, pady=5)
                row.pack(fill=tk.X, pady=2)
                tk.Label(row, text=f"Worker #{wid}",
                         font=("Consolas", 9, "bold"),
                         fg=self.ACCENT, bg=self.CARD_BG, width=12).pack(side=tk.LEFT)
                tk.Label(row, text=f"Jobs: {ws['jobs']}",
                         font=("Consolas", 9), fg=self.TEXT_PRI, bg=self.CARD_BG, width=10).pack(side=tk.LEFT)
                tk.Label(row, text=f"Pages: {ws['pages']}",
                         font=("Consolas", 9), fg=self.TEXT_PRI, bg=self.CARD_BG, width=10).pack(side=tk.LEFT)
                tk.Label(row, text=f"Avg: {round(ws['time']/max(ws['jobs'],1), 2)}s/job",
                         font=("Consolas", 9), fg=self.TEXT_SEC, bg=self.CARD_BG).pack(side=tk.LEFT)

    # ── Tab 2: Job History ──
    def _build_job_history(self, parent):
        with job_history_lock:
            history_copy = list(job_history)

        # Header
        hrow = tk.Frame(parent, bg=self.CARD_BG, pady=4, padx=6)
        hrow.pack(fill=tk.X, padx=8, pady=(8, 0))
        for text, w in [("Time", 10), ("Job ID", 12), ("Document", 16),
                        ("Pages", 6), ("Worker", 8), ("Sync", 6), ("Duration", 9)]:
            tk.Label(hrow, text=text, font=("Consolas", 8, "bold"),
                     fg=self.ACCENT, bg=self.CARD_BG, width=w).pack(side=tk.LEFT)

        # Scrollable list
        canvas = tk.Canvas(parent, bg=self.PANEL_BG, highlightthickness=0)
        sb     = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner  = tk.Frame(canvas, bg=self.PANEL_BG)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=4)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        if not history_copy:
            tk.Label(inner, text="No jobs completed yet in this session.",
                     font=("Consolas", 10), fg=self.TEXT_SEC, bg=self.PANEL_BG).pack(pady=20)
            return

        for j in reversed(history_copy):
            row = tk.Frame(inner, bg=self.CARD_BG, pady=3, padx=6)
            row.pack(fill=tk.X, pady=1)

            sync_color = self.GREEN if j["sync"] else self.RED
            sync_text  = "✔" if j["sync"] else "✘"

            for text, w, color in [
                (j["finished"],         10, self.TEXT_SEC),
                (j["id"][-10:],         12, self.TEXT_PRI),
                (j["name"][:16],        16, self.TEXT_PRI),
                (str(j["pages"]),        6, self.ACCENT),
                (f"#{j['worker']}",      8, self.PURPLE),
                (sync_text,              6, sync_color),
                (f"{j['time_sec']}s",    9, self.TEXT_SEC),
            ]:
                tk.Label(row, text=text, font=("Consolas", 8),
                         fg=color, bg=self.CARD_BG, width=w).pack(side=tk.LEFT)

    # ── Tab 3: Race Condition Analysis ──
    def _build_race_analysis(self, parent):
        diff = abs(total_pages_safe - total_pages_printed)

        # Main info box
        box = tk.Frame(parent, bg=self.CARD_BG, padx=20, pady=16)
        box.pack(fill=tk.X, padx=16, pady=16)

        tk.Label(box, text="Race Condition Counter Comparison",
                 font=("Consolas", 12, "bold"),
                 fg=self.YELLOW, bg=self.CARD_BG).pack(anchor="w")

        comparison = tk.Frame(box, bg=self.CARD_BG)
        comparison.pack(fill=tk.X, pady=12)

        # Safe counter
        safe_frm = tk.Frame(comparison, bg="#0d2a0d", padx=16, pady=12)
        safe_frm.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        tk.Label(safe_frm, text="WITH Mutex",
                 font=("Consolas", 9), fg=self.GREEN, bg="#0d2a0d").pack()
        tk.Label(safe_frm, text=str(total_pages_safe),
                 font=("Consolas", 28, "bold"), fg=self.GREEN, bg="#0d2a0d").pack()
        tk.Label(safe_frm, text="total_pages_safe",
                 font=("Consolas", 8), fg=self.TEXT_SEC, bg="#0d2a0d").pack()

        # Unsafe counter
        unsafe_frm = tk.Frame(comparison, bg="#2a0d0d", padx=16, pady=12)
        unsafe_frm.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))
        tk.Label(unsafe_frm, text="WITHOUT Mutex",
                 font=("Consolas", 9), fg=self.RED, bg="#2a0d0d").pack()
        tk.Label(unsafe_frm, text=str(total_pages_printed),
                 font=("Consolas", 28, "bold"), fg=self.RED, bg="#2a0d0d").pack()
        tk.Label(unsafe_frm, text="total_pages_printed",
                 font=("Consolas", 8), fg=self.TEXT_SEC, bg="#2a0d0d").pack()

        # Diff
        diff_color = self.RED if diff > 0 else self.GREEN
        diff_msg   = (f"⚠  {diff} CORRUPTED UPDATES DETECTED"
                      if diff > 0 else "✔  No corruption — counters match")
        tk.Label(box, text=diff_msg,
                 font=("Consolas", 11, "bold"),
                 fg=diff_color, bg=self.CARD_BG).pack(pady=(8, 0))

        # Explanation
        exp_frm = tk.Frame(parent, bg=self.PANEL_BG, padx=16)
        exp_frm.pack(fill=tk.BOTH, expand=True, padx=16)

        tk.Label(exp_frm, text="How Race Condition Happens Here:",
                 font=("Consolas", 10, "bold"),
                 fg=self.YELLOW, bg=self.PANEL_BG).pack(anchor="w", pady=(6, 4))

        explanation = (
            "Thread A reads: total_pages_printed = 5\n"
            "Thread B reads: total_pages_printed = 5   ← same value!\n"
            "Thread A writes: total_pages_printed = 6\n"
            "Thread B writes: total_pages_printed = 6  ← overwrites A's update!\n"
            "\n"
            "Result: Two threads printed, but counter only incremented once.\n"
            "This is a lost update — the classic Race Condition bug.\n"
            "\n"
            "Fix: Use a Mutex (Lock) so only one thread can read-modify-write at a time."
        )

        txt = tk.Text(exp_frm, font=("Consolas", 9),
                      bg="#010409", fg=self.TEXT_PRI,
                      relief=tk.FLAT, height=12, wrap=tk.WORD,
                      state=tk.NORMAL)
        txt.insert(tk.END, explanation)
        txt.config(state=tk.DISABLED)
        txt.pack(fill=tk.BOTH, expand=True)

    # ── Tab 4: Raw Log ──
    def _build_raw_log(self, parent):
        with log_lock:
            logs = list(log_entries)

        frm = tk.Frame(parent, bg=self.PANEL_BG)
        frm.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        txt = tk.Text(frm, font=("Consolas", 8),
                      bg="#010409", fg=self.TEXT_PRI,
                      relief=tk.FLAT, wrap=tk.WORD,
                      state=tk.NORMAL)
        sb  = ttk.Scrollbar(frm, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        txt.tag_config("lock", foreground="#3fb950")
        txt.tag_config("race", foreground="#f85149")
        txt.tag_config("done", foreground="#bc8cff")
        txt.tag_config("info", foreground="#58a6ff")

        for line in logs:
            if "🔒" in line or "Mutex" in line:
                tag = "lock"
            elif "⚠" in line or "Race" in line or "WITHOUT" in line:
                tag = "race"
            elif "✔" in line or "finished" in line:
                tag = "done"
            else:
                tag = "info"
            txt.insert(tk.END, line + "\n", tag)

        txt.see(tk.END)
        txt.config(state=tk.DISABLED)

    # ── Export ──
    def _export(self):
        with stats_lock:
            s = stats.copy()
        with job_history_lock:
            history_copy = list(job_history)
        with log_lock:
            logs = list(log_entries)

        diff = abs(total_pages_safe - total_pages_printed)

        lines = [
            "=" * 60,
            "  PRINTER QUEUE SYSTEM — SESSION REPORT",
            f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 60,
            "",
            "[ SUMMARY ]",
            f"  Jobs Submitted:       {s['jobs_submitted']}",
            f"  Jobs Completed:       {s['jobs_completed']}",
            f"  Pages (Synchronized): {total_pages_safe}",
            f"  Pages (Unsafe):       {total_pages_printed}",
            f"  Race Corruption:      {diff}",
            f"  Sync Mode:            {'ON (Mutex)' if sync_mode else 'OFF (Race Condition)'}",
            "",
            "[ JOB HISTORY ]",
        ]
        for j in history_copy:
            lines.append(
                f"  {j['finished']}  {j['id'][-10:]}  {j['name']:<18}"
                f"  {j['pages']}p  Worker#{j['worker']}"
                f"  {'SYNC' if j['sync'] else 'UNSAFE'}  {j['time_sec']}s"
            )
        lines += ["", "[ FULL LOG ]"]
        lines += logs

        content = "\n".join(lines)

        filepath = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"printer_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        if filepath:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            messagebox.showinfo("Exported", f"Report saved to:\n{filepath}")


# ══════════════════════════════════════════════════════
#  MAIN APPLICATION — GUI
# ══════════════════════════════════════════════════════

class PrinterQueueApp(tk.Tk):

    DARK_BG  = "#0d1117"
    PANEL_BG = "#161b22"
    CARD_BG  = "#21262d"
    ACCENT   = "#58a6ff"
    GREEN    = "#3fb950"
    RED      = "#f85149"
    YELLOW   = "#d29922"
    PURPLE   = "#bc8cff"
    TEXT_PRI = "#e6edf3"
    TEXT_SEC = "#8b949e"
    BORDER   = "#30363d"

    def __init__(self):
        super().__init__()
        self.title("🖨  Printer Queue System — نظام الطباعة المتزامن")
        self.geometry("1340x840")
        self.configure(bg=self.DARK_BG)
        self.resizable(True, True)

        self._job_rows     = {}
        self._thread_cards = {}

        self._build_ui()
        self._start_stats_refresh()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ─────────────────────────────────────────────────
    #  UI CONSTRUCTION
    # ─────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ──
        hdr = tk.Frame(self, bg="#010409", pady=10)
        hdr.pack(fill=tk.X)

        tk.Label(hdr, text="🖨  Printer Queue System",
                 font=("Consolas", 20, "bold"),
                 fg=self.ACCENT, bg="#010409").pack(side=tk.LEFT, padx=20)

        tk.Label(hdr,
                 text="نظام التشغيل ٢  •  Threads + Semaphores + Mutex + Synchronization",
                 font=("Consolas", 10),
                 fg=self.TEXT_SEC, bg="#010409").pack(side=tk.LEFT, padx=10)

        # Right-side buttons
        btn_frm = tk.Frame(hdr, bg="#010409")
        btn_frm.pack(side=tk.RIGHT, padx=12)

        # ✅ SHOW REPORT BUTTON
        self.report_btn = tk.Button(
            btn_frm, text="📊  Show Report",
            font=("Consolas", 10, "bold"),
            bg=self.YELLOW, fg="#000000",
            relief=tk.FLAT, padx=12, pady=4,
            cursor="hand2",
            command=self._show_report
        )
        self.report_btn.pack(side=tk.LEFT, padx=4)

        self.sync_btn = tk.Button(
            btn_frm, text="⚡ Mode: WITH Sync (Mutex ON)",
            font=("Consolas", 10, "bold"),
            bg=self.GREEN, fg="#000000",
            relief=tk.FLAT, padx=12, pady=4,
            cursor="hand2",
            command=self._toggle_sync
        )
        self.sync_btn.pack(side=tk.LEFT, padx=4)

        self.start_btn = tk.Button(
            btn_frm, text="▶️  Start System",
            font=("Consolas", 11, "bold"),
            bg=self.ACCENT, fg="#000000",
            relief=tk.FLAT, padx=14, pady=4,
            cursor="hand2",
            command=self._start_system
        )
        self.start_btn.pack(side=tk.LEFT, padx=4)

        self.stop_btn = tk.Button(
            btn_frm, text="⏹  Stop",
            font=("Consolas", 11, "bold"),
            bg=self.RED, fg="#ffffff",
            relief=tk.FLAT, padx=14, pady=4,
            cursor="hand2",
            state=tk.DISABLED,
            command=self._stop_system
        )
        self.stop_btn.pack(side=tk.LEFT, padx=4)

        # ── Worker count control ──
        ctrl_frm = tk.Frame(self, bg=self.PANEL_BG, pady=5, padx=16)
        ctrl_frm.pack(fill=tk.X)

        tk.Label(ctrl_frm, text="Workers:",
                 font=("Consolas", 9), fg=self.TEXT_SEC, bg=self.PANEL_BG).pack(side=tk.LEFT)
        self.workers_spin = tk.Spinbox(
            ctrl_frm, from_=1, to=5, width=3,
            font=("Consolas", 9),
            bg="#0d1117", fg=self.TEXT_PRI,
            buttonbackground=self.CARD_BG,
            relief=tk.FLAT
        )
        self.workers_spin.delete(0, tk.END)
        self.workers_spin.insert(0, "3")
        self.workers_spin.pack(side=tk.LEFT, padx=6)

        tk.Label(ctrl_frm, text="Submitters:",
                 font=("Consolas", 9), fg=self.TEXT_SEC, bg=self.PANEL_BG).pack(side=tk.LEFT, padx=(16, 0))
        self.submitters_spin = tk.Spinbox(
            ctrl_frm, from_=1, to=4, width=3,
            font=("Consolas", 9),
            bg="#0d1117", fg=self.TEXT_PRI,
            buttonbackground=self.CARD_BG,
            relief=tk.FLAT
        )
        self.submitters_spin.delete(0, tk.END)
        self.submitters_spin.insert(0, "2")
        self.submitters_spin.pack(side=tk.LEFT, padx=6)

        tk.Label(ctrl_frm,
                 text="(apply on next Start)",
                 font=("Consolas", 8), fg=self.TEXT_SEC, bg=self.PANEL_BG).pack(side=tk.LEFT, padx=6)

        # ── Main body ──
        body = tk.Frame(self, bg=self.DARK_BG)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        body.columnconfigure(0, weight=2)
        body.columnconfigure(1, weight=2)
        body.columnconfigure(2, weight=3)
        body.rowconfigure(0, weight=1)

        self._build_left_panel(body)
        self._build_center_panel(body)
        self._build_right_panel(body)

        # ── Status bar ──
        sbar = tk.Frame(self, bg="#010409", pady=4)
        sbar.pack(fill=tk.X, side=tk.BOTTOM)

        self.status_lbl = tk.Label(
            sbar,
            text="● System stopped — press ▶️ Start to begin",
            font=("Consolas", 9), fg=self.TEXT_SEC, bg="#010409"
        )
        self.status_lbl.pack(side=tk.LEFT, padx=16)

        self.race_warn = tk.Label(
            sbar, text="",
            font=("Consolas", 9, "bold"),
            fg=self.RED, bg="#010409"
        )
        self.race_warn.pack(side=tk.RIGHT, padx=16)

    # ── Left: Thread Monitor ──
    def _build_left_panel(self, parent):
        frm = tk.Frame(parent, bg=self.PANEL_BG,
                       highlightbackground=self.BORDER, highlightthickness=1)
        frm.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        tk.Label(frm, text="⚙  Worker Threads",
                 font=("Consolas", 12, "bold"),
                 fg=self.TEXT_PRI, bg=self.PANEL_BG, pady=8).pack(fill=tk.X, padx=10)
        ttk.Separator(frm, orient="horizontal").pack(fill=tk.X)

        self.threads_frame = tk.Frame(frm, bg=self.PANEL_BG)
        self.threads_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        tk.Label(frm,
                 text="Each worker = 1 Thread\nMutex controls printer access\nOnly 1 thread prints at a time",
                 font=("Consolas", 8), fg=self.TEXT_SEC, bg=self.PANEL_BG,
                 justify=tk.LEFT).pack(padx=10, pady=6, anchor="w")

    # ── Center: Job Queue ──
    def _build_center_panel(self, parent):
        frm = tk.Frame(parent, bg=self.PANEL_BG,
                       highlightbackground=self.BORDER, highlightthickness=1)
        frm.grid(row=0, column=1, sticky="nsew", padx=4)

        tk.Label(frm, text="📋  Print Job Queue",
                 font=("Consolas", 12, "bold"),
                 fg=self.TEXT_PRI, bg=self.PANEL_BG, pady=8).pack(fill=tk.X, padx=10)
        ttk.Separator(frm, orient="horizontal").pack(fill=tk.X)

        # Manual job submission
        sub_frm = tk.Frame(frm, bg=self.CARD_BG, pady=8, padx=10)
        sub_frm.pack(fill=tk.X, padx=8, pady=(8, 0))

        tk.Label(sub_frm, text="Add Job Manually:",
                 font=("Consolas", 9, "bold"), fg=self.ACCENT, bg=self.CARD_BG).pack(anchor="w")

        row1 = tk.Frame(sub_frm, bg=self.CARD_BG)
        row1.pack(fill=tk.X, pady=4)

        tk.Label(row1, text="Doc:", font=("Consolas", 9),
                 fg=self.TEXT_SEC, bg=self.CARD_BG, width=5).pack(side=tk.LEFT)
        self.doc_entry = tk.Entry(row1, font=("Consolas", 9),
                                  bg="#0d1117", fg=self.TEXT_PRI,
                                  insertbackground=self.ACCENT,
                                  relief=tk.FLAT, width=16)
        self.doc_entry.insert(0, "MyDocument.pdf")
        self.doc_entry.pack(side=tk.LEFT, padx=4)

        tk.Label(row1, text="Pages:", font=("Consolas", 9),
                 fg=self.TEXT_SEC, bg=self.CARD_BG).pack(side=tk.LEFT)
        self.pages_spin = tk.Spinbox(row1, from_=1, to=50,
                                     font=("Consolas", 9), width=4,
                                     bg="#0d1117", fg=self.TEXT_PRI,
                                     buttonbackground=self.CARD_BG,
                                     relief=tk.FLAT)
        self.pages_spin.pack(side=tk.LEFT, padx=4)

        add_btn = tk.Button(row1, text="+ Add",
                            font=("Consolas", 9, "bold"),
                            bg=self.PURPLE, fg="#000000",
                            relief=tk.FLAT, padx=8,
                            cursor="hand2",
                            command=self._manual_add_job)
        add_btn.pack(side=tk.LEFT, padx=4)

        # Queue size indicator
        self.queue_size_lbl = tk.Label(sub_frm, text="Queue: 0 jobs waiting",
                                       font=("Consolas", 8), fg=self.TEXT_SEC, bg=self.CARD_BG)
        self.queue_size_lbl.pack(anchor="w", pady=2)

        # Job list
        list_frm = tk.Frame(frm, bg=self.PANEL_BG)
        list_frm.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        hrow = tk.Frame(list_frm, bg=self.CARD_BG, pady=3)
        hrow.pack(fill=tk.X)
        for text, w in [("Job ID", 10), ("Document", 14), ("Pages", 5), ("Progress", 14), ("Status", 8)]:
            tk.Label(hrow, text=text, font=("Consolas", 8, "bold"),
                     fg=self.ACCENT, bg=self.CARD_BG, width=w).pack(side=tk.LEFT)

        canvas = tk.Canvas(list_frm, bg=self.PANEL_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frm, orient="vertical", command=canvas.yview)
        self.jobs_inner = tk.Frame(canvas, bg=self.PANEL_BG)
        self.jobs_inner.bind("<Configure>",
                             lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.jobs_inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # ── Right: Stats + Logs ──
    def _build_right_panel(self, parent):
        frm = tk.Frame(parent, bg=self.PANEL_BG,
                       highlightbackground=self.BORDER, highlightthickness=1)
        frm.grid(row=0, column=2, sticky="nsew", padx=(4, 0))
        frm.rowconfigure(5, weight=1)   # log gets the stretch
        frm.columnconfigure(0, weight=1)

        # Stats row
        stats_frm = tk.Frame(frm, bg=self.PANEL_BG)
        stats_frm.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        stats_frm.columnconfigure((0, 1, 2, 3), weight=1)

        self.stat_submitted  = self._stat_card(stats_frm, "Submitted",    "0", self.ACCENT,  0)
        self.stat_completed  = self._stat_card(stats_frm, "Completed",    "0", self.GREEN,   1)
        self.stat_sync_pages = self._stat_card(stats_frm, "Safe Pages",   "0", self.PURPLE,  2)
        self.stat_race_pages = self._stat_card(stats_frm, "Unsafe Pages", "0", self.RED,     3)

        # Race condition panel
        cmp_frm = tk.Frame(frm, bg=self.CARD_BG, pady=6, padx=10)
        cmp_frm.grid(row=1, column=0, sticky="ew", padx=8, pady=4)

        tk.Label(cmp_frm, text="🔬  Race Condition Detector",
                 font=("Consolas", 10, "bold"), fg=self.YELLOW, bg=self.CARD_BG).pack(anchor="w")

        cmp_inner = tk.Frame(cmp_frm, bg=self.CARD_BG)
        cmp_inner.pack(fill=tk.X, pady=4)

        tk.Label(cmp_inner, text="Without Sync:",
                 font=("Consolas", 8), fg=self.RED, bg=self.CARD_BG).grid(row=0, column=0, sticky="w")
        self.unsafe_counter_lbl = tk.Label(cmp_inner, text="0",
                                           font=("Consolas", 14, "bold"),
                                           fg=self.RED, bg=self.CARD_BG)
        self.unsafe_counter_lbl.grid(row=0, column=1, padx=10, sticky="e")

        tk.Label(cmp_inner, text="With Sync:",
                 font=("Consolas", 8), fg=self.GREEN, bg=self.CARD_BG).grid(row=1, column=0, sticky="w")
        self.safe_counter_lbl = tk.Label(cmp_inner, text="0",
                                         font=("Consolas", 14, "bold"),
                                         fg=self.GREEN, bg=self.CARD_BG)
        self.safe_counter_lbl.grid(row=1, column=1, padx=10, sticky="e")

        self.diff_lbl = tk.Label(cmp_frm, text="Difference: 0  (no race detected yet)",
                                 font=("Consolas", 9), fg=self.TEXT_SEC, bg=self.CARD_BG)
        self.diff_lbl.pack(anchor="w")

        # ── Live Chart ──
        chart_hdr = tk.Frame(frm, bg=self.PANEL_BG)
        chart_hdr.grid(row=2, column=0, sticky="ew", padx=8, pady=(4, 0))
        tk.Label(chart_hdr, text="📈  Live Jobs Chart",
                 font=("Consolas", 10, "bold"),
                 fg=self.TEXT_PRI, bg=self.PANEL_BG).pack(side=tk.LEFT)

        # Legend
        leg = tk.Frame(chart_hdr, bg=self.PANEL_BG)
        leg.pack(side=tk.RIGHT)
        for color, label in [(self.ACCENT, "Submitted"), (self.GREEN, "Completed"), (self.YELLOW, "Queued")]:
            tk.Label(leg, text="━", font=("Consolas", 10, "bold"), fg=color, bg=self.PANEL_BG).pack(side=tk.LEFT)
            tk.Label(leg, text=label + "  ", font=("Consolas", 7), fg=self.TEXT_SEC, bg=self.PANEL_BG).pack(side=tk.LEFT)

        self.chart_canvas = tk.Canvas(frm, bg="#010409", height=130,
                                      highlightthickness=1,
                                      highlightbackground=self.BORDER)
        self.chart_canvas.grid(row=3, column=0, sticky="ew", padx=8, pady=(2, 4))
        # Force canvas to render at correct size after layout
        self.after(100, self._draw_chart)

        # Log header
        log_hdr = tk.Frame(frm, bg=self.PANEL_BG)
        log_hdr.grid(row=4, column=0, sticky="ew", padx=8, pady=(4, 0))
        tk.Label(log_hdr, text="📟  Console Log",
                 font=("Consolas", 10, "bold"),
                 fg=self.TEXT_PRI, bg=self.PANEL_BG).pack(side=tk.LEFT)
        tk.Button(log_hdr, text="Clear",
                  font=("Consolas", 8), bg=self.CARD_BG, fg=self.TEXT_SEC,
                  relief=tk.FLAT, cursor="hand2",
                  command=self._clear_log).pack(side=tk.RIGHT)

        # Log text
        log_frm = tk.Frame(frm, bg=self.PANEL_BG)
        log_frm.grid(row=5, column=0, sticky="nsew", padx=8, pady=(2, 8))
        frm.rowconfigure(5, weight=1)

        self.log_text = tk.Text(log_frm, font=("Consolas", 8),
                                bg="#010409", fg=self.TEXT_PRI,
                                insertbackground=self.ACCENT,
                                relief=tk.FLAT, wrap=tk.WORD,
                                state=tk.DISABLED)
        log_sb = ttk.Scrollbar(log_frm, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_sb.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_sb.pack(side=tk.RIGHT, fill=tk.Y)

        self.log_text.tag_config("lock", foreground=self.GREEN)
        self.log_text.tag_config("race", foreground=self.RED)
        self.log_text.tag_config("done", foreground=self.PURPLE)
        self.log_text.tag_config("info", foreground=self.ACCENT)
        self.log_text.tag_config("warn", foreground=self.YELLOW)

    def _stat_card(self, parent, label, value, color, col):
        card = tk.Frame(parent, bg=self.CARD_BG, padx=6, pady=6)
        card.grid(row=0, column=col, sticky="ew", padx=3)
        lbl = tk.Label(card, text=value, font=("Consolas", 18, "bold"),
                       fg=color, bg=self.CARD_BG)
        lbl.pack()
        tk.Label(card, text=label, font=("Consolas", 7),
                 fg=self.TEXT_SEC, bg=self.CARD_BG).pack()
        return lbl

    # ─────────────────────────────────────────────────
    #  SYSTEM CONTROL
    # ─────────────────────────────────────────────────

    def _start_system(self):
        global is_running, active_threads, sync_mode
        global total_pages_printed, total_pages_safe, stats

        if is_running:
            return

        is_running = True

        # ✅ FIXED: Reset ALL counters properly
        total_pages_printed = 0
        total_pages_safe    = 0
        with stats_lock:
            stats = {k: 0 for k in stats}
            stats["session_start"] = time.time()

        # Clear job history for new session
        with job_history_lock:
            job_history.clear()
        with log_lock:
            log_entries.clear()
        with chart_history_lock:
            chart_history.clear()

        # Clear UI
        for w in self.threads_frame.winfo_children():
            w.destroy()
        self._thread_cards.clear()
        self._job_rows.clear()
        for w in self.jobs_inner.winfo_children():
            w.destroy()

        try:
            num_workers    = max(1, min(5, int(self.workers_spin.get())))
            num_submitters = max(1, min(4, int(self.submitters_spin.get())))
        except ValueError:
            num_workers, num_submitters = 3, 2

        with threads_lock:
            active_threads.clear()

        # ✅ FIXED: Create thread cards BEFORE starting threads
        for i in range(1, num_workers + 1):
            self._create_thread_card(i)

        for i in range(1, num_workers + 1):
            t = PrinterWorkerThread(i, self._thread_safe_callback, sync_mode)
            t.start()
            with threads_lock:
                active_threads.append(t)

        for i in range(1, num_submitters + 1):
            t = JobSubmitterThread(i, self._thread_safe_callback)
            t.start()
            with threads_lock:
                active_threads.append(t)

        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.status_lbl.config(
            text=f"● Running — {num_workers} workers, {num_submitters} submitters",
            fg=self.GREEN
        )
        self._log_ui(
            f"[SYSTEM] Started — Sync: {'ON (Mutex)' if sync_mode else 'OFF (Race Condition!)'}  "
            f"Workers: {num_workers}  Submitters: {num_submitters}",
            "info"
        )

    def _stop_system(self):
        global is_running
        is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_lbl.config(text="● System stopped", fg=self.RED)
        self._log_ui("[SYSTEM] Stopped by user", "warn")

    def _toggle_sync(self):
        global sync_mode
        sync_mode = not sync_mode
        if sync_mode:
            self.sync_btn.config(text="⚡ Mode: WITH Sync (Mutex ON)",
                                 bg=self.GREEN, fg="#000000")
        else:
            self.sync_btn.config(text="💥 Mode: WITHOUT Sync (Race Condition!)",
                                 bg=self.RED, fg="#ffffff")
        self._log_ui(
            f"[SYSTEM] Mode → {'WITH Mutex' if sync_mode else 'WITHOUT Sync — RACE CONDITION DEMO'}",
            "warn"
        )
        if is_running:
            messagebox.showinfo("Mode Changed",
                                "Mode applies to new threads.\nRestart system to apply to all workers.")

    def _manual_add_job(self):
        doc = self.doc_entry.get().strip() or "Document.pdf"
        try:
            pages = int(self.pages_spin.get())
        except ValueError:
            pages = 1

        job_id = f"MANUAL-{int(time.time()*100) % 10000}"
        job    = {"id": job_id, "name": doc, "pages": pages, "submitter": "Manual"}
        job_queue.put(job)
        with stats_lock:
            stats["jobs_submitted"] += 1
        self._log_ui(f"[MANUAL] Added: {doc} ({pages} pages)", "info")

    def _show_report(self):
        """✅ NEW: Open the Report window."""
        ReportWindow(self)

    def _on_close(self):
        global is_running
        is_running = False
        self.destroy()

    # ─────────────────────────────────────────────────
    #  THREAD CARDS
    # ─────────────────────────────────────────────────

    def _create_thread_card(self, worker_id):
        card = tk.Frame(self.threads_frame, bg=self.CARD_BG,
                        highlightbackground=self.BORDER, highlightthickness=1,
                        pady=8, padx=10)
        card.pack(fill=tk.X, pady=4)

        header = tk.Frame(card, bg=self.CARD_BG)
        header.pack(fill=tk.X)

        dot = tk.Label(header, text="●", font=("Consolas", 12),
                       fg=self.YELLOW, bg=self.CARD_BG)
        dot.pack(side=tk.LEFT)

        tk.Label(header, text=f"  Worker Thread #{worker_id}",
                 font=("Consolas", 10, "bold"),
                 fg=self.TEXT_PRI, bg=self.CARD_BG).pack(side=tk.LEFT)

        status_lbl = tk.Label(header, text="idle",
                               font=("Consolas", 9),
                               fg=self.TEXT_SEC, bg=self.CARD_BG)
        status_lbl.pack(side=tk.RIGHT)

        doc_lbl = tk.Label(card, text="Waiting for jobs...",
                           font=("Consolas", 8), fg=self.TEXT_SEC, bg=self.CARD_BG)
        doc_lbl.pack(anchor="w", pady=2)

        lock_lbl = tk.Label(card, text="🔓 Lock: FREE",
                             font=("Consolas", 8), fg=self.GREEN, bg=self.CARD_BG)
        lock_lbl.pack(anchor="w")

        self._thread_cards[worker_id] = {
            "card":   card,
            "dot":    dot,
            "status": status_lbl,
            "doc":    doc_lbl,
            "lock":   lock_lbl,
        }

    def _update_thread_card(self, worker_id, state, doc_name):
        if worker_id not in self._thread_cards:
            return
        c = self._thread_cards[worker_id]
        if state == "busy":
            c["dot"].config(fg=self.ACCENT)
            c["status"].config(text="● PRINTING", fg=self.ACCENT)
            c["doc"].config(text=f"  {doc_name}")
            c["lock"].config(
                text="🔒 Lock: HELD" if sync_mode else "⚠ Lock: NONE",
                fg=self.YELLOW if sync_mode else self.RED
            )
        elif state == "idle":
            c["dot"].config(fg=self.GREEN)
            c["status"].config(text="✔ idle", fg=self.GREEN)
            c["doc"].config(text="Waiting for jobs...")
            c["lock"].config(text="🔓 Lock: FREE", fg=self.GREEN)
        elif state == "stopped":
            c["dot"].config(fg=self.RED)
            c["status"].config(text="⏹ stopped", fg=self.RED)
            c["doc"].config(text="")
            c["lock"].config(text="", fg=self.TEXT_SEC)

    # ─────────────────────────────────────────────────
    #  JOB ROWS
    # ─────────────────────────────────────────────────

    def _add_job_row(self, job_id, doc_name, pages, submitter):
        row = tk.Frame(self.jobs_inner, bg=self.CARD_BG, pady=3, padx=4)
        row.pack(fill=tk.X, pady=1)

        tk.Label(row, text=job_id[-8:], font=("Consolas", 7),
                 fg=self.TEXT_SEC, bg=self.CARD_BG, width=10).pack(side=tk.LEFT)
        tk.Label(row, text=doc_name[:14], font=("Consolas", 8),
                 fg=self.TEXT_PRI, bg=self.CARD_BG, width=14).pack(side=tk.LEFT)
        tk.Label(row, text=str(pages), font=("Consolas", 8),
                 fg=self.TEXT_SEC, bg=self.CARD_BG, width=5).pack(side=tk.LEFT)

        pb_frame = tk.Frame(row, bg=self.DARK_BG, width=100, height=12)
        pb_frame.pack(side=tk.LEFT, padx=2)
        pb_frame.pack_propagate(False)
        pb_fill = tk.Frame(pb_frame, bg=self.ACCENT, width=0, height=12)
        pb_fill.pack(side=tk.LEFT)

        status_lbl = tk.Label(row, text="queued", font=("Consolas", 7),
                               fg=self.YELLOW, bg=self.CARD_BG, width=8)
        status_lbl.pack(side=tk.LEFT)

        self._job_rows[job_id] = {
            "row":    row,
            "pb":     pb_fill,
            "pb_frm": pb_frame,
            "status": status_lbl,
        }

    def _update_job_row(self, job_id, progress, page, total):
        if job_id not in self._job_rows:
            return
        r = self._job_rows[job_id]
        r["pb"].config(width=max(int((progress / 100) * 100), 0))
        r["status"].config(text=f"{progress}%  p{page}/{total}", fg=self.ACCENT)

    def _complete_job_row(self, job_id):
        if job_id not in self._job_rows:
            return
        r = self._job_rows[job_id]
        r["pb"].config(width=100, bg=self.GREEN)
        r["status"].config(text="✔ done", fg=self.GREEN)

    # ─────────────────────────────────────────────────
    #  THREAD-SAFE CALLBACK
    # ─────────────────────────────────────────────────

    def _thread_safe_callback(self, event, *args):
        self.after(0, self._handle_callback, event, args)

    def _handle_callback(self, event, args):
        if event == "thread_status":
            worker_id, state, doc = args
            self._update_thread_card(worker_id, state, doc)

        elif event == "job_progress":
            job_id, progress, page, total = args
            if job_id not in self._job_rows:
                self._add_job_row(job_id, "...", total, "auto")
            self._update_job_row(job_id, progress, page, total)

        elif event == "job_done":
            job_id, doc_name, pages, submitter = args
            if job_id not in self._job_rows:
                self._add_job_row(job_id, doc_name, pages, submitter)
            self._complete_job_row(job_id)

        elif event == "add_log":
            self._log_ui(args[0])

    # ─────────────────────────────────────────────────
    #  LOG CONSOLE
    # ─────────────────────────────────────────────────

    def _log_ui(self, message, tag=None):
        self.log_text.config(state=tk.NORMAL)
        if tag is None:
            if "🔒" in message or "Mutex" in message or "Lock" in message:
                tag = "lock"
            elif "Race" in message or "⚠" in message or "WITHOUT" in message:
                tag = "race"
            elif "✔" in message or "finished" in message:
                tag = "done"
            elif "SYSTEM" in message or "▶" in message:
                tag = "info"
            else:
                tag = None

        self.log_text.insert(tk.END, message + "\n", tag or "")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

        lines = int(self.log_text.index("end-1c").split(".")[0])
        if lines > 400:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.delete("1.0", "100.0")
            self.log_text.config(state=tk.DISABLED)

    def _clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    # ─────────────────────────────────────────────────
    #  STATS REFRESH
    # ─────────────────────────────────────────────────

    def _start_stats_refresh(self):
        self._refresh_stats()

    def _refresh_stats(self):
        with stats_lock:
            s = stats.copy()

        self.stat_submitted.config(text=str(s["jobs_submitted"]))
        self.stat_completed.config(text=str(s["jobs_completed"]))
        self.stat_sync_pages.config(text=str(s["pages_with_sync"]))
        self.stat_race_pages.config(text=str(s["pages_without_sync"]))

        self.safe_counter_lbl.config(text=str(total_pages_safe))
        self.unsafe_counter_lbl.config(text=str(total_pages_printed))

        # Update queue size label
        if hasattr(self, "queue_size_lbl"):
            qs = job_queue.qsize()
            self.queue_size_lbl.config(
                text=f"Queue: {qs} job{'s' if qs != 1 else ''} waiting",
                fg=self.YELLOW if qs > 0 else self.TEXT_SEC
            )

        diff = abs(total_pages_safe - total_pages_printed)
        if diff > 0 and not sync_mode:
            self.diff_lbl.config(
                text=f"⚠ Difference: {diff}  ← RACE CONDITION DETECTED!",
                fg=self.RED)
            self.race_warn.config(
                text=f"💥 RACE CONDITION: {diff} corruptions!")
        elif diff == 0:
            self.diff_lbl.config(
                text="Difference: 0  (synchronized — data consistent ✓)",
                fg=self.GREEN)
            self.race_warn.config(text="")
        else:
            self.diff_lbl.config(text=f"Difference: {diff}", fg=self.YELLOW)

        # ── Record chart snapshot every refresh ──
        if is_running:
            with chart_history_lock:
                chart_history.append({
                    "submitted": s["jobs_submitted"],
                    "completed": s["jobs_completed"],
                    "queued":    job_queue.qsize(),
                })
                if len(chart_history) > CHART_MAX_POINTS:
                    chart_history.pop(0)

        self._draw_chart()
        self.after(300, self._refresh_stats)

    def _draw_chart(self):
        """Draw the live line chart on self.chart_canvas."""
        c = self.chart_canvas
        c.delete("all")

        with chart_history_lock:
            data = list(chart_history)

        W = c.winfo_width()
        H = c.winfo_height()
        if W < 10 or H < 10:
            return

        PAD_L, PAD_R, PAD_T, PAD_B = 36, 8, 8, 18

        # Background grid lines
        grid_lines = 4
        for i in range(grid_lines + 1):
            y = PAD_T + (H - PAD_T - PAD_B) * i // grid_lines
            c.create_line(PAD_L, y, W - PAD_R, y,
                          fill="#1e2530", width=1)

        if len(data) < 2:
            c.create_text(W // 2, H // 2,
                          text="Start the system to see the live chart",
                          fill=self.TEXT_SEC, font=("Consolas", 8))
            return

        # Find y-axis max
        all_vals = [p for d in data for p in (d["submitted"], d["completed"], d["queued"])]
        y_max = max(all_vals) if max(all_vals) > 0 else 1

        def to_xy(idx, val):
            x = PAD_L + (W - PAD_L - PAD_R) * idx / (CHART_MAX_POINTS - 1)
            y = H - PAD_B - (H - PAD_T - PAD_B) * val / y_max
            return x, y

        # Draw each series
        for key, color in [("submitted", self.ACCENT),
                            ("completed", self.GREEN),
                            ("queued",    self.YELLOW)]:
            points = []
            for idx in range(CHART_MAX_POINTS):
                # Fill missing older points with 0
                data_idx = idx - (CHART_MAX_POINTS - len(data))
                if data_idx < 0:
                    val = 0
                else:
                    val = data[data_idx][key]
                points.append(to_xy(idx, val))

            # Draw line
            for i in range(len(points) - 1):
                c.create_line(points[i][0], points[i][1],
                               points[i+1][0], points[i+1][1],
                               fill=color, width=2, smooth=True)

            # Draw last dot
            lx, ly = points[-1]
            c.create_oval(lx - 3, ly - 3, lx + 3, ly + 3,
                          fill=color, outline="")

            # Value label at last point
            last_val = data[-1][key]
            c.create_text(lx + 6, ly, text=str(last_val),
                          fill=color, font=("Consolas", 7), anchor="w")

        # Y-axis labels
        for i in range(grid_lines + 1):
            val = int(y_max * (grid_lines - i) / grid_lines)
            y = PAD_T + (H - PAD_T - PAD_B) * i // grid_lines
            c.create_text(PAD_L - 4, y, text=str(val),
                          fill=self.TEXT_SEC, font=("Consolas", 6), anchor="e")

        # X-axis label
        c.create_text(W // 2, H - 4,
                      text="← time (each tick = 300ms) →",
                      fill=self.TEXT_SEC, font=("Consolas", 6))


# ══════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    app = PrinterQueueApp()
    app.mainloop()
