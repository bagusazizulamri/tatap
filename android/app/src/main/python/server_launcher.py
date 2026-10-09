import os, sys, threading

def start_server(data_dir=None):
    """Jalankan server Uvicorn Tatap di background thread Android."""
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.join(base_dir, "backend")
        frontend_dir = os.path.join(base_dir, "frontend")
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

        if data_dir:
            os.environ["TATAP_DATABASE_PATH"] = os.path.join(data_dir, "anime.db")
            os.environ["TATAP_CACHE_DIR"] = os.path.join(data_dir, "cache")
            os.makedirs(data_dir, exist_ok=True)
            os.makedirs(os.path.join(data_dir, "cache"), exist_ok=True)

        os.environ["APP_HOST"] = "127.0.0.1"
        os.environ["APP_PORT"] = "8767"

        # Import main module setelah environment siap
        import main
        main.frontend_dir = frontend_dir

        import uvicorn
        # Jalankan server
        uvicorn.run(main.app, host="127.0.0.1", port=8767, loop="asyncio", http="h11", log_level="warning")
    except Exception as e:
        print(f"[TATAP-SERVER-ERROR] {e}", flush=True)

def run_in_background(data_dir=None):
    t = threading.Thread(target=start_server, args=(data_dir,), daemon=True)
    t.start()
    return True
