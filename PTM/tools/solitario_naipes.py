# -*- coding: utf-8 -*-
# ARGUMENTOS: solitario naipes cartas baraja klondike juego archmoba poker patience
"""ARCHMOBA SOLITARIO | Klondike clasico, motor propio y sin paquetes pip.

Se integra como una pestaña de PTM mediante App(parent, app=None).
Tambien se ejecuta directamente: python solitario_naipes.py
Reglas: 7 columnas, 4 bases de As a Rey, colores alternados en el tablero,
Rey en columnas vacias. Se puede arrastrar o seleccionar y hacer clic.
El guardado es local en ~/.archmoba/solitario_klondike.json.
"""
from __future__ import annotations

import copy
import json
import random
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

TOOL_NAME = "ARCHMOBA SOLITARIO"
TOOL_VERSION = "1.0.0"
TOOL_DESCRIPTION = "Solitario Klondike de 52 naipes, con arrastre, pistas, deshacer y guardado."

SUITS = ("♠", "♥", "♣", "♦")
SUIT_NAMES = ("Picas", "Corazones", "Treboles", "Diamantes")
RANKS = ("", "A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
SAVE_FILE = Path.home() / ".archmoba" / "solitario_klondike.json"

BG = "#071b18"
FELT = "#0c4b3b"
FELT_LIGHT = "#14624e"
GOLD = "#f0c879"
INK = "#152b34"
RED = "#ce314c"
WHITE = "#fffdf6"
MUTED = "#b3c8bf"


def suit_color(card):
    return RED if card[1] in (1, 3) else INK


def card_label(card):
    return f"{RANKS[card[0]]}{SUITS[card[1]]}"


class SolitaireGame:
    """Logica independiente de Tkinter: permite pruebas de reglas sin pantalla."""

    def __init__(self, draw_count=1, seed=None):
        self.history = []
        self.new_game(draw_count, seed)

    def new_game(self, draw_count=1, seed=None):
        self.draw_count = 3 if draw_count == 3 else 1
        cards = [(rank, suit) for suit in range(4) for rank in range(1, 14)]
        random.Random(seed).shuffle(cards)
        self.tableau = [[] for _ in range(7)]
        for column in range(7):
            for index in range(column + 1):
                self.tableau[column].append((cards.pop(), index == column))
        self.stock = cards
        self.waste = []
        self.foundations = [[] for _ in range(4)]
        self.moves = 0
        self.score = 0
        self.passes = 0
        self.elapsed = 0
        self.history = []
        self.won = False

    def _state(self):
        return {
            "stock": copy.deepcopy(self.stock),
            "waste": copy.deepcopy(self.waste),
            "tableau": copy.deepcopy(self.tableau),
            "foundations": copy.deepcopy(self.foundations),
            "moves": self.moves,
            "score": self.score,
            "passes": self.passes,
            "elapsed": self.elapsed,
            "won": self.won,
            "draw_count": self.draw_count,
        }

    def _remember(self):
        self.history.append(self._state())
        if len(self.history) > 150:
            self.history.pop(0)

    def undo(self):
        if not self.history:
            return False
        state = self.history.pop()
        for key, value in state.items():
            setattr(self, key, value)
        return True

    def draw_stock(self):
        if self.stock:
            self._remember()
            for _ in range(min(self.draw_count, len(self.stock))):
                self.waste.append(self.stock.pop())
        elif self.waste:
            self._remember()
            self.stock = list(reversed(self.waste))
            self.waste.clear()
            self.passes += 1
        else:
            return False
        self.moves += 1
        return True

    def _moving_cards(self, source, index=None):
        zone, col = source
        if zone == "waste":
            return [self.waste[-1]] if self.waste else []
        if zone == "foundation":
            return [self.foundations[col][-1]] if self.foundations[col] else []
        if zone == "tableau":
            pile = self.tableau[col]
            if index is None:
                index = len(pile) - 1
            if not (0 <= index < len(pile)) or not pile[index][1]:
                return []
            stack = pile[index:]
            if not all(face for _, face in stack):
                return []
            cards = [card for card, _ in stack]
            for upper, lower in zip(cards, cards[1:]):
                if upper[0] != lower[0] + 1 or suit_color(upper) == suit_color(lower):
                    return []
            return cards
        return []

    def can_move(self, source, index, target):
        src_zone, src_col = source
        dst_zone, dst_col = target
        if source == target or src_zone not in ("waste", "tableau", "foundation"):
            return False
        if dst_zone not in ("tableau", "foundation"):
            return False
        if not (0 <= dst_col < (7 if dst_zone == "tableau" else 4)):
            return False
        cards = self._moving_cards(source, index)
        if not cards:
            return False
        first = cards[0]
        if dst_zone == "foundation":
            if len(cards) != 1:
                return False
            pile = self.foundations[dst_col]
            return (not pile and first[0] == 1) or bool(
                pile and pile[-1][1] == first[1] and pile[-1][0] + 1 == first[0]
            )
        pile = self.tableau[dst_col]
        if not pile:
            return first[0] == 13
        top, exposed = pile[-1]
        return exposed and top[0] == first[0] + 1 and suit_color(top) != suit_color(first)

    def move(self, source, index, target):
        if not self.can_move(source, index, target):
            return False
        self._remember()
        src_zone, src_col = source
        dst_zone, dst_col = target
        cards = self._moving_cards(source, index)
        if src_zone == "waste":
            self.waste.pop()
        elif src_zone == "foundation":
            self.foundations[src_col].pop()
        else:
            del self.tableau[src_col][len(self.tableau[src_col]) - len(cards):]
            if self.tableau[src_col] and not self.tableau[src_col][-1][1]:
                card, _ = self.tableau[src_col][-1]
                self.tableau[src_col][-1] = (card, True)
                self.score += 5
        if dst_zone == "foundation":
            self.foundations[dst_col].append(cards[0])
            self.score += 10
        else:
            self.tableau[dst_col].extend((card, True) for card in cards)
            if src_zone == "waste":
                self.score += 5
        self.moves += 1
        self.won = all(len(pile) == 13 for pile in self.foundations)
        return True

    def foundation_target(self, card):
        for i in range(4):
            pile = self.foundations[i]
            if (not pile and card[0] == 1) or (
                pile and pile[-1][1] == card[1] and pile[-1][0] + 1 == card[0]
            ):
                return ("foundation", i)
        return None

    def auto_foundation(self, source=None, index=None):
        candidates = []
        if source is not None:
            candidates.append((source, index))
        else:
            if self.waste:
                candidates.append((("waste", 0), None))
            for i, pile in enumerate(self.tableau):
                if pile and pile[-1][1]:
                    candidates.append((("tableau", i), len(pile) - 1))
        for src, idx in candidates:
            cards = self._moving_cards(src, idx)
            if len(cards) != 1:
                continue
            target = self.foundation_target(cards[0])
            if target and self.move(src, idx, target):
                return True
        return False

    def hint(self):
        if self.waste:
            src = ("waste", 0)
            dst = self.foundation_target(self.waste[-1])
            if dst:
                return src, None, dst
        for col, pile in enumerate(self.tableau):
            if pile and pile[-1][1]:
                src = ("tableau", col)
                dst = self.foundation_target(pile[-1][0])
                if dst:
                    return src, len(pile) - 1, dst
        # Priorizar descubrir cartas tapadas, sin proponer un movimiento inutil.
        for col, pile in enumerate(self.tableau):
            for idx, (card, up) in enumerate(pile):
                if not up:
                    continue
                if idx == 0 and card[0] == 13:
                    continue
                for target in range(7):
                    if self.can_move(("tableau", col), idx, ("tableau", target)):
                        if idx > 0 and not pile[idx - 1][1]:
                            return ("tableau", col), idx, ("tableau", target)
        if self.waste:
            for target in range(7):
                if self.can_move(("waste", 0), None, ("tableau", target)):
                    return ("waste", 0), None, ("tableau", target)
        for col, pile in enumerate(self.tableau):
            for idx, (_, up) in enumerate(pile):
                if not up:
                    continue
                for target in range(7):
                    if self.can_move(("tableau", col), idx, ("tableau", target)):
                        return ("tableau", col), idx, ("tableau", target)
        if self.stock or self.waste:
            return ("stock", 0), None, None
        return None

    def serialize(self):
        return {"version": 1, "state": self._state()}

    @classmethod
    def deserialize(cls, payload):
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise ValueError("Partida incompatible")
        state = payload["state"]
        game = cls(state.get("draw_count", 1))
        for name in ("stock", "waste", "foundations"):
            setattr(game, name, [[tuple(c) for c in p] for p in state[name]]
                    if name == "foundations" else [tuple(c) for c in state[name]])
        game.tableau = [[(tuple(card), bool(up)) for card, up in pile]
                        for pile in state["tableau"]]
        for name in ("moves", "score", "passes", "elapsed", "won"):
            setattr(game, name, state[name])
        game.draw_count = 3 if state.get("draw_count") == 3 else 1
        if len(game.tableau) != 7 or len(game.foundations) != 4:
            raise ValueError("Estructura de partida incorrecta")
        all_cards = (game.stock + game.waste +
                     [card for pile in game.foundations for card in pile] +
                     [card for pile in game.tableau for card, _ in pile])
        if (len(all_cards) != 52 or len(set(all_cards)) != 52 or
                set(all_cards) != {(r, s) for r in range(1, 14) for s in range(4)}):
            raise ValueError("Baraja guardada no valida")
        game.history = []
        return game


class SolitaireTool(tk.Frame):
    """Interfaz Canvas adaptable, integrada en PTM y sin ventanas adicionales."""

    def __init__(self, parent, app=None):
        super().__init__(parent, bg=BG)
        self.app = app
        self.game = self._load_game() or SolitaireGame()
        self._selected = None
        self._press = None
        self._drag = None
        self._hitboxes = []
        self._positions = {}
        self._hint = None
        self._hint_until = 0
        self._alive = True
        self._won_shown = self.game.won
        self._last_clock = time.monotonic()
        self._last_save = time.monotonic()
        self._layout()
        self.after(60, self._render)
        self.after(1000, self._tick)

    def _layout(self):
        header = tk.Frame(self, bg=BG, padx=17, pady=12)
        header.pack(fill="x")
        title_row = tk.Frame(header, bg=BG)
        title_row.pack(fill="x")
        tk.Label(title_row, text="♠  ARCHMOBA SOLITARIO", fg=WHITE, bg=BG,
                 font=("Segoe UI", 17, "bold")).pack(side="left")
        tk.Label(title_row, text="KLONDIKE  ·  v" + TOOL_VERSION,
                 fg=GOLD, bg=BG, font=("Segoe UI", 9, "bold")).pack(side="left", padx=16)
        self.info_var = tk.StringVar()
        tk.Label(title_row, textvariable=self.info_var, fg=MUTED, bg=BG,
                 font=("Segoe UI", 10)).pack(side="right")
        buttons = tk.Frame(header, bg=BG)
        buttons.pack(fill="x", pady=(11, 0))
        self._button(buttons, "↻  Nueva partida", self.new_game, accent=True)
        self._button(buttons, "↶  Deshacer", self.undo)
        self._button(buttons, "✦  Pista", self.hint)
        self._button(buttons, "⇧  Auto a bases", self.auto_foundation)
        self.draw_var = tk.StringVar(value="Robar 3" if self.game.draw_count == 3 else "Robar 1")
        self._button(buttons, "🂠  Cambiar robo", self.toggle_draw)
        self.status_var = tk.StringVar(value="Arrastra las cartas o selecciónalas y pulsa el destino.")
        status = tk.Frame(self, bg="#0b3028", padx=17, pady=7)
        status.pack(fill="x", side="bottom")
        tk.Label(status, textvariable=self.status_var, bg="#0b3028", fg="#d4e9db",
                 font=("Segoe UI", 10), anchor="w").pack(fill="x")
        board = tk.Frame(self, bg=FELT)
        board.pack(fill="both", expand=True, padx=10, pady=(0, 9))
        self.canvas = tk.Canvas(board, bg=FELT, bd=0, highlightthickness=0,
                                relief="flat", cursor="hand2")
        scrollbar = tk.Scrollbar(board, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._render())
        self.canvas.bind("<ButtonPress-1>", self._mouse_down)
        self.canvas.bind("<B1-Motion>", self._mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._mouse_up)
        self.canvas.bind("<Double-Button-1>", self._double_click)
        self.canvas.bind("<MouseWheel>", self._mouse_wheel)
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-2, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(2, "units"))
        self.canvas.bind("<Control-z>", self._shortcut_undo)
        self.canvas.bind("<Control-n>", self._shortcut_new)
        self.canvas.bind("<F1>", self._shortcut_hint)

    def _button(self, parent, label, command, accent=False):
        tk.Button(parent, text=label, command=command,
                  bg=GOLD if accent else "#1b443a", fg=INK if accent else WHITE,
                  activebackground="#e4b861" if accent else "#286452",
                  activeforeground=INK if accent else WHITE,
                  relief="flat", bd=0, padx=13, pady=7,
                  font=("Segoe UI", 9, "bold"), cursor="hand2").pack(side="left", padx=(0, 7))

    def _shortcut_undo(self, event=None):
        if self.winfo_ismapped():
            self.undo()

    def _shortcut_new(self, event=None):
        if self.winfo_ismapped():
            self.new_game()

    def _shortcut_hint(self, event=None):
        if self.winfo_ismapped():
            self.hint()

    def _mouse_wheel(self, event):
        self.canvas.yview_scroll(-1 * (1 if event.delta > 0 else -1) * 3, "units")

    def _coords(self, event):
        return self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

    def _scale(self):
        width = max(540, self.canvas.winfo_width())
        return max(0.62, min(1.27, (width - 62) / 826))

    def _card_size(self):
        s = self._scale()
        return 91 * s, 125 * s, s

    def _round_rect(self, x, y, w, h, radius, fill, outline="", thick=1, tag=None):
        # Esquinas redondeadas sin Pillow, mediante un poligono suave de Canvas.
        r = min(radius, w / 3, h / 3)
        pts = [x+r,y, x+w-r,y, x+w,y, x+w,y+r,
               x+w,y+h-r, x+w,y+h, x+w-r,y+h,
               x+r,y+h, x,y+h, x,y+h-r,
               x,y+r, x,y, x+r,y]
        return self.canvas.create_polygon(pts, smooth=True, splinesteps=16,
                                          fill=fill, outline=outline, width=thick,
                                          tags=tag)

    def _draw_slot(self, x, y, w, h, label, highlight=False):
        self._round_rect(x, y, w, h, 9, "#0a3a2f", GOLD if highlight else "#347864",
                         2 if highlight else 1)
        self.canvas.create_text(x + w/2, y + h/2, text=label,
                                fill="#8db6a7", font=("Segoe UI", max(11, int(20*self._scale()))))

    def _draw_card(self, card, x, y, w, h, face_up=True, glow=False, ghost=False):
        s = self._scale()
        if not ghost:
            self._round_rect(x + 2*s, y + 3*s, w, h, 8*s, "#06291f")
        if not face_up:
            self._round_rect(x, y, w, h, 8*s, "#153c67", GOLD if glow else "#91a5c2", 2)
            self._round_rect(x+6*s, y+6*s, w-12*s, h-12*s, 6*s,
                             "#254c78", "#d7b978", 1)
            for i in range(4):
                xx = x + w * (0.22 + i * 0.19)
                self.canvas.create_line(xx, y+12*s, xx, y+h-12*s,
                                        fill="#4e7298", width=max(1, int(s)))
            self.canvas.create_text(x+w/2, y+h/2, text="✦",
                                    font=("Segoe UI Symbol", max(15, int(27*s))), fill=GOLD)
            return
        self._round_rect(x, y, w, h, 8*s, WHITE, GOLD if glow else "#dae3df",
                         2 if glow else 1)
        fg = suit_color(card)
        rank = RANKS[card[0]]
        symbol = SUITS[card[1]]
        self.canvas.create_text(x+11*s, y+12*s, text=rank, anchor="nw",
                                fill=fg, font=("DejaVu Sans", max(9, int(16*s)), "bold"))
        self.canvas.create_text(x+11*s, y+31*s, text=symbol, anchor="nw",
                                fill=fg, font=("DejaVu Sans", max(9, int(16*s))))
        self.canvas.create_text(x+w/2, y+h/2+7*s, text=symbol,
                                fill=fg, font=("DejaVu Sans", max(15, int(42*s))))
        self.canvas.create_text(x+w-9*s, y+h-10*s, text=rank+symbol, anchor="se",
                                fill=fg, font=("DejaVu Sans", max(9, int(13*s)), "bold"))

    def _hit(self, rect, zone, col, idx=None):
        self._hitboxes.append((rect, zone, col, idx))

    def _render(self):
        if not self._alive or not self.canvas.winfo_exists():
            return
        c = self.canvas
        c.delete("all")
        self._hitboxes = []
        self._positions = {}
        w, h, s = self._card_size()
        gap = 26*s
        total = 7*w + 6*gap
        width = max(c.winfo_width(), int(total + 32*s))
        start = max(16*s, (width - total)/2)
        top_y = 54*s
        tab_y = 253*s
        down_step, up_step = 24*s, 34*s
        self._positions["geometry"] = (start, w, h, gap, top_y, tab_y, down_step, up_step)
        c.create_rectangle(0, 0, width, max(c.winfo_height(), 900*s), fill=FELT, outline="")
        c.create_text(start, 18*s, anchor="w", text="MAZO Y DESCARTE",
                      fill="#b5d8c9", font=("Segoe UI", max(9,int(10*s)), "bold"))
        c.create_text(start + 3*(w+gap), 18*s, anchor="w", text="BASES  ·  A → K",
                      fill="#b5d8c9", font=("Segoe UI", max(9,int(10*s)), "bold"))
        # Mazo: un clic roba 1 o 3 naipes; al agotarse se recicla el descarte.
        x = start
        if self.game.stock:
            self._draw_card(None, x, top_y, w, h, face_up=False)
            c.create_text(x+w/2, top_y+h+17*s, text=f"{len(self.game.stock)} en mazo",
                          fill=MUTED, font=("Segoe UI", max(8,int(10*s))))
        else:
            self._draw_slot(x, top_y, w, h, "↻" if self.game.waste else "—")
        self._hit((x,top_y,x+w,top_y+h), "stock", 0)
        # Descarte: se muestran tres cartas escalonadas en modo robo 3.
        waste = self.game.waste
        x = start + (w+gap)
        self._draw_slot(x, top_y, w, h, "DESC.")
        if waste:
            preview = waste[-min(3,len(waste)):] if self.game.draw_count == 3 else waste[-1:]
            for k, card in enumerate(preview):
                offset = k * (12*s) if len(preview) > 1 else 0
                self._draw_card(card, x+offset, top_y, w, h)
            self._hit((x,top_y,x+w+24*s,top_y+h), "waste", 0)
        # Cuatro bases: no se obliga a un palo fijo; se asigna con el primer As.
        for i in range(4):
            x = start + (i+3)*(w+gap)
            pile = self.game.foundations[i]
            target = ("foundation", i)
            self._positions[target] = (x,top_y)
            glow = self._hint is not None and self._hint[2] == target
            self._draw_slot(x, top_y, w, h, "A" if not pile else "", glow)
            if pile:
                self._draw_card(pile[-1], x, top_y, w, h, glow=glow)
            self._hit((x,top_y,x+w,top_y+h), "foundation", i)
        c.create_line(start, 218*s, start+total, 218*s, fill="#44816d", width=2)
        c.create_text(start, 231*s, anchor="w", text="TABLERO  ·  alterna rojo / negro  ·  Rey en columna vacía",
                      fill="#b5d8c9", font=("Segoe UI", max(9,int(10*s))))
        max_bottom = tab_y+h
        for col, pile in enumerate(self.game.tableau):
            x = start + col*(w+gap)
            target = ("tableau", col)
            self._positions[target] = (x,tab_y)
            glow_target = self._hint is not None and self._hint[2] == target
            if not pile:
                self._draw_slot(x, tab_y, w, h, "K", glow_target)
                self._hit((x,tab_y,x+w,tab_y+h), "tableau", col, None)
            y = tab_y
            for idx, (card, up) in enumerate(pile):
                selected = self._selected == (target, idx)
                hinted = self._hint is not None and self._hint[:2] == (target, idx)
                self._draw_card(card, x, y, w, h, up, selected or hinted or (glow_target and idx==len(pile)-1))
                self._hit((x,y,x+w,y+h), "tableau", col, idx)
                max_bottom = max(max_bottom, y+h)
                if idx < len(pile)-1:
                    y += up_step if up else down_step
        if self._drag:
            source, idx, x, y, dx, dy = self._drag
            cards = self.game._moving_cards(source, idx)
            for n, card in enumerate(cards):
                self._draw_card(card, x-dx, y-dy+n*up_step, w, h, True, True, True)
        if self.game.won:
            y = max_bottom + 45*s
            c.create_text(start+total/2, y, text="¡VICTORIA!  ♠ ♥ ♣ ♦",
                          fill=GOLD, font=("Segoe UI", max(16,int(26*s)), "bold"))
            max_bottom += 90*s
        c.configure(scrollregion=(0,0,width,max(c.winfo_height(),max_bottom+35*s)))
        self.info_var.set(f"Puntos  {self.game.score}     Movimientos  {self.game.moves}     "
                          f"Tiempo  {self.game.elapsed//60:02d}:{self.game.elapsed%60:02d}     "
                          f"Robo  {self.game.draw_count}")

    def _find(self, x, y):
        for (x1,y1,x2,y2), zone, col, idx in reversed(self._hitboxes):
            if x1 <= x <= x2 and y1 <= y <= y2:
                return zone, col, idx
        return None, None, None

    def _mouse_down(self, event):
        self.canvas.focus_set()
        x, y = self._coords(event)
        zone, col, card_idx = self._find(x, y)
        self._press = (zone, col, card_idx, x, y)
        self._drag = None

    def _mouse_drag(self, event):
        if not self._press:
            return
        zone, col, card_idx, px, py = self._press
        x, y = self._coords(event)
        if abs(x-px) + abs(y-py) < 9 and self._drag is None:
            return
        if zone not in ("tableau", "waste", "foundation"):
            return
        source = (zone, col)
        index = card_idx if zone == "tableau" else None
        if not self.game._moving_cards(source, index):
            return
        if self._drag is None:
            pos = self._card_origin(source, index)
            if pos is None:
                return
            dx, dy = px-pos[0], py-pos[1]
        else:
            dx, dy = self._drag[4:]
        self._drag = (source, index, x, y, dx, dy)
        self._render()

    def _source_index(self, zone, col, y):
        if zone != "tableau":
            return None
        pile = self.game.tableau[col]
        if not pile:
            return None
        _,_,_,_,_,tab_y,down,up = self._positions["geometry"]
        yy = tab_y
        for i, (_, face_up) in enumerate(pile):
            end = yy + (up if face_up else down) if i < len(pile)-1 else yy + self._card_size()[1]
            if yy <= y < end:
                return i
            yy += up if face_up else down
        return len(pile)-1

    def _card_origin(self, source, index):
        zone, col = source
        start,w,h,gap,top_y,tab_y,down,up = self._positions["geometry"]
        if zone == "waste":
            x = start + w + gap
            visible = min(3,len(self.game.waste)) if self.game.draw_count==3 else 1
            return x+(visible-1)*12*self._scale(), top_y
        if zone == "foundation":
            return self._positions[source]
        if zone == "tableau":
            x, y = self._positions[source]
            for card, exposed in self.game.tableau[col][:index]:
                y += up if exposed else down
            return x,y
        return None

    def _target_at(self, x, y):
        start,w,h,gap,top_y,tab_y,down,up = self._positions["geometry"]
        for i in range(4):
            xx = start + (i+3)*(w+gap)
            if xx-8 <= x <= xx+w+8 and top_y-12 <= y <= top_y+h+25:
                return ("foundation", i)
        for i in range(7):
            xx = start + i*(w+gap)
            if xx-8 <= x <= xx+w+8 and y >= tab_y-12:
                return ("tableau", i)
        return None

    def _mouse_up(self, event):
        if not self._press:
            return
        x, y = self._coords(event)
        zone, col, card_idx, px, py = self._press
        self._press = None
        if self._drag:
            src, idx, _,_,_,_ = self._drag
            self._drag = None
            target = self._target_at(x,y)
            if target and self.game.move(src, idx, target):
                self._after_move("Carta movida.")
            else:
                self.status_var.set("Movimiento no permitido: revisa valor, palo y color.")
            self._render()
            return
        hit_zone, hit_col, hit_idx = self._find(x, y)
        if hit_zone is None:
            return
        if hit_zone == "stock":
            if self.game.draw_stock():
                self._after_move("Naipes robados." if self.game.stock else "Mazo agotado; pulsa para reciclar.")
            return
        target = (hit_zone, hit_col)
        if self._selected and target != self._selected[0] and hit_zone in ("foundation", "tableau"):
            source, index = self._selected
            if self.game.move(source, index, target):
                self._selected = None
                self._after_move("Movimiento realizado.")
                return
        if hit_zone in ("tableau", "waste", "foundation"):
            index = hit_idx if hit_zone == "tableau" else None
            if self.game._moving_cards(target, index):
                self._selected = (target, index)
                cards = self.game._moving_cards(target, index)
                self.status_var.set(f"Seleccionado {card_label(cards[0])}. Pulsa el destino o arrastra.")
            else:
                self._selected = None
        self._render()

    def _double_click(self, event):
        x,y = self._coords(event)
        zone, col, card_idx = self._find(x,y)
        if zone == "stock":
            if self.game.draw_stock():
                self._after_move("Naipes robados.")
            return
        if zone not in ("tableau", "waste"):
            return
        src = (zone,col)
        index = card_idx if zone == "tableau" else None
        if self.game.auto_foundation(src,index):
            self._selected = None
            self._after_move("Carta enviada a su base.")

    def _after_move(self, message):
        self._hint = None
        self._selected = None
        self.status_var.set(message)
        self._save_game()
        self._render()
        if self.game.won and not self._won_shown:
            self._won_shown = True
            self.after(100, lambda: messagebox.showinfo(
                "¡Ganaste!", f"¡Completaste el solitario!\n\nPuntos: {self.game.score}\n"
                f"Movimientos: {self.game.moves}", parent=self))

    def new_game(self):
        if self.game.moves > 0 and not self.game.won:
            if not messagebox.askyesno("Nueva partida", "¿Empezar una nueva partida?", parent=self):
                return
        draw = self.game.draw_count
        self.game.new_game(draw)
        self._selected = None
        self._won_shown = False
        self._last_clock = time.monotonic()
        self.status_var.set("Nueva partida. Coloca los As en las cuatro bases.")
        self._save_game()
        self._render()

    def undo(self):
        if self.game.undo():
            self._selected = None
            self._won_shown = self.game.won
            self.status_var.set("Último movimiento deshecho.")
            self._save_game()
            self._render()
        else:
            self.status_var.set("No hay movimientos para deshacer.")

    def hint(self):
        suggestion = self.game.hint()
        if suggestion is None:
            self.status_var.set("No se encontraron movimientos. Puedes iniciar otra partida.")
            return
        src, idx, dst = suggestion
        if src[0] == "stock":
            self.status_var.set("Pista: pulsa el mazo para descubrir más cartas.")
            return
        cards = self.game._moving_cards(src,idx)
        self._hint = (src,idx,dst)
        self.status_var.set(f"Pista: mueve {card_label(cards[0])} a "
                            f"{'una base' if dst[0]=='foundation' else 'la columna '+str(dst[1]+1)}.")
        self._hint_until = time.monotonic() + 3
        self._render()

    def auto_foundation(self):
        count = 0
        while count < 52 and self.game.auto_foundation():
            count += 1
        if count:
            self._after_move(f"{count} carta(s) enviadas a las bases.")
        else:
            self.status_var.set("Por ahora no hay cartas listas para subir a las bases.")

    def toggle_draw(self):
        new_count = 3 if self.game.draw_count == 1 else 1
        if self.game.moves and not messagebox.askyesno(
                "Cambiar modo", "Cambiar el robo iniciará una nueva partida. ¿Continuar?", parent=self):
            return
        self.game.new_game(new_count)
        self._selected = None
        self._won_shown = False
        self.status_var.set(f"Modo cambiado: robar {new_count} carta(s).")
        self._save_game()
        self._render()

    def _tick(self):
        if not self._alive:
            return
        now = time.monotonic()
        if not self.game.won and self.game.moves:
            self.game.elapsed += min(5, max(0, int(now - self._last_clock)))
        self._last_clock = now
        if self._hint and now > self._hint_until:
            self._hint = None
            self._render()
        if now - self._last_save >= 15:
            self._save_game()
        self.info_var.set(f"Puntos  {self.game.score}     Movimientos  {self.game.moves}     "
                          f"Tiempo  {self.game.elapsed//60:02d}:{self.game.elapsed%60:02d}     "
                          f"Robo  {self.game.draw_count}")
        self.after(1000, self._tick)

    def _save_game(self):
        try:
            SAVE_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = SAVE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.game.serialize(), ensure_ascii=False), encoding="utf-8")
            tmp.replace(SAVE_FILE)
            self._last_save = time.monotonic()
        except OSError:
            pass  # El juego funciona aunque el directorio no sea escribible.

    @staticmethod
    def _load_game():
        try:
            return SolitaireGame.deserialize(json.loads(SAVE_FILE.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, TypeError, IndexError):
            return None

    def on_show(self):
        self._last_clock = time.monotonic()
        self._render()

    def on_hide(self):
        self._save_game()
        self._last_clock = time.monotonic()

    def on_close(self):
        self._alive = False
        self._save_game()


App = SolitaireTool


def main():
    root = tk.Tk()
    root.title(f"{TOOL_NAME} v{TOOL_VERSION}")
    root.geometry("1120x810")
    root.minsize(700, 480)
    game = App(root)
    game.pack(fill="both", expand=True)

    def close():
        game.on_close()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    root.mainloop()


if __name__ == "__main__":
    main()
