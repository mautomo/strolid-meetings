import subprocess
import sys
from pathlib import Path

def run_script(script_path: Path, args: list = []):
    python_exe = Path(__file__).resolve().parents[1] / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        python_exe = Path(sys.executable)
        
    cmd = [str(python_exe), "-u", str(script_path)] + args
    print(f"\n==================================================")
    print(f"RUNNING: {' '.join(cmd)}")
    print(f"==================================================\n")
    
    result = subprocess.run(cmd, capture_output=False, text=True)
    if result.returncode != 0:
        print(f"ERROR: Script {script_path.name} failed with return code {result.returncode}")
        sys.exit(result.returncode)
    print(f"\nSUCCESS: {script_path.name} completed.\n")

def main():
    src_dir = Path(__file__).resolve().parent / "src"
    
    # 1. Extract meetings
    run_script(src_dir / "extract.py")
    
    # 2. Extract docs
    run_script(src_dir / "extract_docs.py")
    
    # 3. Normalize meetings
    run_script(src_dir / "normalize.py")
    
    # 4. Upload meetings to warehouse
    run_script(src_dir / "warehouse.py")
    
    # 5. Chunk, embed, and upload to BigQuery (meeting + docs)
    run_script(src_dir / "embeddings.py")
    
    # 6. Verify RAG search
    run_script(src_dir / "verify_rag.py")
    
    print("\n==================================================")
    print("ALL PIPELINE STEPS COMPLETED SUCCESSFULLY!")
    print("==================================================")

if __name__ == "__main__":
    main()
