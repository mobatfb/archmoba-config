# HERRAMIENTA DE PRUEBA PTM
# La dependencia "humanize" NO se declara en guide.csv a propósito.
# PTM debe detectarla automáticamente desde este import.
from humanize import naturalsize
import tkinter as tk


def App(parent, app):
    frame = tk.Frame(parent, bg="#FFFFFF")

    tk.Label(
        frame,
        text="Prueba de dependencia humanize",
        font=("Segoe UI", 18, "bold"),
        bg="#FFFFFF",
        fg="#101010",
    ).pack(pady=(35, 8))

    tk.Label(
        frame,
        text="PTM debe detectar e instalar automáticamente: humanize",
        font=("Segoe UI", 10),
        bg="#FFFFFF",
        fg="#666666",
    ).pack(pady=(0, 22))

    tk.Label(
        frame,
        text="Escribe una cantidad de bytes:",
        font=("Segoe UI", 10, "bold"),
        bg="#FFFFFF",
        fg="#101010",
    ).pack()

    entry = tk.Entry(
        frame,
        font=("Segoe UI", 11),
        width=30,
        relief="solid",
        bd=1,
    )
    entry.pack(pady=(8, 10))
    entry.insert(0, "1048576")

    result_var = tk.StringVar(value="")

    tk.Label(
        frame,
        textvariable=result_var,
        font=("Segoe UI", 12, "bold"),
        bg="#FFFFFF",
        fg="#176684",
    ).pack(pady=10)

    def convert():
        raw = entry.get().strip()
        try:
            value = int(raw)
            result_var.set(naturalsize(value, binary=True))
        except ValueError:
            result_var.set("Ingresa un número entero válido.")

    tk.Button(
        frame,
        text="Convertir con humanize",
        command=convert,
        bg="#176684",
        fg="#FFFFFF",
        activebackground="#0F536E",
        activeforeground="#FFFFFF",
        relief="flat",
        padx=18,
        pady=8,
        cursor="hand2",
    ).pack(pady=8)

    return frame
