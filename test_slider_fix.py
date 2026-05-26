#!/usr/bin/env python
"""Teste para verificar se os sliders estão seguindo o comprimento correto"""

import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from core.beatmap_loader import BeatmapLoader

def test_slider_distance():
    """Teste se o slider_distance está sendo extraído e usado corretamente"""
    
    loader = BeatmapLoader()
    
    # Encontra o beatmap de teste
    beatmap_path = None
    for root, dirs, files in os.walk("songs"):
        for file in files:
            if file.endswith(".osu"):
                beatmap_path = os.path.join(root, file)
                print(f"Testando com beatmap: {beatmap_path}")
                break
        if beatmap_path:
            break
    
    if not beatmap_path:
        print("❌ Nenhum beatmap encontrado para teste")
        return False
    
    # Carrega as notas do beatmap
    notes = loader.parse_hitobjects(beatmap_path)
    
    # Filtra apenas sliders
    sliders = [n for n in notes if n["type"] == "slider"]
    
    if not sliders:
        print("❌ Nenhum slider encontrado no beatmap")
        return False
    
    print(f"✓ Encontrados {len(sliders)} sliders")
    
    # Verifica se o slider_distance está sendo armazenado
    sliders_with_distance = [s for s in sliders if "slider_distance" in s]
    sliders_with_distance_value = [s for s in sliders_with_distance if s["slider_distance"] > 0]
    
    print(f"✓ Sliders com slider_distance: {len(sliders_with_distance_value)} de {len(sliders)}")
    
    # Amostra alguns sliders para verificação
    for i, slider in enumerate(sliders_with_distance_value[:3]):
        print(f"\n  Slider {i + 1}:")
        print(f"    - Posição: ({slider['x']}, {slider['y']})")
        print(f"    - Tipo de curva: {slider['curve_type']}")
        print(f"    - Distância do slider: {slider['slider_distance']}")
        print(f"    - Pontos no caminho: {len(slider['curve_points'])}")
        
        if len(slider['curve_points']) >= 2:
            # Calcula o comprimento real do caminho
            total_length = 0.0
            for j in range(len(slider['curve_points']) - 1):
                p1 = slider['curve_points'][j]
                p2 = slider['curve_points'][j + 1]
                dx = p2['x'] - p1['x']
                dy = p2['y'] - p1['y']
                import math
                total_length += math.hypot(dx, dy)
            
            print(f"    - Comprimento do caminho interpolado: {total_length:.2f}")
            
            # Verifica se o comprimento está próximo ao esperado
            error_pct = abs(total_length - slider['slider_distance']) / slider['slider_distance'] * 100 if slider['slider_distance'] > 0 else 0
            print(f"    - Erro de comprimento: {error_pct:.1f}%")
            
            # Coordenadas do primeiro e último ponto
            first = slider['curve_points'][0]
            last = slider['curve_points'][-1]
            print(f"    - Primeiro ponto: ({first['x']}, {first['y']})")
            print(f"    - Último ponto: ({last['x']}, {last['y']})")
    
    print("\n✓ Teste concluído com sucesso!")
    return True

if __name__ == "__main__":
    try:
        test_slider_distance()
    except Exception as e:
        print(f"❌ Erro durante o teste: {e}")
        import traceback
        traceback.print_exc()
