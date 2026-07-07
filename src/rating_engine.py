import math
import yaml
import re
from typing import Dict, List, Tuple, Optional


class RatingEngine:
    """四层评级引擎"""
    
    def __init__(self, config_path: str = 'config.yaml'):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        self.weights = self._load_weights()
        self.league_map = self.config.get('league_strength', {})
        self.thresholds = self.config.get('thresholds', {})
        
        # 存储中间计算结果
        self.factors = {}
    
    def _load_weights(self) -> Dict[str, float]:
        """加载权重配置"""
        w = self.config.get('weights', {})
        return {
            'p_clean': w.get('p_clean', 0.30),
            'm_factor': w.get('m_factor', 0.15),
            'h_factor': w.get('h_factor', 0.15),
            'q_score': w.get('q_score', 0.20),
            'stability': w.get('stability', 0.10),
            'upset_signal': w.get('upset_signal', 0.10),
        }
    
    def analyze_match(self, match: Dict) -> Dict:
        """分析单场比赛，返回所有评级因子和选项 A_Score"""
        result = {
            'match_id': match['id'],
            'home': match['对阵球队']['主队']['队名'],
            'away': match['对阵球队']['客队']['队名'],
            'factors': {},
            'options': {},
        }
        
        # 第一层：赛事宏观
        m_factor = self._calc_m_factor(match)
        result['factors']['M_factor'] = m_factor
        
        # 第二层：对阵基本面
        h_factor = self._calc_h_factor(match)
        result['factors']['H_factor'] = h_factor
        
        # 第三层：球队品质
        q_score = self._calc_q_score(match)
        result['factors']['Q_score'] = q_score
        
        # 第四层：赔率微观
        odds_analysis = self._analyze_odds(match)
        result['factors'].update(odds_analysis['factors'])
        
        # 计算各选项 A_Score
        result['options'] = self._calc_all_a_scores(
            match, m_factor, h_factor, q_score, odds_analysis
        )
        
        self.factors[match['id']] = result['factors']
        return result
    
    def _calc_m_factor(self, match: Dict) -> float:
        """第一层：赛事宏观层"""
        info = match['赛事信息']
        league_tier = info['联赛级别']
        time_str = info.get('比赛时间', '')
        
        # 联赛强度
        league_str = self.league_map.get(league_tier, 0.85)
        # 世界杯特殊处理：确保取值为1.0
        if league_tier == 1 or '世界杯' in info.get('联赛', ''):
            league_str = self.league_map.get(1, 1.0)
        
        # 时间窗口：判断是否周末
        is_weekend = self._is_weekend(time_str)
        time_factor = 1.00 if is_weekend else 0.95
        
        # 战意加成
        rivalry = info.get('战意标签', '普通')
        rivalry_factor = 1.08 if rivalry in ['德比/关键战', '杯赛'] else 1.00
        
        # 天气影响
        weather = info.get('天气', '正常')
        weather_factor = 0.95 if weather in ['暴雨', '大雪', '极端高温'] else 1.00
        
        m = (0.40 * league_str + 0.20 * time_factor + 
             0.25 * rivalry_factor + 0.15 * weather_factor)
        return round(m, 4)
    
    def _calc_h_factor(self, match: Dict) -> float:
        """第二层：对阵基本面层"""
        h2h = match.get('历史交锋', '')
        home = match['对阵球队']['主队']
        away = match['对阵球队']['客队']
        
        # 历史克制
        if '主队优' in h2h or self._count_h2h_wins(h2h, '主') > self._count_h2h_wins(h2h, '客'):
            hist = 0.05
        elif '客队优' in h2h or self._count_h2h_wins(h2h, '客') > self._count_h2h_wins(h2h, '主'):
            hist = -0.05
        else:
            hist = 0.00
        
        # 主场优势（世界杯等中立场地需特殊处理，此处按正常主场计算）
        home_win_rate = home.get('主场胜率', 0.40)
        home_adv = (home_win_rate - 0.35) * 0.5
        
        # 近期动量差
        home_pts = self._parse_recent_points(home.get('近期6场', ''))
        away_pts = self._parse_recent_points(away.get('近期6场', ''))
        momentum = (home_pts - away_pts) * 0.3
        
        h = 1.00 + hist + home_adv + momentum
        return round(h, 4)
    
    def _calc_q_score(self, match: Dict) -> float:
        """第三层：球队品质层"""
        home = match['对阵球队']['主队']
        away = match['对阵球队']['客队']
        
        # 进攻效率（使用 xG 或场均进球，None 时回退默认值）
        home_goals = home.get('xG') or home.get('场均进球', 1.5)
        away_goals = away.get('xG') or away.get('场均进球', 1.3)
        avg_goals = (float(home_goals) + float(away_goals)) / 2
        attack = min(avg_goals / 3.0, 1.0) * 0.25
        
        # 防守稳固度
        home_conceded = home.get('xGA') or home.get('场均失球', 1.3)
        away_conceded = away.get('xGA') or away.get('场均失球', 1.2)
        avg_conceded = (float(home_conceded) + float(away_conceded)) / 2
        defense = (1.0 - min(avg_conceded / 3.0, 1.0)) * 0.25
        
        # 阵容完整度
        home_injury = home.get('伤病影响', '无')
        away_injury = away.get('伤病影响', '无')
        injury_score = self._calc_injury_score(home_injury, away_injury)
        squad = injury_score * 0.30
        
        # 风格匹配度
        home_style = home.get('教练风格', '未知')
        away_style = away.get('教练风格', '未知')
        style_match = self._calc_style_match(home_style, away_style)
        style = style_match * 0.20
        
        q = attack + defense + squad + style
        return round(max(0.60, min(0.95, q)), 4)
    
    def _analyze_odds(self, match: Dict) -> Dict:
        """第四层：赔率微观分析"""
        odds_data = match['赔率数据']
        result = {'factors': {}, 'clean_probs': {}, 'stability': {}, 'upset': {}}
        
        # 对每种赔率类型计算去偏概率
        for odds_type in ['胜平负', '总进球数', '半全场']:
            odds_dict = odds_data.get(odds_type, {})
            if odds_dict:
                clean = self._clean_probability(odds_dict)
                result['clean_probs'][odds_type] = clean
        
        # 赔率稳定性（默认值，实际需对比初盘）
        result['factors']['stability'] = 0.90
        
        # 冷门信号检测
        result['factors']['upset_signal'] = self._detect_upset(odds_data)
        
        return result
    
    def _calc_all_a_scores(self, match: Dict, m: float, h: float, q: float, odds_analysis: Dict) -> Dict:
        """计算所有投注选项的 A_Score"""
        options = {}
        
        # 总进球数选项
        zjq_clean = odds_analysis['clean_probs'].get('总进球数', {})
        zjq_odds = match['赔率数据'].get('总进球数', {})
        for goal_range, odds in zjq_odds.items():
            p_clean = zjq_clean.get(goal_range, 1.0/odds if odds > 0 else 0.01)
            a = self._calc_a_score(p_clean, m, h, q, 
                                   odds_analysis['factors']['stability'],
                                   odds_analysis['factors']['upset_signal'])
            options[f'总进球{goal_range}'] = {
                'type': '总进球数',
                'value': goal_range,
                'odds': odds,
                'p_clean': round(p_clean, 4),
                'a_score': round(a, 4),
            }
        
        # 半全场选项
        bqc_clean = odds_analysis['clean_probs'].get('半全场', {})
        bqc_odds = match['赔率数据'].get('半全场', {})
        for result_type, odds in bqc_odds.items():
            p_clean = bqc_clean.get(result_type, 1.0/odds if odds > 0 else 0.01)
            a = self._calc_a_score(p_clean, m, h, q,
                                   odds_analysis['factors']['stability'],
                                   odds_analysis['factors']['upset_signal'])
            options[f'半全场{result_type}'] = {
                'type': '半全场',
                'value': result_type,
                'odds': odds,
                'p_clean': round(p_clean, 4),
                'a_score': round(a, 4),
            }
        
        # 胜平负选项
        spf_clean = odds_analysis['clean_probs'].get('胜平负', {})
        spf_odds = match['赔率数据'].get('胜平负', {})
        for result_type, odds in spf_odds.items():
            p_clean = spf_clean.get(result_type, 1.0/odds if odds > 0 else 0.01)
            a = self._calc_a_score(p_clean, m, h, q,
                                   odds_analysis['factors']['stability'],
                                   odds_analysis['factors']['upset_signal'])
            options[f'胜平负{result_type}'] = {
                'type': '胜平负',
                'value': result_type,
                'odds': odds,
                'p_clean': round(p_clean, 4),
                'a_score': round(a, 4),
            }
        
        return options
    
    def _calc_a_score(self, p_clean: float, m: float, h: float, q: float,
                      stability: float, upset: float) -> float:
        """计算单个选项的 A_Score"""
        # 将 M 和 H 缩放到 0-1
        m_scaled = (m - 0.80) / 0.40
        h_scaled = (h - 0.80) / 0.40
        m_scaled = max(0.0, min(1.0, m_scaled))
        h_scaled = max(0.0, min(1.0, h_scaled))
        
        a = (self.weights['p_clean'] * p_clean +
             self.weights['m_factor'] * m_scaled +
             self.weights['h_factor'] * h_scaled +
             self.weights['q_score'] * q +
             self.weights['stability'] * stability -
             self.weights['upset_signal'] * upset)
        return max(0.0, min(1.0, a))
    
    def _clean_probability(self, odds_dict: Dict[str, float]) -> Dict[str, float]:
        """计算去偏概率"""
        odds_values = list(odds_dict.values())
        if not odds_values:
            return {}
        imp = [1.0 / o for o in odds_values]
        total_imp = sum(imp)
        if total_imp == 0:
            return {}
        clean_values = [p / total_imp for p in imp]
        return {k: round(v, 4) for k, v in zip(odds_dict.keys(), clean_values)}
    
    # ---- 辅助方法 ----
    
    def _is_weekend(self, time_str: str) -> bool:
        """判断是否周末"""
        for wd in ['周六', '周日', 'Saturday', 'Sunday']:
            if wd in time_str:
                return True
        return False
    
    def _count_h2h_wins(self, h2h: str, side: str) -> int:
        """从历史交锋文本中统计胜场数"""
        if side == '主':
            pattern = r'主队?(\d+)胜'
        else:
            pattern = r'客队?(\d+)胜'
        match = re.search(pattern, h2h)
        return int(match.group(1)) if match else 0
    
    def _parse_recent_points(self, recent_str: str) -> float:
        """解析近期战绩为积分率"""
        if not recent_str:
            return 0.45  # 默认中等水平
        wins = re.search(r'(\d+)胜', recent_str)
        draws = re.search(r'(\d+)平', recent_str)
        losses = re.search(r'(\d+)负', recent_str)
        w = int(wins.group(1)) if wins else 0
        d = int(draws.group(1)) if draws else 0
        l = int(losses.group(1)) if losses else 0
        total = w + d + l
        if total == 0:
            return 0.45
        return (w * 3 + d * 1) / (total * 3)
    
    def _calc_injury_score(self, home_injury: str, away_injury: str) -> float:
        """计算阵容完整度得分"""
        score_map = {
            '无': 1.0,
            '轻伤': 0.95,
            '主力缺阵': 0.90,
            '核心缺阵': 0.85,
            '多名核心缺阵': 0.75,
            '主力前锋伤缺': 0.88,
        }
        home_score = 1.0
        away_score = 1.0
        for desc, score in score_map.items():
            if desc in home_injury:
                home_score = min(home_score, score)
            if desc in away_injury:
                away_score = min(away_score, score)
        return (home_score + away_score) / 2
    
    def _calc_style_match(self, home_style: str, away_style: str) -> float:
        """计算风格匹配度"""
        style_pairs = {
            ('高位压迫', '防守反击'): 1.05,
            ('防守反击', '控球'): 1.05,
            ('控球', '高位压迫'): 1.05,
        }
        if (home_style, away_style) in style_pairs:
            return style_pairs[(home_style, away_style)]
        if (away_style, home_style) in style_pairs:
            return 0.95
        return 1.00
    
    def _detect_upset(self, odds_data: Dict) -> float:
        """检测冷门信号"""
        spf = odds_data.get('胜平负', {})
        min_odds = min(spf.values()) if spf else 999
        if min_odds < 1.50:
            return 0.15
        return 0.0
    
    def get_top_options(self, match_result: Dict, top_n: int = 5) -> List[Dict]:
        """获取某场比赛 A_Score 最高的选项"""
        options = match_result['options']
        sorted_opts = sorted(options.items(), key=lambda x: x[1]['a_score'], reverse=True)
        return [{'name': k, **v} for k, v in sorted_opts[:top_n]]