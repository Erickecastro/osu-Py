#!/usr/bin/env python
"""Teste visual dos sliders com o novo sistema de normalização"""

import os
import sys
import math
sys.path.insert(0, os.path.dirname(__file__))

from core.beatmap_loader import BeatmapLoader

def calculate_arc_length(points):
    """Calcula o comprimento total do caminho interpolado"""
    total = 0.0
    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]
        dx = p2['x'] - p1['x']
        dy = p2['y'] - p1['y']
        total += math.hypot(dx, dy)
    return total

def find_endpoint(points, target_length):
    """Encontra o ponto no caminho que corresponde ao target_length"""
    arc_length = 0.0
    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]
        dx = p2['x'] - p1['x']
        dy = p2['y'] - p1['y']
        segment_length = math.hypot(dx, dy)
        
        if arc_length + segment_length >= target_length:
            # Interpola linearmente dentro desse segmento
            t = (target_length - arc_length) / segment_length if segment_length > 0 else 0
            x = p1['x'] + (p2['x'] - p1['x']) * t
            y = p1['y'] + (p2['y'] - p1['y']) * t
            return {'x': x, 'y': y}
        
        arc_length += segment_length
    
    # Se chegou ao final, retorna o último ponto
    return points[-1]

def test_slider_endpoints():
    """Verifica se os sliders terminam no ponto correto"""
    
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
        return False
    
    notes = loader.parse_hitobjects(beatmap_path)
    sliders = [n for n in notes if n["type"] == "slider"][:10]  # Primeiros 10
    
    print("Verificação de Endpoints dos Sliders:")
    print("=" * 70)
    
    all_correct = True
    for i, slider in enumerate(sliders):
        actual_length = calculate_arc_length(slider['curve_points'])
        expected_length = slider['slider_distance']
        
        # Encontra o endpoint esperado (ponto em expected_length)
        endpoint = find_endpoint(slider['curve_points'], expected_length)
        last_point = slider['curve_points'][-1]
        
        # Calcula distância entre endpoint esperado e último ponto
        endpoint_error = math.hypot(
            endpoint['x'] - last_point['x'],
            endpoint['y'] - last_point['y']
        )
        
        length_error = abs(actual_length - expected_length)
        
        status = "✓" if length_error < expected_length * 0.1 else "⚠"
        
        print(f"\n{status} Slider {i + 1}:")
        print(f"    Comprimento esperado: {expected_length:.2f}")
        print(f"    Comprimento real:    {actual_length:.2f}")
        print(f"    Erro:                {length_error:.2f} ({length_error/expected_length*100:.1f}%)")
        print(f"    Último ponto:        ({last_point['x']:.0f}, {last_point['y']:.0f})")
        print(f"    Endpoint esperado:   ({endpoint['x']:.0f}, {endpoint['y']:.0f})")
        print(f"    Erro de endpoint:    {endpoint_error:.2f}")
        
        if length_error > expected_length * 0.1:
            all_correct = False
    
    print("\n" + "=" * 70)
    if all_correct:
        print("✓ Todos os sliders têm comprimento correto!")
    else:
        print("⚠ Alguns sliders podem precisar de ajustes")
    
    return all_correct

if __name__ == "__main__":
    try:
        test_slider_endpoints()
    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
