# HERRAMIENTA DE PRUEBA PTM
# "opencv-python" NO se declara en guide.csv a propósito.
# PTM debe inferirlo automáticamente desde: import cv2
import cv2
import tkinter as tk


def App(parent, app):
    frame = tk.Frame(parent, bg="#FFFFFF")

    tk.Label(
        frame,
        text="Prueba de dependencia pesada: OpenCV",
        font=("Segoe UI", 18, "bold"),
        bg="#FFFFFF",
        fg="#101010",
    ).pack(pady=(35, 8))

    tk.Label(
        frame,
        text="PTM debe detectar cv2 e instalar automáticamente opencv-python.",
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
        justify="center",
    ).pack(padx=25, pady=12)

    def test_opencv():
        image = cv2.UMat(120, 200, cv2.CV_8UC3)
        result_var.set(
            f"OpenCV {cv2.__version__} funcionando\n\n"
            "Matriz de prueba creada correctamente:\n"
            "200 x 120 píxeles · 3 canales"
        )

    tk.Button(
        frame,
        text="Probar OpenCV",
        command=test_opencv,
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
