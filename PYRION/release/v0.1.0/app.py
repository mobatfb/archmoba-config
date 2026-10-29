import tkinter as tk

APP_NAME = "PYRION"
APP_VERSION = "0.1.0"

class PyrionApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("640x360")
        self.configure(bg="#101218")

        tk.Label(
            self,
            text="PYRION",
            bg="#101218",
            fg="#FFFFFF",
            font=("Segoe UI", 28, "bold"),
        ).pack(expand=True)

if __name__ == "__main__":
    app = PyrionApp()
    app.mainloop()
