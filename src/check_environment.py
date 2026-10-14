import sys
from project_paths import PROJECT_DIR, WORK_DIR, OUTPUT_DIR

def main():
    print("Python:", sys.version.split()[0])
    print("Executable:", sys.executable)
    print("Isolated environment:", sys.prefix != sys.base_prefix)
    for path in (WORK_DIR, OUTPUT_DIR):
        path.mkdir(parents=True, exist_ok=True)
    for path in (PROJECT_DIR, WORK_DIR, OUTPUT_DIR):
        print("Directory:", path)
    print("Environment check passed")

if __name__ == "__main__":
    main()
