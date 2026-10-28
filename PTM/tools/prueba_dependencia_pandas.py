# HERRAMIENTA DE PRUEBA PTM
# "pandas" NO se declara en guide.csv a propósito.
# PTM debe detectarla automáticamente desde este import.
import pandas as pd
import tkinter as tk


def create_tool(parent, app):
    frame = tk.Frame(parent, bg="#FFFFFF")

    tk.Label(
        frame,
        text="Prueba de dependencia pesada: pandas",
        font=("Segoe UI", 18, "bold"),
        bg="#FFFFFF",
        fg="#101010",
    ).pack(pady=(35, 8))

    tk.Label(
        frame,
        text="PTM debe detectar e instalar pandas y sus dependencias automáticamente.",
        font=("Segoe UI", 10),
        bg="#FFFFFF",
        fg="#666666",
    ).pack(pady=(0, 20))

    result_var = tk.StringVar(value="")

    tk.Label(
        frame,
        textvariable=result_var,
        font=("Consolas", 10),
        bg="#FFFFFF",
        fg="#176684",
        justify="left",
    ).pack(padx=25, pady=12)

    def test_pandas():
        df = pd.DataFrame(
            {
                "Herramienta": ["PTM", "AMDEV", "ARCHMOBA"],
                "Valor": [10, 20, 30],
            }
        )
        total = int(df["Valor"].sum())
        result_var.set(
            f"pandas {pd.__version__} funcionando\n\n"
            f"{df.to_string(index=False)}\n\n"
            f"TOTAL = {total}"
        )

    tk.Button(
        frame,
        text="Probar pandas",
        command=test_pandas,
        bg="#176684",
        fg="#FFFFFF",
        activebackground="#0F536E",
        activeforeground="#FFFFFF",
        relief="flat",
        padx=20,
        pady=8,
        cursor="hand2",
    ).pack(pady=8)

    return frame
