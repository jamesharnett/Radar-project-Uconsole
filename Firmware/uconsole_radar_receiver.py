#!/usr/bin/env python3
"""
RD-03D Radar Receiver — uConsole (Pygame)
Empfängt UDP-Broadcast-Pakete vom XIAO ESP32-S3 (Access-Point-Modus),
zeichnet ein Radar-Display und spielt einen echten Sinus-Sweep-Sound bei
Zielannäherung (statt der Piezo-Buzzer-Beschränkungen vom Giga-Sketch).

Abhängigkeiten:
    pip install pygame numpy --break-system-packages

Netzwerk:
    Verbindet dich vorher manuell mit dem WiFi "RadarNet" (Passwort
    "radar12345"), das der XIAO als Access Point bereitstellt.
    UDP Port 4210, Broadcast — keine feste IP-Konfiguration nötig.
"""

import socket
import struct
import time
import math
import numpy as np
import pygame

# ── Netzwerk ──
UDP_PORT = 4210
MAX_TARGETS = 3
MAGIC = 0xD03DA7A
PACKET_FMT = "<II" + "hhhB" * MAX_TARGETS
PACKET_SIZE = struct.calcsize(PACKET_FMT)

# ── Display ──
SCREEN_W, SCREEN_H = 800, 480
RADAR_CX, RADAR_CY = SCREEN_W // 2, SCREEN_H
RADAR_R = 420
SECTOR_HALF = 60.0
MAX_DIST_MM = 8000.0

C_BG = (10, 14, 15)
C_GREEN = (74, 222, 128)
C_GDIM = (30, 90, 60)
C_RED = (248, 60, 60)
C_AMBER = (250, 190, 30)
C_CYAN = (60, 220, 240)
DOT_COLS = [C_RED, C_AMBER, C_CYAN]

# ── Sound-Parameter (gleiche Werte wie im Giga-Sketch zuletzt) ──
BEEP_DIST_MIN, BEEP_DIST_MAX = 300.0, 8000.0
BEEP_INTERVAL_MIN, BEEP_INTERVAL_MAX = 0.12, 0.9   # Sekunden
BEEP_FREQ_MIN, BEEP_FREQ_MAX = 700.0, 1400.0       # Hz
PULSE_FREQ = 300.0
PULSE_INTERVAL = 1.8
SAMPLE_RATE = 44100


def make_sweep(freq_start, freq_end, duration, volume=0.5):
    """Echter, weicher Sinus-Sweep (statt 3-stufigem Treppchen wie am Piezo)."""
    n = max(1, int(SAMPLE_RATE * duration))
    t = np.linspace(0, duration, n, endpoint=False)
    freq = np.linspace(freq_start, freq_end, n)
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    wave = np.sin(phase) * volume
    fade = max(1, int(0.006 * SAMPLE_RATE))
    if n > 2 * fade:
        wave[:fade] *= np.linspace(0, 1, fade)
        wave[-fade:] *= np.linspace(1, 0, fade)
    audio = (wave * 32767).astype(np.int16)
    stereo = np.column_stack([audio, audio])
    return pygame.sndarray.make_sound(np.ascontiguousarray(stereo))


class Target:
    __slots__ = ("x", "y", "spd", "valid")
    def __init__(self):
        self.x = self.y = self.spd = 0
        self.valid = False


def recv_socket():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", UDP_PORT))
    s.setblocking(False)
    return s


def dist_to_r(dist_mm):
    return min(dist_mm / MAX_DIST_MM, 1.0) * RADAR_R


def target_to_px(x_mm, y_mm):
    r = dist_to_r(math.hypot(x_mm, y_mm))
    angle_deg = math.degrees(math.atan2(x_mm, y_mm)) if (x_mm or y_mm) else 0
    rad = math.radians(angle_deg - 90.0)
    px = RADAR_CX + r * math.cos(rad)
    py = RADAR_CY + r * math.sin(rad)
    return int(px), int(py)


def draw_sector(surf, font_small):
    for a5 in range(-int(SECTOR_HALF), int(SECTOR_HALF) + 1, 30):
        rad = math.radians(a5 - 90.0)
        col = C_GDIM if a5 == 0 else (0, 40, 70)
        ex = RADAR_CX + RADAR_R * math.cos(rad)
        ey = RADAR_CY + RADAR_R * math.sin(rad)
        pygame.draw.line(surf, col, (RADAR_CX, RADAR_CY), (ex, ey), 1)

    for dist_m in (1, 2, 3, 4, 5, 6, 7, 8):
        r = dist_to_r(dist_m * 1000)
        col = C_GREEN if dist_m in (1, 8) else C_GDIM
        rect = pygame.Rect(RADAR_CX - r, RADAR_CY - r, r * 2, r * 2)
        pygame.draw.arc(surf, col, rect,
                         math.radians(180 - SECTOR_HALF - 90),
                         math.radians(180 + SECTOR_HALF - 90), 1)

    # dickere Randlinien
    for off in (-1, 0, 1):
        for edge in (-SECTOR_HALF, SECTOR_HALF):
            rad = math.radians(edge - 90.0)
            ex = RADAR_CX + off + RADAR_R * math.cos(rad)
            ey = RADAR_CY + RADAR_R * math.sin(rad)
            pygame.draw.line(surf, C_GREEN, (RADAR_CX + off, RADAR_CY), (ex, ey), 1)

    pygame.draw.circle(surf, C_GREEN, (RADAR_CX, RADAR_CY), 5)
    pygame.draw.circle(surf, C_GDIM, (RADAR_CX, RADAR_CY), 9, 1)


def main():
    pygame.mixer.pre_init(frequency=SAMPLE_RATE, channels=2)
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("RD-03D Radar")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("monospace", 14)
    font_big = pygame.font.SysFont("monospace", 28, bold=True)

    sock = recv_socket()
    targets = [Target() for _ in range(MAX_TARGETS)]
    last_packet_t = 0.0

    muted = False
    mute_rect = pygame.Rect(SCREEN_W - 140, SCREEN_H - 80, 130, 40)

    ping_channel = pygame.mixer.Channel(0)
    pulse_channel = pygame.mixer.Channel(1)
    last_beep_t = 0.0
    last_pulse_t = 0.0
    ping_radius = None  # None = kein sichtbarer Ring gerade aktiv
    ping_start_t = 0.0
    PING_SPEED = RADAR_R / 1.6  # px/s, Sweep-Dauer ~1.6s

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if mute_rect.collidepoint(event.pos):
                    muted = not muted

        # ── UDP empfangen (mehrere Pakete pro Frame möglich, nur letztes zählt) ──
        while True:
            try:
                data, _addr = sock.recvfrom(2048)
            except BlockingIOError:
                break
            if len(data) < PACKET_SIZE:
                continue
            vals = struct.unpack(PACKET_FMT, data[:PACKET_SIZE])
            magic, frame_count = vals[0], vals[1]
            if magic != MAGIC:
                continue
            rest = vals[2:]
            for i in range(MAX_TARGETS):
                x, y, spd, valid = rest[i*4:i*4+4]
                targets[i].x, targets[i].y, targets[i].spd = x, y, spd
                targets[i].valid = bool(valid)
            last_packet_t = time.time()

        now = time.time()
        connected = (now - last_packet_t) < 3.0

        # ── nächstgelegenes Ziel ──
        closest_mm = None
        for t in targets:
            if t.valid:
                d = math.hypot(t.x, t.y)
                if closest_mm is None or d < closest_mm:
                    closest_mm = d

        # ── Annäherungs-Ping (Sweep-Ton + visueller Ring synchron) ──
        if not muted and closest_mm is not None:
            d = max(BEEP_DIST_MIN, min(BEEP_DIST_MAX, closest_mm))
            t_norm = (d - BEEP_DIST_MIN) / (BEEP_DIST_MAX - BEEP_DIST_MIN)
            interval = BEEP_INTERVAL_MIN + t_norm * (BEEP_INTERVAL_MAX - BEEP_INTERVAL_MIN)
            freq = BEEP_FREQ_MAX - t_norm * (BEEP_FREQ_MAX - BEEP_FREQ_MIN)
            if now - last_beep_t >= interval and not ping_channel.get_busy():
                snd = make_sweep(freq * 0.6, freq, 0.09, volume=0.55)
                ping_channel.play(snd)
                last_beep_t = now
                ping_radius = 0.0
                ping_start_t = now

        # ── Hintergrund-Puls (unabhängig von Zielerkennung) ──
        if not muted and now - last_pulse_t >= PULSE_INTERVAL and not pulse_channel.get_busy():
            snd = make_sweep(PULSE_FREQ, PULSE_FREQ, 0.05, volume=0.3)
            pulse_channel.play(snd)
            last_pulse_t = now

        # ── Zeichnen ──
        screen.fill(C_BG)
        draw_sector(screen, font)

        # sichtbarer Ping-Ring
        if ping_radius is not None:
            ping_radius = (now - ping_start_t) * PING_SPEED
            if ping_radius <= RADAR_R:
                pygame.draw.circle(screen, C_GREEN, (RADAR_CX, RADAR_CY),
                                    int(ping_radius), 1)
            else:
                ping_radius = None

        for i, t in enumerate(targets):
            if not t.valid:
                continue
            px, py = target_to_px(t.x, t.y)
            pygame.draw.circle(screen, DOT_COLS[i], (px, py), 18, 2)
            pygame.draw.circle(screen, DOT_COLS[i], (px, py), 11, 1)
            pygame.draw.circle(screen, DOT_COLS[i], (px, py), 5)

        # Range-HUD (Basis der Kuppel, wie beim Giga-Sketch)
        hud_w, hud_h = 140, 44
        hud_rect = pygame.Rect(RADAR_CX - hud_w // 2, RADAR_CY - hud_h, hud_w, hud_h)
        pygame.draw.rect(screen, (0, 0, 0), hud_rect)
        pygame.draw.rect(screen, C_GDIM, hud_rect, 1)
        label = f"{closest_mm/1000:.2f}m" if closest_mm is not None else "---"
        txt = font_big.render(label, True, C_RED if closest_mm is not None else C_GDIM)
        screen.blit(txt, txt.get_rect(center=hud_rect.center))

        # TARGETS-Box unten links
        tgt_rect = pygame.Rect(10, SCREEN_H - 80, 140, 60)
        pygame.draw.rect(screen, (8, 32, 32), tgt_rect)
        pygame.draw.rect(screen, C_GDIM, tgt_rect, 1)
        screen.blit(font.render("TARGETS", True, C_GDIM), (tgt_rect.x + 6, tgt_rect.y + 4))
        line_y = tgt_rect.y + 20
        for i, t in enumerate(targets):
            if not t.valid:
                continue
            d = math.hypot(t.x, t.y) / 1000.0
            txt = font.render(f"T{i+1} {d:.2f}m", True, DOT_COLS[i])
            screen.blit(txt, (tgt_rect.x + 6, line_y))
            line_y += 16

        # Mute-Button unten rechts
        pygame.draw.rect(screen, (20, 0, 0) if muted else (0, 20, 10), mute_rect)
        pygame.draw.rect(screen, C_RED if muted else C_GREEN, mute_rect, 1)
        label = "STUMM" if muted else "BUZZER AN"
        txt = font.render(label, True, C_RED if muted else C_GREEN)
        screen.blit(txt, txt.get_rect(center=mute_rect.center))

        # Verbindungsstatus oben rechts
        status = "RD-03D: OK" if connected else "RD-03D: ---"
        col = C_GREEN if connected else C_RED
        screen.blit(font.render(status, True, col), (SCREEN_W - 140, 10))

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()
    sock.close()


if __name__ == "__main__":
    main()
