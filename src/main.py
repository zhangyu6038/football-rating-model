#!/usr/bin/env python3
"""
Football Rating Model V2.0 - 主入口
用法：
  python3 src/main.py --input /tmp/match_data.json --output reports/2026-07-07_report.md
  python3 src/main.py --manual  # 手动输入模式
"""

import argparse
import json
import sys
import os
import yaml
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_collector import DataCollector
from rating_engine import RatingEngine
from calibration import CalibrationEngine
from optimizer import PortfolioOptimizer
from reporter import ReportGenerator


def load_config(config_path: str = 'config.yaml') -> dict:
    """加载配置文件"""
    paths = [
        config_path,
        os.path.join(os.path.dirname(__file__), '..', 'config.yaml'),
        'config.yaml',
    ]
    for p in paths:
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
    print("[WARNING] config.yaml 未找到，使用默认配置")
    return {
        'league_strength': {1:1.0, 2:0.85, 3:0.75, 'cup':0.90},
        'weights': {'p_clean':0.30, 'm_factor':0.15, 'h_factor':0.15, 'q_score':0.20, 'stability':0.10, 'upset_signal':0.10},
        'thresholds': {'a_score_entry':0.55, 'a_score_downgrade':0.45, 'hedge_trigger':0.35},
        'constraints': {'max_total_cost':30, 'max_combinations':3, 'max_multiplier':3, 'core_budget_ratio':0.70, 'hedge_budget_ratio':0.20},
        'calibration': {'rsi_hot_threshold':0.75, 'rsi_discount':0.95, 'prd_max':1.08, 'prd_min':1.00, 'hedge_odds_min':5.0},
    }


def main():
    parser = argparse.ArgumentParser(description='Football Rating Model V2.0')
    parser.add_argument('--input', '-i', type=str, help='输入 JSON 文件路径')
    parser.add_argument('--output', '-o', type=str, default=None, help='输出报告路径')
    parser.add_argument('--manual', action='store_true', help='手动输入模式')
    parser.add_argument('--config', '-c', type=str, default='config.yaml', help='配置文件路径')
    args = parser.parse_args()
    
    config = load_config(args.config)
    collector = DataCollector(config)
    
    if args.manual:
        print("手动输入模式：请粘贴 JSON 格式的比赛数据（粘贴后按 Ctrl+D 结束）：")
        raw_input = sys.stdin.read()
        try:
            data = json.loads(raw_input)
            matches = collector.load_manual(data if isinstance(data, list) else [data])
        except json.JSONDecodeError:
            print("[ERROR] JSON 格式错误")
            sys.exit(1)
    elif args.input:
        matches = collector.load_from_webbridge(args.input)
    else:
        print("[ERROR] 请指定 --input 或 --manual")
        sys.exit(1)
    
    if len(matches) < 2:
        print("[ERROR] 至少需要2场比赛才能生成组合")
        if len(matches) == 1:
            print("[INFO] 仅1场比赛，输出单场评级")
        else:
            sys.exit(1)
    
    engine = RatingEngine(args.config)
    ratings = []
    all_options_ranking = []
    
    for match in matches:
        result = engine.analyze_match(match)
        ratings.append(result)
        
        for opt_name, opt_data in result['options'].items():
            all_options_ranking.append({
                'match': f"{result['home']} vs {result['away']}",
                'option': opt_name,
                'odds': opt_data['odds'],
                'p_clean': opt_data['p_clean'],
                'a_score': opt_data['a_score'],
            })
    
    all_options_ranking.sort(key=lambda x: x['a_score'], reverse=True)
    
    entry_threshold = config['thresholds']['a_score_entry']
    match_a_options = [o for o in ratings[0]['options'].values() 
                       if o['a_score'] >= entry_threshold and o['type'] in ['总进球数', '半全场']]
    match_b_options = [o for o in ratings[1]['options'].values()
                       if o['a_score'] >= entry_threshold and o['type'] in ['总进球数', '半全场']]
    
    if not match_a_options:
        downgrade = config['thresholds']['a_score_downgrade']
        match_a_options = [o for o in ratings[0]['options'].values()
                           if o['a_score'] >= downgrade and o['type'] in ['总进球数', '半全场']]
        print(f"[INFO] 比赛1 无选项达到 {entry_threshold}，降至 {downgrade}")
    if not match_b_options:
        downgrade = config['thresholds']['a_score_downgrade']
        match_b_options = [o for o in ratings[1]['options'].values()
                           if o['a_score'] >= downgrade and o['type'] in ['总进球数', '半全场']]
        print(f"[INFO] 比赛2 无选项达到 {entry_threshold}，降至 {downgrade}")
    
    calibrator = CalibrationEngine(config)
    match_a_calibrated = calibrator.calibrate_options(
        {f"{o['type']}{o['value']}": o for o in match_a_options}
    )
    match_b_calibrated = calibrator.calibrate_options(
        {f"{o['type']}{o['value']}": o for o in match_b_options}
    )
    
    optimizer = PortfolioOptimizer(config)
    
    temp_combos = []
    for oa in match_a_calibrated.values():
        for ob in match_b_calibrated.values():
            temp_combos.append({'prob': oa['p_clean'] * ob['p_clean']})
    
    hedge_needed = calibrator.check_hedge_needed(temp_combos)
    hedge_option = None
    if hedge_needed:
        hedge_option = calibrator.select_hedge_option(ratings[0]['options'], ratings[0]['match_id'])
        if not hedge_option:
            hedge_option = calibrator.select_hedge_option(ratings[1]['options'], ratings[1]['match_id'])
    
    portfolio = optimizer.generate_combinations(
        list(match_a_calibrated.values()),
        list(match_b_calibrated.values()),
        hedge_option,
    )
    
    report_data = {
        'matches': ratings,
        'rankings': all_options_ranking,
        'portfolio': portfolio,
    }
    
    reporter = ReportGenerator()
    report_md = reporter.generate(report_data)
    
    if args.output:
        os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report_md)
        print(f"[OK] 报告已保存至 {args.output}")
    else:
        print(report_md)
    
    json_output = args.output.replace('.md', '.json') if args.output else None
    if json_output:
        with open(json_output, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2, default=str)


if __name__ == '__main__':
    main()
