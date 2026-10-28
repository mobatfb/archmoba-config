# -*- coding: utf-8 -*-
"""ENTER - Infinite Dungeon | prototipo independiente, sin servidor ni BD.

Ejecucion: python ENTER_Infinite_Dungeon_Pantalla_Completa_20_Menos_Dificil.py
Requisitos: Python 3.10+ y Tkinter (incluido normalmente en Python para Windows).
Controles: empieza en la galeria de personajes; F9 entra/sale del juego.
           F11 activa/desactiva pantalla completa; Esc vuelve a ventana.
           Ctrl+Q cierra el juego.
           Galeria: A/D, flechas o rueda del raton; ESPACIO pausa la camara;
           V cambia la vista frontal/lateral/espalda.
           Juego: WASD/flechas mover, disparo automatico al enemigo mas cercano,
           portal inferior para avanzar; portal superior para retroceder.
           Jefes cada 10 pisos; jefes gigantes en 100, 1000, 10000, 100000, 1000000.
           Cada jefe vencido se recuerda por separado y no reaparece.
           En un piso NUEVO el combate comienza automaticamente al entrar.
           En pisos ya completados, la unica plataforma central sin texto
           permite repetir el combate cuando el jugador la pisa.
           La plataforma de mejoras esta visible si no hay enemigos.
           Pisar la plataforma inferior derecha abre las mejoras en la parte
           superior central: el personaje sigue moviendose, y cuando SALE de
           la plataforma el menu se cierra y guarda SOLO si se compro una mejora.
           Clic para comprar mejoras, sin necesidad de pulsar PLAY.
Al ganar se cura con una animacion verde hasta el 100% y se guarda
la victoria de forma automatica (POST simulado).
Al morir se desintegra durante 2 segundos y recupera el checkpoint
(GET simulado). No se guarda al cambiar de nivel. Al salir de una sala
segura se conserva el descanso ganado, sin confirmar compras pendientes.
Guardado LOCAL JSON junto al script, nunca en Laravel.
Balance: enemigos y jefes -20% HP, ataque y armadura.
Descanso: 10 minutos en salas seguras cargan EXP x2 para la proxima victoria;
          maximo una carga, persistida mediante guardado local atomico.
Aliado: algunas batallas generan un icono holografico aleatorio con el casco
        del PLAYER. Recogerlo invoca un clon con IA propia y fallos visuales.
        El clon solo ataca a enemigos y desaparece al finalizar el combate.
Video: el ancho virtual se adapta al monitor para ocupar toda la pantalla.
"""
from __future__ import annotations
import colorsys
import json
import math
import random
import shutil
import time
import tkinter as tk
import sys
from pathlib import Path

# Tamano virtual de referencia. La anchura se adapta al monitor al iniciar,
# conservando la misma escala en X e Y (sin bandas ni personajes deformados).
BASE_W, BASE_H = 920, 608
W, H = BASE_W, BASE_H
# Arena mas vertical: se invierte la sensacion de ancho/alto.
FIELD = (200, 34, 720, 590)
DOOR_Y = (FIELD[1] + FIELD[3]) / 2
# La mazmorra se recorre DESCENDIENDO: verde abajo = continuar;
# azul arriba = regresar al nivel anterior.
NEXT_PORTAL_X = W / 2
NEXT_PORTAL_Y = FIELD[3] - 33
BACK_PORTAL_X = W / 2
BACK_PORTAL_Y = FIELD[1] + 33
SAVE = Path(__file__).with_name('ENTER_progreso_local.json')
BG = '#051011'
GREEN = '#3dfc8d'
CYAN = '#42e4f5'
AMBER = '#f5c66d'
FONT = 'Consolas'
HEAL_SECONDS = 1.8
TRAP_POSITION = (W / 2, DOOR_Y)
TRAP_RADIUS_X = 34.0
TRAP_RADIUS_Y = 27.0
SUMMON_SECONDS = 0.80
UPGRADE_OPEN_SECONDS = 0.78  # Proyeccion holografica al pisar la plataforma.
UPGRADE_TOP = 76
UPGRADE_CARD_TOP = 151
UPGRADE_CARD_BOTTOM = 246
# Velocidad fisica fija del jugador: la estadistica de SPEED no la aumenta.
PLAYER_MOVE_SPEED = 245.0
# Mantener enemigos en movimiento incluso con mejoras enormes.
MIN_ENEMY_MOVE_SPEED = 28.0
MIN_BOSS_MOVE_SPEED = 46.0
# Un mismo factor para TODO el combate, incluidos los jefes de 1.000.000.
# Se reducen resistencia, armadura y dano infligido por los adversarios 20%.
ENEMY_DIFFICULTY = 0.80
# Un beneficio temporal de EXP por descansar en una sala libre de combate.
REST_CHARGE_SECONDS = 10.0 * 60.0
LOCAL_AUTOSAVE_SECONDS = 10.0 * 60.0
# Una sola oportunidad de encontrar al clon en cada batalla.
CLONE_PICKUP_CHANCE = 0.36
CLONE_BOSS_PICKUP_CHANCE = 0.42


def configure_display(root):
    """Usa el ancho real del monitor en fullscreen sin estirar sprites.

    Las coordenadas del juego se calculan ANTES de construir el escenario.
    W aumenta en monitores 16:9, 16:10 y ultrawide, mientras H permanece
    igual. La arena se ensancha proporcionalmente y los portales, menu y HUD
    se alinean con el nuevo centro. En pantallas estrechas se conserva la
    referencia: el lienzo aun llena toda la ventana al escalar por separado.
    """
    global W, FIELD, DOOR_Y, NEXT_PORTAL_X, NEXT_PORTAL_Y
    global BACK_PORTAL_X, BACK_PORTAL_Y, TRAP_POSITION
    screen_w = max(1, root.winfo_screenwidth())
    screen_h = max(1, root.winfo_screenheight())
    W = max(BASE_W, round(H * screen_w / screen_h))
    # En monitores anchos el terreno tambien aprovecha el ancho, sin
    # modificar la altura ni el tamano de los personajes y objetos.
    width = 520.0 * (W / BASE_W)
    FIELD = ((W-width)/2, 34, (W+width)/2, 590)
    DOOR_Y = (FIELD[1] + FIELD[3]) / 2
    NEXT_PORTAL_X = BACK_PORTAL_X = W / 2
    NEXT_PORTAL_Y = FIELD[3] - 33
    BACK_PORTAL_Y = FIELD[1] + 33
    TRAP_POSITION = (W/2, DOOR_Y)


def enable_windows_dpi_awareness():
    """Evita que Windows escale la ventana como si no conociera su DPI."""
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        if hasattr(user32, 'SetProcessDpiAwarenessContext'):
            if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
                return
        try:
            if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:
                return
        except (AttributeError, OSError):
            pass
        user32.SetProcessDPIAware()
    except (AttributeError, OSError, ValueError):
        pass


def clamp(v, a, b): return max(a, min(b, v))
def distance(a, b, c, d): return math.hypot(a-c, b-d)


class ResponsiveCanvas(tk.Canvas):
    """Proyecta toda la escena sobre el tamano exacto del lienzo.

    En fullscreen, el ancho virtual ya se adapto al monitor; X e Y usan
    esencialmente la misma escala y no hay bandas negras. Si se redimensiona
    libremente una ventana a otra proporcion, tampoco se recorta contenido.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.virtual_width = W
        self.virtual_height = H
        self.view_scale_x = 1.0
        self.view_scale_y = 1.0
        self.view_scale = 1.0
        self.bind('<Configure>', self._resize_virtual_view)

    def _resize_virtual_view(self, event):
        width = max(1, int(event.width))
        height = max(1, int(event.height))
        self.view_scale_x = width / self.virtual_width
        self.view_scale_y = height / self.virtual_height
        self.view_scale = min(self.view_scale_x, self.view_scale_y)

    def to_game(self, x, y):
        # Misma transformacion que el dibujo, para clicks correctos a 4K.
        return (float(x) / max(1e-6, self.view_scale_x),
                float(y) / max(1e-6, self.view_scale_y))

    def _create(self, item_type, args, options):
        coords = tk._flatten(args)
        if len(coords) % 2:
            return super()._create(item_type, args, options)
        physical = tuple(float(value) *
                         (self.view_scale_x if idx % 2 == 0 else self.view_scale_y)
                         for idx, value in enumerate(coords))
        opts = options.copy()
        if 'width' in opts:
            try:
                opts['width'] = max(1.0, float(opts['width']) * self.view_scale)
            except (ValueError, TypeError):
                pass
        font = opts.get('font')
        if isinstance(font, (tuple, list)) and len(font) >= 2:
            try:
                font_size = int(font[1])
                new_size = max(6, round(abs(font_size) * self.view_scale))
                opts['font'] = (font[0], new_size if font_size >= 0 else -new_size,
                                *font[2:])
            except (ValueError, TypeError):
                pass
        return super()._create(item_type, physical, opts)


class EnterGame:
    def __init__(self, root):
        self.root = root
        root.title('ENTER | INFINITE DUNGEON  /  ARCHMOBA')
        root.geometry(f'{W}x{H}')
        root.minsize(420, 310)
        root.resizable(True, True)
        root.configure(bg=BG)
        self.canvas = ResponsiveCanvas(root, width=W, height=H,
                                       bg=BG, highlightthickness=0,
                                       bd=0)
        self.canvas.pack(fill='both', expand=True)
        self._fullscreen_active = False
        self._fullscreen_touched = False
        self._windowed_geometry = f'{W}x{H}+80+60'
        self.keys = set()
        self.aim = (W/2+120, DOOR_Y)
        self.bullets = []
        self.enemy_bullets = []
        self.particles = []
        self.message = ''
        self.message_until = 0
        self.last_shot = 0.0
        self.last = time.monotonic()
        self.frame = 0.0
        self.state = 'upgrade'
        self.intro_room = True
        self.level = 1
        self.max_level = 1
        # Ultimo nivel normal superado, independientemente de los pisos que
        # se vuelvan a visitar. No requiere listas en el archivo de guardado.
        self.checkpoint_level = 0
        self.xp = 0
        self.last_level_xp = 0  # Recompensa de la ultima victoria.
        self.last_win_was_replay = False
        # La recarga cuenta solamente en salas vacias; nunca se multiplica la
        # EXP acumulada: el bono se aplica UNA vez a la proxima victoria.
        self.rest_seconds = 0.0
        self.xp_boost_ready = False
        self.safe_autosave_elapsed = 0.0
        self._rest_dirty = False
        self.hp_up = 0
        self.gun_up = 0
        self.shield_up = 0
        self.speed_up = 0
        self.door_progress = 0.0
        self.upgrade_pad_lock = False
        self.upgrade_return_state = 'cleared'
        self.upgrade_open_started_at = 0.0
        self.upgrades_pending_save = False  # Solo guardar si hubo una compra real.
        self.player_vx = 0.0
        self.player_vy = 0.0
        # Ultima direccion conservada, incluso al dejar de caminar.
        self.player_facing = (0.0, 1.0)
        self.life = self.max_hp
        self.enemies = []
        self.shield_flash = 0.0
        self.hit_invuln = 0.0
        self.death_restart_at = 0.0
        self.death_anim_start = 0.0
        self.death_particles = []
        self.heal_from = self.life
        self.heal_to = self.life
        self.heal_started_at = 0.0
        self.heal_until = 0.0
        self.boss_stage = False
        self.boss_floor = 0
        self.transition_target = None
        self.transition_entry_side = 'top'
        self.transition_started_at = 0.0
        self.transition_mid_at = 0.0
        self.transition_until = 0.0
        self.transition_entered = False
        self.transition_particles = []
        self.spawn_fx_until = 0.0
        self.obstacles = []
        self.hazards = []
        self.pending_enemies = []
        self.trap_triggered = False
        # Pisos nunca completados: los enemigos se materializan al entrar.
        # Pisos completados: se invocan solamente al pisar la placa central.
        self.auto_summon_on_entry = False
        # El icono y la IA del clon pertenecen a cada combate, no al save.
        self.clone_pickup = None
        self.ally_clone = None
        self.summon_started_at = 0.0
        self.summon_until = 0.0
        self._load()
        self.start_room()
        root.bind('<KeyPress>', self.keydown)
        root.bind('<KeyRelease>', self.keyup)
        root.bind('<ButtonPress-1>', self.mousepress)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.bind('<MouseWheel>', self.roster_wheel)
        root.bind('<Button-4>', self.roster_wheel)
        root.bind('<Button-5>', self.roster_wheel)
        # Modo de prueba separado de la partida: no combate, no EXP, no guardado.
        self.roster_mode = True
        self.roster_scroll = 0.0
        self.roster_auto = True
        self.roster_direction = 1
        self.roster_manual_until = 0.0
        self.roster_view = 0
        self.roster_keys = set()
        self.roster_entries = self.build_roster_entries()
        self.tick()
        # Inicio real a pantalla completa. Sin cambiar resolucion del monitor.
        self.root.after(60, self._initial_fullscreen)

    # Cada nivel de mejora multiplica el atributo actual por 1.10.
    # El escudo parte del 5%: el 10% de un escudo inicial del 0% seria siempre 0.
    # Se impide una compra que supere 85% de mitigacion, para evitar inmunidad.
    @property
    def max_hp(self): return 100.0 * (1.10 ** self.hp_up)
    @property
    def damage(self): return 13.0 * (1.10 ** self.gun_up)
    @property
    def shield(self): return min(0.85, 0.05 * (1.10 ** self.shield_up))
    @property
    def player_speed(self):
        # Estadistica virtual: sirve para comparar con los enemigos.
        # No representa la velocidad fisica del personaje.
        return PLAYER_MOVE_SPEED * (1.10 ** self.speed_up)

    @property
    def player_move_speed(self):
        # Siempre identica aunque el usuario compre SPEED 100 veces.
        return PLAYER_MOVE_SPEED

    @staticmethod
    def stat_text(value, decimals=1):
        return f'{value:,.{decimals}f}'.rstrip('0').rstrip('.')

    def next_stat(self, kind):
        current = {'hp': self.max_hp, 'gun': self.damage,
                   'shield': self.shield, 'speed': self.player_speed}[kind]
        return current * 1.10

    def can_upgrade(self, kind):
        # Todos los upgrades comprables proporcionan exactamente +10%.
        # Evita valores infinitos tras cargar un checkpoint editado o extremo.
        if kind == 'shield':
            return self.next_stat(kind) <= 0.85 + 1e-12
        level = {'hp': self.hp_up, 'gun': self.gun_up,
                 'speed': self.speed_up}[kind]
        return level < 500

    def enemy_speed(self, enemy):
        """Velocidad real del enemigo tras descontar la estadistica SPEED.

        El jugador siempre camina a PLAYER_MOVE_SPEED. Los puntos SPEED
        restan velocidad al enemigo respecto del juego sin mejoras:
            velocidad_enemigo = velocidad_natural - (SPEED - SPEED_inicial).
        La velocidad natural del enemigo sigue aumentando con el nivel.
        """
        if enemy['name'] == 'OVERSEER':
            # Los jefes conservan una movilidad minima y tienen fases propias.
            natural = min(142.0, 80.0 + math.log10(max(10, self.boss_floor))*13.0)
            minimum = MIN_BOSS_MOVE_SPEED
        else:
            natural = min(438.0, (40.0 + 45.0 * enemy['speed']) *
                          (1.0 + 0.035 * (self.level - 1))**0.48)
            minimum = MIN_ENEMY_MOVE_SPEED
        speed_advantage = self.player_speed - PLAYER_MOVE_SPEED
        return max(minimum, natural - speed_advantage)

    def enemy_movement_speed(self, enemy):
        """Velocidad final de la IA, incluidos los impulsos de cada rol."""
        speed = self.enemy_speed(enemy)
        name = enemy['name']
        dist = distance(self.player_x, self.player_y, enemy['x'], enemy['y'])
        if name == 'OVERSEER':
            phase = max(1, min(3, int(enemy.get('phase', 1))))
            speed *= (1.0, 1.30, 1.62)[phase-1]
            if dist > 165:
                speed *= 1.08
        elif name == 'STRIKER' and dist > 140:
            speed *= 1.17
        return speed

    @staticmethod
    def boss_rank(floor):
        """Prioridad: un solo jefe por decena; cuanto mas divisible, mayor."""
        if floor % 1_000_000 == 0:
            return 5
        if floor % 100_000 == 0:
            return 4
        if floor % 10_000 == 0:
            return 3
        if floor % 1_000 == 0:
            return 2
        if floor % 100 == 0:
            return 1
        return 0

    @staticmethod
    def boss_level(floor):
        """LV propio de cada clase de jefe, independiente del piso normal.

        10 -> OVERSEER LV 1, 20 -> LV 2; 100 -> COLOSSUS LV 1,
        400 -> LV 4; 1000 -> TITAN LV 1, etc. La categoria con el
        divisor mas alto prevalece en los multiples compartidos.
        """
        floor = int(floor)
        if floor < 10 or floor % 10 != 0:
            raise ValueError('Solo existen niveles de jefe tras pisos multiplos de 10')
        rank = EnterGame.boss_rank(floor)
        return floor // (10 ** (rank + 1))

    @staticmethod
    def boss_name(rank):
        return ('OVERSEER', 'COLOSSUS', 'TITAN', 'LEVIATHAN', 'OMEGA', 'SINGULARITY')[rank]

    @staticmethod
    def boss_scale(rank):
        return (1.22, 1.52, 1.88, 2.25, 2.65, 3.05)[rank]

    @staticmethod
    def boss_palette(floor, rank):
        # El color varia por cada decena y no solo por cada 6 jefes.
        hue = ((floor // 10) * 0.61803398875 + rank * 0.086) % 1.0
        r,g,b = colorsys.hsv_to_rgb(hue, 0.60 if rank<3 else 0.43, 1.0)
        return '#%02x%02x%02x' % (round(r*255), round(g*255), round(b*255))

    def relative_speed(self, enemy):
        # HUD: velocidad real del enemigo MENOS la velocidad fisica fija
        # del jugador. Incluye los impulsos propios del rol y de las fases.
        # La cifra SPEED comprada ya se desconto dentro de enemy_speed().
        return self.enemy_movement_speed(enemy) - self.player_move_speed

    def upgrade_cost(self, kind):
        level = {'hp': self.hp_up, 'gun': self.gun_up, 'shield': self.shield_up,
                 'speed': self.speed_up}[kind]
        base = {'hp': 45, 'gun': 55, 'shield': 50, 'speed': 65}[kind]
        return round(base * (1.33 ** min(30, level)) * max(1, 1 + (level-30)*.20))

    def _save(self):
        """Guarda progreso secuencial usando solo level y max_level.

        level representa el ultimo nivel normal completado, mientras que
        max_level representa el siguiente nivel normal desbloqueado. Cuando
        level=max_level y es multiplo de 10, el jefe de ese piso esta pendiente.
        La escritura atomica preserva el checkpoint si se interrumpe.
        """
        data = dict(level=max(1, self.checkpoint_level),
                    max_level=self.max_level, xp=self.xp,
                    last_level_xp=self.last_level_xp,
                    last_win_was_replay=self.last_win_was_replay,
                    hp_up=self.hp_up, gun_up=self.gun_up,
                    shield_up=self.shield_up, speed_up=self.speed_up,
                    life=round(self.life, 2),
                    rest_seconds=round(self.rest_seconds, 2),
                    xp_boost_ready=bool(self.xp_boost_ready))
        try:
            temp = SAVE.with_suffix('.tmp')
            temp.write_text(json.dumps(data, indent=2), encoding='utf-8')
            temp.replace(SAVE)
            self._rest_dirty = False
            self.safe_autosave_elapsed = 0.0
            return True
        except OSError:
            self.notice('⚠')
            return False

    def _reset_progress(self):
        """Nueva partida; aun no existe un nivel normal completado."""
        self.level = 1
        self.max_level = 1
        self.checkpoint_level = 0
        self.xp = 0
        self.last_level_xp = 0
        self.last_win_was_replay = False
        self.rest_seconds = 0.0
        self.xp_boost_ready = False
        self.safe_autosave_elapsed = 0.0
        self._rest_dirty = False
        self.hp_up = 0
        self.gun_up = 0
        self.shield_up = 0
        self.speed_up = 0
        self.boss_floor = 0
        self.life = self.max_hp

    def level_completed(self, floor):
        """Progreso lineal: pisos anteriores al checkpoint ya estan completos."""
        floor = int(floor)
        return floor >= 1 and floor <= self.checkpoint_level

    def boss_completed(self, floor):
        """Cada jefe desbloquea el siguiente piso normal del mismo bloque."""
        floor = int(floor)
        return floor >= 10 and floor % 10 == 0 and self.max_level > floor

    def _load(self):
        """Carga JSON moderno o migra una partida antigua con listas.

        No se borran la EXP ni las mejoras. Se crea una copia .bak antes de
        quitar cleared y bosses_defeated de un guardado antiguo.
        """
        self._reset_progress()
        if not SAVE.exists():
            return False
        try:
            data = json.loads(SAVE.read_text(encoding='utf-8'))
            old_max = clamp(int(data.get('max_level', 1)), 1, 10**8)
            old_level = clamp(int(data.get('level', 1)), 1, old_max)
            legacy = 'cleared' in data or 'bosses_defeated' in data
            if legacy:
                # El formato anterior guardaba el piso en el que se estaba
                # cuando se hizo el checkpoint, no necesariamente el mas alto.
                old_cleared = set(int(n) for n in data.get('cleared', [])
                                  if 1 <= int(n) <= old_max)
                defeated = set(int(n) for n in data.get('bosses_defeated', [])
                               if int(n) >= 10 and int(n) % 10 == 0)
                checkpoint_level = max(max(old_cleared, default=0), old_max-1)
                # El viejo max_level avanzaba a 11 ya tras ganar el piso 10;
                # el nuevo solo avanza de 10 a 11 tras derrotar a ese jefe.
                # Repetir la misma regla para 20, 30, etc.
                if (checkpoint_level > 0 and checkpoint_level % 10 == 0 and
                        checkpoint_level == old_max - 1 and
                        checkpoint_level not in defeated):
                    max_level = checkpoint_level
                else:
                    max_level = old_max
                loaded_level = max(1, checkpoint_level)
            else:
                max_level = old_max
                # Sin listas, level ya es el ultimo nivel normal superado.
                checkpoint_level = clamp(old_level, 0, max_level)
                if max_level == 1 and old_level == 1:
                    # La primera sala puede no haber sido completada.
                    checkpoint_level = 0
                loaded_level = max(1, checkpoint_level)

            xp = clamp(int(data.get('xp', 0)), 0, 10**12)
            upgrades = {}
            for name in ('hp_up', 'gun_up', 'shield_up', 'speed_up'):
                upgrades[name] = clamp(int(data.get(name, 0)), 0, 500)
            self.max_level = max_level
            self.checkpoint_level = checkpoint_level
            self.level = loaded_level
            self.xp = xp
            self.last_level_xp = clamp(int(data.get('last_level_xp', 0)), 0, 10**12)
            self.last_win_was_replay = bool(data.get('last_win_was_replay', False))
            raw_rest = float(data.get('rest_seconds', 0.0))
            self.rest_seconds = clamp(raw_rest, 0.0, REST_CHARGE_SECONDS) if math.isfinite(raw_rest) else 0.0
            self.xp_boost_ready = bool(data.get('xp_boost_ready', False))
            if self.xp_boost_ready:
                self.rest_seconds = REST_CHARGE_SECONDS
            self.safe_autosave_elapsed = 0.0
            self._rest_dirty = False
            for name, value in upgrades.items():
                setattr(self, name, value)
            self.life = clamp(float(data.get('life', self.max_hp)), 1, self.max_hp)
            if legacy:
                # Actualizar el formato una sola vez, sin perder el original.
                backup = SAVE.with_name(SAVE.name + '.bak')
                if not backup.exists():
                    try:
                        shutil.copy2(SAVE, backup)
                    except OSError:
                        pass
                self._save()
            return True
        except (ValueError, TypeError, OSError, OverflowError):
            self._reset_progress()
            self.notice('⚠')
            return False

    def is_rest_room(self):
        """La sala esta realmente libre de combate, tambien si ya fue explorada.

        No acumular tiempo durante invocaciones, peleas, transiciones, muertes
        ni en un nivel nuevo cuyo combate se activa automaticamente.
        """
        current = self.upgrade_return_state if self.state == 'upgrade' else self.state
        return (current in ('ready', 'cleared') and
                self.state in ('ready', 'cleared', 'upgrade') and
                not self.enemies and
                (current == 'cleared' or not self.auto_summon_on_entry))

    def update_rest_charge(self, elapsed):
        """Recarga EXP x2 con tiempo real, sin saturar ni usar servidores.

        El intervalo local de seguridad es de 10 min, pero ganar una batalla,
        salir tras comprar una mejora o completar la carga tambien guarda.
        Al estar la carga lista no se acumulan mas bonos.
        """
        if not self.is_rest_room() or getattr(self, 'roster_mode', False):
            return
        elapsed = max(0.0, float(elapsed))
        if not math.isfinite(elapsed) or elapsed <= 0.0:
            return
        self.safe_autosave_elapsed += elapsed
        if not self.xp_boost_ready:
            before = self.rest_seconds
            self.rest_seconds = min(REST_CHARGE_SECONDS, self.rest_seconds + elapsed)
            if self.rest_seconds > before:
                self._rest_dirty = True
            if self.rest_seconds >= REST_CHARGE_SECONDS:
                self.xp_boost_ready = True
                # Guardar la carga al instante: debe sobrevivir un reinicio.
                # Las mejoras todavia en compra NO se confirman por accidente.
                if not self.upgrades_pending_save:
                    self._save()
        if (self.safe_autosave_elapsed >= LOCAL_AUTOSAVE_SECONDS and
                self._rest_dirty and not self.upgrades_pending_save):
            self._save()

    def notice(self, msg, secs=2.4):
        self.message, self.message_until = msg, time.monotonic() + secs

    @property
    def is_level_zero(self):
        """La sala cero no muestra numero, puerta izquierda ni mejoras."""
        return self.intro_room and self.level == 0

    def portals_available(self):
        """Abiertos al regresar a un piso superado; se cierran al repetir combate.

        No basta con tener el nivel en el historial si hay monstruos activos:
        durante invocacion y combate los portales permanecen bloqueados.
        """
        effective_state = (self.upgrade_return_state
                           if self.state == 'upgrade' else self.state)
        if effective_state == 'cleared':
            return True
        if effective_state != 'ready' or self.intro_room:
            return False
        if self.boss_stage:
            return self.boss_completed(self.boss_floor)
        return self.level_completed(self.level)

    def start_room(self, force_zero=False):
        """Prepara una sala segura sin enemigos y sin grabar nada.

        Sala cero: no hay mejoras, numero ni puerta izquierda.
        Al cargar un checkpoint, el menu solo se abre al pisar la plataforma.
        """
        self.intro_room = True
        has_progress = bool(self.checkpoint_level or self.xp or self.hp_up or self.gun_up or
                            self.shield_up or self.speed_up or self.max_level > 1)
        if force_zero or not has_progress:
            self.level = 0
        # La sala siempre se inicia vacia, sin abrir el menu automaticamente.
        self.state = 'cleared'
        self.door_progress = 1.0
        self.upgrade_pad_lock = False
        self.upgrade_return_state = 'cleared'
        self.upgrade_open_started_at = 0.0
        self.upgrades_pending_save = False
        self.clone_pickup = None
        self.ally_clone = None
        self.heal_until = 0.0
        self.boss_stage = False
        self.boss_floor = 0
        self.pending_enemies.clear()
        self.trap_triggered = False
        self.auto_summon_on_entry = False
        self.summon_started_at = 0.0
        self.summon_until = 0.0
        self.obstacles.clear()
        self.hazards.clear()
        # Inicio / checkpoint: entrar por arriba y caminar hacia el fondo.
        self.player_x, self.player_y = W / 2, FIELD[1] + 95.0
        self.player_vx = self.player_vy = 0.0
        self.player_facing = (0.0, 1.0)
        self.enemies.clear()
        self.bullets.clear()
        self.enemy_bullets.clear()
        self.particles.clear()
        self.death_particles.clear()
        self.aim = (self.player_x + 100, self.player_y)

    def restore_checkpoint(self):
        """Tras morir: simula un GET y regresa a la sala segura.

        No modifica el checkpoint: recupera la ultima victoria o salida del portal.
        Las mejoras pendientes al morir se descartan si no se salio del portal.
        """
        self._load()
        self.start_room()
        self.keys.clear()
        self.shield_flash = 0.0
        self.hit_invuln = 0.0
        self.last_shot = 0.0
        self.message = ''
        self.message_until = 0.0
        self.death_particles.clear()

    def enter_level(self, number, first=False):
        self.last_level_xp = 0  # El siguiente combate aun no ha dado EXP.
        self.last_win_was_replay = False
        self.level = max(1, number)
        # Solo una visita a un nivel no superado activa el combate de inmediato.
        # Volver a un nivel superado deja disponible la plataforma central.
        self.auto_summon_on_entry = not self.level_completed(self.level)
        self.state = 'ready'
        self.upgrade_return_state = 'ready'
        self.upgrade_open_started_at = 0.0
        self.upgrade_pad_lock = False
        self.intro_room = False
        self.boss_stage = False
        self.boss_floor = 0
        self.door_progress = 1.0 if self.level_completed(self.level) else 0.0
        self.upgrades_pending_save = False
        self.clone_pickup = None
        self.ally_clone = None
        self.heal_until = 0.0
        self.player_vx = self.player_vy = 0.0
        self.hit_invuln = 0.0
        # Entrada segura junto al portal superior; se desciende hacia el combate.
        self.player_x, self.player_y = W / 2, FIELD[1] + 90
        self.player_facing = (0.0, 1.0)
        self.bullets.clear()
        self.enemy_bullets.clear()
        self.particles.clear()
        self.last_shot = 0.0
        self.aim = (self.player_x + 100, self.player_y)
        self.enemies = []
        self.pending_enemies = []
        self.trap_triggered = False
        self.summon_started_at = 0.0
        self.summon_until = 0.0
        self.build_arena_features()
        # Exactly four opponents; their health, attack and defense grow forever.
        # Los cuatro soldados aparecen DENTRO del suelo 3D, no fuera de
        # sus bordes; siguen formando las dos filas originales.
        positions = [(FIELD[0]+73, 172), (FIELD[2]-73, 170),
                     (FIELD[0]+34, 489), (FIELD[2]-34, 487)]
        classes = [
            # Vida relativa, ataque relativo, velocidad, color.
            ('DRONE', 1.05, 0.92, 4.10, '#e67ded'),
            ('GUARD', 1.48, 1.12, 2.70, '#fe7b80'),
            ('TANK', 2.65, 1.42, 1.85, '#ffb35e'),
            ('STRIKER', 1.32, 1.34, 4.85, '#ff536f'),
        ]
        n = self.level
        for ((x,y), (name, hmul, amul, speed, color)) in zip(positions, classes):
            # La vida y defensa escalan desde una base amenazante, no desde enemigos de tutorial.
            base_health = round((43 + 7.5 * (n-1)**1.17 + 1.4 * (n-1)**1.28) * hmul)
            health = max(1, round(base_health * ENEMY_DIFFICULTY))
            self.enemies.append(dict(x=float(x), y=float(y), name=name,
                hp=health, hpmax=health,
                attack=(8.5 + 0.85*(n-1)**1.14)*amul*ENEMY_DIFFICULTY,
                defense=(1.7 + 0.16*(n-1)**1.03)*(1.85 if name == 'TANK' else 1.0)*ENEMY_DIFFICULTY,
                speed=speed, color=color, orbit=1 if name in ('DRONE','GUARD') else -1,
                next_fire=time.monotonic()+random.uniform(.75,1.25),
                # El destello precedente al disparo permite esquivar con reflejos.
                radius=17 if name=='TANK' else 13))
        # Los enemigos se preparan fuera de la arena hasta materializarse.
        self.pending_enemies = self.enemies
        self.enemies = []
        self.message = ''
        self.message_until = 0.0
        # Entrada directa: activar ahora los pisos nuevos. Si se entra a traves
        # de un portal, esperar a que termine la transicion para que la
        # invocacion holografica se reproduzca completa en la nueva sala.
        if self.auto_summon_on_entry and self.transition_target is None:
            self.trigger_enemy_ambush(time.monotonic())

    def keydown(self, e):
        k = e.keysym.lower()
        if k == 'f11':
            self.set_fullscreen(not self._fullscreen_active)
            return 'break'
        if k == 'escape' and self._fullscreen_active:
            self.set_fullscreen(False)
            return 'break'
        if k == 'q' and (getattr(e, 'state', 0) & 0x0004):
            self.close()
            return 'break'
        if k == 'f9':
            self.roster_mode = not self.roster_mode
            self.roster_keys.clear()
            self.keys.clear()
            return
        if self.roster_mode:
            if k in ('a', 'd', 'left', 'right'):
                self.roster_keys.add(k)
                self.roster_manual_until = time.monotonic() + 2.5
            elif k == 'space':
                self.roster_auto = not self.roster_auto
            elif k == 'v':
                self.roster_view = (self.roster_view + 1) % 4
            elif k in ('1', '2', '3', '4'):
                self.roster_view = int(k) - 1
            elif k == 'home':
                self.roster_scroll = 0.0
                self.roster_manual_until = time.monotonic() + 3
            elif k == 'end':
                self.roster_scroll = self.roster_scroll_max()
                self.roster_manual_until = time.monotonic() + 3
            return
        self.keys.add(k)
        # El panel no bloquea el movimiento; solo alejarse del portal lo cierra.

    def keyup(self, e):
        k = e.keysym.lower()
        self.roster_keys.discard(k)
        self.keys.discard(k)

    def mousepress(self, e):
        # Los botones se comprueban en coordenadas logicas, tambien a 4K.
        event_x, event_y = self.canvas.to_game(e.x, e.y)
        e.x, e.y = event_x, event_y
        if self.roster_mode:
            # Botones del visor: volver al juego y recorrer la fila.
            if W-166 <= e.x <= W-14 and 10 <= e.y <= 58:
                self.roster_mode = False
                self.roster_keys.clear()
                self.keys.clear()
            elif e.x < 86 and 255 < e.y < 448:
                self.roster_scroll = clamp(self.roster_scroll-440, 0, self.roster_scroll_max())
                self.roster_manual_until = time.monotonic() + 3
            elif e.x > W-86 and 255 < e.y < 448:
                self.roster_scroll = clamp(self.roster_scroll+440, 0, self.roster_scroll_max())
                self.roster_manual_until = time.monotonic() + 3
            return
        # Durante la apertura los botones aun no existen visualmente.
        if self.state == 'upgrade' and self.upgrade_open_progress() >= 1.0:
            if self.try_upgrade_at(e.x, e.y): return

    def try_upgrade_at(self, x, y):
        for i, kind in enumerate(('hp', 'gun', 'shield', 'speed')):
            left = 124 + (W-BASE_W)//2 + i * 169
            if (left <= x <= left + 158 and
                    UPGRADE_CARD_TOP <= y <= UPGRADE_CARD_BOTTOM):
                cost = self.upgrade_cost(kind)
                if self.xp < cost or not self.can_upgrade(kind):
                    self.notice('✕')
                    return True
                self.xp -= cost
                if kind == 'hp':
                    previous_max_hp = self.max_hp
                    self.hp_up += 1
                    self.life = min(self.max_hp, self.life + (self.max_hp - previous_max_hp))
                elif kind == 'gun': self.gun_up += 1
                elif kind == 'shield': self.shield_up += 1
                else: self.speed_up += 1
                # Solo marcar cambios al comprar una mejora realmente.
                self.upgrades_pending_save = True
                # Las mejoras siguen pendientes hasta alejarse de la plataforma.
                # Si la mejora fue de vida, ampliar el objetivo visual de curacion.
                if kind == 'hp' and self.heal_until > time.monotonic():
                    self.heal_to = self.life
                return True
        return False

    def nearest_enemy(self):
        """Selecciona al oponente vivo mas cercano."""
        if not self.enemies:
            return None
        return min(self.enemies, key=lambda enemy: (
            (enemy['x'] - self.player_x)**2 + (enemy['y'] - self.player_y)**2))

    def upgrade_pad_center(self):
        # Parte inferior derecha, sin bloquear el portal de avance.
        return (FIELD[2] - 98, FIELD[3] - 62)

    def on_upgrade_pad(self, x=None, y=None):
        if x is None: x = self.player_x
        if y is None: y = self.player_y
        cx, cy = self.upgrade_pad_center()
        rx, ry = 78.0, 24.0
        return (((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2) <= 1.0

    def arena_x_bounds(self, y, margin=20.0):
        """Limites horizontales segun la perspectiva del piso 3D."""
        top_y = FIELD[1] + 14.0
        bottom_y = FIELD[3] - 8.0
        t = clamp((y - top_y) / max(1.0, bottom_y - top_y), 0.0, 1.0)
        # Debe coincidir aproximadamente con el trapecio dibujado.
        left_edge = (FIELD[0] + 90.0) + ((FIELD[0] - 24.0) - (FIELD[0] + 90.0)) * t
        right_edge = (FIELD[2] - 90.0) + ((FIELD[2] + 24.0) - (FIELD[2] - 90.0)) * t
        return left_edge + margin, right_edge - margin

    def build_random_servers(self, boss=False):
        """Genera entre 1 y 7 servidores holograficos en posiciones aleatorias."""
        obstacles = []
        count = random.randint(2, 7) if boss else random.randint(1, 7)
        palettes = ['#18333b', '#1c3741', '#16323a', '#1a3640', '#24404a', '#203842']
        trap_x, trap_y = TRAP_POSITION
        pad_x, pad_y = self.upgrade_pad_center()
        for _ in range(count):
            placed = False
            for _try in range(80):
                y = random.uniform(FIELD[1] + 92, FIELD[3] - 92)
                left_bound, right_bound = self.arena_x_bounds(y, 64)
                if right_bound - left_bound < 40:
                    continue
                x = random.uniform(left_bound, right_bound)
                r = random.randint(18, 28) if not boss else random.randint(20, 32)
                # Evita tapar la placa central, la plataforma upgrade,
                # el spawn del jugador y las dos salidas verticales.
                if distance(x, y, trap_x, trap_y) < r + 72:
                    continue
                if distance(x, y, pad_x, pad_y) < r + 74:
                    continue
                if distance(x, y, W / 2, DOOR_Y + 118) < r + 78:
                    continue
                if distance(x, y, NEXT_PORTAL_X, NEXT_PORTAL_Y + 26) < r + 74:
                    continue
                if distance(x, y, BACK_PORTAL_X, BACK_PORTAL_Y - 26) < r + 74:
                    continue
                if any(distance(x, y, obs['x'], obs['y']) < r + obs['r'] + 42 for obs in obstacles):
                    continue
                obstacles.append({'x': x, 'y': y, 'r': r, 'color': random.choice(palettes)})
                placed = True
                break
            if not placed:
                break
        if not obstacles:
            obstacles.append({'x': W/2 + 135, 'y': DOOR_Y - 42, 'r': 22, 'color': '#1c3741'})
        return obstacles

    def build_arena_features(self):
        self.obstacles = []
        self.hazards = []
        if self.intro_room:
            return
        self.obstacles = self.build_random_servers(boss=self.boss_stage)

    def resolve_obstacles(self, x, y, radius):
        for obs in self.obstacles:
            dx = x - obs['x']
            dy = y - obs['y']
            dist = math.hypot(dx, dy)
            need = obs['r'] + radius
            if dist < need:
                if dist < 1e-5:
                    dx, dy, dist = 1.0, 0.0, 1.0
                push = need - dist
                x += dx / dist * push
                y += dy / dist * push
        return x, y

    def hazard_damage(self, x, y):
        # Ya no usamos trampas de daño; ahora solo aparecen objetos/cajas.
        return 0.0

    def standing_on_trigger(self, x=None, y=None):
        """La unica placa activa al contacto de los pies con su superficie."""
        if x is None:
            x = self.player_x
        if y is None:
            y = self.player_y
        px, py = TRAP_POSITION
        return ((x - px) / TRAP_RADIUS_X) ** 2 + ((y - py) / TRAP_RADIUS_Y) ** 2 <= 1.0

    def prepare_clone_pickup(self):
        """Con probabilidad moderada, deja un unico casco coleccionable.

        Se busca una posicion caminable que no este dentro de un servidor,
        de un enemigo o de la zona inmediata del jugador.
        """
        self.clone_pickup = None
        self.ally_clone = None
        chance = CLONE_BOSS_PICKUP_CHANCE if self.boss_stage else CLONE_PICKUP_CHANCE
        if not self.enemies or random.random() >= chance:
            return False
        for _ in range(110):
            y = random.uniform(FIELD[1] + 77, FIELD[3] - 87)
            left, right = self.arena_x_bounds(y, 38)
            if right <= left:
                continue
            x = random.uniform(left, right)
            if distance(x, y, self.player_x, self.player_y) < 105:
                continue
            if any(distance(x, y, o['x'], o['y']) < o['r'] + 39
                   for o in self.obstacles):
                continue
            if any(distance(x, y, e['x'], e['y']) < e['radius'] + 38
                   for e in self.enemies):
                continue
            if distance(x, y, *TRAP_POSITION) < 54:
                continue
            self.clone_pickup = {'x': x, 'y': y}
            return True
        return False

    def collect_clone_pickup(self, now):
        """Proyecta el cuerpo del PLAYER con una IA autonoma, solo aliada."""
        pickup = self.clone_pickup
        if self.state != 'fight' or pickup is None:
            return False
        if distance(self.player_x, self.player_y, pickup['x'], pickup['y']) > 28:
            return False
        x = clamp(pickup['x'] + 31, *self.arena_x_bounds(pickup['y'], 22))
        y = clamp(pickup['y'] - 18, FIELD[1]+25, FIELD[3]-25)
        x, y = self.resolve_obstacles(x, y, 15)
        x = clamp(x, *self.arena_x_bounds(y, 21))
        self.ally_clone = dict(
            x=x, y=y, vx=0.0, vy=0.0,
            facing=(0.0, -1.0),
            hp=max(35.0, self.max_hp*0.58),
            max_hp=max(35.0, self.max_hp*0.58),
            next_fire=now + 0.25,
            born_at=now, orbit=random.choice((-1, 1)),
        )
        self.clone_pickup = None
        for i in range(14):
            ang = i * math.tau / 14
            self.particles.append([
                x + math.cos(ang)*random.uniform(10, 22),
                y + math.sin(ang)*random.uniform(6, 16),
                0.38, '#be90ff' if i % 2 else '#74ffff'
            ])
        return True

    def damage_ally_clone(self, amount):
        clone = self.ally_clone
        if clone is None:
            return
        clone['hp'] -= max(0.0, amount)
        if clone['hp'] <= 0.0:
            for i in range(18):
                ang = i*math.tau/18
                self.particles.append([
                    clone['x']+math.cos(ang)*random.uniform(4, 30),
                    clone['y']+math.sin(ang)*random.uniform(3, 20),
                    0.4, '#ba7aff' if i % 2 else '#8cffff'
                ])
            self.ally_clone = None

    def update_ally_clone(self, dt, now):
        """IA independiente: flanquea, evita servidores y solo hiere enemigos."""
        clone = self.ally_clone
        if clone is None or self.state != 'fight' or not self.enemies:
            return
        enemy = min(self.enemies, key=lambda e:
                    (e['x']-clone['x'])**2 + (e['y']-clone['y'])**2)
        dx, dy = enemy['x']-clone['x'], enemy['y']-clone['y']
        dist = max(1.0, math.hypot(dx, dy))
        # Pelea a distancia y se mueve alrededor de su blanco. Los errores
        # simulados dan un ligero balanceo sin congelar ni descontrolar la IA.
        ideal = 151.0 if enemy['name'] == 'OVERSEER' else 107.0
        radial = (0.98 if dist > ideal + 24 else
                  -0.93 if dist < ideal - 33 else 0.0)
        sway = 0.80 + 0.17*math.sin(self.frame*3.4+clone['born_at'])
        mx = dx / dist*radial - dy / dist*sway*clone['orbit']
        my = dy / dist*radial + dx / dist*sway*clone['orbit']
        norm = max(1.0, math.hypot(mx, my))
        speed = PLAYER_MOVE_SPEED*0.73
        clone['vx'] = mx / norm*speed
        clone['vy'] = my / norm*speed
        ny = clamp(clone['y'] + clone['vy']*dt, FIELD[1]+25, FIELD[3]-25)
        nx = clamp(clone['x'] + clone['vx']*dt, *self.arena_x_bounds(ny, 19))
        nx, ny = self.resolve_obstacles(nx, ny, 15)
        clone['x'] = clamp(nx, *self.arena_x_bounds(ny, 19))
        clone['y'] = clamp(ny, FIELD[1]+25, FIELD[3]-25)
        clone['facing'] = (dx/dist, dy/dist)
        if now >= clone['next_fire'] and dist <= 540:
            # Las balas del clon se identifican solo para el efecto visual;
            # comparten la colision AMIGA que exclusivamente golpea enemigos.
            self.bullets.append([
                clone['x'], clone['y'], dx/dist*590, dy/dist*590,
                self.damage*0.58, 0.0, 'ally'
            ])
            clone['next_fire'] = now + 0.36

    def trigger_enemy_ambush(self, now):
        """Activa la materializacion al entrar por primera vez o pisar la placa."""
        if self.state != 'ready' or self.trap_triggered or not self.pending_enemies:
            return
        self.trap_triggered = True
        self.clone_pickup = None
        self.ally_clone = None
        self.state = 'summoning'
        self.summon_started_at = now
        self.summon_until = now + SUMMON_SECONDS
        self.summon_frame = self.frame
        self.bullets.clear()
        self.enemy_bullets.clear()
        self.particles.clear()
        self.last_shot = now
        self.message = ''
        self.message_until = 0.0

    def draw_enemy_summoning(self):
        """Proyeccion digital previa al nacimiento de los enemigos."""
        if self.state != 'summoning' or not self.pending_enemies:
            return
        c = self.canvas
        elapsed = max(0.0, self.frame - self.summon_frame)
        progress = clamp(elapsed / SUMMON_SECONDS, 0.0, 1.0)
        for e in self.pending_enemies:
            x, y = e['x'], e['y']
            col = e['color']
            r = min(65.0, 18.0 + e['radius'] * 0.68)
            scan = 0.5 + 0.5 * math.sin(self.frame * 17.0 + x * 0.02)
            c.create_oval(x-r, y-r*0.49, x+r, y+r*0.49,
                          outline=col, width=2)
            c.create_oval(x-r*(.45 + progress * .55), y-r*(.25 + progress * .28),
                          x+r*(.45 + progress * .55), y+r*(.25 + progress * .28),
                          outline='#b9ffff', width=1)
            for j in range(3):
                yy = y-40 + ((progress*90 + j*24) % 83)
                ww = (7.0 + scan * 4) * (1.0 - j*.15)
                c.create_line(x-ww, yy, x+ww, yy, fill=col, width=2)
            for side in (-1, 1):
                ax = x + side * min(32.0, e['radius'] + 10.0)
                c.create_line(ax, y-31*(1-progress), ax, y+22*progress,
                              fill=col, width=1)

    def position_player_at_portal(self, entry_side):
        """Aparece dentro de la sala, frente al portal por el que ha entrado.

        Avance por abajo -> llegada junto al portal superior.
        Retroceso por arriba -> llegada junto al portal inferior.
        La separacion del umbral evita reactivar el portal accidentalmente.
        """
        if entry_side == 'top':
            self.player_x = BACK_PORTAL_X
            self.player_y = FIELD[1] + 85.0
            self.player_facing = (0.0, 1.0)
        elif entry_side == 'bottom':
            self.player_x = NEXT_PORTAL_X
            self.player_y = FIELD[3] - 90.0
            self.player_facing = (0.0, -1.0)
        else:
            raise ValueError('Portal de entrada no reconocido: ' + str(entry_side))
        self.player_vx = 0.0
        self.player_vy = 0.0
        self.aim = (self.player_x, self.player_y + 100 * self.player_facing[1])

    def start_transition(self, target, entry_side='top'):
        self.state = 'warp'
        self.clone_pickup = None
        self.ally_clone = None
        self.transition_target = target
        self.transition_entry_side = entry_side
        self.transition_started_at = time.monotonic()
        self.transition_mid_at = self.transition_started_at + 0.34
        self.transition_until = self.transition_started_at + 0.72
        self.transition_entered = False
        self.player_vx = self.player_vy = 0.0
        self.bullets.clear()
        self.enemy_bullets.clear()
        self.particles.clear()
        self.transition_particles = []
        colors = (GREEN, CYAN, '#d6fff5', '#59ffb0')
        for _ in range(36):
            ang = random.uniform(0, math.tau)
            speed = random.uniform(45, 170)
            self.transition_particles.append({
                'x': self.player_x, 'y': self.player_y,
                'vx': math.cos(ang) * speed,
                'vy': math.sin(ang) * speed,
                'ttl': random.uniform(0.25, 0.72),
                'max_ttl': 0.72,
                'size': random.uniform(1.6, 4.2),
                'color': random.choice(colors),
            })

    def update_transition(self, dt, now):
        for p in self.transition_particles[:]:
            p['ttl'] -= dt
            if p['ttl'] <= 0:
                self.transition_particles.remove(p)
                continue
            p['x'] += p['vx'] * dt
            p['y'] += p['vy'] * dt
        if not self.transition_entered and now >= self.transition_mid_at:
            target = self.transition_target
            if isinstance(target, tuple) and target[0] == 'boss':
                self.enter_boss_stage(target[1])
            else:
                self.enter_level(int(target))
            # La sala prepara primero sus enemigos y servidores; despues
            # se coloca al jugador junto al portal correspondiente.
            self.position_player_at_portal(self.transition_entry_side)
            self.hit_invuln = max(self.hit_invuln, 0.65)
            self.spawn_fx_until = now + 0.70
            self.transition_entered = True
            self.state = 'warp'  # Continua la reconstruccion de la nueva sala.
        if self.transition_entered and now >= self.transition_until:
            # Al llegar a un piso nuevo, la invocacion se activa al instante.
            # Un piso ya conocido queda en espera de que pisen la placa.
            self.state = 'ready' if self.pending_enemies else 'cleared'
            self.transition_target = None
            self.transition_particles.clear()
            if self.auto_summon_on_entry and self.state == 'ready':
                self.trigger_enemy_ambush(now)
            elif self.portals_available():
                # Al reaparecer en una zona descubierta, portales listos sin espera.
                self.door_progress = 1.0

    def enter_boss_stage(self, floor):
        """Una sala extra despues de cada piso divisible por 10."""
        floor = int(floor)
        if floor < 10 or floor % 10:
            raise ValueError('Un jefe solo aparece tras los pisos 10, 20, 30...')
        self.last_level_xp = 0
        self.last_win_was_replay = False
        self.level = floor
        self.state = 'ready'
        self.upgrade_return_state = 'ready'
        self.upgrade_open_started_at = 0.0
        self.upgrade_pad_lock = False
        self.intro_room = False
        self.boss_stage = True
        self.boss_floor = floor
        self.auto_summon_on_entry = not self.boss_completed(floor)
        self.door_progress = 1.0 if self.boss_completed(floor) else 0.0
        self.upgrades_pending_save = False
        self.clone_pickup = None
        self.ally_clone = None
        self.heal_until = 0.0
        self.player_vx = self.player_vy = 0.0
        self.player_facing = (0.0, 1.0)
        self.hit_invuln = 1.2
        # Entrar desde el portal superior, manteniendo distancia del megajefe.
        self.player_x, self.player_y = W/2, FIELD[1]+92
        self.bullets.clear()
        self.enemy_bullets.clear()
        self.particles.clear()
        self.last_shot = 0.0
        self.aim = (self.player_x, FIELD[3]-130)
        self.pending_enemies = []
        self.trap_triggered = False
        self.summon_started_at = 0.0
        self.summon_until = 0.0
        self.build_arena_features()
        tier = max(1, floor // 10)
        rank = self.boss_rank(floor)
        boss_lv = self.boss_level(floor)
        scale = self.boss_scale(rank)
        radius = round(21 * scale + 7)
        # El jefe 10 aguanta mas y necesita esquivas sostenidas.
        # Escala para conservar la jerarquia de megajefes sin alterar enemigos normales.
        base_hp = round((760 + 50 * math.sqrt(floor)) * (3.30 + rank*.62))
        hp = max(1, round(base_hp * ENEMY_DIFFICULTY))
        attack = (17.5 + 0.70 * floor**.35) * (1 + rank*.15) * 1.30 * ENEMY_DIFFICULTY
        defense = (3.9 + .28 * math.sqrt(floor)) * ENEMY_DIFFICULTY
        color = self.boss_palette(floor, rank)
        self.enemies = [dict(
            x=float(W/2), y=float(FIELD[3]-175-rank*12), name='OVERSEER',
            hp=hp, hpmax=hp, attack=attack, defense=defense,
            speed=3.05, color=color, orbit=(-1 if tier%2==0 else 1),
            next_fire=time.monotonic()+0.95, radius=radius, boss_tier=tier,
            boss_rank=rank, boss_scale=scale, boss_name=self.boss_name(rank),
            boss_lv=boss_lv,
            phase=1, charge_started=0.0, charge_until=0.0,
            next_burst=time.monotonic()+2.4,
            beam_started=0.0, beam_until=0.0, beam_heading=0.0,
            next_beam=time.monotonic()+4.7,
            beam_effect_until=0.0, beam_effect_heading=0.0,
            phase_flash_until=0.0, facing=(0.0, 1.0))]
        # Un jefe pendiente aparece al entrar; la placa solo es necesaria
        # si esa sala de jefe ya habia sido completada previamente.
        self.pending_enemies = self.enemies
        self.enemies = []
        self.message = ''
        self.message_until = 0.0
        if self.auto_summon_on_entry and self.transition_target is None:
            self.trigger_enemy_ambush(time.monotonic())

    def start_death_animation(self, now):
        self.state = 'dead'
        self.clone_pickup = None
        self.ally_clone = None
        self.heal_until = 0.0
        self.death_anim_start = now
        self.death_restart_at = now + 2.0
        self.notice('', 0.0)
        self.bullets.clear()
        self.enemy_bullets.clear()
        self.particles.clear()
        self.shield_flash = 0.0
        self.hit_invuln = 0.0
        self.player_vx = 0.0
        self.player_vy = 0.0
        self.death_particles = []
        colors = [GREEN, CYAN, '#d5ffeb', '#59ffb0', '#2a689a']
        for _ in range(58):
            ang = random.uniform(0, math.tau)
            speed = random.uniform(36, 155)
            lift = random.uniform(-62, 48)
            px = self.player_x + random.uniform(-13, 13)
            py = self.player_y + random.uniform(-18, 16)
            ttl = random.uniform(0.8, 2.0)
            size = random.uniform(1.8, 4.8)
            self.death_particles.append({
                'x': px, 'y': py,
                'vx': math.cos(ang) * speed,
                'vy': math.sin(ang) * speed + lift,
                'ttl': ttl, 'max_ttl': ttl,
                'size': size,
                'color': random.choice(colors),
            })

    def update_death_animation(self, dt):
        for p in self.death_particles[:]:
            p['ttl'] -= dt
            if p['ttl'] <= 0:
                self.death_particles.remove(p)
                continue
            p['x'] += p['vx'] * dt
            p['y'] += p['vy'] * dt
            p['vy'] -= 12.0 * dt

    def start_healing(self, now):
        """Vida real al maximo; el HUD la anima hasta llegar al 100%."""
        self.heal_from = clamp(self.life, 0.0, self.max_hp)
        self.life = self.max_hp
        self.heal_to = self.life
        self.heal_started_at = now
        self.heal_until = now + HEAL_SECONDS

    def healing_progress(self, now=None):
        if now is None:
            now = time.monotonic()
        if self.heal_until <= self.heal_started_at or now >= self.heal_until:
            return 1.0
        return clamp((now - self.heal_started_at) / HEAL_SECONDS, 0.0, 1.0)

    def display_life(self, now=None):
        """Progreso visual; el guardado siempre usa la vida ya curada."""
        if now is None:
            now = time.monotonic()
        if now < self.heal_until:
            p = self.healing_progress(now)
            p = p * p * (3 - 2 * p)
            return self.heal_from + (self.heal_to - self.heal_from) * p
        return self.life

    def draw_healing(self):
        now = time.monotonic()
        if now >= self.heal_until or self.state not in ('cleared', 'upgrade'):
            return
        p = self.healing_progress(now)
        c = self.canvas
        x, y = self.player_x, self.player_y
        colors = ('#154b46', '#1e8574', '#48d8ac', '#a8ffcc')
        # Anillos holograficos expansivos alrededor del personaje.
        for i in range(3):
            phase = (p * 2.0 + i / 3.0) % 1.0
            radius = 12.0 + phase * 53.0
            color = colors[max(0, min(3, int((1.0 - phase) * 4)))]
            c.create_oval(x-radius, y-radius*0.63,
                          x+radius, y+radius*0.63,
                          outline=color, width=2 if phase < 0.45 else 1)
        # Cruces de energia que ascienden, estilo regeneracion digital.
        for i in range(9):
            phase = (p * 2.3 + i / 9.0) % 1.0
            angle = (i / 9.0) * math.tau + self.frame * 0.8
            px = x + math.cos(angle) * (17 + phase * 22)
            py = y + math.sin(angle) * 9 - phase * 41
            size = max(1.0, 4.0 * (1.0 - phase))
            color = '#afffd0' if phase < 0.45 else '#44cb93'
            c.create_line(px - size, py, px + size, py,
                          fill=color, width=2)
            c.create_line(px, py - size, px, py + size,
                          fill=color, width=2)

    def emit_boss_energy_ring(self, enemy):
        """Descarga radial escalonada, visible y esquivable en las tres fases."""
        phase = enemy.get('phase', 1)
        rank = enemy.get('boss_rank', 0)
        count = (18, 23, 29)[phase - 1] + min(10, rank * 2)
        speed = (222, 257, 300)[phase - 1] + min(80, rank * 12)
        rotation = self.frame * 0.91 + enemy['boss_tier'] * 0.37
        for i in range(count):
            angle = rotation + math.tau * i / count
            vx, vy = math.cos(angle), math.sin(angle)
            start = enemy['radius'] + 9
            self.enemy_bullets.append([
                enemy['x'] + vx * start, enemy['y'] + vy * start,
                vx * speed, vy * speed,
                enemy['attack'] * (.40 if phase == 1 else .46 if phase == 2 else .53),
                0.0, '#ffb56e' if phase == 3 else '#ff8bdb',
                'boss_ring'
            ])
        for i in range(12):
            a = math.tau * i / 12
            self.particles.append([
                enemy['x'] + math.cos(a) * enemy['radius'],
                enemy['y'] + math.sin(a) * enemy['radius'],
                .35, '#ffae69' if phase == 3 else '#ff8bdc'
            ])

    def emit_boss_beam(self, enemy, now):
        """Rayo directo que atraviesa cajas; marca la direccion antes de golpear."""
        heading = enemy.get('beam_heading', 0.0)
        ux, uy = math.cos(heading), math.sin(heading)
        dx = self.player_x - enemy['x']
        dy = self.player_y - enemy['y']
        forward = dx * ux + dy * uy
        separation = abs(dx * uy - dy * ux)
        width = 19.0 + (6 if enemy.get('phase', 1) == 3 else 0)
        if 0 < forward < 740 and separation <= width + 9:
            # El golpe sucede una sola vez y permite apartarse durante el aviso.
            self.life -= max(8.0, enemy['attack'] * (1 - self.shield) * .95)
            self.shield_flash = max(self.shield_flash, .38)
            self.hit_invuln = max(self.hit_invuln, .16)
        enemy['beam_effect_heading'] = heading
        enemy['beam_effect_until'] = now + .24
        enemy['beam_until'] = 0.0
        enemy['beam_started'] = 0.0
        enemy['next_beam'] = now + (5.0, 4.3, 3.7)[enemy['phase'] - 1]
        enemy['next_burst'] = max(enemy['next_burst'], now + 1.20)
        for i in range(11):
            d = enemy['radius'] + 12 + i * 47
            self.particles.append([
                enemy['x'] + ux * d, enemy['y'] + uy * d,
                .31, '#ffb68a'
            ])

    def update_boss_attack(self, enemy, now):
        """Jefe con tres fases, ondas radiales y rayo telegrafiado."""
        if enemy['hp'] <= 0:
            return
        pct = enemy['hp'] / max(1.0, enemy['hpmax'])
        old_phase = enemy.get('phase', 1)
        phase = 3 if pct <= .31 else 2 if pct <= .67 else 1
        if phase > old_phase:
            enemy['phase'] = phase
            enemy['phase_flash_until'] = now + 1.10
            enemy['next_burst'] = min(enemy['next_burst'], now + .95)
            enemy['next_fire'] = max(enemy['next_fire'], now + .20)
        else:
            enemy['phase'] = phase
        beam_until = enemy.get('beam_until', 0.0)
        if beam_until:
            if now >= beam_until:
                self.emit_boss_beam(enemy, now)
            return
        ring_until = enemy.get('charge_until', 0.0)
        if ring_until:
            if now >= ring_until:
                self.emit_boss_energy_ring(enemy)
                enemy['charge_until'] = 0.0
                enemy['charge_started'] = 0.0
                enemy['next_burst'] = now + (3.85, 3.1, 2.45)[phase - 1]
            return
        if now >= enemy.get('next_beam', float('inf')):
            enemy['beam_started'] = now
            enemy['beam_until'] = now + (.94, .80, .69)[phase - 1]
            enemy['beam_heading'] = math.atan2(
                self.player_y - enemy['y'], self.player_x - enemy['x'])
            enemy['next_fire'] = max(enemy['next_fire'], enemy['beam_until'] + .12)
            return
        if now >= enemy.get('next_burst', float('inf')):
            warn = (.80, .66, .54)[phase - 1]
            enemy['charge_started'] = now
            enemy['charge_until'] = now + warn
            enemy['next_fire'] = max(enemy['next_fire'], now + warn + .16)

    def draw_boss_attack_warning(self, enemy):
        """Anillos de carga y linea del rayo que puede esquivarse a tiempo."""
        c = self.canvas
        now = time.monotonic()
        x, y = enemy['x'], enemy['y']
        phase = enemy.get('phase', 1)
        if phase >= 2:
            r = enemy['radius'] + 13 + 4 * math.sin(self.frame * 9)
            c.create_oval(x-r, y-r*.6, x+r, y+r*.6,
                          outline='#ff7b66' if phase == 3 else '#e66a58', width=2)
        if now < enemy.get('phase_flash_until', 0):
            r = enemy['radius'] + 25 + 18 * math.sin(self.frame * 6)**2
            c.create_oval(x-r, y-r, x+r, y+r, outline='#ffb866', width=2)
        beam_until = enemy.get('beam_until', 0.0)
        beam_active = beam_until and now < beam_until
        effect_active = now < enemy.get('beam_effect_until', 0.0)
        if beam_active or effect_active:
            angle = (enemy['beam_heading'] if beam_active
                     else enemy.get('beam_effect_heading', 0.0))
            ux, uy = math.cos(angle), math.sin(angle)
            nx, ny = -uy, ux
            width = 19 + (6 if phase == 3 else 0)
            ex, ey = x + ux * 740, y + uy * 740
            warn_color = '#e25676' if beam_active else '#fff1ba'
            if beam_active:
                for side in (-1, 1):
                    offset = side * width
                    c.create_line(x + nx*offset, y + ny*offset,
                                  ex + nx*offset, ey + ny*offset,
                                  fill=warn_color, width=2, dash=(9, 6))
                c.create_line(x, y, ex, ey, fill='#963447', width=2, dash=(5, 7))
            else:
                c.create_line(x, y, ex, ey, fill='#ff834f', width=8)
                c.create_line(x, y, ex, ey, fill='#fff5c7', width=3)
        until = enemy.get('charge_until', 0.0)
        if not until or now >= until:
            return
        duration = (.80, .66, .54)[phase - 1]
        fraction = clamp(1.0 - (until - now) / duration, 0.0, 1.0)
        radius = enemy['radius'] + 24 + 24 * fraction
        col = '#ffcd82' if phase == 3 else '#ff9adb'
        c.create_oval(x-radius, y-radius*.70, x+radius, y+radius*.70,
                      outline=col, width=3)
        c.create_oval(x-radius*.73, y-radius*.45,
                      x+radius*.73, y+radius*.45,
                      outline='#a86c9c', width=1)
        for i in range(10):
            a = self.frame * 1.3 + math.tau * i / 10
            sx = x + math.cos(a) * (radius-9)
            sy = y + math.sin(a) * (radius*.70-7)
            ex = x + math.cos(a) * radius
            ey = y + math.sin(a) * radius*.70
            c.create_line(sx, sy, ex, ey, fill=col, width=2)

    def player_fire(self, target):
        """Dispara a la posicion actual del enemigo seleccionado."""
        dx,dy = target['x']-self.player_x, target['y']-self.player_y
        length = max(1, math.hypot(dx,dy))
        self.bullets.append([self.player_x, self.player_y, dx/length*660, dy/length*660, self.damage, 0])

    def update(self, dt, now):
        if self.state == 'warp':
            return
        if self.state not in ('ready', 'summoning', 'fight', 'cleared', 'upgrade'): return
        vx = (('d' in self.keys or 'right' in self.keys) - ('a' in self.keys or 'left' in self.keys))
        vy = (('s' in self.keys or 'down' in self.keys) - ('w' in self.keys or 'up' in self.keys))
        length = max(1, math.hypot(vx, vy))
        # Limite fisico fijo. Los upgrades SPEED solo modifican enemigos.
        self.player_vx = self.player_move_speed * vx / length
        self.player_vy = self.player_move_speed * vy / length
        if vx or vy:
            self.player_facing = (vx / length, vy / length)
        proposed_x = self.player_x + self.player_vx * dt
        proposed_y = clamp(self.player_y + self.player_vy * dt, FIELD[1]+23, FIELD[3]-23)
        # DESCENDER por el portal inferior para avanzar;
        # SUBIR por el portal superior para regresar.
        # El cruce solo ocurre en la direccion elegida con puertas disponibles.
        doors_available = self.portals_available()
        player_margin = 10 if doors_available and self.state != 'upgrade' else 24
        left_bound, right_bound = self.arena_x_bounds(proposed_y, player_margin)
        self.player_x = clamp(proposed_x, left_bound, right_bound)
        self.player_y = proposed_y
        self.player_x, self.player_y = self.resolve_obstacles(
            self.player_x, self.player_y, 15)
        self.player_x = clamp(self.player_x, left_bound, right_bound)
        self.player_y = clamp(self.player_y, FIELD[1]+23, FIELD[3]-23)
        if (doors_available and self.state != 'upgrade' and
                self.door_progress >= .90):
            back_trigger = (abs(self.player_x-BACK_PORTAL_X) <= 72 and
                            self.player_y <= FIELD[1] + 26)
            next_trigger = (abs(self.player_x-NEXT_PORTAL_X) <= 72 and
                            self.player_y >= FIELD[3] - 26)
            if vy < 0 and back_trigger:
                if self.boss_stage:
                    self.start_transition(self.boss_floor, entry_side='bottom')
                    return
                if self.level == 1:
                    self.start_room(force_zero=True)
                    self.position_player_at_portal('bottom')
                    return
                if self.level > 1:
                    self.start_transition(self.level - 1, entry_side='bottom')
                    return
            if vy > 0 and next_trigger:
                if self.boss_stage:
                    self.start_transition(self.boss_floor + 1, entry_side='top')
                    return
                if self.is_level_zero:
                    target = 1
                elif self.intro_room:
                    target = (self.level + 1 if self.level_completed(self.level)
                              else self.level)
                else:
                    target = self.level + 1
                floor_before_target = target - 1
                if (floor_before_target >= 10 and floor_before_target % 10 == 0
                        and not self.boss_completed(floor_before_target)):
                    self.start_transition(('boss', floor_before_target), entry_side='top')
                else:
                    self.start_transition(target, entry_side='top')
                return
        self.shield_flash = max(0, self.shield_flash-dt)
        self.hit_invuln = max(0, self.hit_invuln-dt)
        # Permitir usar mejoras ANTES del combate, cuando el piso esta vacio,
        # y tambien despues de ganar. La plataforma se apaga con enemigos vivos.
        if self.state in ('ready', 'cleared', 'upgrade'):
            if not self.is_level_zero:
                on_pad = self.on_upgrade_pad(self.player_x, self.player_y)
                if self.state == 'upgrade':
                    # Salir del holograma devuelve al estado previo (ready o cleared).
                    # Solo confirma el guardado si se compro alguna mejora.
                    if not on_pad:
                        self.state = self.upgrade_return_state
                        self.upgrade_pad_lock = False
                        self.upgrade_open_started_at = 0.0
                        if self.upgrades_pending_save:
                            previous_life = self.life
                            self.life = self.max_hp
                            if self._save():
                                self.upgrades_pending_save = False
                            else:
                                self.life = previous_life
                    return
                if on_pad and not self.upgrade_pad_lock and not self.enemies:
                    self.upgrade_return_state = self.state
                    self.state = 'upgrade'
                    self.upgrade_open_started_at = now
                    self.upgrade_pad_lock = True
                    return
                if not on_pad:
                    self.upgrade_pad_lock = False
            if self.state == 'ready' and self.standing_on_trigger(self.player_x, self.player_y):
                self.trigger_enemy_ambush(now)
            return
        if self.state == 'summoning':
            if now >= self.summon_until:
                # Solo aqui se materializan los enemigos reales.
                self.enemies = self.pending_enemies
                self.pending_enemies = []
                for enemy in self.enemies:
                    enemy['next_fire'] = now + random.uniform(0.65, 1.12)
                self.state = 'fight'
                self.last_shot = now - 0.10
                self.hit_invuln = max(self.hit_invuln, 0.32)
                self.prepare_clone_pickup()
            return
        hazard_tick = self.hazard_damage(self.player_x, self.player_y)
        if hazard_tick > 0:
            self.life -= hazard_tick * dt
            self.shield_flash = max(self.shield_flash, 0.08)
        if self.clone_pickup is not None:
            self.collect_clone_pickup(now)
        if self.ally_clone is not None:
            self.update_ally_clone(dt, now)
        target = self.nearest_enemy()
        if target is not None:
            self.aim = (target['x'], target['y'])
            if now-self.last_shot >= .19:
                self.player_fire(target)
                self.last_shot = now
        for b in self.bullets[:]:
            b[0] += b[2]*dt; b[1] += b[3]*dt; b[5] += dt
            if not (FIELD[0]<b[0]<FIELD[2] and FIELD[1]<b[1]<FIELD[3]) or b[5]>1.6:
                self.bullets.remove(b); continue
            if any(distance(b[0], b[1], obs['x'], obs['y']) < obs['r'] + 4 for obs in self.obstacles):
                self.bullets.remove(b); continue
            for enemy in self.enemies[:]:
                if distance(b[0],b[1],enemy['x'],enemy['y']) < enemy['radius']+5:
                    dealt = max(1.0, b[4]-enemy['defense']*.6)
                    enemy['hp'] -= dealt
                    self.particles.append([b[0],b[1],.23,enemy['color']])
                    self.bullets.remove(b)
                    if enemy['hp'] <= 0:
                        self.enemies.remove(enemy)
                        for i in range(6): self.particles.append([enemy['x']+random.randrange(-12,13),enemy['y']+random.randrange(-12,13),.4,enemy['color']])
                    break
        for enemy in self.enemies:
            dx,dy = self.player_x-enemy['x'], self.player_y-enemy['y']
            dist = max(1,math.hypot(dx,dy))
            name = enemy['name']
            if name == 'OVERSEER':
                self.update_boss_attack(enemy, now)
            speed = self.enemy_movement_speed(enemy)
            # IA de cuatro roles: flanqueo, fuego lateral, presion y carga.
            # La rapidez real sigue siendo la del enemigo y se compara con la del jugador.
            preferred = {'DRONE': 92, 'GUARD': 145, 'TANK': 103, 'STRIKER': 32, 'OVERSEER': 145}[name]
            radial = 1.0 if dist > preferred + 12 else (-0.56 if dist < preferred - 27 else 0.0)
            strafe = {'DRONE': .80, 'GUARD': .56, 'TANK': .12, 'STRIKER': .14, 'OVERSEER': .38}[name]
            # Los enemigos no se paran en seco: rodean al personaje y ajustan su distancia.
            mx = dx/dist * radial - dy/dist * strafe * enemy['orbit']
            my = dy/dist * radial + dx/dist * strafe * enemy['orbit']
            length = max(1, math.hypot(mx,my))
            move_speed = speed
            move_vx = mx / length * move_speed
            move_vy = my / length * move_speed
            enemy['move_dx'] = move_vx
            enemy['move_dy'] = move_vy
            if abs(move_vx)+abs(move_vy) > 2:
                enemy['facing'] = (move_vx, move_vy)
            next_y = clamp(enemy['y'] + move_vy * dt, FIELD[1]+22, FIELD[3]-22)
            left_bound, right_bound = self.arena_x_bounds(next_y, enemy['radius'] + 6)
            enemy['x'] = clamp(enemy['x'] + move_vx * dt, left_bound, right_bound)
            enemy['y'] = next_y
            enemy['x'], enemy['y'] = self.resolve_obstacles(enemy['x'], enemy['y'], enemy['radius'])
            enemy['hp'] = max(1.0, enemy['hp'] - self.hazard_damage(enemy['x'], enemy['y']) * dt * 0.18)
            # Retardo y aviso muy breve antes del tiro, para permitir esquivar.
            if now >= enemy['next_fire'] and dist < 505:
                projectile_speed = {
                    'DRONE': 310.0, 'GUARD': 345.0, 'TANK': 265.0, 'STRIKER': 385.0, 'OVERSEER': 360.0
                }[name] + min(105, (self.level-1)*1.5)
                lead = min(.42, dist/projectile_speed * {
                    'DRONE': .34, 'GUARD': .52, 'TANK': .38, 'STRIKER': .66, 'OVERSEER': .58
                }[name])
                # Algunos rivales reconocen al clon como combatiente: puede
                # recibir dano y desaparecer, sin convertirlo en jugador.
                clone_target = (self.ally_clone is not None and
                                random.random() < 0.25 and
                                distance(enemy['x'], enemy['y'],
                                         self.ally_clone['x'], self.ally_clone['y']) < 415)
                if clone_target:
                    aim_x = self.ally_clone['x'] + self.ally_clone['vx']*lead
                    aim_y = self.ally_clone['y'] + self.ally_clone['vy']*lead
                else:
                    aim_x = self.player_x + self.player_vx*lead
                    aim_y = self.player_y + self.player_vy*lead
                heading = math.atan2(aim_y-enemy['y'],aim_x-enemy['x'])
                # Tanque: dos proyectiles en abanico; las otras unidades un disparo.
                if name == 'OVERSEER':
                    if (enemy.get('charge_until',0) > now or
                            enemy.get('beam_until',0) > now):
                        # Aviso: no solapar otras rafagas con el especial.
                        continue
                    phase = enemy.get('phase',1)
                    count = (7, 9, 11)[phase-1]
                    spread = (.42, .52, .63)[phase-1]
                    offsets = tuple(-spread + 2*spread*i/(count-1)
                                    for i in range(count))
                    projectile_speed *= (1.04, 1.16, 1.27)[phase-1]
                else:
                    offsets = (-.13, .13) if name == 'TANK' else (0.0,)
                for angle in offsets:
                    ang=heading+angle
                    self.enemy_bullets.append([
                        enemy['x'], enemy['y'], math.cos(ang)*projectile_speed,
                        math.sin(ang)*projectile_speed, enemy['attack'] *
                        (.66 if name == 'TANK' else (.72 if name == 'OVERSEER' else 1.0)), 0.0,
                        enemy['color']
                    ])
                cooldown = {'DRONE': 1.05, 'GUARD': 1.26, 'TANK': 1.69, 'STRIKER': .82, 'OVERSEER': .76}[name]
                if name == 'OVERSEER':
                    cooldown *= (1.0, .78, .60)[enemy.get('phase',1)-1]
                enemy['next_fire'] = now + max(.33, cooldown - min(.21,(self.level-1)*.006) + random.uniform(-.06,.10))
            if dist < enemy['radius'] + 15:
                self.life -= max(.1,enemy['attack']*(1-self.shield)) * dt * 1.3
                self.shield_flash = .12
            if (self.ally_clone is not None and
                    distance(enemy['x'], enemy['y'],
                             self.ally_clone['x'], self.ally_clone['y']) < enemy['radius'] + 15):
                self.damage_ally_clone(enemy['attack'] * dt * 0.83)
        for b in self.enemy_bullets[:]:
            b[0]+=b[2]*dt; b[1]+=b[3]*dt; b[5]+=dt
            if not (FIELD[0]<b[0]<FIELD[2] and FIELD[1]<b[1]<FIELD[3]) or b[5]>3.8:
                self.enemy_bullets.remove(b); continue
            if (not (len(b) > 7 and b[7] == 'boss_ring') and
                    any(distance(b[0], b[1], obs['x'], obs['y']) < obs['r'] + 5
                        for obs in self.obstacles)):
                self.enemy_bullets.remove(b); continue
            if (self.ally_clone is not None and
                    distance(b[0], b[1], self.ally_clone['x'], self.ally_clone['y']) < 16):
                self.damage_ally_clone(max(1.0, b[4]*0.7))
                self.enemy_bullets.remove(b)
                continue
            if distance(b[0],b[1],self.player_x,self.player_y)<17:
                if self.hit_invuln <= 0:
                    self.life -= max(.6,b[4]*(1-self.shield))
                    self.hit_invuln = .11  # Protege de dos impactos en el mismo fotograma.
                    self.shield_flash = .27
                self.enemy_bullets.remove(b)
        for part in self.particles[:]:
            part[2]-=dt
            if part[2]<=0: self.particles.remove(part)
        if self.life<=0:
            # Derrota: NO guardar ni borrar la partida; se desintegra y luego
            # recupera el ultimo checkpoint mediante GET simulado.
            self.start_death_animation(now)
        elif not self.enemies:
            # Al caer el cuarto enemigo, limpiar TODOS los efectos de combate:
            # proyectiles propios/enemigos, restos de destruccion y aro de impacto.
            # El suelo, las puertas y el menu de mejoras permanecen intactos.
            self.bullets.clear()
            self.enemy_bullets.clear()
            self.particles.clear()
            self.pending_enemies.clear()
            self.clone_pickup = None
            self.ally_clone = None
            self.shield_flash = 0.0
            self.hit_invuln = 0.0
            self.player_vx = 0.0
            self.player_vy = 0.0
            if self.boss_stage:
                first_boss_win = not self.boss_completed(self.boss_floor)
                boss_gain = 145 + 22 * (self.boss_floor // 10)
                gain = boss_gain if first_boss_win else max(1, round(boss_gain * 0.5))
                if first_boss_win:
                    # El jefe de 10 desbloquea el 11; el de 20, el 21, etc.
                    self.checkpoint_level = max(self.checkpoint_level, self.boss_floor)
                    self.max_level = max(self.max_level, self.boss_floor + 1)
                self.last_win_was_replay = not first_boss_win
            else:
                new = not self.level_completed(self.level)
                base_gain = 4 * (18 + 3 * (self.level - 1))
                if new:
                    self.checkpoint_level = max(self.checkpoint_level, self.level)
                    # En cada decena, el siguiente numero se desbloquea SOLO
                    # al derrotar al jefe intermedio (10->boss->11).
                    unlocked = self.level if self.level % 10 == 0 else self.level + 1
                    self.max_level = max(self.max_level, unlocked)
                    gain = base_gain
                else:
                    gain = max(1, int(round(base_gain * 0.5)))
                self.last_win_was_replay = not new
            # Una sola recarga: la siguiente victoria da EXP x2. Nunca se
            # duplica lo que el jugador ya tenia acumulado antes del combate.
            if self.xp_boost_ready:
                gain *= 2
                self.xp_boost_ready = False
                self.rest_seconds = 0.0
                self._rest_dirty = True
            self.last_level_xp = gain
            self.xp += gain
            # La EXP ganada solo se muestra cuando se abre el menu pisando
            # la plataforma; no dibujar +EXP flotando sobre la arena.
            self.message_until = 0.0
            # La vida real queda guardada al 100%; el HUD muestra la subida
            # progresiva y el personaje recibe un aura de curacion holografica.
            self.start_healing(now)
            # Finalizar SIN abrir automaticamente el menu de mejoras.
            self.state = 'cleared'
            self.door_progress = 0.0
            # Si el personaje esta sobre la plataforma al vencer, exigirle
            # salir y volver a entrar para no abrir el menu de inmediato.
            self.upgrade_pad_lock = True
            # La victoria se guarda automaticamente una sola vez.
            # Las compras posteriores se guardan cuando se deja la plataforma.
            self._save()


    def label(self,x,y,text,color=GREEN,size=12,anchor='center',bold=False):
        self.canvas.create_text(x,y,text=text,fill=color,font=(FONT,size,'bold' if bold else 'normal'),anchor=anchor)

    def rect(self,x1,y1,x2,y2,fill,outline='',width=1):
        self.canvas.create_rectangle(x1,y1,x2,y2,fill=fill,outline=outline,width=width)

    def draw_icon(self, x, y, kind, color, scale=1.0):
        c = self.canvas
        s = scale
        if kind == 'heart':
            c.create_oval(x-9*s, y-7*s, x+1*s, y+3*s, fill=color, outline='')
            c.create_oval(x-1*s, y-7*s, x+9*s, y+3*s, fill=color, outline='')
            c.create_polygon(x-12*s, y-1*s, x+12*s, y-1*s, x, y+14*s, fill=color, outline='')
        elif kind == 'shield':
            c.create_polygon(x, y-14*s, x+12*s, y-7*s, x+9*s, y+10*s, x, y+15*s, x-9*s, y+10*s, x-12*s, y-7*s,
                             fill=color, outline='#eaffff', width=1)
        elif kind == 'bolt':
            c.create_polygon(x-3*s, y-14*s, x+5*s, y-14*s, x+1*s, y-2*s, x+10*s, y-2*s,
                             x-4*s, y+15*s, x-1*s, y+3*s, x-9*s, y+3*s, fill=color, outline='')
        elif kind == 'xp':
            c.create_polygon(x, y-14*s, x+10*s, y-4*s, x+14*s, y+8*s, x, y+15*s, x-14*s, y+8*s, x-10*s, y-4*s,
                             fill=color, outline='#fff7d0', width=1)
        elif kind == 'back':
            c.create_line(x+13*s, y, x-10*s, y, fill=color, width=max(2,int(3*s)))
            c.create_line(x-10*s, y, x, y-10*s, fill=color, width=max(2,int(3*s)))
            c.create_line(x-10*s, y, x, y+10*s, fill=color, width=max(2,int(3*s)))
        elif kind == 'next':
            c.create_line(x-13*s, y, x+10*s, y, fill=color, width=max(2,int(3*s)))
            c.create_line(x+10*s, y, x, y-10*s, fill=color, width=max(2,int(3*s)))
            c.create_line(x+10*s, y, x, y+10*s, fill=color, width=max(2,int(3*s)))
        elif kind == 'plus':
            c.create_line(x-10*s, y, x+10*s, y, fill=color, width=max(2,int(4*s)))
            c.create_line(x, y-10*s, x, y+10*s, fill=color, width=max(2,int(4*s)))
        elif kind == 'play':
            c.create_polygon(x-8*s, y-11*s, x+12*s, y, x-8*s, y+11*s, fill=color, outline='')
        elif kind == 'speed':
            # Running/dash streaks to denote movement speed.
            c.create_line(x-13*s, y-7*s, x+5*s, y-7*s, fill=color, width=max(2,int(3*s)))
            c.create_line(x-8*s, y, x+13*s, y, fill=color, width=max(2,int(3*s)))
            c.create_line(x-13*s, y+7*s, x+4*s, y+7*s, fill=color, width=max(2,int(3*s)))
        elif kind == 'retry':
            c.create_arc(x-13*s, y-13*s, x+13*s, y+13*s, start=25, extent=280, style='arc', outline=color, width=max(2,int(3*s)))
            c.create_polygon(x+11*s, y-6*s, x+15*s, y-16*s, x+3*s, y-12*s, fill=color, outline='')
        elif kind == 'skull':
            c.create_oval(x-13*s, y-12*s, x+13*s, y+10*s, fill=color, outline='')
            c.create_oval(x-7*s, y-4*s, x-2*s, y+1*s, fill=BG, outline='')
            c.create_oval(x+2*s, y-4*s, x+7*s, y+1*s, fill=BG, outline='')
            c.create_rectangle(x-6*s, y+6*s, x+6*s, y+11*s, fill=color, outline='')
        elif kind == 'chip':
            c.create_rectangle(x-12*s, y-10*s, x+12*s, y+10*s, fill=color, outline='#d6fff4', width=1)
            for dx in (-15,-12,12,15):
                c.create_line(x+dx*s, y-6*s, x+dx*s, y+6*s, fill=color, width=1)
            for dy in (-13,-10,10,13):
                c.create_line(x-6*s, y+dy*s, x+6*s, y+dy*s, fill=color, width=1)

    def draw_player_original(self, x, y, palette, scale=1.0, facing=(1,0), move_vec=(0,0), boss=False, armed=True):
        """Modelo del soldado original, previo al rediseño de los seis personajes.

        Se conservan su silueta, mochila, pasos, arma, respiración y
        contorno holográfico. Únicamente se redondea el casco frontal.
        """
        c=self.canvas
        s=scale
        dx,dy=facing
        mag=max(1e-6, math.hypot(dx,dy)); dx/=mag; dy/=mag
        sx,sy=-dy,dx
        mvx,mvy=move_vec
        move_mag = math.hypot(mvx, mvy)
        pace = min(1.0, move_mag / 130.0)
        step_wave = math.sin(self.frame * 12.0 + x * 0.03 + y * 0.02) * 4.2 * pace
        idle = max(0.0, 1.0 - pace * 1.7)
        breathe = math.sin(self.frame * 3.3 + x * 0.018) * 1.6 * s * idle
        torso_lift = -abs(breathe) * 0.28
        boot, body, armor, skin, head, accent = palette
        back_view = dy < -0.55 and abs(dy) > abs(dx) * 0.75
        # Paleta holografica: conserva el acento del personaje, pero con
        # rellenos digitales oscuros y contornos de neon.
        glow = accent
        glow_soft = '#bdfdff'
        shell = '#0b1f28'
        shell2 = '#102b35'
        shell3 = '#123946'
        visor = '#d8ffff' if not boss else '#ffd0f0'
        yb = y + breathe
        # sombra / halo
        c.create_oval(x-15*s,y+12*s-abs(breathe)*0.3,x+15*s,y+19*s-abs(breathe)*0.3, fill='#041013', outline='')
        c.create_oval(x-16*s,y+10*s-abs(breathe)*0.25,x+16*s,y+18*s-abs(breathe)*0.25, outline=glow, width=1)
        # piernas animadas
        stride_a = step_wave
        stride_b = -step_wave
        left_hip = (x-4.8*s, yb+6*s+torso_lift)
        right_hip = (x+4.8*s, yb+6*s+torso_lift)
        left_foot = (x-7*s + dx*stride_a*0.55 + sx*1.1*s, y+16*s + abs(stride_a)*0.22)
        right_foot = (x+7*s + dx*stride_b*0.55 - sx*1.1*s, y+16*s + abs(stride_b)*0.22)
        c.create_line(left_hip[0], left_hip[1], left_foot[0], left_foot[1], fill=glow, width=max(2,int(3*s)))
        c.create_line(right_hip[0], right_hip[1], right_foot[0], right_foot[1], fill=glow, width=max(2,int(3*s)))
        c.create_line(left_foot[0]-2.0*s, left_foot[1], left_foot[0]+2.0*s, left_foot[1], fill=glow_soft, width=max(2,int(2*s)))
        c.create_line(right_foot[0]-2.0*s, right_foot[1], right_foot[0]+2.0*s, right_foot[1], fill=glow_soft, width=max(2,int(2*s)))
        # torso holografico con respiracion sutil cuando esta quieto.
        c.create_polygon(x-9*s,yb-2*s+torso_lift, x+9*s,yb-2*s+torso_lift, x+11*s,yb+8*s, x-11*s,yb+8*s, fill=shell, outline=glow, width=2)
        c.create_rectangle(x-6*s,yb+1*s,x+6*s,yb+11*s,fill=shell2, outline='')
        c.create_rectangle(x-4.4*s,yb+2.2*s,x+4.4*s,yb+9.6*s,fill='', outline=glow_soft, width=1)
        for yy in (-0.6, 2.4, 5.0, 7.6):
            c.create_line(x-7.2*s, yb+yy*s, x+7.2*s, yb+yy*s, fill=glow, width=1)
        if back_view:
            c.create_rectangle(x-4.8*s, yb+0.2*s, x+4.8*s, yb+8.8*s, fill=shell3, outline='')
            c.create_rectangle(x-2.8*s, yb+1.6*s, x+2.8*s, yb+7.8*s, fill='', outline=glow_soft, width=1)
            c.create_oval(x-6.3*s,yb-14.8*s,x+6.3*s,yb-0.8*s, fill=shell, outline=glow)
            c.create_arc(x-7.6*s,yb-16.1*s,x+7.6*s,yb-1.0*s, start=0, extent=180, style='pieslice', fill=shell2, outline=glow)
            c.create_rectangle(x-4.4*s, yb-8.8*s, x+4.4*s, yb-4.6*s, fill='', outline=glow_soft, width=1)
            c.create_line(x-4.0*s,yb-5.8*s,x+4.0*s,yb-5.8*s,fill=glow,width=max(1,int(2*s)))
        else:
            # Conserva el casco del player original, pero ahora el frente es
            # completamente curvado: desaparece la placa cuadrada de arriba.
            c.create_oval(x-7.6*s, yb-16.4*s, x+7.6*s, yb-0.9*s,
                          fill=shell, outline=glow, width=2)
            c.create_oval(x-6.8*s, yb-16.0*s, x+6.8*s, yb-7.3*s,
                          fill=shell2, outline='#70eddf', width=1)
            c.create_oval(x-5.1*s, yb-11.1*s, x+5.1*s, yb-6.4*s,
                          fill='#153c49', outline='#9cf9ff', width=1)
            c.create_line(x-3.9*s, yb-9.0*s, x+3.9*s, yb-9.0*s,
                          fill=visor, width=max(1, int(2*s)))
            c.create_arc(x-5.6*s, yb-8.5*s, x+5.6*s, yb-1.5*s,
                         start=190, extent=160, style='arc',
                         outline=glow, width=1)
        # Brazos / arma holograficos.
        arm_color = glow
        rifle_core = '#83f5ff'
        rifle_shell = '#1b5b66'
        if not armed:
            c.create_line(x-8*s, yb+1*s, x-10*s, yb+10*s, fill=arm_color, width=max(2, int(3*s)))
            c.create_line(x+8*s, yb+1*s, x+10*s, yb+9*s, fill=arm_color, width=max(2, int(3*s)))
            c.create_line(x+13*s, yb+5*s, x+13*s, yb+17*s, fill=rifle_core, width=max(2, int(3*s)))
            c.create_line(x+10.8*s, yb+5*s, x+16.8*s, yb+5*s, fill=glow_soft, width=max(1, int(2*s)))
            c.create_rectangle(x+10*s, yb+11*s, x+15*s, yb+14*s, fill='', outline=rifle_shell, width=1)
        else:
            shoulder_y = yb+0.8*s
            front_hand_x = x+dx*10*s
            front_hand_y = yb-1*s+dy*10*s
            rear_shoulder_x = x-8*s
            front_shoulder_x = x+8*s
            c.create_line(rear_shoulder_x,shoulder_y,rear_shoulder_x-6*s-sx*2*s,shoulder_y+5*s, fill=arm_color, width=max(2,int(3*s)))
            c.create_line(front_shoulder_x,shoulder_y,front_hand_x,front_hand_y, fill=arm_color, width=max(2,int(3*s)))
            muzzle_x = front_hand_x + dx*14*s
            muzzle_y = front_hand_y + dy*14*s
            if back_view:
                c.create_line(front_hand_x-1.0*s, front_hand_y-1.0*s, muzzle_x, muzzle_y-1.5*s, fill=rifle_core, width=max(2,int(3*s)))
            else:
                c.create_line(front_hand_x,front_hand_y, muzzle_x, muzzle_y, fill=rifle_core, width=max(2,int(3*s)))
            c.create_line(front_hand_x, front_hand_y, muzzle_x, muzzle_y, fill=glow_soft, width=max(1,int(1*s)))
        c.create_oval(x-2*s,yb-1*s,x+2*s,yb+3*s, fill=glow, outline='')
        # Destellos laterales para que todo el personaje se vea como un holograma.
        c.create_line(x-10*s, yb-3*s, x-13*s, yb+5*s, fill=glow, width=1)
        c.create_line(x+10*s, yb-3*s, x+13*s, yb+5*s, fill=glow, width=1)

    def draw_player_lateral(self, x, y, palette, scale=1.0, direction=1,
                            move_vec=(0,0), armed=True, aim_vec=None):
        """Perfil lateral del PLAYER original, espejado a izquierda o derecha.

        La forma del cuerpo, el casco redondeado, las piernas y la posicion
        del fusil se dibujan de perfil. No modifica los modelos enemigos.
        """
        c = self.canvas
        s = float(scale)
        side = 1 if direction >= 0 else -1
        speed = math.hypot(*move_vec)
        walk = clamp(speed / 115.0, 0.0, 1.0)
        cycle = self.frame * 12.2
        stride = math.sin(cycle) * 5.3 * walk
        step_lift = max(0.0, math.sin(cycle)) * 2.1 * walk
        other_lift = max(0.0, -math.sin(cycle)) * 2.1 * walk
        breathe = math.sin(self.frame * 3.3 + x * 0.018) * 1.5 * (1.0-walk)
        bounce = -abs(math.sin(cycle)) * 0.65 * walk
        by = breathe + bounce
        neon = palette[-1]
        ice = '#c8ffff'
        shell = '#0b1f28'
        plate = '#103440'
        chest = '#175364'

        def pt(f, up):
            return (x + side*f*s, y + up*s)

        def line(f1, y1, f2, y2, color=neon, width=2):
            a, b = pt(f1, y1), pt(f2, y2)
            return c.create_line(a[0], a[1], b[0], b[1],
                                 fill=color, width=max(1, round(width*s)))

        def polygon(pts, fill=shell, outline=neon, width=1):
            xy = []
            for f, h in pts:
                xy.extend(pt(f, h))
            return c.create_polygon(*xy, fill=fill, outline=outline,
                                    width=max(1, round(width*s)))

        def oval(f1, h1, f2, h2, fill='', outline=neon, width=1):
            a, b = pt(f1, h1), pt(f2, h2)
            return c.create_oval(min(a[0],b[0]), min(a[1],b[1]),
                                 max(a[0],b[0]), max(a[1],b[1]),
                                 fill=fill, outline=outline,
                                 width=max(1, round(width*s)))

        # Una sombra ovalada mantiene ancladas las botas al suelo 3D.
        c.create_oval(x-15*s, y+12*s, x+15*s, y+19*s,
                      fill='#041013', outline='')
        c.create_oval(x-17*s, y+11*s, x+17*s, y+19*s,
                      outline='#236a65', width=1)

        # Pierna lejana, seguida de la pierna cercana: alternancia al caminar.
        line(-3.5, 5+by, -5.5+stride, 11+other_lift, '#25748a', 3)
        line(-5.5+stride, 11+other_lift, -7+stride, 16+other_lift,
             '#51aac5', 3)
        line(-11+stride, 16+other_lift, -3+stride, 16+other_lift,
             '#79d9ee', 2)
        line(2.5, 5+by, 4-stride, 11+step_lift, neon, 3)
        line(4-stride, 11+step_lift, 6-stride, 16+step_lift,
             '#80ffe0', 3)
        line(1-stride, 16+step_lift, 10-stride, 16+step_lift,
             ice, 2)

        # Mochila en el lado posterior: deja claro hacia donde mira el jugador.
        polygon([(-8,-5+by),(-12,-4+by),(-12,6+by),(-7,8+by)],
                '#0b2c38', '#67c7dc', 1)
        line(-11,-1+by,-11,5+by, '#5bffe1', 1)
        oval(-12,1+by,-9,4+by,'#64ddda','',1)

        # Cuerpo visto de costado: armadura estrecha, pecho al frente.
        polygon([(-7,-5+by),(3,-7+by),(8,-4+by),
                 (7,4+by),(4,9+by),(-6,8+by)],
                shell, neon, 2)
        polygon([(1,-5+by),(7,-3+by),(6,5+by),(2,7+by)],
                plate, '#80ffe2', 1)
        line(-5,1+by,6,2+by,'#2b8c96',1)
        line(-4,5+by,5,5+by,'#45bdbe',1)
        oval(2,-2+by,4,1+by,'#adfff0','',1)
        line(-6,8+by,4,9+by,'#33879b',2)

        # Casco frontal antiguo, redondeado y en autentico perfil.
        oval(-5.6,-17+by,8.1,-3.4+by, shell, '#79ffe0', 2)
        oval(-4.5,-15.8+by,6.1,-6.7+by, plate, '#46b6c1', 1)
        # La visera sobresale hacia el sentido de avance, igual en espejo.
        polygon([(3,-12+by),(9,-11.6+by),(11,-9.2+by),
                 (8,-6.4+by),(3,-7.4+by)],
                chest, '#b7ffff', 1)
        line(4,-9.4+by,10,-9.1+by, ice, 2)
        oval(-5.8,-10+by,-2.0,-5.5+by, '#1d6d7a','#8fe9e7',1)
        line(-2.0,-3.9+by,5.0,-3.6+by,neon,1)

        # Brazo lejano sombreado, brazo cercano articulado.
        line(-4,-1+by,-7,5+by, '#327f94', 3)
        line(-7,5+by,-2,9+by, '#5fb8c7', 2)
        line(5,-1+by,8,3+by, neon, 3)
        line(8,3+by,10,2+by, '#a1fff0', 2)

        if armed:
            # Apunta al enemigo real aunque el cuerpo mire al lado del movimiento.
            if aim_vec is None:
                ax, ay = float(side), 0.0
            else:
                ax, ay = aim_vec
            length = max(0.001, math.hypot(ax, ay))
            ax, ay = ax/length, ay/length
            hand = pt(10, 2+by)
            muzzle = (hand[0] + ax*19*s, hand[1] + ay*19*s)
            c.create_line(hand[0], hand[1], muzzle[0], muzzle[1],
                          fill='#297e92', width=max(2, round(4*s)))
            c.create_line(hand[0], hand[1], muzzle[0], muzzle[1],
                          fill='#c2ffff', width=max(1, round(2*s)))
            c.create_oval(muzzle[0]-1.6*s,muzzle[1]-1.6*s,
                          muzzle[0]+1.6*s,muzzle[1]+1.6*s,
                          fill='#e1ffff', outline='')
        else:
            # Rifle enfundado contra la cadera, no flotando enfrente.
            line(-10,5+by,-10,17+by, '#7ddbe7', 3)
            line(-12,6+by,-7,6+by, ice, 2)
            line(-12,13+by,-8,13+by, '#258698', 1)

        # Pequeños trazos de energía en las articulaciones del holograma.
        oval(5.4,-2.6+by,8.5,0.6+by, '#9bffe6','',1)
        line(-5,-1+by,-8,1+by,neon,1)

    def draw_character(self, x, y, palette, scale=1.0, facing=(1,0),
                       move_vec=(0,0), boss=False, armed=True,
                       model='GUARD', variant=0):
        """Seis siluetas originales, trazadas y animadas con Tkinter (sin imagenes)."""
        c = self.canvas
        s = float(scale)
        vx, vy = move_vec
        speed = math.hypot(vx, vy)
        idle = clamp(1.0 - speed / 24.0, 0.0, 1.0)
        cycle = self.frame
        breath = math.sin(cycle * 2.85 + (x+y)*0.003) * 1.5 * idle
        stride = math.sin(cycle * 12.0 + x*0.02) * min(1., speed/95.) * 4.0
        dx, dy = facing
        leng = max(0.001, math.hypot(dx, dy))
        dx, dy = dx/leng, dy/leng
        behind = dy < -0.55 and abs(dy) > abs(dx) * .75
        accent = palette[-1]
        body_dark = '#0b1e26'
        plate_dark = '#102d38'
        neon_white = '#d8ffff'

        def line(ax, ay, bx, by, color=None, width=2, dash=None):
            kw = {'fill': color or accent, 'width': max(1, int(width*s))}
            if dash:
                kw['dash'] = dash
            return c.create_line(x+ax*s, y+ay*s, x+bx*s, y+by*s, **kw)

        def poly(coords, color=body_dark, outline=None, width=2):
            xy = []
            for ax, ay in coords:
                xy += [x+ax*s, y+ay*s]
            return c.create_polygon(*xy, fill=color, outline=outline if outline is not None else accent,
                                    width=max(1, int(width*s)))

        def oval(ax, ay, bx, by, color='', outline=None, width=2):
            return c.create_oval(x+ax*s, y+ay*s, x+bx*s, y+by*s,
                                 fill=color, outline=outline if outline is not None else accent,
                                 width=max(1, int(width*s)))

        def leg_pair(spread=5, length=17, thick=3):
            # El desplazamiento alterno da pasos reales; en reposo respira el torso.
            line(-spread, 6+breath, -spread-2-stride, length, accent, thick)
            line(spread, 6+breath, spread+2+stride, length, accent, thick)
            line(-spread-5-stride, length, -spread+2-stride, length, neon_white, 2)
            line(spread-2+stride, length, spread+5+stride, length, neon_white, 2)

        def aim_weapon(ax, ay, reach=25, col='#9cfaff'):
            if armed:
                bx = ax + dx*reach
                by = ay + dy*reach
                line(ax, ay, bx, by, col, 3)
                line(bx-dx*5, by-dy*5, bx, by, neon_white, 1)
                oval(bx-1.7, by-1.7, bx+1.7, by+1.7, '#bbffff', outline='')
            else:
                line(ax, ay, ax, ay+12, '#7ed2de', 3)
                line(ax-3, ay+4, ax+3, ay+4, neon_white, 1)

        # Suelo: halo dinamico para separar las figuras holograficas de la arena.
        shadow_width = 21 if model == 'TANK' else 26 if model == 'OVERSEER' else 16
        oval(-shadow_width, 13, shadow_width, 19, '#051217', outline='')
        oval(-shadow_width-2, 12, shadow_width+2, 19, '', '#25505c', 1)

        if model == 'PLAYER':
            # Explorador futurista: botas, cintura estrecha, chaleco, casco y rifle.
            leg_pair(5, 18, 3)
            poly([(-12,-4+breath),(-6,-7+breath),(6,-7+breath),(12,-4+breath),
                  (8,9+breath),(-8,9+breath)], '#0c2331', '#64ffc5', 2)
            poly([(-7,-3+breath),(0,-5+breath),(7,-3+breath),(5,6+breath),
                  (0,9+breath),(-5,6+breath)], '#123b49', '#8affd8', 1)
            oval(-3,0+breath,3,6+breath, '#8cffe5', '#cefff5', 1)
            line(-9,-2+breath,-15,4+breath,'#62dff5',3)
            line(-15,4+breath,-10,11+breath,'#62dff5',2)
            line(9,-2+breath,14,5+breath,'#62dff5',3)
            if behind:
                poly([(-8,-13+breath),(8,-13+breath),(7,-2+breath),(-7,-2+breath)],
                     '#0b2936','#89ffe2',1)
                line(-4,-7+breath,4,-7+breath,'#50ffd0',2)
            else:
                # Cabeza frontal mas redondeada y menos cuadrada.
                oval(-7.8,-17.6+breath,7.8,-3.6+breath,'#0c2a35','#6dfddd',2)
                c.create_arc(x-8.6*s, y+(-17.9+breath)*s, x+8.6*s, y+(-8.1+breath)*s,
                             start=0, extent=180, style='pieslice',
                             fill='#153544', outline='#9cf9ff', width=max(1, int(1*s)))
                oval(-5.9,-12.2+breath,5.9,-7.2+breath,'', '#c8ffff',1)
                line(-4.6,-9.7+breath,4.6,-9.7+breath,neon_white,2)
                line(-3.0,-6.5+breath,3.0,-6.5+breath,'#77ffe2',1)
            # Armadura angular de hombros, antena unica y arma activa/guardada.
            poly([(-13,-6+breath),(-6,-7+breath),(-10,-1+breath),(-15,0+breath)],
                 '#184452','#7defff',1)
            poly([(6,-7+breath),(13,-6+breath),(15,0+breath),(10,-1+breath)],
                 '#184452','#7defff',1)
            line(4,-17+breath,6,-22+breath,'#6cf9d8',1)
            oval(4,-24+breath,8,-20+breath,'#b7fff3', outline='')
            aim_weapon(14,5+breath,23,'#b1fcff')

        elif model == 'DRONE':
            # Dron aereo sin piernas: orbe flotante, dos turbinas y antenas.
            float_y = -6 + math.sin(cycle*4.5+x*.02)*3.0
            oval(-23,float_y-2,23,float_y+12,'', '#205d72',1)
            for side in (-1,1):
                side_x = 20*side
                poly([(side_x-10,float_y-7),(side_x+10,float_y-7),
                      (side_x+12,float_y-1),(side_x-12,float_y-1)],
                     '#122f43', '#c1a0ff',1)
                oval(side_x-9,float_y-7,side_x+9,float_y-2,
                     '', '#d7baff',1)
                line(side_x-8,float_y-4,side_x+8,float_y-4,
                     '#f0d2ff',1)
                line(13*side,float_y+1,22*side,float_y-3,accent,3)
            # Torso en rombo/cuerpo insectoide.
            poly([(0,float_y-15),(13,float_y-8),(15,float_y+5),
                  (0,float_y+15),(-15,float_y+5),(-13,float_y-8)],
                 '#10223e',accent,2)
            oval(-7,float_y-7,7,float_y+7,'#37234b','#f0afff',1)
            oval(-3,float_y-3,3,float_y+3,'#f5dfff','#faf1ff',1)
            line(-4,float_y-15,-10,float_y-25,accent,2)
            line(4,float_y-15,10,float_y-25,accent,2)
            for side in (-1,1):
                oval(8*side-2,float_y-9,8*side+2,float_y-5,'#d1a9ff',outline='')
            # Propulsor descendente intermitente.
            h = 9 + 5*(.5+.5*math.sin(cycle*11.0))
            line(-5,float_y+13,-3,float_y+13+h,'#713ba8',1)
            line(5,float_y+13,3,float_y+13+h,'#d8b3ff',1)

        elif model == 'GUARD':
            # Centinela: escudo rectangular visible y casco pesado.
            leg_pair(7,18,4)
            poly([(-11,-5+breath),(11,-5+breath),(12,9+breath),
                  (3,12+breath),(-10,9+breath)],'#162b39','#ff959f',2)
            poly([(-8,-3+breath),(8,-3+breath),(7,6+breath),
                  (-8,6+breath)], '#3b2634','#ffc1c8',1)
            line(-6,1+breath,6,1+breath,'#ffb4c8',1)
            # Protector lateral proyectado; muy distinto del jugador.
            poly([(-20,-2+breath),(-10,-5+breath),(-11,13+breath),
                  (-20,17+breath),(-26,9+breath)],
                 '#1a2430','#ff9cb1',2)
            line(-22,1+breath,-15,13+breath,'#ff5c85',2)
            oval(-7,-17+breath,8,-4+breath,'#232c39','#ff8ea1',2)
            poly([(-9,-15+breath),(10,-15+breath),(9,-8+breath),(-9,-8+breath)],
                 '#592e3d','#f9b6bd',1)
            line(-6,-8+breath,7,-8+breath,neon_white,2)
            line(10,-2+breath,15,7+breath,accent,3)
            aim_weapon(16,2+breath,24,'#ffd2da')

        elif model == 'TANK':
            # Tanque: mech ancho, caderas reforzadas, cañones dobles.
            for side in (-1,1):
                t = stride*0.6*side
                poly([(side*8,6+breath),(side*18,8+breath),
                      (side*20+t,20),(side*8+t,20)],
                     '#302717','#ffc778',2)
                line(side*8+t,20,side*24+t,20,'#fff0ba',4)
            poly([(-20,-9+breath),(-13,-15+breath),(13,-15+breath),
                  (20,-9+breath),(17,12+breath),(-17,12+breath)],
                 '#362b18','#ffd27e',3)
            poly([(-12,-7+breath),(12,-7+breath),(10,8+breath),
                  (-10,8+breath)],'#4b3720','#ffe3ab',1)
            oval(-6,-3+breath,6,9+breath,'#6c5422','#ffdf8c',2)
            oval(-3,0+breath,3,6+breath,'#fff7c4',outline='')
            # Casco plano en forma de torreta.
            poly([(-12,-17+breath),(-8,-22+breath),(8,-22+breath),
                  (12,-17+breath),(9,-12+breath),(-9,-12+breath)],
                 '#4c351b','#ffe0a4',2)
            line(-7,-16+breath,7,-16+breath,neon_white,3)
            for side in (-1,1):
                poly([(side*15,-15+breath),(side*26,-15+breath),
                      (side*26,1+breath),(side*17,2+breath)],
                     '#402d1d','#ffd387',2)
                line(side*20,-14+breath,side*20,0+breath,'#ffeead',2)
                line(side*22,0+breath,side*26,8+breath,'#ffaa59',3)
            aim_weapon(20,2+breath,31,'#ffe9bc')

        elif model == 'STRIKER':
            # Asaltante agil: delgado, hombros en punta, cuchillas laterales.
            leg_pair(4,20,2)
            poly([(-8,-8+breath),(0,-12+breath),(8,-8+breath),
                  (6,9+breath),(0,12+breath),(-6,9+breath)],
                 '#251727','#ff638f',2)
            poly([(-5,-4+breath),(0,0+breath),(5,-4+breath),
                  (2,7+breath),(-2,7+breath)],
                 '#5a203d','#ffa2c8',1)
            for side in (-1,1):
                poly([(side*7,-7+breath),(side*18,-12+breath),
                      (side*12,-1+breath)], '#38213e','#ff7aa9',2)
                line(side*9,0+breath,side*18,8+breath,'#ffadc3',2)
                line(side*17,7+breath,side*(22+3*math.sin(cycle*7)),18+breath,
                     '#ff4788',3)
            # Cabeza triangular/mascara angular.
            poly([(-7,-19+breath),(7,-19+breath),(9,-10+breath),
                  (0,-6+breath),(-9,-10+breath)],
                 '#2c1932','#ff79ae',2)
            line(-5,-12+breath,5,-12+breath,'#fff0ff',2)
            line(-15,9+breath,-23,16+breath,'#963e91',1)
            line(15,9+breath,23,16+breath,'#963e91',1)
            if armed:
                aim_weapon(12,3+breath,23,'#ffabdb')

        elif model == 'OVERSEER':
            # Modelo jefe: constructo mecanico con piezas especiales por decena.
            tier = max(1, int(variant))
            style = (tier - 1) % 5
            hue = accent
            bob = math.sin(cycle*2.5)*2.0
            # Patas articuladas pesadas.
            for side in (-1,1):
                poly([(side*8,9+bob),(side*19,12+bob),
                      (side*22,25+bob),(side*10,25+bob)],
                     '#211b30',hue,2)
                line(side*12,24+bob,side*27,24+bob,neon_white,3)
            # Tronco hexagonal, pecho con nucleo luminoso.
            poly([(-17,-18+bob),(-9,-25+bob),(9,-25+bob),
                  (17,-18+bob),(19,13+bob),(0,19+bob),(-19,13+bob)],
                 '#171927',hue,3)
            poly([(-12,-11+bob),(0,-16+bob),(12,-11+bob),
                  (10,10+bob),(0,13+bob),(-10,10+bob)],
                 '#252035',neon_white,1)
            core_phase = 0.5+0.5*math.sin(cycle*5+tier)
            core_size = 5 + 2*core_phase
            poly([(0,-core_size+bob),(core_size,0+bob),(0,core_size+bob),
                  (-core_size,0+bob)], '#d8ffff', hue,1)
            # Cabeza y visor cuadrado robotico.
            poly([(-12,-32+bob),(12,-32+bob),(15,-19+bob),
                  (6,-16+bob),(-6,-16+bob),(-15,-19+bob)],
                 '#251627',hue,3)
            line(-9,-24+bob,9,-24+bob,neon_white,3)
            line(-14,6+bob,14,6+bob,hue,1)
            # Seis variantes mecanicas base, para que cada jefe cambie de silueta.
            if style == 0:
                # Emperador: cuernos y hombreras en forma de corona.
                for side in (-1,1):
                    poly([(side*11,-29+bob),(side*20,-49+bob),
                          (side*24,-19+bob)], '#3a1a2b',hue,2)
                    poly([(side*16,-16+bob),(side*35,-24+bob),
                          (side*30,0+bob),(side*19,6+bob)],
                         '#2e1527',hue,2)
                    line(side*27,-5+bob,side*33,16+bob,hue,3)
            elif style == 1:
                # Guardián orbital: doble aro giroscopico, dos turbinas.
                oval(-31,-38+bob,31,16+bob,'', hue,1)
                oval(-25,-30+bob,25,9+bob,'', '#bc9cff',1)
                for side in (-1,1):
                    oval(side*26-8,-15+bob,side*26+8,0+bob,'#2d1d44',hue,2)
                    line(side*26,-19+bob,side*26,-30+bob,hue,2)
            elif style == 2:
                # Arácnido: cuatro brazos segmentados asimétricos.
                for side in (-1,1):
                    line(side*17,-10+bob,side*31,-20+bob,hue,4)
                    line(side*31,-20+bob,side*39,-2+bob,neon_white,3)
                    line(side*17,8+bob,side*30,20+bob,hue,4)
                    line(side*30,20+bob,side*43,10+bob,neon_white,3)
            elif style == 3:
                # Ala-fantasma: dos paneles solares oscilantes.
                wing = 2*math.sin(cycle*3+tier)
                for side in (-1,1):
                    poly([(side*15,-20+bob),(side*(41+wing),-39+bob),
                          (side*37,8+bob),(side*19,11+bob)],
                         '#132831',hue,2)
                    line(side*19,-10+bob,side*37,-28+bob,neon_white,2)
            else:
                # Monolito: dos enormes escudos y emisores verticales.
                for side in (-1,1):
                    poly([(side*22,-26+bob),(side*36,-26+bob),
                          (side*40,23+bob),(side*23,16+bob)],
                         '#2b1c2e',hue,3)
                    line(side*29,-17+bob,side*31,14+bob,neon_white,2)
                    oval(side*28-3,-22+bob,side*28+3,-16+bob,'#e9ffff',outline='')
            # Identidad unica para cada decena, inclusive si el estilo vuelve a rotar:
            # cantidad y posicion angular de satelites aumenta con la decena.
            # Cambiar geometria cada diez pisos (tambien tras la decena 160).
            sat_count = 3 + (tier % 17)
            orbit_r = 33 + 2 * (tier % 19)
            for i in range(sat_count):
                ang = cycle*.8*(1 if tier%2 else -1) + i*math.tau/sat_count
                px = math.cos(ang)*orbit_r
                py = -4+bob + math.sin(ang)*orbit_r*.52
                oval(px-1.6,py-1.6,px+1.6,py+1.6,
                     '#efffff' if i%3==0 else hue,outline='')
            line(0,-32+bob,0,-36 - min(10,tier)*.6+bob,hue,2)
            oval(-2,-40-min(10,tier)*.6+bob,2,-36-min(10,tier)*.6+bob,
                 '#d9ffff',outline='')
        else:
            raise ValueError('Modelo no reconocido: '+str(model))

        # Vista posterior propia de los humanoides enemigos. Cuando se mueven
        # hacia arriba, no se ven los ojos de la mascara frontal.
        if behind and model in ('GUARD', 'TANK', 'STRIKER'):
            if model == 'GUARD':
                helmet_w,helmet_h = 10,17
                pack_width = 7
            elif model == 'TANK':
                helmet_w,helmet_h = 13,21
                pack_width = 11
            else:
                helmet_w,helmet_h = 9,19
                pack_width = 5
            poly([(-helmet_w,-helmet_h+breath),(helmet_w,-helmet_h+breath),
                  (helmet_w-2,-6+breath),(-helmet_w+2,-6+breath)],
                 '#122734',accent,2)
            line(-helmet_w+3,-10+breath,helmet_w-3,-10+breath,
                 '#9dfbff',2)
            poly([(-pack_width,-3+breath),(pack_width,-3+breath),
                  (pack_width,7+breath),(-pack_width,7+breath)],
                 '#112b39',accent,1)
            line(-pack_width+2,1+breath,pack_width-2,1+breath,
                 '#c2fff8',1)

    def draw_boss_rank_effect(self, e, foreground=False):
        """Seis clases de jefe: con cada 100 / 1000 / ... cambia silueta y tamano."""
        rank = e.get('boss_rank', 0)
        if rank == 0:
            return
        c = self.canvas
        x, y = e['x'], e['y']
        s = e.get('boss_scale', 1.22)
        glow = e['color']
        t = self.frame
        def line(a,b,d,f,col=None,width=2):
            return c.create_line(x+a*s,y+b*s,x+d*s,y+f*s,fill=col or glow,width=width)
        def poly(points,fill='',color=None,width=2):
            q=[]
            for px,py in points: q.extend([x+px*s,y+py*s])
            return c.create_polygon(*q,fill=fill,outline=color or glow,width=width)
        def ellipse(rx,ry,shift=0,col=None,width=2):
            return c.create_oval(x-rx*s,y+shift*s-ry*s,x+rx*s,y+shift*s+ry*s,
                                 fill='',outline=col or glow,width=width)
        if not foreground:
            if rank == 1:  # Centurion: astas laterales de energia.
                for side in (-1,1):
                    poly([(side*22,-26),(side*45,-40),(side*41,8),(side*25,13)],'',glow,2)
                    line(side*27,-20,side*37,0,'#f1fffc',2)
            elif rank == 2:  # Titan: propulsores alados.
                for side in (-1,1):
                    poly([(side*18,-28),(side*63,-43),(side*56,3),(side*20,11)],'',glow,3)
                    line(side*23,-17,side*53,-33,'#c7f8ff',2)
                    ellipse(16,23, -11,glow,1)
            elif rank == 3:  # Leviatan: seis brazos mecanicos y antenas.
                for side in (-1,1):
                    for dy in (-18,0,18):
                        line(side*17,dy,side*45,dy-16,glow,4)
                        line(side*45,dy-16,side*57,dy-6,'#ffffff',2)
            elif rank == 4:  # Omega: monolitos de armadura y grandes aros.
                for side in (-1,1):
                    poly([(side*30,-49),(side*55,-53),(side*57,28),(side*31,23)],'',glow,3)
                    line(side*43,-45,side*43,22,'#d9ffff',3)
                ellipse(70,48,-3,glow,3)
            else:  # Singularidad: nucleo, aros y rayos orbitales.
                for side in (-1,1):
                    poly([(side*33,-55),(side*74,-66),(side*82,38),(side*32,30)],'',glow,3)
                    for i in range(3):
                        yy=-44+i*35
                        line(side*49,yy,side*69,yy+math.sin(t*4+i)*6,'#f3ffff',3)
                ellipse(93,57,-8,glow,3)
                ellipse(65,81,-6,'#c6f8ff',2)
        else:
            if rank == 1:
                # Emisores rotativos exclusivos del 100.
                for side in (-1,1):
                    line(side*26,-30,side*44,-45,glow,3)
                    ellipse(12,8,-30,'#eaffff',1)
            elif rank == 2:
                ellipse(32,45,-10,glow,2)
                for i in range(3):
                    ang=t*1.1+i*math.tau/3
                    px=x+35*s*math.cos(ang)
                    py=y-9*s+24*s*math.sin(ang)
                    c.create_oval(px-3,py-3,px+3,py+3,fill='#e5ffff',outline='')
            elif rank == 3:
                for i in range(5):
                    py=-42+i*19
                    line(-58,py,58,-py*.22,glow,1)
                ellipse(38,52,-10,'#c3f7ff',1)
            elif rank == 4:
                for i in range(3):
                    ellipse(25+i*19,18+i*15,-5,glow,1)
                poly([(0,-68),(11,-54),(0,-41),(-11,-54)],'', '#eaffff',2)
            elif rank >= 5:
                # Nucleo de singularidad pulsante visible por delante.
                phase=1+0.16*math.sin(t*3)
                r=18*phase
                poly([(0,-r),(r,0),(0,r),(-r,0)],'', '#faffff',3)
                for i in range(7):
                    a=(i*math.tau/7)+t*.65
                    bx=math.cos(a)*64; by=math.sin(a)*44-10
                    mx=math.cos(a)*78; my=math.sin(a)*58-10
                    line(bx,by,mx,my,glow,3)
                    line(mx,my,mx+math.sin(a*3)*5,my+8,'#eaffff',2)

    def build_roster_entries(self):
        """Una unica fila: jugador, enemigos normales y los seis jefes reales."""
        lineup = [
            ('PLAYER', None, 74, 'JUGADOR'),
            ('DRONE', None, 80, 'ENEMIGO'),
            ('GUARD', None, 72, 'ENEMIGO'),
            ('TANK', None, 76, 'ENEMIGO'),
            ('STRIKER', None, 78, 'ENEMIGO'),
        ]
        for floor, half_width in ((10, 105), (100, 129), (1000, 170),
                                  (10000, 200), (100000, 250), (1000000, 322)):
            lineup.append((self.boss_name(self.boss_rank(floor)), floor,
                           half_width, 'JEFE'))
        entries = []
        previous = 0.0
        current = 24.0
        for idx, (name, floor, half_width, kind) in enumerate(lineup):
            # Ninguna silueta comparte la misma posicion horizontal.
            current += half_width + (previous + 34 if idx else 0)
            entries.append(dict(name=name, floor=floor, half=half_width,
                                kind=kind, world_x=current,
                                boss_lv=self.boss_level(floor) if floor else None))
            previous = half_width
        self.roster_world_width = current + previous + 70
        return entries

    def roster_scroll_max(self):
        return max(0.0, self.roster_world_width - W)

    def roster_wheel(self, e):
        if not self.roster_mode:
            return
        delta = (e.delta / 120) if getattr(e, 'delta', 0) else (
            1 if getattr(e, 'num', 0) == 4 else -1)
        self.roster_scroll = clamp(self.roster_scroll - 114*delta,
                                   0.0, self.roster_scroll_max())
        self.roster_manual_until = time.monotonic() + 3.0

    def update_roster(self, dt, now):
        move = (int('d' in self.roster_keys or 'right' in self.roster_keys) -
                int('a' in self.roster_keys or 'left' in self.roster_keys))
        max_scroll = self.roster_scroll_max()
        if move:
            self.roster_scroll = clamp(self.roster_scroll + move*540*dt,
                                       0.0, max_scroll)
            self.roster_manual_until = now + 2.5
        elif self.roster_auto and now >= self.roster_manual_until:
            self.roster_scroll += self.roster_direction*140*dt
            if self.roster_scroll >= max_scroll:
                self.roster_scroll = max_scroll
                self.roster_direction = -1
            elif self.roster_scroll <= 0:
                self.roster_scroll = 0
                self.roster_direction = 1

    def draw_roster(self):
        """Escaparate desplazable con los dibujos originales, NO imagenes."""
        c = self.canvas
        c.delete('all')
        c.create_rectangle(0, 0, W, H, fill='#030c13', outline='')
        camera = self.roster_scroll
        baseline = 363
        # Suelo continuo en perspectiva de laboratorio, sin zonas de combate.
        c.create_polygon(0, baseline+17, W, baseline+17,
                         W, H-48, 0, H-48,
                         fill='#071b23', outline='#174c5b', width=2)
        for iy in range(0, 8):
            yy = baseline + 25 + iy*25
            if yy < H-48:
                c.create_line(0, yy, W, yy, fill='#104653', width=1)
        for ix in range(-200, W+200, 70):
            xx = ix - (camera % 70)
            c.create_line(xx, baseline+17, xx-22, H-48,
                          fill='#143541', width=1)
        c.create_line(0, baseline+12, W, baseline+12,
                      fill='#2d808a', width=2)
        c.create_line(0, baseline+15, W, baseline+15,
                      fill='#17444c', width=5)

        fronts = ((0,1), (0,-1), (-1,0), (1,0))
        facing = fronts[self.roster_view]
        enemy_palettes = {
            'DRONE': ('#6c3d72','#9552a1','#e67ded','#94b1ff','#6b7aa0','#f5c5ff'),
            'GUARD': ('#533746','#8d5468','#fe7b80','#dca188','#4c6d80','#ffd0d3'),
            'TANK': ('#6e4b22','#a16831','#ffb35e','#d6a481','#667247','#ffe0b5'),
            'STRIKER': ('#5d2633','#9a324d','#ff536f','#de9a83','#4d5b76','#ffb0c0'),
            'OVERSEER': ('#4b2235','#8c3354','#ff5372','#e3a0ac','#5b6681','#ffd5de'),
        }
        player_palette=('#2d4f76','#567390','#2a689a','#c8875d','#56774d',GREEN)
        for i, entry in enumerate(self.roster_entries):
            x = entry['world_x'] - camera
            # Dibujar solo las figuras que pueden ser visibles. Los jefes
            # gigantes necesitan un margen adicional por sus efectos.
            if x+entry['half'] < -35 or x-entry['half'] > W+35:
                continue
            floor = entry['floor']
            name = entry['name']
            rank = self.boss_rank(floor) if floor else 0
            accent = (GREEN if name=='PLAYER' else
                      enemy_palettes[name][-1] if not floor else
                      self.boss_palette(floor, rank))
            halo = min(entry['half']*.68, 155)
            c.create_oval(x-halo, baseline-4, x+halo, baseline+24,
                          fill='#091a24', outline='#1f4c5a', width=2)
            c.create_oval(x-halo*.64, baseline, x+halo*.64, baseline+19,
                          fill='', outline=accent, width=1)
            for ring in range(2):
                rr = halo*(.6 + .2*ring) + 2*math.sin(self.frame*3+i)
                c.create_arc(x-rr, baseline-rr*.12,
                             x+rr, baseline+rr*.12+17,
                             start=((self.frame*75+i*23+ring*160)%360),
                             extent=78, style='arc', outline=accent, width=2)
            # Lineas de medicion a ras del suelo.
            c.create_line(x, baseline+27, x, H-62,
                          fill='#163f49', width=1)
            c.create_line(x-9, H-71, x+9, H-71,
                          fill=accent, width=2)

            if name == 'PLAYER':
                if self.roster_view in (2,3):
                    self.draw_player_lateral(x, baseline-4, player_palette, 1.02,
                                             -1 if self.roster_view==2 else 1,
                                             (0,0), armed=False, aim_vec=facing)
                else:
                    self.draw_player_original(x, baseline-4, player_palette, 1.02,
                                              facing, (0,0), armed=False)
            elif floor is None:
                size={'DRONE':.87,'GUARD':.95,'TANK':1.04,'STRIKER':.96}[name]
                self.draw_character(x, baseline-4, enemy_palettes[name], size,
                                    facing, (0,0), boss=False, armed=True,
                                    model=name)
            else:
                scale = self.boss_scale(rank)
                boss_obj = {'x':x, 'y':baseline-4, 'color':accent,
                            'boss_rank':rank, 'boss_scale':scale}
                palette=(*enemy_palettes['OVERSEER'][:-1], accent)
                self.draw_boss_rank_effect(boss_obj,foreground=False)
                self.draw_character(x, baseline-4, palette, scale, facing,
                                    (0,0), boss=True, armed=True,
                                    model='OVERSEER', variant=floor//10)
                self.draw_boss_rank_effect(boss_obj,foreground=True)

            # Identificadores visibles incluso con jefes a escala completa.
            c.create_text(x, 492, text=name, fill='#e6ffff',
                          font=(FONT, 11 if len(name)<12 else 10,'bold'))
            if floor:
                subtitle='NIVEL '+f'{floor:,}'.replace(',', '.')
            elif name=='PLAYER':
                subtitle='JUGADOR'
            else:
                subtitle='ENEMIGO'
            c.create_text(x, 513, text=subtitle, fill=accent,
                          font=(FONT, 9, 'bold'))
            if floor:
                c.create_text(x, 532, text=f"BOSS LV {entry['boss_lv']}",
                              fill='#deffff', font=(FONT, 10, 'bold'))

        # Las etiquetas y los botones permanecen fijos mientras corre la camara.
        c.create_rectangle(0, 0, W, 80, fill='#061820',
                           outline='#225b64', width=2)
        c.create_text(26, 23, text='ENTER  //  GALERIA DE MODELOS',
                      fill='#a5ffe8', anchor='w',
                      font=(FONT, 17, 'bold'))
        c.create_text(27, 55, text='11 PERSONAJES  |  ENEMIGOS Y JEFES HASTA 1.000.000',
                      fill='#7bb9c5', anchor='w',font=(FONT, 10))
        c.create_rectangle(W-163, 12, W-15, 56, fill='#112a30',
                           outline='#53e6bf', width=2)
        c.create_text(W-89, 34, text='F9  JUGAR',
                      fill='#adffe5', font=(FONT, 11, 'bold'))
        # Flechas laterales clicables.
        for xpos, direction in ((42,-1),(W-42,1)):
            c.create_oval(xpos-27,292,xpos+27,350,
                          fill='#0c2630',outline='#2f9cb0',width=2)
            if direction < 0:
                points=(xpos+9,305,xpos-12,321,xpos+9,337)
            else:
                points=(xpos-9,305,xpos+12,321,xpos-9,337)
            c.create_polygon(*points, fill='#8bf9e8', outline='')
        # Barra de navegacion y ayuda.
        c.create_rectangle(0, H-52, W, H, fill='#061820',
                           outline='#225b64', width=2)
        progress = camera / max(1.0,self.roster_scroll_max())
        c.create_rectangle(17, H-41, W-17, H-35,
                           fill='#12343d', outline='')
        thumb_w = 120
        thumb_x = 17 + (W-34-thumb_w)*progress
        c.create_rectangle(thumb_x, H-41, thumb_x+thumb_w, H-35,
                           fill='#6cfed5', outline='')
        view_names=('FRENTE','ESPALDA','IZQUIERDA','DERECHA')
        mode = 'CAMARA AUTO' if self.roster_auto else 'CAMARA PAUSADA'
        c.create_text(26, H-18,
                      text=f'A/D O FLECHAS: MOVER  |  ESPACIO: AUTO  |  V: VISTA ({view_names[self.roster_view]})',
                      fill='#b2dbe4', font=(FONT,9), anchor='w')
        c.create_text(W-22, H-18, text=mode,
                      fill='#6df3c3', font=(FONT,9), anchor='e')

    def draw_north_portal(self, active):
        """Portal de REGRESO en el borde superior, azul y transparente."""
        c = self.canvas
        cx, cy = BACK_PORTAL_X, BACK_PORTAL_Y
        phase = self.frame
        outline = '#4ec7ff' if active else '#885267'
        light = '#d8f8ff' if active else '#ad637b'
        low = '#17465e' if active else '#54293a'
        pulse = .5 + .5 * math.sin(phase * 5.4)
        # Umbral eliptico sobre el suelo (el mismo sitio donde se cruza).
        for a, b, col, w in ((86, 22, low, 3), (75, 17, outline, 2),
                             (58, 11, light, 1)):
            c.create_oval(cx-a, cy-b, cx+a, cy+b,
                          fill='', outline=col, width=w)
        # Dos columnas en perspectiva y arco futurista superior.
        for side in (-1, 1):
            foot_x = cx + side * 69
            head_x = cx + side * 55
            c.create_line(foot_x, cy + 3, head_x, cy-43,
                          fill=low, width=6)
            c.create_line(foot_x, cy + 3, head_x, cy-43,
                          fill=outline, width=2)
            c.create_oval(head_x-4, cy-48, head_x+4, cy-40,
                          fill=light if active else low, outline='')
        c.create_arc(cx-60, cy-69, cx+60, cy-7, start=0, extent=180,
                     style='arc', outline=outline, width=3)
        if not active:
            c.create_line(cx-30, cy-11, cx+30, cy-11,
                          fill='#9b4d69', width=3)
            return
        # Luz ondulante y anillos en movimiento: nunca se congelan.
        for i in range(6):
            t = (phase*.52 + i/6) % 1.0
            px = cx - 51 + t*102
            py = cy-11 + math.sin(phase*3.7+i)*4
            c.create_line(px, py-22*pulse, px, py+9,
                          fill=outline if i%2 else light, width=2)
        for i in range(3):
            t = (phase*.79 + i/3) % 1.0
            ring_r = 14 + t*54
            c.create_oval(cx-ring_r, cy-ring_r*.20,
                          cx+ring_r, cy+ring_r*.20,
                          outline=outline if i != 2 else low, width=1)
        # Flecha holografica sin texto para indicar la salida superior.
        arrow_d = 3 * math.sin(phase*4.3)
        c.create_line(cx-13, cy-22+arrow_d, cx, cy-33+arrow_d,
                      fill=light, width=2)
        c.create_line(cx, cy-33+arrow_d, cx+13, cy-22+arrow_d,
                      fill=light, width=2)

    def draw_south_portal(self, active):
        """Portal de AVANCE visible por completo, sin recortar el arco abajo."""
        c = self.canvas
        # El umbral fisico sigue en NEXT_PORTAL_Y; el holograma se proyecta
        # un poco antes para que su arco/columnas quepan enteros en pantalla.
        cx, cy = NEXT_PORTAL_X, min(NEXT_PORTAL_Y - 24, H - 72)
        phase = self.frame
        outline = '#64ffc8' if active else '#885267'
        light = '#d3ffe9' if active else '#ad637b'
        low = '#175e59' if active else '#54293a'
        pulse = .5 + .5 * math.sin(phase * 5.1)
        for a, b, col, w in ((86, 22, low, 3), (75, 17, outline, 2),
                             (58, 11, light, 1)):
            c.create_oval(cx-a, cy-b, cx+a, cy+b,
                          fill='', outline=col, width=w)
        for side in (-1, 1):
            foot_x = cx + side * 69
            head_x = cx + side * 55
            c.create_line(foot_x, cy - 3, head_x, cy+43,
                          fill=low, width=6)
            c.create_line(foot_x, cy - 3, head_x, cy+43,
                          fill=outline, width=2)
            c.create_oval(head_x-4, cy+40, head_x+4, cy+48,
                          fill=light if active else low, outline='')
        c.create_arc(cx-60, cy+7, cx+60, cy+69, start=180, extent=180,
                     style='arc', outline=outline, width=3)
        if not active:
            c.create_line(cx-30, cy+11, cx+30, cy+11,
                          fill='#9b4d69', width=3)
            return
        for i in range(6):
            t = (phase*.52 + i/6) % 1.0
            px = cx - 51 + t*102
            py = cy+11 + math.sin(phase*3.7+i)*4
            c.create_line(px, py-9, px, py+22*pulse,
                          fill=outline if i%2 else light, width=2)
        for i in range(3):
            t = (phase*.79 + i/3) % 1.0
            ring_r = 14 + t*54
            c.create_oval(cx-ring_r, cy-ring_r*.20,
                          cx+ring_r, cy+ring_r*.20,
                          outline=outline if i != 2 else low, width=1)
        arrow_d = 3 * math.sin(phase*4.3)
        c.create_line(cx-13, cy+22-arrow_d, cx, cy+33-arrow_d,
                      fill=light, width=2)
        c.create_line(cx, cy+33-arrow_d, cx+13, cy+22-arrow_d,
                      fill=light, width=2)

    def draw_server_obstacle(self, obs, idx=0):
        c = self.canvas
        ox, oy, rr = obs['x'], obs['y'], obs['r']
        rack_w = rr * 1.00
        rack_h = rr * 1.55
        lean = rr * 0.78   # mas inclinacion
        depth = rr * 0.56
        fill = obs.get('color', '#245e6c')
        edge = '#8af6ff'
        edge2 = '#d6ffff'
        pulse = 0.5 + 0.5 * math.sin(self.frame * 2.2 + idx * 0.8)
        # cara frontal del servidor (mas alta y angosta)
        flt = (ox-rack_w*0.58, oy-rack_h*0.62)
        frt = (ox+rack_w*0.22, oy-rack_h*0.62-lean)
        frb = (ox+rack_w*0.22, oy+rack_h*0.48-lean)
        flb = (ox-rack_w*0.58, oy+rack_h*0.48)
        # cara lateral derecha
        srt = (frt[0]+depth, frt[1]+depth*0.33)
        srb = (frb[0]+depth, frb[1]+depth*0.33)
        # tapa superior
        stl = (flt[0]+depth*0.28, flt[1]-depth*0.22)
        strp = (frt[0]+depth, frt[1]+depth*0.33)
        sbl = (ox-rack_w*0.02, oy-rack_h*0.62-depth*0.22)
        # base/halo
        c.create_oval(ox-rack_w*0.95, oy+rack_h*0.28, ox+rack_w*0.95, oy+rack_h*0.72,
                      outline='#1a4652', width=1)
        c.create_polygon(flt[0],flt[1], frt[0],frt[1], frb[0],frb[1], flb[0],flb[1],
                         fill=fill, outline=edge, width=2)
        c.create_polygon(frt[0],frt[1], srt[0],srt[1], srb[0],srb[1], frb[0],frb[1],
                         fill='#173947', outline=edge, width=1)
        c.create_polygon(stl[0],stl[1], sbl[0],sbl[1], strp[0],strp[1], frt[0],frt[1],
                         fill='#102b35', outline=edge, width=1)
        # ranuras / bahias del servidor
        for k in range(3):
            yy = oy - rack_h*0.30 + k * rack_h * 0.28
            shift = -lean * ((yy - flt[1]) / max(1.0, (flb[1] - flt[1])))
            x1 = ox - rack_w*0.38
            x2 = ox + rack_w*0.02
            c.create_line(x1, yy, x2, yy + shift*0.15, fill=edge2 if k == 1 else '#7de9ff', width=2)
            c.create_line(x1, yy+5, x2-3, yy+5 + shift*0.15, fill='#4ed9f5', width=1)
        # leds / actividad
        led_y = oy + rack_h*0.17
        c.create_oval(ox-rack_w*0.10, led_y-4, ox+rack_w*0.08, led_y+4,
                      fill='#dfffff' if pulse > 0.5 else '#51bfd0', outline='')
        c.create_line(ox+rack_w*0.30, oy-rack_h*0.30-lean*0.86,
                      ox+rack_w*0.30, oy+rack_h*0.32-lean*0.86, fill='#8af6ff', width=1)
        c.create_line(ox+rack_w*0.42, oy-rack_h*0.18-lean*0.86,
                      ox+rack_w*0.42, oy+rack_h*0.20-lean*0.86, fill='#56dbff', width=1)

    def draw_player_occluding_obstacles(self):
        """Redibuja solo los servidores que deben quedar delante del player."""
        for i, obs in enumerate(self.obstacles):
            base_y = obs['y'] + obs['r'] * 0.48
            if (self.player_y <= base_y or
                    (self.ally_clone is not None and self.ally_clone['y'] <= base_y)):
                self.draw_server_obstacle(obs, i)

    def draw_background(self):
        c=self.canvas
        self.rect(0,0,W,H,BG)
        # Hologram pedestal below the arena.
        c.create_oval(FIELD[0]+105, FIELD[3], FIELD[2]-105, H, fill='#06181d', outline='#0f3d43', width=2)
        c.create_oval(FIELD[0]+128, FIELD[3]+16, FIELD[2]-128, H+14, outline='#2ce8a0', width=2)
        c.create_oval(FIELD[0]+168, FIELD[3]+34, FIELD[2]-168, H+26, outline='#38d8ff', width=1)
        # CAPA 1: numero grande o nombre del juego proyectado en el fondo.
        cx = (FIELD[0] + FIELD[2]) / 2
        cy = (FIELD[1] + FIELD[3]) / 2 + 18
        if self.is_level_zero:
            title_text = 'ENTER'
            c.create_text(cx + 7, cy + 10, text=title_text,
                          fill='#0a554f', font=(FONT, 118, 'bold'))
            c.create_text(cx, cy, text=title_text,
                          fill='#59ffb0', font=(FONT, 118, 'bold'))
        elif self.boss_stage:
            # Sala de jefe tras cada decena: en lugar del numero,
            # el suelo proyecta BOSS como parte del holograma de la arena.
            c.create_text(cx + 7, cy + 10, text='BOSS',
                          fill='#61223d', font=(FONT, 120, 'bold'))
            c.create_text(cx, cy, text='BOSS',
                          fill='#ff728f', font=(FONT, 120, 'bold'))
            # Proyeccion del nivel propio del jefe, debajo del titulo BOSS.
            c.create_text(cx, cy+90, text=f'LV {self.boss_level(self.boss_floor)}',
                          fill='#fbb9cc', font=(FONT, 22, 'bold'))
        else:
            level_text = str(self.level)
            font_size = max(95, 196 - 16*max(0, len(level_text)-2))
            c.create_text(cx + 7, cy + 10, text=level_text,
                          fill='#0a554f', font=(FONT, font_size, 'bold'))
            c.create_text(cx, cy, text=level_text,
                          fill='#59ffb0', font=(FONT, font_size, 'bold'))
        # Colores de la arena segun el estado.
        if self.state in ('fight', 'summoning'):
            arena_outline = '#ff5b74'
            arena_inner = '#9b5465'
            arena_outer = '#6f3145'
            arena_grid_a = '#4a1e28'
            arena_grid_b = '#34131e'
        elif self.state in ('cleared', 'upgrade'):
            arena_outline = '#45beff'
            arena_inner = '#3f88b7'
            arena_outer = '#24576f'
            arena_grid_a = '#173649'
            arena_grid_b = '#102938'
        else:
            arena_outline = '#37e6c8'
            arena_inner = '#1f8ca0'
            arena_outer = '#1d6d77'
            arena_grid_a = '#123c3b'
            arena_grid_b = '#0d3132'
        # Arena todavia mas inclinada / 3D.
        tl = (FIELD[0] + 74, FIELD[1] + 6)
        tr = (FIELD[2] - 74, FIELD[1] + 6)
        br = (FIELD[2] + 48, FIELD[3] + 12)
        bl = (FIELD[0] - 48, FIELD[3] + 12)
        tl2 = (FIELD[0] + 90, FIELD[1] + 14)
        tr2 = (FIELD[2] - 90, FIELD[1] + 14)
        br2 = (FIELD[2] + 24, FIELD[3] - 8)
        bl2 = (FIELD[0] - 24, FIELD[3] - 8)
        drop = 28
        # Caras laterales / frontal para reforzar el 3D.
        c.create_polygon(bl[0], bl[1], br[0], br[1], br[0], br[1]+drop, bl[0], bl[1]+drop,
                         fill='#07141a', outline=arena_outer, width=1)
        c.create_polygon(tr[0], tr[1], br[0], br[1], br[0]+13, br[1]+drop, tr[0]+13, tr[1]+drop,
                         fill='#061116', outline=arena_outer, width=1)
        c.create_polygon(tl[0], tl[1], bl[0], bl[1], bl[0]-13, bl[1]+drop, tl[0]-13, tl[1]+drop,
                         fill='#061116', outline=arena_outer, width=1)
        # Piso superior proyectado.
        c.create_polygon(tl[0], tl[1], tr[0], tr[1], br[0], br[1], bl[0], bl[1],
                         fill='#071d21', stipple='gray25', outline=arena_outline, width=3)
        c.create_polygon(tl2[0], tl2[1], tr2[0], tr2[1], br2[0], br2[1], bl2[0], bl2[1],
                         fill='', outline=arena_inner, width=1)
        c.create_polygon(tl[0]-8, tl[1]-8, tr[0]+8, tr[1]-8, br[0]+8, br[1]+8, bl[0]-8, bl[1]+8,
                         fill='', outline=arena_outer, width=1)
        # Perspectiva de la cuadricula.
        cols = 22
        rows = 14
        for i in range(cols + 1):
            t = i / cols
            top_x = tl2[0] + (tr2[0] - tl2[0]) * t
            top_y = tl2[1] + (tr2[1] - tl2[1]) * t
            bot_x = bl2[0] + (br2[0] - bl2[0]) * t
            bot_y = bl2[1] + (br2[1] - bl2[1]) * t
            alpha_color = arena_grid_a if i % 2 == 0 else arena_grid_b
            c.create_line(top_x, top_y, bot_x, bot_y, fill=alpha_color, width=1)
        for j in range(rows + 1):
            t = j / rows
            left_x = tl2[0] + (bl2[0] - tl2[0]) * t
            left_y = tl2[1] + (bl2[1] - tl2[1]) * t
            right_x = tr2[0] + (br2[0] - tr2[0]) * t
            right_y = tr2[1] + (br2[1] - tr2[1]) * t
            c.create_line(left_x, left_y, right_x, right_y, fill=arena_grid_a, width=1)
        for offset in (0.08, 0.18, 0.28):
            tx1 = tl2[0] + (tr2[0] - tl2[0]) * offset
            ty1 = tl2[1] + (tr2[1] - tl2[1]) * offset
            tx2 = tr2[0] - (tr2[0] - tl2[0]) * offset
            ty2 = tr2[1] - (tr2[1] - tl2[1]) * offset
            bx1 = bl2[0] + (br2[0] - bl2[0]) * offset
            by1 = bl2[1] + (br2[1] - bl2[1]) * offset
            bx2 = br2[0] - (br2[0] - bl2[0]) * offset
            by2 = br2[1] - (br2[1] - bl2[1]) * offset
            c.create_line(tx1, ty1, tx2, ty2, fill=arena_outer)
            c.create_line(bx1, by1, bx2, by2, fill=arena_outer)
        # Digitos decorativos.
        for i, x in enumerate(range(54, W-54, 44)):
            for j in range(4):
                self.label(x, FIELD[1] + 12 + j*8, '0' if (i+j)%2==0 else '1', '#1f5d48', 8)
                self.label(x, FIELD[3] - 12 - j*8, '1' if (i+j)%2==0 else '0', '#1f5d48', 8)
        # Luz roja parpadeante al invocar y durante el combate.
        if self.state in ('fight', 'summoning'):
            flash = 0.5 + 0.5 * math.sin(self.frame * 9.5)
            hot = flash > 0.58
            outer = '#ff3e5f' if hot else '#8a2032'
            mid = '#ff7289' if hot else '#b23f58'
            core = '#ffd3d9' if hot else '#ff8ba1'
            # Barrido rojo en bordes superiores y laterales.
            c.create_line(FIELD[0]-18, FIELD[1]-8, FIELD[2]+18, FIELD[1]-8, fill=outer, width=3)
            c.create_line(FIELD[0]-24, FIELD[1]+14, FIELD[0]-24, FIELD[3]+18, fill='#6e1e2c', width=2)
            c.create_line(FIELD[2]+24, FIELD[1]+14, FIELD[2]+24, FIELD[3]+18, fill='#6e1e2c', width=2)
            c.create_line(FIELD[0]-24, FIELD[1]+14 + 18*flash, FIELD[0]-24, FIELD[1]+46 + 18*flash, fill=outer, width=4)
            c.create_line(FIELD[2]+24, FIELD[3]-46 - 18*flash, FIELD[2]+24, FIELD[3]-14 - 18*flash, fill=outer, width=4)
            # Balizas rojas en esquinas superiores.
            for bx in (FIELD[0] + 34, FIELD[2] - 34):
                by = FIELD[1] - 14
                c.create_oval(bx-20, by-20, bx+20, by+20, outline=outer, width=2)
                c.create_oval(bx-13, by-13, bx+13, by+13, outline=mid, width=2)
                c.create_oval(bx-6, by-6, bx+6, by+6, fill=core, outline='')
            # Reflejo rojo sobre la arena para alarma visual.
            c.create_polygon(tl2[0]+8, tl2[1]+6, tr2[0]-8, tr2[1]+6, br2[0]-18, br2[1]-24, bl2[0]+18, bl2[1]-24,
                             fill='', outline='#7e2635', width=1)
        # Objetos de la arena: servidores holograficos mas inclinados.
        for i, obs in enumerate(self.obstacles):
            self.draw_server_obstacle(obs, i)
        # Una unica placa central: en pisos nuevos la activa la entrada;
        # en pisos completados queda en espera de que la pise el jugador.
        # Nunca causa dano y no tiene texto flotante.
        if not self.intro_room and self.state in ('ready', 'summoning', 'fight', 'cleared', 'upgrade'):
            tx, ty = TRAP_POSITION
            pulse = 0.5 + 0.5 * math.sin(self.frame * 5.0)
            active = self.state == 'summoning'
            spent = self.trap_triggered and not active
            glow = ('#526b72' if spent else '#ff536b' if active else
                    ('#ffcc72' if pulse > .35 else '#b67338'))
            ring = '#223d46' if spent else '#9b2e3a' if active else '#7e4d2a'
            inner = '#688c94' if spent else '#ff9dab' if active else '#ffdb9d'
            c.create_oval(tx-49, ty-23, tx+49, ty+23,
                          outline=ring, width=2)
            c.create_oval(tx-37, ty-17, tx+37, ty+17,
                          outline=glow, width=2)
            c.create_oval(tx-28, ty-12, tx+28, ty+12,
                          outline=inner, width=1)
            # Triangulo de advertencia sobre la unica placa.
            c.create_polygon(tx, ty-11, tx+12, ty+9, tx-12, ty+9,
                             fill='#14252d' if spent else '#51212d' if active else '#402420',
                             outline=glow, width=2)
            c.create_line(tx, ty-4, tx, ty+3, fill=inner, width=2)
            c.create_oval(tx-1.3, ty+5, tx+1.3, ty+7.5,
                          fill=inner, outline='')
            c.create_arc(tx-42,ty-22,tx+42,ty+22,
                         start=45 if spent else (self.frame*85)%360,
                         extent=58, style='arc', outline=inner, width=2)

        # Portales transparentes: SOLO luces y lineas animadas, sin fondo oscuro.
        # Cada coordenada sigue la inclinacion del lado real del suelo.
        cy = DOOR_Y
        def edge_point(a, b, yy):
            t = clamp((yy - a[1]) / max(1., b[1]-a[1]), 0., 1.)
            return (a[0] + (b[0]-a[0])*t, yy)
        def draw_side_portal(kind, active):
            left = kind == 'back'
            side = -1 if left else 1
            bottom = bl2 if left else br2
            top = tl2 if left else tr2
            c_outer = '#38b8ff' if left else '#55ffc7'
            c_inner = '#c8faff' if left else '#d5ffe5'
            color = c_outer if active else '#715062'
            y1, y2 = cy-68, cy+68
            ptop = edge_point(top,bottom,y1)
            pbot = edge_point(top,bottom,y2)
            # Piel de luz con cuatro vertices oblicuos. fill='' es totalmente
            # transparente: nunca tapar los cuadros del escenario.
            x1 = ptop[0] + 4*side
            x2 = ptop[0] + 34*side
            x3 = pbot[0] + 34*side
            x4 = pbot[0] + 4*side
            for glow_width, offs, tone in ((5,4,'#164c53'),(2,0,color)):
                c.create_polygon(x1+offs*side,y1-4,x2+offs*side,y1-12,
                                 x3+offs*side,y2+12,x4+offs*side,y2+4,
                                 fill='',outline=tone,width=glow_width)
            c.create_line(x1+8*side,y1-2,x4+8*side,y2+2,fill=color,width=1)
            c.create_line(x2-5*side,y1-8,x3-5*side,y2+8,fill=color,width=1)
            # Aro superior e inferior apenas elipticos, dentro de la plataforma.
            for pos, yy in ((ptop, y1),(pbot,y2)):
                ccx = pos[0] + 19*side
                c.create_oval(ccx-16,yy-7,ccx+16,yy+7,
                              fill='',outline=color,width=2)
            if not active:
                # Contorno apagado, sin panel opaco.
                for i in range(3):
                    yy=cy-34+i*34
                    ex=edge_point(top,bottom,yy)[0]
                    c.create_line(ex+8*side,yy,ex+30*side,yy,
                                  fill='#7a384a',width=1)
                return
            # Barrido continuo vertical + trazos ondulantes, tipo holograma.
            for i in range(7):
                phase = (self.frame*0.55 + i/7.0) % 1.
                yy = y1+11+(y2-y1-22)*phase
                edge_x=edge_point(top,bottom,yy)[0]
                shimmer=math.sin(self.frame*7.8+i*1.3)*3
                c.create_line(edge_x+(7+shimmer)*side,yy,
                              edge_x+(29-shimmer)*side,yy+math.sin(i+self.frame*5)*2,
                              fill=c_inner if i%3==0 else c_outer,width=2)
            for i in range(5):
                yy=y1+12+i*26
                ex=edge_point(top,bottom,yy)[0]
                phase=self.frame*3.1+i*2
                dx=7+20*(.5+.5*math.sin(phase))
                py=yy+3*math.cos(phase)
                c.create_oval(ex+(dx-2)*side,py-2,
                              ex+(dx+2)*side,py+2,
                              fill=c_inner,outline='')
            # Pisada luminosa alineada al suelo: sin fondo ni rectangulos.
            fy=y2+3
            fx=pbot[0]+12*side
            pulse=0.5+0.5*math.sin(self.frame*4.6)
            c.create_oval(fx-24-4*pulse,fy-11,fx+24+4*pulse,fy+11,
                          fill='',outline=c_outer,width=2)
        # La unica salida de la sala 0 es ABAJO; el regreso se abre ARRIBA.
        if not self.is_level_zero:
            self.draw_north_portal(self.portals_available())
        self.draw_south_portal(self.portals_available())
        for px,py in ((FIELD[0]-112,139),(FIELD[2]+111,139),
                      (FIELD[0]-112,519),(FIELD[2]+111,519)):
            c.create_oval(px-8,py-8,px+8,py+8,outline='#2ce8a0',width=2)
            c.create_oval(px-3,py-3,px+3,py+3,fill=GREEN,outline='')
        # Plataforma visible mientras no hay monstruos, antes o despues del combate.
        if (not self.is_level_zero and not self.enemies and
                self.state in ('ready', 'summoning', 'cleared', 'upgrade')):
            pcx, pcy = self.upgrade_pad_center()
            pad_color = '#87f0ff' if self.state == 'upgrade' else '#59ffb0'
            halo_color = '#194f63' if self.state == 'upgrade' else '#1f6041'
            wave = 0.5 + 0.5 * math.sin(self.frame * 4.2)
            ring_shift = math.sin(self.frame * 3.0) * 3.0
            c.create_oval(pcx-95, pcy-31, pcx+95, pcy+31, outline=halo_color, width=2)
            c.create_oval(pcx-80, pcy-20, pcx+80, pcy+20, outline=pad_color, width=2)
            c.create_oval(pcx-58-ring_shift*0.2, pcy-10-ring_shift*0.05, pcx+58+ring_shift*0.2, pcy+10+ring_shift*0.05, outline=pad_color, width=1)
            for i in range(3):
                rr = 18 + i * 16 + wave * 7
                c.create_oval(pcx-rr, pcy-rr*0.28, pcx+rr, pcy+rr*0.28, outline=pad_color if i < 2 else halo_color, width=1)
            c.create_line(pcx-38, pcy, pcx+38, pcy, fill=pad_color, width=2)
            c.create_line(pcx, pcy-12, pcx, pcy+12, fill=pad_color, width=2)
            for i in range(4):
                ang = self.frame * 1.8 + i * (math.tau / 4)
                lx = pcx + math.cos(ang) * 48
                ly = pcy + math.sin(ang) * 9
                c.create_line(lx, ly-18-wave*7, lx, ly-4, fill=pad_color, width=1)
                c.create_oval(lx-2, ly-22-wave*7, lx+2, ly-18-wave*7, fill='#d7ffff', outline='')

    def draw_clone_pickup(self):
        """Icono de casco original del PLAYER con errores de simulacion."""
        item = self.clone_pickup
        if item is None or self.state != 'fight':
            return
        c = self.canvas
        x, y = item['x'], item['y']
        t = self.frame
        pulse = 0.5 + 0.5*math.sin(t*5.8)
        floaty = math.sin(t*3.4)*3.0
        c.create_oval(x-29, y+12, x+29, y+24,
                      outline='#5c5bb2', width=1)
        for i, color in enumerate(('#305d8d', '#72eaff', '#c1a1ff')):
            rad = 23 + i*4 + pulse*(5 if i == 2 else 1)
            c.create_oval(x-rad, y+floaty-rad,
                          x+rad, y+floaty+rad,
                          outline=color, width=1 if i != 1 else 2)
        y += floaty
        # Cabeza / casco del PLAYER; usar la forma ovalada original.
        c.create_oval(x-10,y-15,x+10,y+6,
                      fill='#0a2630',outline='#72ffcf',width=2)
        c.create_arc(x-10,y-16,x+10,y-3,start=0,extent=180,
                     style='pieslice',fill='#17505a',outline='#b4ffff')
        c.create_oval(x-7,y-7,x+7,y+1,fill='#123442',outline='#82ffeb')
        c.create_line(x-6,y-4,x+6,y-4,fill='#e9ffff',width=3)
        c.create_line(x-12,y+10,x+12,y+10,fill='#8bffe3',width=2)
        for i in range(4):
            dy = -18+i*10
            jitter = math.sin(t*19+i*6.1)*6
            c.create_line(x-15+jitter, y+dy, x-9+jitter, y+dy,
                          fill='#ff8dff' if i % 2 else '#87ffff', width=1)

    def draw_ally_clone(self):
        """El mismo PLAYER en una proyeccion violeta/cian con glitches activos."""
        a = self.ally_clone
        if a is None or self.state != 'fight':
            return
        c = self.canvas
        x,y = a['x'],a['y']
        glitch = 0.5+0.5*math.sin(self.frame*25.0+a['born_at']*3)
        palette = ('#283b71','#415987','#3c6fa1','#9bcdf3','#7894b2','#b99bff')
        # Silueta errante desplazada en algunas tramas, como un error digital.
        offset = 3.5*math.sin(self.frame*71.0) if glitch > .87 else 0.0
        if glitch > .76:
            c.create_line(x-15+offset,y-16,x+14+offset,y-16,
                          fill='#f191ff',width=2)
            c.create_line(x-13-offset,y+5,x+16-offset,y+5,
                          fill='#81faff',width=2)
        self.draw_player_original(x+offset,y,palette,0.97,
                                  a['facing'],(a['vx'],a['vy']),armed=True)
        for i in range(3):
            phase = (self.frame*1.7 + i/3.0) % 1.0
            r = 21 + phase*10
            col = '#c487ff' if i % 2 else '#5beeff'
            c.create_arc(x-r,y+11-r*.3,x+r,y+11+r*.3,
                         start=10+phase*180,extent=90,
                         style='arc',outline=col,width=1)
        for i in range(4):
            line_y = y-17 + ((self.frame*27 + i*13)%36)
            dx = math.sin(self.frame*14+i*9)*4
            c.create_line(x-10+dx,line_y,x+9+dx,line_y,
                          fill='#a6ffff' if i%2 else '#c396ff',width=1)
        # La barra confirma que es una entidad aliada que puede desintegrarse.
        ratio = clamp(a['hp']/a['max_hp'], 0.0, 1.0)
        self.rect(x-17,y-33,x+17,y-30,'#102336')
        self.rect(x-17,y-33,x-17+ratio*34,y-30,'#99a8ff')

    def draw_actor(self):
        x,y=self.player_x,self.player_y
        if self.state == 'dead':
            return
        armed = self.state == 'fight'
        moving = abs(self.player_vx)+abs(self.player_vy) > 2
        if armed:
            target = self.nearest_enemy()
            if target is not None:
                self.aim = (target['x'], target['y'])
        if moving:
            # En movimiento se conserva el apuntado automatico en combate.
            facing = (self.aim[0]-x,self.aim[1]-y) if armed else self.player_facing
        else:
            # Si subio y se detuvo, sigue mostrando la espalda.
            facing = self.player_facing
        if self.shield_flash and armed:
            r=23+math.sin(self.frame*12)*2
            self.canvas.create_oval(x-r,y-r,x+r,y+r,outline=CYAN,width=3)
        palette=('#2d4f76','#567390','#2a689a','#c8875d','#56774d',GREEN)
        # Elegir una autentica vista de perfil al caminar a los lados.
        # Tambien se recuerda el costado al parar; arriba/abajo mantienen
        # exactamente el soldado original y su vista posterior.
        travel = self.player_facing
        if abs(travel[0]) > abs(travel[1]) * 1.05:
            gun_aim = ((self.aim[0]-x, self.aim[1]-y)
                       if armed else travel)
            self.draw_player_lateral(x, y, palette, 1.02,
                                     1 if travel[0] > 0 else -1,
                                     (self.player_vx, self.player_vy),
                                     armed=armed, aim_vec=gun_aim)
        else:
            self.draw_player_original(x,y,palette,1.02,facing,
                                      (self.player_vx,self.player_vy),
                                      boss=False,armed=armed)

    def draw_enemies(self):
        palettes={
            'DRONE': ('#6c3d72','#9552a1','#e67ded','#94b1ff','#6b7aa0','#f5c5ff'),
            'GUARD': ('#533746','#8d5468','#fe7b80','#dca188','#4c6d80','#ffd0d3'),
            'TANK': ('#6e4b22','#a16831','#ffb35e','#d6a481','#667247','#ffe0b5'),
            'STRIKER': ('#5d2633','#9a324d','#ff536f','#de9a83','#4d5b76','#ffb0c0'),
            'OVERSEER': ('#4b2235','#8c3354','#ff5372','#e3a0ac','#5b6681','#ffd5de'),
        }
        for e in self.enemies:
            x,y=e['x'],e['y']; r=e['radius']
            dx,dy=self.player_x-x,self.player_y-y
            model=e['name']
            boss = model == 'OVERSEER'
            if boss:
                scale=e.get('boss_scale',1.22)
                palette=(*palettes['OVERSEER'][:-1],e['color'])
                self.draw_boss_rank_effect(e,foreground=False)
                self.draw_boss_attack_warning(e)
            else:
                scale={'DRONE':.87,'GUARD':.95,'TANK':1.04,'STRIKER':.96}[model]
                palette=palettes[model]
            direction = (dx,dy)
            if not boss and (abs(e.get('move_dx',0))+abs(e.get('move_dy',0)) < 2):
                direction=e.get('facing',direction)
            self.draw_character(x,y,palette,scale,direction,
                                (e.get('move_dx',0.),e.get('move_dy',0.)),
                                boss=boss,armed=True,model=model,
                                variant=e.get('boss_tier',0))
            if boss:
                self.draw_boss_rank_effect(e,foreground=True)
            if e['next_fire']-time.monotonic()<.18:
                warning=21 if not boss else min(104, 28*scale)
                self.canvas.create_oval(x-warning,y-warning,x+warning,y+warning,
                                        outline=e['color'],width=2)
            if boss:
                bw=min(270,round(74*scale))
                by=y-37*scale-23
                label=e.get('boss_name','BOSS')
                boss_lv=e.get('boss_lv', self.boss_level(self.boss_floor))
                self.label(x,by-13,f'{label}  LV {boss_lv}',e['color'],10,'center',True)
            else:
                bw=38
                by=y-r-14
            self.rect(x-bw/2,by,x+bw/2,by+5,'#271923')
            health_color = '#ffa366' if boss and e.get('phase',1)==2 else e['color']
            self.rect(x-bw/2,by,x-bw/2+bw*max(0,e['hp'])/e['hpmax'],by+5,health_color)

    def draw_rest_status(self):
        """Medidor pequeno de recarga, fuera del paso de los dos portales."""
        if not self.is_rest_room():
            return
        c = self.canvas
        left = 16
        right = min(FIELD[0]-12, left+166)
        if right-left < 90:
            return
        top = H-67
        pct = clamp(self.rest_seconds/REST_CHARGE_SECONDS, 0.0, 1.0)
        c.create_rectangle(left-6,top-8,right+6,top+50,
                           fill='#081e25',outline='#356d7d',width=1)
        self.label(left,top+1,'EXP x2', '#a5fff2', 12,'w',True)
        if self.xp_boost_ready:
            text = 'LISTO'
            col = '#d69bff'
        else:
            remaining = max(0,math.ceil(REST_CHARGE_SECONDS-self.rest_seconds))
            text = f'{remaining//60:02d}:{remaining%60:02d}'
            col = '#72d9eb'
        self.label(right,top+1,text,col,10,'e',True)
        self.rect(left,top+20,right,top+30,'#102b37','#357a8f')
        self.rect(left+2,top+22,left+2+(right-left-4)*pct,top+28,
                  '#c58bff' if self.xp_boost_ready else '#69f2d7')
        self.label(left,top+42,'SIGUIENTE VICTORIA', '#6aabbc',8,'w')

    def draw_hud(self):
        c=self.canvas
        c.create_rectangle(0,0,W,64,fill='#07161b',outline='#165a59',width=2)
        y = 33
        # Todo el contenido de la parte superior organizado en una sola linea.
        x = 26
        if not self.is_level_zero:
            self.draw_icon(x, y, 'chip', GREEN, 0.68)
            self.label(x+20, y, str(self.max_level), '#bdf3ff', 12, 'w', True)
            x += 72
        # El numero SPEED es una ventaja virtual; la velocidad en pantalla
        # permanece limitada por PLAYER_MOVE_SPEED.
        self.draw_icon(x, y, 'speed', CYAN, 0.66)
        self.label(x+20, y, str(round(self.player_speed)), CYAN, 12, 'w', True)
        x += 68
        nearest = self.nearest_enemy()
        if nearest is not None:
            diff = round(self.relative_speed(nearest))
            diff_color = '#ff7294' if diff > 0 else GREEN
            self.draw_icon(x, y, 'speed', diff_color, 0.58)
            self.label(x+20, y, f'{diff:+d}', diff_color, 11, 'w', True)
            x += 68
        self.draw_icon(x, y, 'heart', '#ff6d76', 0.72)
        bar_x1 = x + 24
        bar_x2 = bar_x1 + 206
        self.rect(bar_x1, y-6, bar_x2, y+6, '#142b30', '#2f7d6a')
        shown_life = clamp(self.display_life(), 0.0, self.max_hp)
        self.rect(bar_x1+2, y-4, bar_x1+2+202*shown_life/self.max_hp, y+4,
                  '#58fa8d' if shown_life>self.max_hp*.3 else '#f87068')
        self.label((bar_x1+bar_x2)/2, y, f'{max(0,round(shown_life))}/{self.stat_text(self.max_hp)}', '#d8ffed', 10, 'center', True)
        enemy_base = bar_x2 + 25
        for i in range(4):
            cx = enemy_base + i*20
            on = i < len(self.enemies)
            c.create_oval(cx-6, y-6, cx+6, y+6,
                          fill='#ff5e77' if on else '#15332b',
                          outline='#ff8ea0' if on else '#2b5d54')
        self.draw_icon(W-250, y, 'xp', AMBER, 0.70)
        self.label(W-230, y, str(self.xp), AMBER, 12, 'w', True)
        if self.xp_boost_ready:
            self.label(W-244, y+20, 'x2 LISTO', '#d59bff', 9, 'w', True)
        self.draw_icon(W-158, y, 'bolt', CYAN, 0.70)
        self.label(W-138, y, self.stat_text(self.damage), '#d7fbff', 12, 'w', True)
        self.draw_icon(W-82, y, 'shield', GREEN, 0.66)
        self.label(W-62, y, str(int(self.shield*100)), '#d7fbff', 12, 'w', True)

    def draw(self):
        c=self.canvas; c.delete('all')
        self.draw_background()
        self.draw_enemy_summoning()
        self.draw_hud()
        # Mostrar municion y residuos SOLO mientras haya combate activo.
        # Evita que un efecto restante se dibuje durante la victoria.
        if self.state == 'fight':
            for b in self.bullets:
                friendly = len(b)>6 and b[6]=='ally'
                c.create_oval(b[0]-4,b[1]-4,b[0]+4,b[1]+4,
                              fill='#ba87ff' if friendly else CYAN,
                              outline='#f2deff' if friendly else '#dbffff')
            for b in self.enemy_bullets:
                c.create_oval(b[0]-5,b[1]-5,b[0]+5,b[1]+5,fill=b[6] if len(b)>6 else '#ff617b',outline='#ffd2db')
        self.draw_enemies()
        self.draw_clone_pickup()
        self.draw_ally_clone()
        self.draw_actor()
        self.draw_rest_status()
        self.draw_player_occluding_obstacles()
        self.draw_healing()
        if time.monotonic() < self.spawn_fx_until and self.state in ('fight', 'cleared', 'upgrade'):
            p = 1.0 - (self.spawn_fx_until - time.monotonic()) / 0.6
            for mult, col in ((24, '#8efde7'), (40, '#42e4f5')):
                rr = 12 + p * mult
                c.create_oval(self.player_x-rr, self.player_y-rr*0.62, self.player_x+rr, self.player_y+rr*0.62,
                              outline=col, width=2 if mult == 24 else 1)
        if self.state == 'warp':
            progress = clamp((time.monotonic() - self.transition_started_at) / max(0.01, self.transition_until - self.transition_started_at), 0.0, 1.0)
            rr = 18 + progress * 58
            c.create_oval(self.player_x-rr, self.player_y-rr, self.player_x+rr, self.player_y+rr, outline='#78fff1', width=2)
            c.create_oval(self.player_x-rr*0.58, self.player_y-rr*0.58, self.player_x+rr*0.58, self.player_y+rr*0.58, outline='#59ffb0', width=1)
            for p in self.transition_particles:
                alpha = max(0.0, p['ttl'] / p['max_ttl'])
                r = max(1.0, p['size'] * alpha)
                c.create_oval(p['x']-r, p['y']-r, p['x']+r, p['y']+r, fill=p['color'], outline='')
        if self.state == 'fight':
            for x,y,t,color in self.particles:
                r=max(1,5*t/.4)
                c.create_oval(x-r,y-r,x+r,y+r,fill=color,outline='')
        if time.monotonic()<self.message_until:
            self.label(W/2,153,self.message,AMBER,24,bold=True)
        # La placa proyecta energia antes de desplegar el menu holografico.
        if self.state == 'upgrade':
            self.draw_upgrade_activation()
            self.draw_upgrade()
        if self.state=='dead':
            # Desintegracion de 2 segundos y autocarga del checkpoint.
            progress = clamp((time.monotonic() - self.death_anim_start) / 2.0, 0.0, 1.0)
            ring_r = 16 + progress * 46
            c.create_oval(self.player_x-ring_r, self.player_y-ring_r,
                          self.player_x+ring_r, self.player_y+ring_r,
                          outline='#7bfff8', width=2)
            c.create_oval(self.player_x-ring_r*0.58, self.player_y-ring_r*0.58,
                          self.player_x+ring_r*0.58, self.player_y+ring_r*0.58,
                          outline='#59ffb0', width=1)
            for p in self.death_particles:
                alpha = p['ttl'] / p['max_ttl']
                r = max(1.0, p['size'] * alpha)
                c.create_oval(p['x']-r, p['y']-r, p['x']+r, p['y']+r,
                              fill=p['color'], outline='')
            # Silueta que se desvanece al centro.
            if progress < 0.65:
                fade = 1.0 - progress / 0.65
                h = 18 * fade
                c.create_line(self.player_x, self.player_y-14*fade, self.player_x, self.player_y+12*fade,
                              fill='#c9fff3', width=max(1,int(3*fade)))
                c.create_line(self.player_x-7*fade, self.player_y-2*fade, self.player_x+7*fade, self.player_y-2*fade,
                              fill='#8fffe1', width=max(1,int(2*fade)))

    def upgrade_open_progress(self, now=None):
        """0..1: animacion cada vez que se pisa la plataforma de mejoras."""
        if self.state != 'upgrade':
            return 0.0
        if self.upgrade_open_started_at <= 0.0:
            # Respaldo para partidas y pruebas que asignen el estado directamente.
            return 1.0
        if now is None:
            now = time.monotonic()
        return clamp((now - self.upgrade_open_started_at) / UPGRADE_OPEN_SECONDS,
                     0.0, 1.0)

    def draw_upgrade_activation(self):
        """Proyeccion permanente: solo se apaga al salir del circulo."""
        if self.state != 'upgrade':
            return
        progress = self.upgrade_open_progress()
        c = self.canvas
        cx, cy = self.upgrade_pad_center()
        warmup = min(1.0, progress*2.5)
        palette = ('#1b655f', '#39bbaa', '#78ffe2', '#cbfff7')
        # Los aros siguen expandiendose incluso despues de abrirse el menu.
        for i in range(3):
            phase = (self.frame * .56 + i / 3.0) % 1.0
            radius = 14.0 + 90.0 * phase * warmup
            color = palette[min(3, int((1.0-phase) * 4.0))]
            c.create_oval(cx-radius, cy-radius*.30,
                          cx+radius, cy+radius*.30,
                          outline=color, width=2 if phase < .45 else 1)
        # Haces que respiran y suben continuamente.
        for i in range(9):
            phase = i/9.0*math.tau + self.frame * .93
            bx = cx + math.cos(phase) * 52.0
            by = cy + math.sin(phase) * 13.0
            float_phase = .5 + .5 * math.sin(self.frame*6.8+i*.7)
            height = (27.0 + 46.0 * float_phase) * warmup
            c.create_line(bx, by-4, bx, by-height,
                          fill='#2b9a96', width=2)
            c.create_line(bx, by-height, bx, by-height+11,
                          fill='#aafff3', width=1)
            c.create_oval(bx-2.0,by-height-2.0,bx+2.0,by-height+2.0,
                          fill='#d4ffff', outline='')
        # Scan de los pies a la cabeza sin interrumpir el movimiento.
        scan_phase = (self.frame*.79) % 1.0
        scan_y = self.player_y + 17.0 - scan_phase*38.0
        c.create_line(self.player_x-10, scan_y,
                      self.player_x+10, scan_y,
                      fill='#b6fff1', width=2)
        for side in (-1,1):
            x = cx + side*73
            sway = math.sin(self.frame*4+side)*9
            c.create_line(x, cy-18, x, cy-53-sway,
                          fill='#45e6c4', width=1)

    def draw_upgrade(self):
        """Panel holografico superior, sin bloquear al personaje ni las puertas."""
        c = self.canvas
        offset = (W - BASE_W) // 2
        x1, y1, x2, y2 = 108+offset, UPGRADE_TOP, 812+offset, 267
        progress = self.upgrade_open_progress()
        if progress < 1.0:
            # Primero se expande desde el centro, despues baja como un escaneo.
            spread = clamp(progress / 0.57, 0.0, 1.0)
            spread = spread * spread * (3.0 - 2.0 * spread)
            deploy = clamp((progress - 0.18) / 0.82, 0.0, 1.0)
            deploy = deploy * deploy * (3.0 - 2.0 * deploy)
            left = W/2 - (W/2-x1) * spread
            right = W/2 + (x2-W/2) * spread
            bottom = y1 + (y2-y1) * deploy
            if spread > 0.01:
                c.create_rectangle(left, y1, right, max(y1+2, bottom),
                                   fill='#071d27', stipple='gray75',
                                   outline='#4ef5c9', width=2)
                c.create_line(left-5, y1, right+5, y1, fill='#afffeb', width=2)
                if deploy > 0.02:
                    for xx in range(int(left)+14, int(right)-6, 31):
                        c.create_line(xx, y1+4, xx, bottom-2,
                                      fill='#134347', width=1)
                    for yy in range(y1+21, int(bottom), 25):
                        c.create_line(left+8, yy, right-8, yy,
                                      fill='#164348', width=1)
                    c.create_line(left+5, bottom-1, right-5, bottom-1,
                                  fill='#b9fff3', width=3)
                    for px in (left, right):
                        c.create_line(px-5, bottom, px+5, bottom,
                                      fill='#bafff3', width=2)
            return
        # Cristal semitransparente, doble marco luminoso y reticula digital.
        c.create_rectangle(x1, y1, x2, y2, fill='#071d27',
                           stipple='gray75', outline='#4ef5c9', width=3)
        c.create_rectangle(x1+7, y1+7, x2-7, y2-7,
                           outline='#258eac', width=1)
        for px,py in ((x1,y1),(x2,y1),(x1,y2),(x2,y2)):
            c.create_line(px-8,py,px+8,py,fill='#85ffe0',width=2)
            c.create_line(px,py-8,px,py+8,fill='#85ffe0',width=2)
        for gx in range(x1+25, x2-12, 36):
            c.create_line(gx, y1+14, gx, y2-13, fill='#123940', width=1)
        for gy in range(y1+23, y2-9, 24):
            c.create_line(x1+13, gy, x2-13, gy, fill='#123940', width=1)
        xp_center = W / 2
        xp_half_width = max(9, len(str(self.xp)) * 5.2)
        self.draw_icon(xp_center - xp_half_width - 24, 119, 'xp', AMBER, .75)
        self.label(xp_center, 118, str(self.xp), AMBER, 17, 'center', True)
        if self.last_level_xp > 0 or self.last_win_was_replay:
            bonus_text = f'+{self.last_level_xp}'
            self.label(xp_center + xp_half_width + 20, 119,
                       bonus_text, '#a2ffd0', 10, 'w', True)
        items = [('hp','heart','#58f89a',self.max_hp,False),
                 ('gun','bolt',CYAN,self.damage,False),
                 ('shield','shield','#f6cc79',self.shield*100,True),
                 ('speed','speed','#d797ff',self.player_speed,False)]
        for i,(kind,icon,color,value,is_percent) in enumerate(items):
            left = 124+offset+i*169
            cost = self.upgrade_cost(kind)
            allowed = self.can_upgrade(kind)
            afford = self.xp >= cost and allowed
            stat = self.stat_text(value) + ('%' if is_percent else '')
            increase = ('+' + self.stat_text(value*.10, 2 if is_percent else 1)
                        + ('%' if is_percent else '')) if allowed else 'MAX'
            border = color if afford else '#4f676e'
            fill = '#102e36' if afford else '#17252b'
            c.create_rectangle(left, UPGRADE_CARD_TOP,
                               left+158, UPGRADE_CARD_BOTTOM,
                               fill=fill, stipple='gray75',
                               outline=border, width=2)
            c.create_rectangle(left+6, UPGRADE_CARD_TOP+6,
                               left+152, UPGRADE_CARD_BOTTOM-6,
                               outline='#2b5b66', width=1)
            self.draw_icon(left+79, 174, icon,
                           color if afford else '#758183', .84)
            self.label(left+76, 202, stat, '#e4f9f2', 13, 'e', True)
            self.label(left+83, 203, increase,
                       '#76f7a8' if afford else '#7a998a', 9, 'w', True)
            self.draw_icon(left+53, 229, 'xp',
                           '#e9d38c' if afford else '#7e7862', .45)
            self.label(left+79, 229, str(cost),
                       '#e9d38c' if afford else '#7e7862', 10, 'w', True)
        # Cristal con escaneo perpetuo mientras se pisa la plataforma.
        scan = y1 + 10 + ((self.frame * 47) % (y2-y1-20))
        c.create_line(x1+10, scan, x2-10, scan,
                      fill='#24737d', width=1)
        for k in range(4):
            px = 124 + offset + k*169
            streak = ((self.frame*32 + k*30) % 137)
            c.create_line(px+10+streak, UPGRADE_CARD_BOTTOM-3,
                          px+25+streak, UPGRADE_CARD_BOTTOM-3,
                          fill='#76f7d9', width=2)
        flicker = math.sin(self.frame * 5.5) > 0.0
        if flicker:
            for px in (x1+13, x2-13):
                c.create_oval(px-3, y1+6, px+3, y1+12,
                              fill='#b9fff0', outline='')
        # Sin PLAY: abandonar el circulo guarda solo si se compro una mejora.

    def tick(self):
        now=time.monotonic()
        elapsed=max(0.0,now-self.last)
        dt=min(.040,elapsed); self.last=now; self.frame+=dt
        if self.roster_mode:
            self.update_roster(dt,now)
            self.draw_roster()
            self.root.after(16,self.tick)
            return
        if self.state == 'dead':
            self.update_death_animation(dt)
            if now >= self.death_restart_at:
                self.restore_checkpoint()
                now = time.monotonic()
        if self.state == 'warp':
            self.update_transition(dt, now)
            now = time.monotonic()
        self.update_rest_charge(elapsed)
        doors_available = self.portals_available()
        want_open = 1.0 if doors_available else 0.0
        self.door_progress += (want_open-self.door_progress)*min(1.0,dt*5.5)
        self.update(dt,now)
        self.draw()
        self.root.after(16,self.tick)

    def _initial_fullscreen(self):
        if not self._fullscreen_touched:
            self.set_fullscreen(True)

    def set_fullscreen(self, enabled):
        """Pantalla completa sin barra de tareas y con Esc/F11 para salir.

        Windows: ventana sin bordes con prioridad topmost y dimensiones exactas
        del monitor. La barra de tareas queda detras del juego. Al salir se
        restauran los marcos y se quita la prioridad topmost.
        Otros sistemas: modo fullscreen nativo de Tk.
        """
        enabled = bool(enabled)
        if enabled == self._fullscreen_active:
            return
        self._fullscreen_touched = True
        root = self.root
        if enabled:
            self._windowed_geometry = root.geometry()
            self._fullscreen_active = True
            if sys.platform == 'win32':
                # El modo normal "maximizado" deja la barra de tareas visible.
                # Una ventana POPUP borderless cubre el monitor completo.
                root.overrideredirect(True)
                root.geometry(f'{root.winfo_screenwidth()}x{root.winfo_screenheight()}+0+0')
                root.attributes('-topmost', True)
                root.update_idletasks()
                self._reinforce_windows_fullscreen()
                root.after(120, self._reinforce_windows_fullscreen)
            else:
                root.attributes('-fullscreen', True)
                # Tambien cubrir el area completa si no hay gestor de ventanas
                # (por ejemplo, maquinas Linux/Xvfb en pruebas).
                root.geometry(f'{root.winfo_screenwidth()}x{root.winfo_screenheight()}+0+0')
            root.lift()
            root.focus_force()
        else:
            self._fullscreen_active = False
            if sys.platform == 'win32':
                root.attributes('-topmost', False)
                root.overrideredirect(False)
            else:
                root.attributes('-fullscreen', False)
            root.geometry(self._windowed_geometry)
            root.lift()
            root.focus_force()

    def _reinforce_windows_fullscreen(self):
        if not self._fullscreen_active or sys.platform != 'win32':
            return
        try:
            import ctypes
            hwnd = int(self.root.winfo_id())
            user32 = ctypes.windll.user32
            # Definir firmas de punteros; evitar truncamiento HWND en Windows 64-bit.
            user32.GetAncestor.argtypes = (ctypes.c_void_p, ctypes.c_uint)
            user32.GetAncestor.restype = ctypes.c_void_p
            user32.SetWindowPos.argtypes = (
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, ctypes.c_uint)
            user32.SetWindowPos.restype = ctypes.c_bool
            # El id devuelto por Tk puede ser la ventana cliente.
            # GA_ROOT = 2 obtiene la ventana nativa superior.
            top_hwnd = user32.GetAncestor(ctypes.c_void_p(hwnd), 2) or hwnd
            # Coordenadas REALES del monitor, no el area de trabajo que
            # Windows resta por la barra de tareas. Compatible multi-monitor.
            from ctypes import wintypes
            class _Rect(ctypes.Structure):
                _fields_ = [(s, wintypes.LONG) for s in
                            ('left', 'top', 'right', 'bottom')]
            class _MonitorInfo(ctypes.Structure):
                _fields_ = [('cbSize', wintypes.DWORD),
                            ('rcMonitor', _Rect), ('rcWork', _Rect),
                            ('dwFlags', wintypes.DWORD)]
            user32.MonitorFromWindow.argtypes = (ctypes.c_void_p, wintypes.DWORD)
            user32.MonitorFromWindow.restype = ctypes.c_void_p
            user32.GetMonitorInfoW.argtypes = (ctypes.c_void_p,
                                                ctypes.POINTER(_MonitorInfo))
            user32.GetMonitorInfoW.restype = wintypes.BOOL
            monitor = user32.MonitorFromWindow(ctypes.c_void_p(top_hwnd), 2)
            info = _MonitorInfo()
            info.cbSize = ctypes.sizeof(info)
            if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                bounds = info.rcMonitor
                left, top = int(bounds.left), int(bounds.top)
                width, height = (int(bounds.right - bounds.left),
                                 int(bounds.bottom - bounds.top))
            else:
                left = top = 0
                width = self.root.winfo_screenwidth()
                height = self.root.winfo_screenheight()
            # HWND_TOPMOST = -1, SWP_SHOWWINDOW | SWP_FRAMECHANGED.
            user32.SetWindowPos(ctypes.c_void_p(top_hwnd),
                                ctypes.c_void_p(-1), left, top,
                                width, height, 0x0040 | 0x0020)
        except (AttributeError, OSError, ValueError, OverflowError):
            # El borderless + topmost de Tk sigue siendo funcional.
            pass
        self.root.lift()
        self.root.focus_force()

    def close(self):
        # El descanso es progreso local seguro. Nunca confirmar mejoras que
        # continuan pendientes en la plataforma, ni guardar un combate activo.
        if (self.is_rest_room() and self._rest_dirty and
                not self.upgrades_pending_save):
            self._save()
        self.root.destroy()


def main():
    enable_windows_dpi_awareness()
    root=tk.Tk()
    configure_display(root)
    EnterGame(root)
    root.mainloop()


if __name__=='__main__':
    main()
