# HERRAMIENTA DE PRUEBA PTM
# La dependencia "textdistance" NO se declara en guide.csv a propósito.
# PTM debe detectarla automáticamente desde este import.
import textdistance
import tkinter as tk


def App(parent, app):
    frame = tk.Frame(parent, bg="#FFFFFF")

    tk.Label(
        frame,
        text="Prueba de dependencia textdistance",
        font=("Segoe UI", 18, "bold"),
        bg="#FFFFFF",
        fg="#101010",
    ).pack(pady=(35, 8))

    tk.Label(
        frame,
        text="PTM debe detectar e instalar automáticamente: textdistance",
        font=("Segoe UI", 10),
        bg="#FFFFFF",
        fg="#666666",
    ).pack(pady=(0, 22))

    form = tk.Frame(frame, bg="#FFFFFF")
    form.pack()

    tk.Label(
        form,
        text="Texto 1:",
        font=("Segoe UI", 10, "bold"),
        bg="#FFFFFF",
        fg="#101010",
    ).grid(row=0, column=0, sticky="e", padx=(0, 8), pady=5)

    first = tk.Entry(form, font=("Segoe UI", 11), width=28, relief="solid", bd=1)
    first.grid(row=0, column=1, pady=5)
    first.insert(0, "ARCHMOBA")

    tk.Label(
        form,
        text="Texto 2:",
        font=("Segoe UI", 10, "bold"),
        bg="#FFFFFF",
        fg="#101010",
    ).grid(row=1, column=0, sticky="e", padx=(0, 8), pady=5)

    second = tk.Entry(form, font=("Segoe UI", 11), width=28, relief="solid", bd=1)
    second.grid(row=1, column=1, pady=5)
    second.insert(0, "ARCHMOVA")

    result_var = tk.StringVar(value="")

    tk.Label(
        frame,
        textvariable=result_var,
        font=("Segoe UI", 12, "bold"),
        bg="#FFFFFF",
        fg="#176684",
    ).pack(pady=14)

    def compare():
        a = first.get()
        b = second.get()
        distance = textdistance.levenshtein.distance(a, b)
        similarity = textdistance.levenshtein.normalized_similarity(a, b)
        result_var.set(
            f"Distancia: {distance}  |  Similitud: {similarity * 100:.1f}%"
        )

    tk.Button(
        frame,
        text="Comparar con textdistance",
        command=compare,
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
