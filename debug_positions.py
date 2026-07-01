import pygame
import sys

# Simulando as variáveis do osu!
osu_base_width = 640
osu_base_height = 480
playfield_width = 512
playfield_height = 384

# Teste com diferentes resoluções
test_resolutions = [
    (1920, 1080),
    (1280, 720),
    (640, 480),
]

# Teste com algumas coordenadas de notas
test_notes = [
    (0, 0),      # Canto superior esquerdo do playfield
    (256, 192),  # Centro do playfield
    (512, 384),  # Canto inferior direito do playfield
    (100, 100),
]

print("="*60)
print("DEBUG: Verificacao de Escala e Offset do Playfield")
print("="*60)

for width, height in test_resolutions:
    print(f"\nResolução: {width}x{height}")

    # Cálculo da escala
    scale = min(width / osu_base_width, height / osu_base_height)

    # Cálculo dos offsets
    offset_x = (width - (playfield_width * scale)) / 2
    offset_y = (height - (playfield_height * scale)) / 2

    print(f"  Escala: {scale:.4f}")
    print(f"  Offset X: {offset_x:.2f}")
    print(f"  Offset Y: {offset_y:.2f}")

    print("\n  Posições das notas:")
    for note_x, note_y in test_notes:
        # Calculando a posição na tela
        screen_x = offset_x + note_x * scale
        screen_y = offset_y + note_y * scale
        print(f"    Nota osu! ({note_x}, {note_y}) -> Tela ({screen_x:.2f}, {screen_y:.2f})")

print("\n" + "="*60)

# Verificando se a fórmula está correta
print("\nVerificação rápida:")
print("  - Para 640x480 (resolução base osu!):")
print("    Escala = 1.0, offset_x = 64, offset_y = 48")
print("    Nota (256, 192) → Tela (256+64, 192+48) = (320, 240) (CENTRO DA TELA) ✓")
print("="*60)
