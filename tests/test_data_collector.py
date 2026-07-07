import pytest
import json
import os
import tempfile
from unittest.mock import patch, mock_open

from src.data_collector import DataCollector, FALLBACK_MANUAL_TEMPLATE


@pytest.fixture
def sample_config():
    """测试配置"""
    return {
        'league_strength': {1: 1.0, 2: 0.85, 'cup': 0.9},
        'weights': {'p_clean': 0.3, 'm_factor': 0.15},
    }


@pytest.fixture
def sample_raw_match():
    """原始比赛数据样本"""
    return {
        'id': 'match_001',
        'league': '英超',
        'home': '曼联',
        'away': '利物浦',
        'time': '2026-07-10 20:00',
        'weather': '晴朗',
        'odds': {
            'spf': {'胜': 2.10, '平': 3.20, '负': 3.10},
            'zjq': {'0': 8.0, '1': 4.5, '2': 3.2, '3': 3.5, '4': 5.0, '5': 8.0, '6+': 12.0},
            'bqc': {'胜胜': 3.5, '平胜': 4.0, '负胜': 6.0, '胜平': 5.0, '平平': 5.5, '负平': 7.0, '胜负': 8.0, '平负': 6.5, '负负': 4.0},
        },
        'recent': {
            'home_recent': '4胜1平1负',
            'home_goals': 1.8,
            'home_conceded': 1.1,
            'home_win_rate': 0.65,
            'home_injury': '无',
            'home_xg': 1.7,
            'home_xga': 1.0,
            'home_style': '高位压迫',
            'away_recent': '3胜2平1负',
            'away_goals': 1.5,
            'away_conceded': 1.2,
            'away_win_rate': 0.45,
            'away_injury': '轻伤',
            'away_xg': 1.4,
            'away_xga': 1.1,
            'away_style': '防守反击',
        },
        'h2h': '主队3胜2平1负',
        'notes': '德比大战',
    }


@pytest.fixture
def collector(sample_config):
    """DataCollector 实例"""
    return DataCollector(sample_config)


class TestDataCollectorInit:
    """测试初始化"""
    
    def test_init(self, collector, sample_config):
        assert collector.config == sample_config
        assert collector.raw_data is None
        assert collector.standardized_matches == []
    
    def test_known_leagues(self, collector):
        assert collector.KNOWN_LEAGUES['英超'] == 1
        assert collector.KNOWN_LEAGUES['英冠'] == 2
        assert collector.KNOWN_LEAGUES['欧冠'] == 'cup'
        assert collector.KNOWN_LEAGUES['世界杯'] == 1


class TestLoadFromWebbridge:
    """测试从 WebBridge 加载数据"""
    
    def test_load_from_webbridge(self, collector, sample_raw_match):
        webbridge_data = {'matches': [sample_raw_match]}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(webbridge_data, f)
            temp_path = f.name
        
        try:
            result = collector.load_from_webbridge(temp_path)
            assert len(result) == 1
            assert result[0]['id'] == 'match_001'
            assert result[0]['赛事信息']['联赛'] == '英超'
            assert result[0]['对阵球队']['主队']['队名'] == '曼联'
            assert result[0]['对阵球队']['客队']['队名'] == '利物浦'
        finally:
            os.unlink(temp_path)
    
    def test_load_from_webbridge_empty(self, collector):
        webbridge_data = {'matches': []}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(webbridge_data, f)
            temp_path = f.name
        
        try:
            result = collector.load_from_webbridge(temp_path)
            assert result == []
        finally:
            os.unlink(temp_path)
    
    def test_load_from_webbridge_no_matches_key(self, collector):
        webbridge_data = {}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(webbridge_data, f)
            temp_path = f.name
        
        try:
            result = collector.load_from_webbridge(temp_path)
            assert result == []
        finally:
            os.unlink(temp_path)


class TestLoadManual:
    """测试手动加载数据"""
    
    def test_load_manual(self, collector, sample_raw_match):
        result = collector.load_manual([sample_raw_match])
        assert len(result) == 1
        assert result[0]['id'] == 'match_001'
    
    def test_load_manual_multiple(self, collector, sample_raw_match):
        match2 = sample_raw_match.copy()
        match2['id'] = 'match_002'
        match2['home'] = '切尔西'
        match2['away'] = '阿森纳'
        
        result = collector.load_manual([sample_raw_match, match2])
        assert len(result) == 2
        assert result[0]['id'] == 'match_001'
        assert result[1]['id'] == 'match_002'


class TestStandardizeSingle:
    """测试单场比赛标准化"""
    
    def test_standardize_single_basic(self, collector, sample_raw_match):
        result = collector._standardize_single(sample_raw_match)
        
        assert result is not None
        assert result['id'] == 'match_001'
        assert result['赛事信息']['联赛'] == '英超'
        assert result['赛事信息']['联赛级别'] == 1
        assert result['赛事信息']['战意标签'] == '德比/关键战'
        assert result['对阵球队']['主队']['队名'] == '曼联'
        assert result['对阵球队']['客队']['队名'] == '利物浦'
        assert result['赔率数据']['胜平负']['胜'] == 2.10
        assert result['赔率数据']['总进球数']['2'] == 3.2
    
    def test_standardize_single_minimal_data(self, collector):
        """测试最小数据（只有必填字段）"""
        minimal = {
            'home': '球队A',
            'away': '球队B',
            'league': '未知联赛',
        }
        result = collector._standardize_single(minimal)
        
        assert result is not None
        assert result['对阵球队']['主队']['队名'] == '球队A'
        assert result['对阵球队']['客队']['队名'] == '球队B'
        assert result['赛事信息']['联赛级别'] == 2  # 默认次级
        assert result['赔率数据']['胜平负'] == {}
    
    def test_standardize_single_missing_teams(self, collector):
        """测试缺少球队名称时返回 None"""
        no_home = {'away': '球队B', 'league': '英超'}
        assert collector._standardize_single(no_home) is None
        
        no_away = {'home': '球队A', 'league': '英超'}
        assert collector._standardize_single(no_away) is None
    
    def test_standardize_single_chinese_keys(self, collector):
        """测试中文键名"""
        chinese_data = {
            '赛事': '西甲',
            '主队': '皇马',
            '客队': '巴萨',
            '赔率': {
                '胜平负': {'胜': 2.0, '平': 3.0, '负': 3.5},
            },
        }
        result = collector._standardize_single(chinese_data)
        
        assert result is not None
        assert result['赛事信息']['联赛'] == '西甲'
        assert result['对阵球队']['主队']['队名'] == '皇马'
        assert result['对阵球队']['客队']['队名'] == '巴萨'
    
    def test_standardize_single_cup_competition(self, collector):
        """测试杯赛识别"""
        cup_match = {
            'home': '球队A',
            'away': '球队B',
            'league': '欧冠',
        }
        result = collector._standardize_single(cup_match)
        assert result['赛事信息']['联赛级别'] == 'cup'
        assert result['赛事信息']['战意标签'] == '杯赛'
    
    def test_standardize_single_world_cup(self, collector):
        """测试世界杯识别"""
        wc_match = {
            'home': '巴西',
            'away': '阿根廷',
            'league': '世界杯小组赛',
        }
        result = collector._standardize_single(wc_match)
        assert result['赛事信息']['联赛级别'] == 1


class TestDetectLeagueTier:
    """测试联赛级别检测"""
    
    def test_top_tier(self, collector):
        assert collector._detect_league_tier('英超') == 1
        assert collector._detect_league_tier('中超联赛') == 1
        assert collector._detect_league_tier('世界杯') == 1
    
    def test_second_tier(self, collector):
        assert collector._detect_league_tier('英冠') == 2
        assert collector._detect_league_tier('德乙') == 2
    
    def test_cup(self, collector):
        assert collector._detect_league_tier('欧冠') == 'cup'
        assert collector._detect_league_tier('足总杯') == 'cup'
    
    def test_infer_from_name(self, collector):
        assert collector._detect_league_tier('甲级联赛') == 1
        assert collector._detect_league_tier('乙级联赛') == 2
    
    def test_default(self, collector):
        assert collector._detect_league_tier('某某联赛') == 2


class TestDetectRivalry:
    """测试战意标签检测"""
    
    def test_derby(self, collector):
        raw = {'notes': '伦敦德比'}
        assert collector._detect_rivalry('英超', raw) == '德比/关键战'
    
    def test_relegation(self, collector):
        raw = {'notes': '保级大战'}
        assert collector._detect_rivalry('英超', raw) == '德比/关键战'
    
    def test_title_race(self, collector):
        raw = {'notes': '争冠关键战'}
        assert collector._detect_rivalry('英超', raw) == '德比/关键战'
    
    def test_cup(self, collector):
        raw = {'notes': '普通比赛'}
        assert collector._detect_rivalry('足总杯', raw) == '杯赛'
    
    def test_normal(self, collector):
        raw = {'notes': '普通比赛'}
        assert collector._detect_rivalry('英超', raw) == '普通'
    
    def test_chinese_notes(self, collector):
        raw = {'备注': '淘汰赛'}
        assert collector._detect_rivalry('英超', raw) == '德比/关键战'


class TestParseOddsDict:
    """测试赔率字典解析"""
    
    def test_parse_valid_odds(self, collector):
        odds = {'胜': '2.10', '平': '3.20', '负': '3.10'}
        result = collector._parse_odds_dict(odds)
        assert result['胜'] == 2.10
        assert result['平'] == 3.20
        assert result['负'] == 3.10
    
    def test_parse_numeric_odds(self, collector):
        odds = {'0': 8.0, '1': 4.5}
        result = collector._parse_odds_dict(odds)
        assert result['0'] == 8.0
        assert result['1'] == 4.5
    
    def test_parse_invalid_values(self, collector):
        odds = {'胜': '2.10', '平': 'invalid', '负': None}
        result = collector._parse_odds_dict(odds)
        assert result['胜'] == 2.10
        assert '平' not in result
        assert '负' not in result
    
    def test_parse_empty(self, collector):
        assert collector._parse_odds_dict({}) == {}
        assert collector._parse_odds_dict(None) == {}


class TestGetMatchPairs:
    """测试比赛配对"""
    
    def test_single_match(self, collector, sample_raw_match):
        collector.load_manual([sample_raw_match])
        pairs = collector.get_match_pairs()
        assert pairs == []
    
    def test_two_matches(self, collector, sample_raw_match):
        match2 = sample_raw_match.copy()
        match2['id'] = 'match_002'
        match2['home'] = '切尔西'
        match2['away'] = '阿森纳'
        
        collector.load_manual([sample_raw_match, match2])
        pairs = collector.get_match_pairs()
        assert len(pairs) == 1
        assert pairs[0][0]['id'] == 'match_001'
        assert pairs[0][1]['id'] == 'match_002'
    
    def test_three_matches(self, collector, sample_raw_match):
        matches = [sample_raw_match.copy() for _ in range(3)]
        for i, m in enumerate(matches):
            m['id'] = f'match_{i}'
            m['home'] = f'球队{i}'
        
        collector.load_manual(matches)
        pairs = collector.get_match_pairs()
        assert len(pairs) == 3  # C(3,2) = 3


class TestValidateData:
    """测试数据验证"""
    
    def test_complete_data(self, collector, sample_raw_match):
        match = collector._standardize_single(sample_raw_match)
        issues = collector.validate_data(match)
        assert issues == []
    
    def test_missing_zjq(self, collector):
        match = {
            '赔率数据': {
                '胜平负': {'胜': 2.0},
                '半全场': {'胜胜': 3.0},
            }
        }
        issues = collector.validate_data(match)
        assert '缺少总进球数赔率' in issues
    
    def test_missing_spf(self, collector):
        match = {
            '赔率数据': {
                '总进球数': {'0': 8.0},
            }
        }
        issues = collector.validate_data(match)
        assert '缺少胜平负赔率' in issues
    
    def test_missing_bqc(self, collector):
        match = {
            '赔率数据': {
                '胜平负': {'胜': 2.0},
                '总进球数': {'0': 8.0},
            }
        }
        issues = collector.validate_data(match)
        assert '缺少半全场赔率（可降级）' in issues
    
    def test_empty_odds(self, collector):
        match = {'赔率数据': {}}
        issues = collector.validate_data(match)
        assert '缺少总进球数赔率' in issues
        assert '缺少半全场赔率（可降级）' in issues
        assert '缺少胜平负赔率' in issues


class TestStandardizeBatch:
    """测试批量标准化"""
    
    def test_batch_with_invalid(self, collector, sample_raw_match):
        invalid_match = {'home': '', 'away': '球队B'}  # 缺少主队
        matches = [sample_raw_match, invalid_match]
        
        result = collector._standardize_batch(matches)
        assert len(result) == 1
        assert result[0]['id'] == 'match_001'
    
    def test_batch_all_invalid(self, collector):
        matches = [
            {'home': '', 'away': 'B'},
            {'home': 'A', 'away': ''},
        ]
        result = collector._standardize_batch(matches)
        assert result == []
    
    def test_batch_exception_handling(self, collector):
        """测试异常处理"""
        # 创建一个会导致异常的数据
        bad_match = {'home': 'A', 'away': 'B', 'odds': object()}  # odds 不可迭代
        matches = [bad_match]
        
        result = collector._standardize_batch(matches)
        assert result == []  # 应该跳过异常项，不崩溃


class TestFallbackTemplate:
    """测试降级模板"""
    
    def test_template_exists(self):
        assert FALLBACK_MANUAL_TEMPLATE is not None
        assert '请手动输入比赛数据' in FALLBACK_MANUAL_TEMPLATE
        assert '胜平负' in FALLBACK_MANUAL_TEMPLATE
        assert '总进球数' in FALLBACK_MANUAL_TEMPLATE
        assert '半全场' in FALLBACK_MANUAL_TEMPLATE
