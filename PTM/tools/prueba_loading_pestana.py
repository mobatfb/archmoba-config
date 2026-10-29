# ARGUMENTOS: prueba loading pestaña proceso bucle iniciar detener spinner
import threading
import time
import tkinter as tk


def App(parent, app):
    tool_key = app.current_key
    frame = tk.Frame(parent, bg="#FFFFFF")
    frame.columnconfigure(0, weight=1)

    stop_event = threading.Event()
    worker_ref = {"thread": None, "running": False}
    counter_var = tk.StringVar(value="Proceso detenido.")
    status_var = tk.StringVar(value="Pulsa Iniciar proceso para comenzar.")

    tk.Label(
        frame,
        text="Prueba loading en pestaña",
        font=("Segoe UI", 19, "bold"),
        bg="#FFFFFF",
        fg="#101010",
    ).grid(row=0, column=0, pady=(35, 8))

    tk.Label(
        frame,
        text="Ejecuta un bucle en segundo plano para probar el indicador animado de la pestaña.",
        font=("Segoe UI", 10),
        bg="#FFFFFF",
        fg="#666666",
        wraplength=600,
        justify="center",
    ).grid(row=1, column=0, padx=25, pady=(0, 20))

    tk.Label(
        frame,
        textvariable=counter_var,
        font=("Consolas", 16, "bold"),
        bg="#FFFFFF",
        fg="#176684",
    ).grid(row=2, column=0, pady=(5, 8))

    tk.Label(
        frame,
        textvariable=status_var,
        font=("Segoe UI", 9),
        bg="#FFFFFF",
        fg="#666666",
    ).grid(row=3, column=0, pady=(0, 18))

    buttons = tk.Frame(frame, bg="#FFFFFF")
    buttons.grid(row=4, column=0, pady=8)

    def set_running_ui(running):
        start_button.configure(state=("disabled" if running else "normal"))
        stop_button.configure(state=("normal" if running else "disabled"))

    def finish_process(message="Proceso detenido."):
        worker_ref["running"] = False
        app.set_tool_processing(False, key=tool_key)
        counter_var.set(message)
        status_var.set("El indicador de carga de la pestaña debe haberse detenido.")
        set_running_ui(False)

    def start_process():
        if worker_ref["running"]:
            return

        stop_event.clear()
        worker_ref["running"] = True
        set_running_ui(True)
        app.set_tool_processing(True, key=tool_key)
        status_var.set("Proceso activo. El icono de la pestaña debe estar animándose.")

        def worker():
            counter = 0
            while not stop_event.is_set():
                counter += 1
                try:
                    frame.after(
                        0,
                        lambda n=counter: counter_var.set(
                            f"Bucle ejecutándose... ciclo {n}"
                        ),
                    )
                except tk.TclError:
                    break
                time.sleep(0.35)

            try:
                frame.after(0, finish_process)
            except tk.TclError:
                pass

        thread = threading.Thread(target=worker, daemon=True)
        worker_ref["thread"] = thread
        thread.start()

    def stop_process():
        if not worker_ref["running"]:
            return
        status_var.set("Deteniendo proceso...")
        stop_button.configure(state="disabled")
        stop_event.set()

    start_button = tk.Button(
        buttons,
        text="Iniciar proceso",
        command=start_process,
        bg="#176684",
        fg="#FFFFFF",
        activebackground="#0F536E",
        activeforeground="#FFFFFF",
        relief="flat",
        padx=18,
        pady=8,
        cursor="hand2",
    )
    start_button.pack(side="left", padx=6)

    stop_button = tk.Button(
        buttons,
        text="Detener proceso",
        command=stop_process,
        bg="#C62828",
        fg="#FFFFFF",
        activebackground="#A91F1F",
        activeforeground="#FFFFFF",
        relief="flat",
        padx=18,
        pady=8,
        cursor="hand2",
        state="disabled",
    )
    stop_button.pack(side="left", padx=6)

    class ToolLifecycle:
        def on_close(self):
            stop_event.set()

    lifecycle = ToolLifecycle()
    frame.on_close = lifecycle.on_close
    return frame
