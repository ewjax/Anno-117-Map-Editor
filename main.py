"""
Anno 117 Map Template Editor - Entry Point
"""
import os
import sys
import tkinter as tk

# Ensure the app's own directory is on the path when launched directly
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from app_window import MapEditorApp
from island_registry import IslandRegistry
from fertility_registry import FertilityRegistry
from fertility_set_registry import FertilitySetRegistry
import tool_setup_dialog


def main():
    root = tk.Tk()
    root.title("Anno 117 Map Template Editor")
    root.geometry("1440x900")
    root.minsize(900, 600)

    # Dark window background to avoid white flash on startup
    root.configure(bg="#0b192c")

    app = MapEditorApp(root)

    import threading

    def _load_islands():
        IslandRegistry.instance().load()
        root.after(0, app.refresh_all_canvases)

    threading.Thread(target=_load_islands, daemon=True).start()
    threading.Thread(target=FertilityRegistry.instance().load, daemon=True).start()
    threading.Thread(target=FertilitySetRegistry.instance().load, daemon=True).start()
    root.protocol("WM_DELETE_WINDOW", app._on_close)

    root.after(300, lambda: tool_setup_dialog.check_and_prompt(root, app))

    root.mainloop()


if __name__ == "__main__":
    main()
