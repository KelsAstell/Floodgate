#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
成就数据导出脚本
将 constant.py 中的 ACHIEVEMENT_DATA 导出为 JSON 文件
"""

import json
import os
import sys
from datetime import datetime

# 设置控制台编码
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 添加项目路径以便导入模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from openapi.constant import ACHIEVEMENT_DATA, ACHIEVEMENT_IDMAP
except ImportError as e:
    print(f"导入模块失败: {e}")
    print("请确保在项目根目录运行此脚本")
    sys.exit(1)

def export_achievements_to_json(output_file="achievements.json", indent=2):
    """
    将成就数据导出为 JSON 文件
    
    Args:
        output_file (str): 输出文件名
        indent (int): JSON 缩进空格数
    """
    try:
        # 确保输出目录存在
        output_dir = os.path.dirname(os.path.abspath(output_file))
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # 合并 ACHIEVEMENT_DATA 和 ACHIEVEMENT_IDMAP
        merged_achievements = {}
        for ach_id, achievement_data in ACHIEVEMENT_DATA.items():
            # 创建新的数据字典，保留原有数据
            merged_data = achievement_data.copy()
            # 添加转换后的 IDMAP 数据
            if ach_id in ACHIEVEMENT_IDMAP:
                idmap_value = ACHIEVEMENT_IDMAP[ach_id]
                # 将 "10/102339" 转换为 "10_102339"
                icon_id = idmap_value.replace('/', '_')
                merged_data['icon_id'] = icon_id
            merged_achievements[ach_id] = merged_data
        
        # 准备导出数据
        export_data = {
            "export_time": datetime.now().isoformat(),
            "total_count": len(merged_achievements),
            "achievements": merged_achievements
        }
        
        # 写入 JSON 文件
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=indent)
        
        print(f"成功导出 {len(merged_achievements)} 个成就到文件: {output_file}")
        print(f"导出时间: {export_data['export_time']}")
        
        # 显示统计信息
        rarity_count = {}
        mask_count = 0
        icon_id_count = 0
        
        for achievement in merged_achievements.values():
            rarity = achievement.get('rarity', 'unknown')
            rarity_count[rarity] = rarity_count.get(rarity, 0) + 1
            if achievement.get('mask', False):
                mask_count += 1
            if 'icon_id' in achievement:
                icon_id_count += 1
        
        print("\n统计信息:")
        print(f"   总成就数: {len(merged_achievements)}")
        print(f"   包含图标ID的成就数: {icon_id_count}")
        print(f"   隐藏成就数: {mask_count}")
        print("   稀有度分布:")
        for rarity, count in sorted(rarity_count.items()):
            print(f"     - {rarity}: {count} 个")
            
    except Exception as e:
        print(f"导出失败: {e}")
        sys.exit(1)

def export_achievements_simple(output_file="achievements_simple.json"):
    """
    简单格式导出（只导出合并后的数据）
    """
    try:
        # 合并 ACHIEVEMENT_DATA 和 ACHIEVEMENT_IDMAP
        merged_achievements = {}
        for ach_id, achievement_data in ACHIEVEMENT_DATA.items():
            merged_data = achievement_data.copy()
            if ach_id in ACHIEVEMENT_IDMAP:
                idmap_value = ACHIEVEMENT_IDMAP[ach_id]
                # 将 "10/102339" 转换为 "10_102339"
                icon_id = idmap_value.replace('/', '_')
                merged_data['icon_id'] = icon_id
            merged_achievements[ach_id] = merged_data
            
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(merged_achievements, f, ensure_ascii=False, indent=2)
        print(f"简单格式导出完成: {output_file}")
    except Exception as e:
        print(f"简单格式导出失败: {e}")

if __name__ == "__main__":
    print("开始导出成就数据...")
    
    # 标准格式导出
    export_achievements_to_json("achievements.json")
    
    # 简单格式导出
    export_achievements_simple("achievements_simple.json")
    
    print("\n所有导出任务完成！")
