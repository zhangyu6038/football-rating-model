from typing import Dict, List, Optional


class CalibrationEngine:
    """智能校准引擎"""
    
    def __init__(self, config: dict):
        self.config = config.get('calibration') or {}
        self.thresholds = config.get('thresholds') or {}
        self.rsi_hot = self.config.get('rsi_hot_threshold', 0.75)
        self.rsi_discount = self.config.get('rsi_discount', 0.95)
        self.prd_max = self.config.get('prd_max', 1.08)
        self.prd_min = self.config.get('prd_min', 1.00)
        self.hedge_odds_min = self.config.get('hedge_odds_min', 5.0)
        self.hedge_trigger = self.thresholds.get('hedge_trigger', 0.35)
    
    def calibrate_options(self, options: Dict, market_heat: float = 0.5,
                          q_change: float = 0.0, odds_change: float = 0.0) -> Dict:
        """对选项进行智能校准"""
        calibrated = {}
        for name, opt in options.items():
            new_opt = opt.copy()
            a_score = opt['a_score']
            
            # RSI 校准：市场过热时降低高概率选项的吸引力
            if market_heat > self.rsi_hot and opt['p_clean'] > 0.25:
                a_score *= self.rsi_discount
            
            # PRD 补偿：基本面改善但赔率未动
            prd = self._calc_prd(q_change, odds_change)
            if prd > 1.0 and opt['p_clean'] > 0.20:
                a_score *= prd
            
            new_opt['a_score'] = round(min(1.0, a_score), 4)
            new_opt['calibrated'] = True
            calibrated[name] = new_opt
        
        return calibrated
    
    def _calc_prd(self, q_change: float, odds_change: float) -> float:
        """计算认知滞后补偿因子"""
        if q_change <= 0:
            return 1.0
        prd = 1.0 + max(0, (q_change - odds_change)) * 0.5
        return max(self.prd_min, min(self.prd_max, prd))
    
    def check_hedge_needed(self, core_combos: List[Dict]) -> bool:
        """检查是否需要黑天鹅对冲"""
        if not core_combos:
            return True
        min_prob = min(c['prob'] for c in core_combos)
        return min_prob < self.hedge_trigger
    
    def select_hedge_option(self, options: Dict, match_id: str) -> Optional[Dict]:
        """选择黑天鹅对冲选项"""
        candidates = []
        for name, opt in options.items():
            if opt['type'] == '胜平负' and opt['odds'] >= self.hedge_odds_min and opt['a_score'] >= 0.25:
                candidates.append({'name': name, **opt})
        
        if not candidates:
            spf_opts = [(n, o) for n, o in options.items() if o['type'] == '胜平负']
            if spf_opts:
                spf_opts.sort(key=lambda x: x[1]['odds'], reverse=True)
                name, opt = spf_opts[0]
                return {'name': name, **opt}
            return None
        
        candidates.sort(key=lambda x: x['odds'], reverse=True)
        return candidates[0]