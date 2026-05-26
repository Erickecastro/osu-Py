#!/usr/bin/env python
"""Script para criar um teste visual dos sliders sem precisar do jogo inteiro"""

import os
import sys
import math
sys.path.insert(0, os.path.dirname(__file__))

try:
    import pygame
    print("✓ pygame disponível")
except ImportError:
    print("❌ pygame não instalado")
    sys.exit(1)

try:
    import pygame_gui
    print("✓ pygame_gui disponível")
except ImportError:
    print("❌ pygame_gui não instalado")
    sys.exit(1)

from core.beatmap_loader import BeatmapLoader

# Inicializa Pygame
pygame.init()
pygame.mixer.init()

# Cria uma janela simples
WIDTH, HEIGHT = 1024, 768
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Slider Visual Test")
clock = pygame.time.Clock()

# Carrega um beatmap
loader = BeatmapLoader()
beatmap_path = None
for root, dirs, files in os.walk("songs"):
    for file in files:
        if file.endswith(".osu"):
            beatmap_path = os.path.join(root, file)
            break
    if beatmap_path:
        break

if not beatmap_path:
    print("❌ Nenhum beatmap encontrado")
    pygame.quit()
    sys.exit(1)

print(f"Carregando beatmap: {beatmap_path}")
notes = loader.parse_hitobjects(beatmap_path)
sliders = [n for n in notes if n["type"] == "slider"][:20]  # Primeiros 20 sliders

print(f"✓ Carregados {len(sliders)} sliders para visualização")

# Função para escalar coordenadas de beatmap para tela
def scale_pos(x, y):
    """Converte de coordenadas de beatmap (512x384) para tela (1024x768)"""
    # Playfield: 512x384 (padrão osu)
    # Margem de segurança
    margin_x = 50
    margin_y = 50
    
    scale_x = (WIDTH - 2 * margin_x) / 512.0
    scale_y = (HEIGHT - 2 * margin_y) / 384.0
    
    screen_x = margin_x + x * scale_x
    screen_y = margin_y + y * scale_y
    
    return int(screen_x), int(screen_y)

# Loop principal
running = True
current_slider = 0
show_info = True

while running:
    clock.tick(60)
    
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
            elif event.key == pygame.K_RIGHT:
                current_slider = (current_slider + 1) % len(sliders)
            elif event.key == pygame.K_LEFT:
                current_slider = (current_slider - 1) % len(sliders)
            elif event.key == pygame.K_i:
                show_info = not show_info
    
    # Desenha fundo
    screen.fill((30, 30, 30))
    
    # Desenha grade de beatmap
    playfield_x1, playfield_y1 = scale_pos(0, 0)
    playfield_x2, playfield_y2 = scale_pos(512, 384)
    pygame.draw.rect(screen, (80, 80, 80), (playfield_x1, playfield_y1, playfield_x2 - playfield_x1, playfield_y2 - playfield_y1), 2)
    
    # Desenha slider atual
    if current_slider < len(sliders):
        slider = sliders[current_slider]
        
        # Extrai informações do slider
        start_x, start_y = scale_pos(slider["x"], slider["y"])
        curve_points = slider["curve_points"]
        
        # Desenha o caminho da curva
        if len(curve_points) > 1:
            scaled_points = [scale_pos(p["x"], p["y"]) for p in curve_points]
            
            # Desenha linha do caminho
            for i in range(len(scaled_points) - 1):
                pygame.draw.line(screen, (100, 200, 255), scaled_points[i], scaled_points[i+1], 2)
        
        # Desenha pontos ao longo do caminho
        if len(curve_points) > 0:
            for i, p in enumerate(curve_points):
                if i % max(1, len(curve_points) // 10) == 0:
                    x, y = scale_pos(p["x"], p["y"])
                    pygame.draw.circle(screen, (100, 200, 255), (x, y), 3)
        
        # Desenha círculo de início
        pygame.draw.circle(screen, (0, 255, 0), (start_x, start_y), 8)
        pygame.draw.circle(screen, (0, 200, 0), (start_x, start_y), 8, 2)
        
        # Desenha círculo de fim
        if len(curve_points) > 0:
            end_point = curve_points[-1]
            end_x, end_y = scale_pos(end_point["x"], end_point["y"])
            pygame.draw.circle(screen, (255, 0, 0), (end_x, end_y), 8)
            pygame.draw.circle(screen, (200, 0, 0), (end_x, end_y), 8, 2)
        
        # Mostra informações
        if show_info:
            font = pygame.font.Font(None, 24)
            
            # Calcula comprimento real
            real_length = 0.0
            for i in range(len(curve_points) - 1):
                p1 = curve_points[i]
                p2 = curve_points[i + 1]
                dx = p2["x"] - p1["x"]
                dy = p2["y"] - p1["y"]
                real_length += math.hypot(dx, dy)
            
            info_lines = [
                f"Slider {current_slider + 1}/{len(sliders)}",
                f"Tipo: {slider['curve_type']}",
                f"Posição: ({slider['x']}, {slider['y']})",
                f"Comprimento esperado: {slider['slider_distance']:.2f}",
                f"Comprimento real: {real_length:.2f}",
                f"Erro: {abs(real_length - slider['slider_distance']):.2f} ({abs(real_length - slider['slider_distance'])/slider['slider_distance']*100:.1f}%)",
                f"Pontos: {len(curve_points)}",
                "",
                "Controles:",
                "← → : Mudar slider",
                "I : Alternar informações",
                "ESC : Sair"
            ]
            
            for i, line in enumerate(info_lines):
                text = font.render(line, True, (255, 255, 255))
                screen.blit(text, (10, 10 + i * 25))
    
    pygame.display.flip()

pygame.quit()
print("✓ Teste visual encerrado")
