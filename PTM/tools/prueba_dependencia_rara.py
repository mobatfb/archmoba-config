# HERRAMIENTA DE PRUEBA PTM
# La dependencia "boltons" NO se declara en guide.csv a propósito.
# PTM debe detectarla automáticamente desde este import.
from boltons.strutils import camel2under
import tkinter as tk


def App(parent, app):
    frame = tk.Frame(parent, bg="#FFFFFF")

    tk.Label(
        frame,
        text="Prueba de dependencia rara",
        font=("Segoe UI", 18, "bold"),
        bg="#FFFFFF",
        fg="#101010",
    ).pack(pady=(35, 8))

    tk.Label(
        frame,
        text="PTM detectó e instaló automáticamente: boltons",
        font=("Segoe UI", 10),
        bg="#FFFFFF",
        fg="#666666",
    ).pack(pady=(0, 22))

    tk.Label(
        frame,
        text="Escribe texto en CamelCase:",
        font=("Segoe UI", 10, "bold"),
        bg="#FFFFFF",
        fg="#101010",
    ).pack()

    entry = tk.Entry(
        frame,
        font=("Segoe UI", 11),
        width=36,
        relief="solid",
        bd=1,
    )
    entry.pack(pady=(8, 10))
    entry.insert(0, "HolaMundoPTM")

    result_var = tk.StringVar(value="")

    result = tk.Label(
        frame,
        textvariable=result_var,
        font=("Segoe UI", 11, "bold"),
        bg="#FFFFFF",
        fg="#176684",
    )
    result.pack(pady=10)

    def convert():
        value = entry.get().strip()
        if not value:
            result_var.set("Escribe algún texto.")
            return
        result_var.set(camel2under(value))

    tk.Button(
        frame,
        text="Convertir con boltons",
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
