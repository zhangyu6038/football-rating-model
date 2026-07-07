import json
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime


class DataCollector:
    """数据采集与标准化器"""
    
    # 已知联赛列表（用于自动识别联赛级别）—— 已加入世界杯
    KNOWN_LEAGUES = {
        # 顶级联赛
        '英超': 1, '西甲': 1, '德甲': 1, '意甲': 1, '法甲': 1,
        '中超': 1, '日职': 1, 'K联赛': 1, '荷甲': 1, '葡超': 1,
        '世界杯': 1,              # 世界杯，级别=顶级
        # 次级联赛
        '英冠': 2, '德乙': 2, '意乙': 2, '西乙': 2, '法乙': 2,
        '日乙': 2, '中甲': 2,
        # 杯赛
        '欧冠': 'cup', '欧罗巴': 'cup', '欧协联': 'cup',
        '足总杯': 'cup', '德国杯': 'cup', '意大利杯': 'cup',
        '国王杯': 'cup', '亚冠': 'cup',
    }
    
    def __init__(self, config: dict):
        self.config = config
        self.raw_data = None
        self.standardized_matches = []
    
    def load_from_webbridge(self, filepath: str) -> List[Dict]:
        """从 WebBridge 抓取结果或样本文件中加载数据"""
        with open(filepath, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        self.raw_data = raw
        # 兼容两种格式：含 matches 键的字典，或直接列表
        matches = raw.get('matches', []) if isinstance(raw, dict) else raw
        self.standardized_matches = self._standardize_batch(matches)
        return self.standardized_matches
    
    def load_manual(self, match_data_list: List[Dict]) -> List[Dict]:
        """加载手动输入的数据"""
        self.standardized_matches = self._standardize_batch(match_data_list)
        return self.standardized_matches
    
    def _standardize_batch(self, matches_raw: List[Dict]) -> List[Dict]:
        """批量标准化比赛数据"""
        standardized = []
        for raw in matches_raw:
            try:
                match = self._standardize_single(raw)
                if match:
                    standardized.append(match)
            except Exception as e:
                print(f"[WARNING] 标准化失败，跳过: {raw.get('id','unknown')} - {e}")
        return standardized
    
    def _standardize_single(self, raw: Dict) -> Optional[Dict]:
        """标准化单场比赛数据"""
        # 解析联赛信息
        league_name = raw.get('league', raw.get('赛事', ''))
        league_tier = self._detect_league_tier(league_name)
        
        # 解析球队
        home_team = raw.get('home', raw.get('主队', ''))
        away_team = raw.get('away', raw.get('客队', ''))
        
        if not home_team or not away_team:
            return None
        
        # 解析赔率
        odds = raw.get('odds', raw.get('赔率', {}))
        spf = odds.get('spf', odds.get('胜平负', {}))
        zjq = odds.get('zjq', odds.get('总进球数', {}))
        bqc = odds.get('bqc', odds.get('半全场', {}))
        
        # 解析基本面（可选字段，缺失则设默认值）
        recent = raw.get('recent', raw.get('近期数据', {}))
        h2h = raw.get('h2h', raw.get('历史交锋', ''))
        
        # 构建标准结构
        match = {
            'id': raw.get('id', f"{home_team}_{away_team}"),
            '赛事信息': {
                '联赛': league_name,
                '联赛级别': league_tier,
                '比赛时间': raw.get('time', raw.get('比赛时间', '未知')),
                '天气': raw.get('weather', raw.get('天气', '正常')),
                '战意标签': self._detect_rivalry(league_name, raw),
            },
            '对阵球队': {
                '主队': {
                    '队名': home_team,
                    '近期6场': recent.get('home_recent', recent.get('主队近期', '未知')),
                    '场均进球': recent.get('home_goals', recent.get('主队场均进球', 1.5)),
                    '场均失球': recent.get('home_conceded', recent.get('主队场均失球', 1.3)),
                    '主场胜率': recent.get('home_win_rate', 0.40),
                    '伤病影响': recent.get('home_injury', '无'),
                    'xG': recent.get('home_xg', recent.get('主队xG', None)),
                    'xGA': recent.get('home_xga', recent.get('主队xGA', None)),
                    '教练风格': recent.get('home_style', '未知'),
                },
                '客队': {
                    '队名': away_team,
                    '近期6场': recent.get('away_recent', recent.get('客队近期', '未知')),
                    '场均进球': recent.get('away_goals', recent.get('客队场均进球', 1.3)),
                    '场均失球': recent.get('away_conceded', recent.get('客队场均失球', 1.2)),
                    '客场胜率': recent.get('away_win_rate', 0.30),
                    '伤病影响': recent.get('away_injury', '无'),
                    'xG': recent.get('away_xg', recent.get('客队xG', None)),
                    'xGA': recent.get('away_xga', recent.get('客队xGA', None)),
                    '教练风格': recent.get('away_style', '未知'),
                }
            },
            '历史交锋': h2h,
            '赔率数据': {
                '胜平负': self._parse_odds_dict(spf),
                '总进球数': self._parse_odds_dict(zjq),
                '半全场': self._parse_odds_dict(bqc),
            }
        }
        return match
    
    def _detect_league_tier(self, league_name: str) -> int:
        """自动检测联赛级别"""
        for name, tier in self.KNOWN_LEAGUES.items():
            if name in league_name:
                return tier
        # 默认按联赛名称中的数字推断
        if '甲' in league_name or '超' in league_name:
            return 1
        elif '乙' in league_name:
            return 2
        return 2  # 默认次级
    
    def _detect_rivalry(self, league_name: str, raw: Dict) -> str:
        """检测战意标签"""
        notes = raw.get('notes', raw.get('备注', ''))
        if any(kw in notes for kw in ['德比', '保级', '争冠', '淘汰赛', '决赛']):
            return '德比/关键战'
        if '杯' in league_name:
            return '杯赛'
        return '普通'
    
    def _parse_odds_dict(self, odds_data) -> Dict:
        """解析赔率字典，确保值为浮点数"""
        if not odds_data:
            return {}
        result = {}
        for k, v in odds_data.items():
            try:
                result[str(k)] = float(v)
            except (ValueError, TypeError):
                pass
        return result
    
    def get_match_pairs(self) -> List[Tuple[Dict, Dict]]:
        """获取可组合的比赛对（两两配对）"""
        matches = self.standardized_matches
        pairs = []
        for i in range(len(matches)):
            for j in range(i+1, len(matches)):
                pairs.append((matches[i], matches[j]))
        return pairs
    
    def validate_data(self, match: Dict) -> List[str]:
        """验证数据完整性，返回缺失字段列表"""
        issues = []
        odds = match.get('赔率数据', {})
        if not odds.get('总进球数'):
            issues.append('缺少总进球数赔率')
        if not odds.get('半全场'):
            issues.append('缺少半全场赔率（可降级）')
        if not odds.get('胜平负'):
            issues.append('缺少胜平负赔率')
        return issues


# 降级策略：当 WebBridge 抓取失败时的回退方案
FALLBACK_MANUAL_TEMPLATE = """
请手动输入比赛数据，格式如下（可输入多场）：

比赛1：{主队名} vs {客队名}（{联赛名}）
胜平负：{胜赔} / {平赔} / {负赔}
总进球数：0球{赔率}，1球{赔率}，2球{赔率}，3球{赔率}，4球{赔率}，5球{赔率}，6+球{赔率}
半全场：胜胜{赔率}，平胜{赔率}，负胜{赔率}，胜平{赔率}，平平{赔率}，负平{赔率}，胜负{赔率}，平负{赔率}，负负{赔率}
主队近期：近6场{W}胜{D}平{L}负，场均进球{X}，场均失球{Y}
客队近期：近6场{W}胜{D}平{L}负，场均进球{X}，场均失球{Y}

比赛2：（同上格式）
"""