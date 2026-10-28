# HERRAMIENTA DE PRUEBA PTM
# "pyarrow" NO se declara en guide.csv a propósito.
# PTM debe detectarla automáticamente desde este import.
import pyarrow as pa
import tkinter as tk


def create_tool(parent, app):
    frame = tk.Frame(parent, bg="#FFFFFF")

    tk.Label(
        frame,
        text="Prueba de dependencia pesada: pyarrow",
        font=("Segoe UI", 18, "bold"),
        bg="#FFFFFF",
        fg="#101010",
    ).pack(pady=(35, 8))

    tk.Label(
        frame,
        text="PTM debe detectar e instalar pyarrow automáticamente desde el import.",
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
        wraplength=600,
    ).pack(padx=25, pady=12)

    def test_pyarrow():
        table = pa.table(
            {
                "aplicacion": ["PTM", "AMDEV", "ARCHMOBA"],
                "valor": [10, 20, 30],
            }
        )
        result_var.set(
            f"pyarrow {pa.__version__} funcionando\n\n"
            f"Filas: {table.num_rows}\n"
            f"Columnas: {table.num_columns}\n"
            f"Schema: {table.schema}"
        )

    tk.Button(
        frame,
        text="Probar pyarrow",
        command=test_pyarrow,
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
