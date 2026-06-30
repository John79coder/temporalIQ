import subprocess
import sys
import os
import re
from datetime import datetime

# --- Constants ---
VALID_MODES = ("build", "restart", "migrate")
DOCKER_ENV_FILE = ".env.docker"
LINES_PER_FILE = 400
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DOCKER = ["docker", "compose", "--env-file", DOCKER_ENV_FILE]

ERROR_MARKERS = (
    "error",
    "failed",
    "exception",
    "traceback",
)


# --- State ---
index = 1
line_count = 0
total_lines = 0
last_stage = ""
writer = None


# --- Helpers ---
def separator():
    print("============================================================")


def write_status(msg, color="cyan"):
    colors = {
        "cyan":    "\033[96m",
        "white":   "\033[97m",
        "green":   "\033[92m",
        "magenta": "\033[95m",
        "yellow":  "\033[93m",
        "red":     "\033[91m",
    }
    print(f"{colors.get(color, '')}[{datetime.now().strftime('%H:%M:%S')}] {msg}\033[0m")


def run(cmd, **kwargs):
    return subprocess.run(DOCKER + cmd, text=True, **kwargs)


DUPLICATE_TABLE_PATTERNS = (
    re.compile(r"DuplicateTable", re.IGNORECASE),
    re.compile(r'relation ".+?" already exists', re.IGNORECASE),
    re.compile(r"psycopg2\.errors\.DuplicateTable", re.IGNORECASE),
)


def _is_duplicate_table_error(output: str) -> bool:
    return any(p.search(output) for p in DUPLICATE_TABLE_PATTERNS)


def run_migrations():
    write_status("Running migrations...", "yellow")
    result = run(
        ["exec", "app", "flask", "db", "upgrade"],
        capture_output=True,
    )

    # Always print the full migration output first so context is visible above the summary.
    combined = (result.stdout or "") + (result.stderr or "")
    if combined.strip():
        print(combined, end="")

    if result.returncode == 0:
        print("\033[92m✅ Migrations applied successfully!\033[0m")
        return 0

    # --- Failure diagnostics ---
    if _is_duplicate_table_error(combined):
        print("\033[91m❌ Migration FAILED — schema already exists in the target database.\033[0m")
        print()
        print("\033[93mDiagnosis:\033[0m")
        print("  The database already contains one or more tables that the initial")
        print("  Alembic migration is trying to create. This usually means you are")
        print("  reusing an existing PostgreSQL database or Docker volume that was")
        print("  created outside of (or before) Alembic migration tracking, so the")
        print("  alembic_version table is absent or out of sync.")
        print()
        print("\033[93mNext steps:\033[0m")
        print("  1. If this is a disposable dev database, delete the volume and recreate it:")
        print("       docker compose down -v")
        print("       docker compose up -d db")
        print("       python docker-builder.py migrate")
        print()
        print("  2. If the database contains data you need to keep, connect to it and")
        print("     check whether the alembic_version table exists and what revision it")
        print("     holds:")
        print("       docker compose exec db psql -U <user> -d <dbname> -c \\\\")
        print('         "SELECT * FROM alembic_version;"')
        print("     Then stamp Alembic to the matching revision before retrying:")
        print("       docker compose exec app flask db stamp <revision>")
        print("       python docker-builder.py migrate")
        print()
        print("\033[91mNo database changes have been made by this tool.\033[0m")
    else:
        print("\033[91m❌ Migration FAILED — run: python docker-builder.py migrate\033[0m")

    return result.returncode


def open_new_log_file(num, output_dir):
    global writer, line_count
    if writer:
        writer.close()
    filepath = os.path.join(output_dir, f"build_log_{num:03d}.txt")
    writer = open(filepath, "w", encoding="utf-8")
    line_count = 0
    write_status(f"Created: {os.path.basename(filepath)}", "white")


# --- Entry point ---
mode = sys.argv[1] if len(sys.argv) > 1 else None

if mode not in VALID_MODES:
    print(f"Usage: python docker-builder.py [build|restart|migrate]")
    print(f"  build   — full image rebuild")
    print(f"  restart — restart app container only (use for code changes)")
    print(f"  migrate — run flask db upgrade inside the app container")
    sys.exit(1)

print("\n============================================================")
print(" TemporalIQ Docker Manager")
separator()
print()

# --- RESTART ---
if mode == "restart":
    write_status("Restarting app container...", "yellow")
    result = run(["restart", "app"])
    print()
    separator()
    if result.returncode == 0:
        print("\033[92m✅ App restarted successfully!\033[0m")
    else:
        print("\033[91m❌ Restart FAILED\033[0m")
    separator()
    sys.exit(result.returncode)

# --- MIGRATE ---
if mode == "migrate":
    exit_code = run_migrations()
    separator()
    sys.exit(exit_code)

# --- BUILD ---
TIMESTAMP = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "build_logs", TIMESTAMP)
os.makedirs(OUTPUT_DIR, exist_ok=True)

open_new_log_file(index, OUTPUT_DIR)
write_status("Starting Docker build (streaming output)...", "yellow")
write_status(f"Logs → {OUTPUT_DIR}", "cyan")

process = subprocess.Popen(
    DOCKER + ["build", "--no-cache", "--progress=plain"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    encoding="utf-8",
    errors="replace",
    bufsize=1
)

start_time = datetime.now()

for raw_line in process.stdout:
    line = raw_line.rstrip("\n")
    writer.write(line + "\n")
    writer.flush()
    total_lines += 1
    line_count += 1

    line_lower = line.lower()
    if any(m in line_lower for m in ERROR_MARKERS):
        write_status(f"⚠ {line}", "red")

    m = re.match(r"^#\d+\s+\[(.+?)\]", line)
    if m:
        stage = m.group(1)
        if stage != last_stage:
            last_stage = stage
            write_status(f"→ Stage: {stage}", "magenta")

    if line_count >= LINES_PER_FILE:
        index += 1
        open_new_log_file(index, OUTPUT_DIR)

process.wait()
build_succeeded = (process.returncode == 0)
writer.close()

duration = str(datetime.now() - start_time).split(".")[0]  # HH:MM:SS, no microseconds

print()
separator()
if build_succeeded:
    print("\033[92m✅ Build completed successfully!\033[0m")
    print("\033[93mRun 'docker compose up -d' to start containers, then 'python docker-builder.py migrate' if needed.\033[0m")
else:
    print("\033[91m❌ Build FAILED\033[0m")
    print(f"\033[93mCheck logs for details: {OUTPUT_DIR}\033[0m")
    print(f"\033[93mLast log file: build_log_{index:03d}.txt\033[0m")

print(f"Duration: {duration}")
print(f"Logs saved to: {OUTPUT_DIR}")
separator()