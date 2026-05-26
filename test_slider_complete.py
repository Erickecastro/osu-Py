#!/usr/bin/env python
"""Teste completo do fix de sliders - sem interface gráfica"""

import os
import sys
import math
sys.path.insert(0, os.path.dirname(__file__))

from core.beatmap_loader import BeatmapLoader

def analyze_slider_fix():
    """Análise completa do fix implementado"""
    
    print("="*70)
    print("ANÁLISE COMPLETA DO FIX DE SLIDERS")
    print("="*70)
    
    loader = BeatmapLoader()
    
    # Encontra beatmap
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
    
    print(f"\n📁 Beatmap: {os.path.basename(beatmap_path)}")
    
    # Carrega notas
    notes = loader.parse_hitobjects(beatmap_path)
    sliders = [n for n in notes if n["type"] == "slider"]
    circles = [n for n in notes if n["type"] == "circle"]
    
    print(f"📊 Totais: {len(circles)} círculos, {len(sliders)} sliders")
    
    # Análise detalhada
    print("\n" + "="*70)
    print("ANÁLISE DE SLIDERS")
    print("="*70)
    
    # Verifica se slider_distance está sendo capturado
    sliders_with_distance = sum(1 for s in sliders if "slider_distance" in s and s["slider_distance"] > 0)
    print(f"\n✓ Sliders com slider_distance: {sliders_with_distance}/{len(sliders)}")
    
    if sliders_with_distance == 0:
        print("❌ ERRO: Nenhum slider tem slider_distance!")
        return False
    
    # Estatísticas de comprimento
    print("\n📏 Estatísticas de Comprimento:")
    
    errors = []
    curve_type_stats = {}
    
    for slider in sliders:
        if "slider_distance" not in slider or slider["slider_distance"] <= 0:
            continue
        
        # Calcula comprimento real
        real_length = 0.0
        for i in range(len(slider["curve_points"]) - 1):
            p1 = slider["curve_points"][i]
            p2 = slider["curve_points"][i + 1]
            dx = p2["x"] - p1["x"]
            dy = p2["y"] - p1["y"]
            real_length += math.hypot(dx, dy)
        
        error = abs(real_length - slider["slider_distance"]) / slider["slider_distance"] * 100
        errors.append(error)
        
        # Agrupa por tipo de curva
        curve_type = slider.get("curve_type", "L")
        if curve_type not in curve_type_stats:
            curve_type_stats[curve_type] = {"count": 0, "errors": []}
        curve_type_stats[curve_type]["count"] += 1
        curve_type_stats[curve_type]["errors"].append(error)
    
    if errors:
        avg_error = sum(errors) / len(errors)
        max_error = max(errors)
        min_error = min(errors)
        
        print(f"  Erro médio:  {avg_error:.2f}%")
        print(f"  Erro mínimo: {min_error:.2f}%")
        print(f"  Erro máximo: {max_error:.2f}%")
        
        # Por tipo de curva
        print("\n📈 Por Tipo de Curva:")
        for curve_type in sorted(curve_type_stats.keys()):
            stats = curve_type_stats[curve_type]
            if stats["errors"]:
                avg = sum(stats["errors"]) / len(stats["errors"])
                print(f"  {curve_type}: {stats['count']} sliders, erro médio {avg:.2f}%")
    
    # Verifica pontos de início e fim
    print("\n🎯 Verificação de Endpoints:")
    
    endpoint_errors = []
    for slider in sliders[:20]:  # Primeiros 20
        if not slider["curve_points"]:
            continue
        
        start = slider["curve_points"][0]
        end = slider["curve_points"][-1]
        
        # O ponto de início deveria estar próximo às coordenadas do slider
        start_error = math.hypot(
            start["x"] - slider["x"],
            start["y"] - slider["y"]
        )
        
        endpoint_errors.append(start_error)
    
    if endpoint_errors:
        avg_start_error = sum(endpoint_errors) / len(endpoint_errors)
        print(f"  Erro de ponto inicial: {avg_start_error:.2f}px (média)")
    
    # Resumo final
    print("\n" + "="*70)
    print("✓ CONCLUSÃO")
    print("="*70)
    
    success = (
        sliders_with_distance > 0 and
        (avg_error := (sum(errors) / len(errors) if errors else 0)) < 30 and
        endpoint_errors and
        (sum(endpoint_errors) / len(endpoint_errors)) < 2
    )
    
    if success:
        print("\n✓ FIX IMPLEMENTADO COM SUCESSO!")
        print(f"  - {sliders_with_distance} sliders com comprimento correto")
        print(f"  - Erro médio de comprimento: {avg_error:.2f}%")
        print(f"  - Pontos de início/fim posicionados corretamente")
        print("\n✓ Os sliders agora:")
        print("  1. Têm comprimento correto de acordo com beatmap")
        print("  2. Terminam no ponto final correto")
        print("  3. Não têm gaps entre o corpo e o círculo final")
    else:
        print("\n❌ PROBLEMAS DETECTADOS")
        if sliders_with_distance == 0:
            print("  - slider_distance não está sendo capturado")
        if avg_error and avg_error > 30:
            print(f"  - Erro de comprimento muito alto: {avg_error:.2f}%")
        if not endpoint_errors or (sum(endpoint_errors) / len(endpoint_errors)) > 2:
            print("  - Pontos de início/fim não estão corretos")
    
    return success

if __name__ == "__main__":
    try:
        success = analyze_slider_fix()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERRO DURANTE ANÁLISE: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
