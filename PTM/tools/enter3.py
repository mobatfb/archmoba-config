import tkinter as tk

def create_tool(parent, app):
    frame = tk.Frame(parent, bg="white")
    tk.Label(
        frame,
        text="Hola",
        bg="white",
        fg="black",
        font=("Segoe UI", 28, "bold"),
    ).pack(expand=True)
    return frame
