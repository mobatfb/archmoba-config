# ARGUMENTOS: pdf word docx convertir convertidor documentos oficina
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

from pdf2docx import Converter


def create_tool(parent, app):
    frame = tk.Frame(parent, bg="#FFFFFF")
    frame.columnconfigure(0, weight=1)

    source_var = tk.StringVar()
    target_var = tk.StringVar()
    status_var = tk.StringVar(value="Selecciona un archivo PDF para comenzar.")

    tk.Label(
        frame,
        text="Convertidor PDF a Word",
        font=("Segoe UI", 19, "bold"),
        bg="#FFFFFF",
        fg="#101010",
    ).grid(row=0, column=0, pady=(30, 6))

    tk.Label(
        frame,
        text="Convierte documentos PDF a archivos Word (.docx).",
        font=("Segoe UI", 10),
        bg="#FFFFFF",
        fg="#666666",
    ).grid(row=1, column=0, pady=(0, 22))

    form = tk.Frame(frame, bg="#FFFFFF")
    form.grid(row=2, column=0, padx=28, sticky="ew")
    form.columnconfigure(0, weight=1)

    source_entry = tk.Entry(
        form, textvariable=source_var, font=("Segoe UI", 10),
        relief="solid", bd=1
    )
    source_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=5)

    target_entry = tk.Entry(
        form, textvariable=target_var, font=("Segoe UI", 10),
        relief="solid", bd=1
    )
    target_entry.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=5)

    def select_pdf():
        path = filedialog.askopenfilename(
            title="Seleccionar PDF",
            filetypes=[("Archivos PDF", "*.pdf")],
        )
        if not path:
            return
        source_var.set(path)
        target_var.set(str(Path(path).with_suffix(".docx")))
        status_var.set("PDF seleccionado. Listo para convertir.")

    def select_target():
        initial = Path(source_var.get()).stem if source_var.get() else "documento"
        path = filedialog.asksaveasfilename(
            title="Guardar documento Word",
            defaultextension=".docx",
            initialfile=initial + ".docx",
            filetypes=[("Documento Word", "*.docx")],
        )
        if path:
            target_var.set(path)

    tk.Button(
        form, text="Seleccionar PDF", command=select_pdf,
        bg="#176684", fg="#FFFFFF", relief="flat", padx=12, pady=6,
        cursor="hand2"
    ).grid(row=0, column=1, pady=5)

    tk.Button(
        form, text="Guardar como...", command=select_target,
        bg="#176684", fg="#FFFFFF", relief="flat", padx=12, pady=6,
        cursor="hand2"
    ).grid(row=1, column=1, pady=5)

    status = tk.Label(
        frame, textvariable=status_var, font=("Segoe UI", 9),
        bg="#FFFFFF", fg="#666666", wraplength=600, justify="center"
    )
    status.grid(row=3, column=0, padx=25, pady=(18, 8))

    convert_button = tk.Button(
        frame, text="Convertir a Word",
        bg="#C62828", fg="#FFFFFF", activebackground="#A91F1F",
        activeforeground="#FFFFFF", relief="flat", padx=22, pady=9,
        cursor="hand2"
    )
    convert_button.grid(row=4, column=0, pady=8)

    def set_busy(busy):
        convert_button.configure(
            state=("disabled" if busy else "normal"),
            cursor=("arrow" if busy else "hand2"),
        )

    def finish_success(output):
        status_var.set(f"Conversión completada: {output}")
        set_busy(False)
        app.set_tool_processing(False)
        app.show_dialog(
            "Convertidor PDF a Word",
            "El documento Word se generó correctamente.",
            kind="success",
        )

    def finish_error(exc):
        status_var.set("No se pudo completar la conversión.")
        set_busy(False)
        app.set_tool_processing(False)
        app.show_dialog(
            "Convertidor PDF a Word",
            f"Error durante la conversión:\n\n{exc}",
            kind="error",
        )

    def convert():
        source = source_var.get().strip()
        target = target_var.get().strip()

        if not source or not Path(source).is_file():
            app.show_dialog(
                "Convertidor PDF a Word",
                "Selecciona un archivo PDF válido.",
                kind="warning",
            )
            return
        if not target:
            target = str(Path(source).with_suffix(".docx"))
            target_var.set(target)

        set_busy(True)
        app.set_tool_processing(True)
        status_var.set("Convirtiendo PDF a Word...")

        def worker():
            converter = None
            try:
                converter = Converter(source)
                converter.convert(target)
                converter.close()
                converter = None
                frame.after(0, lambda: finish_success(target))
            except Exception as exc:
                if converter is not None:
                    try:
                        converter.close()
                    except Exception:
                        pass
                frame.after(0, lambda e=exc: finish_error(e))

        threading.Thread(target=worker, daemon=True).start()

    convert_button.configure(command=convert)
    return frame
