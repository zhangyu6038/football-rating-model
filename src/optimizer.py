import math
from typing import Dict, List, Tuple


class PortfolioOptimizer:
    """投注组合优化器"""
    
    def __init__(self, config: dict):
        constraints = config.get('constraints', {})
        self.max_cost = constraints.get('max_total_cost', 30)
        self.max_combos = constraints.get('max_combinations', 3)
        self.max_mult = constraints.get('max_multiplier', 3)
        self.core_ratio = constraints.get('core_budget_ratio', 0.70)
        self.hedge_ratio = constraints.get('hedge_budget_ratio', 0.20)
        self.risk_aversion = 0.5  # λ
    
    def generate_combinations(self, match_a_options: List[Dict], 
                              match_b_options: List[Dict],
                              hedge_option: Dict = None) -> Dict:
        """生成投注组合"""
        all_combos = []
        for opt_a in match_a_options:
            for opt_b in match_b_options:
                combo_prob = opt_a['p_clean'] * opt_b['p_clean']
                combo_odds = opt_a['odds'] * opt_b['odds']
                combo_a_score = (opt_a['a_score'] + opt_b['a_score']) / 2
                
                expected_return = combo_prob * combo_odds
                if expected_return < 1.0:
                    continue
                
                all_combos.append({
                    'name': f"{opt_a['value']}球×{opt_b['value']}球",
                    'match_a_option': opt_a,
                    'match_b_option': opt_b,
                    'odds': round(combo_odds, 2),
                    'prob': round(combo_prob, 4),
                    'a_score': round(combo_a_score, 4),
                    'expected_return': round(expected_return, 4),
                })
        
        if not all_combos:
            return self._empty_result("未找到有效组合")
        
        for c in all_combos:
            c['score'] = c['expected_return'] - self.risk_aversion * (1 - c['prob'])
        all_combos.sort(key=lambda x: x['score'], reverse=True)
        
        core_combos = all_combos[:self.max_combos]
        core_budget = self.max_cost * self.core_ratio
        
        for c in core_combos:
            mult = math.ceil(core_budget / (c['odds'] * 2 * len(core_combos)))
            mult = min(mult, self.max_mult)
            c['multiplier'] = mult
            c['cost'] = mult * 2
            c['return'] = round(c['cost'] * c['odds'] / 2, 2)
        
        total_core_cost = sum(c['cost'] for c in core_combos)
        
        hedge_part = None
        remaining = self.max_cost - total_core_cost
        if hedge_option and remaining >= 2:
            hedge_mult = min(2, math.floor(remaining / 2))
            if hedge_mult > 0:
                hedge_part = {
                    'name': f"对冲-{hedge_option['value']}",
                    'option': hedge_option,
                    'odds': hedge_option['odds'],
                    'multiplier': hedge_mult,
                    'cost': hedge_mult * 2,
                    'return': round(hedge_mult * 2 * hedge_option['odds'] / 2, 2),
                    'type': 'hedge',
                }
        
        total_cost = total_core_cost + (hedge_part['cost'] if hedge_part else 0)
        
        stress_test = self._stress_test(core_combos, hedge_part, total_cost)
        best_return = max(c['return'] for c in core_combos) if core_combos else 0
        is_protected = best_return >= total_cost
        
        return {
            'core_combinations': core_combos,
            'hedge': hedge_part,
            'total_cost': total_cost,
            'best_return': best_return,
            'is_protected': is_protected,
            'stress_test': stress_test,
        }
    
    def _stress_test(self, core_combos: List[Dict], hedge: Dict, total_cost: float) -> Dict:
        """四种情景压力测试"""
        scenarios = []
        
        if core_combos:
            best = max(core_combos, key=lambda x: x['return'])
            scenarios.append({
                '情景': '最优',
                '命中组合': best['name'],
                '总回报': best['return'],
                '盈亏': round(best['return'] - total_cost, 2),
            })
        
        if len(core_combos) >= 2:
            second = sorted(core_combos, key=lambda x: x['return'], reverse=True)[1]
            scenarios.append({
                '情景': '次优',
                '命中组合': second['name'],
                '总回报': second['return'],
                '盈亏': round(second['return'] - total_cost, 2),
            })
        
        if hedge:
            scenarios.append({
                '情景': '仅对冲',
                '命中组合': hedge['name'],
                '总回报': hedge['return'],
                '盈亏': round(hedge['return'] - total_cost, 2),
            })
        
        scenarios.append({
            '情景': '极端（全黑）',
            '命中组合': '无',
            '总回报': 0,
            '盈亏': -total_cost,
        })
        
        return scenarios
    
    def _empty_result(self, reason: str) -> Dict:
        return {
            'core_combinations': [],
            'hedge': None,
            'total_cost': 0,
            'best_return': 0,
            'is_protected': False,
            'stress_test': [],
            'warning': reason,
        }