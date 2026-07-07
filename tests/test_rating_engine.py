import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from rating_engine import RatingEngine


@pytest.fixture
def engine():
    return RatingEngine(config_path='config.yaml')


@pytest.fixture
def sample_match():
    return {
        'id': 'test_1',
        '赛事信息': {
            '联赛': '英超',
            '联赛级别': 1,
            '比赛时间': '周六20:00',
            '天气': '晴',
            '战意标签': '普通',
        },
        '对阵球队': {
            '主队': {
                '队名': '曼城',
                '近期6场': '4胜1平1负',
                '场均进球': 2.5,
                '场均失球': 0.8,
                '主场胜率': 0.75,
                '伤病影响': '无',
                '教练风格': '高位压迫',
            },
            '客队': {
                '队名': '阿森纳',
                '近期6场': '3胜2平1负',
                '场均进球': 1.8,
                '场均失球': 1.0,
                '客场胜率': 0.50,
                '伤病影响': '轻伤',
                '教练风格': '防守反击',
            }
        },
        '历史交锋': '近6场主队4胜1平1负',
        '赔率数据': {
            '胜平负': {'胜': 1.85, '平': 3.40, '负': 4.20},
            '总进球数': {'0': 15.00, '1': 6.00, '2': 3.50, '3': 3.80, '4': 5.50, '5': 9.00, '6+': 20.00},
            '半全场': {'胜胜': 2.80, '平胜': 4.50, '负胜': 18.00, '胜平': 12.00, '平平': 6.00, '负平': 8.00, '胜负': 35.00, '平负': 9.00, '负负': 6.50}
        }
    }


class TestRatingEngine:
    def test_init_loads_config(self, engine):
        assert engine.weights['p_clean'] == 0.30
        assert engine.weights['q_score'] == 0.20
    
    def test_analyze_match_returns_expected_keys(self, engine, sample_match):
        result = engine.analyze_match(sample_match)
        assert 'match_id' in result
        assert 'home' in result
        assert 'away' in result
        assert 'factors' in result
        assert 'options' in result
        assert result['match_id'] == 'test_1'
    
    def test_m_factor_calculation(self, engine, sample_match):
        result = engine.analyze_match(sample_match)
        m = result['factors']['M_factor']
        assert 0.8 <= m <= 1.1
    
    def test_h_factor_calculation(self, engine, sample_match):
        result = engine.analyze_match(sample_match)
        h = result['factors']['H_factor']
        assert 0.8 <= h <= 1.2
    
    def test_q_score_calculation(self, engine, sample_match):
        result = engine.analyze_match(sample_match)
        q = result['factors']['Q_score']
        assert 0.60 <= q <= 0.95
    
    def test_options_generated_for_all_types(self, engine, sample_match):
        result = engine.analyze_match(sample_match)
        options = result['options']
        assert any('总进球' in k for k in options.keys())
        assert any('半全场' in k for k in options.keys())
        assert any('胜平负' in k for k in options.keys())
    
    def test_a_score_in_range(self, engine, sample_match):
        result = engine.analyze_match(sample_match)
        for opt in result['options'].values():
            assert 0.0 <= opt['a_score'] <= 1.0
    
    def test_clean_probability(self, engine):
        odds = {'胜': 2.0, '平': 3.0, '负': 4.0}
        clean = engine._clean_probability(odds)
        total = sum(clean.values())
        assert abs(total - 1.0) < 0.001
    
    def test_clean_probability_empty(self, engine):
        assert engine._clean_probability({}) == {}
    
    def test_is_weekend_true(self, engine):
        assert engine._is_weekend('周六20:00') is True
        assert engine._is_weekend('Sunday') is True
    
    def test_is_weekend_false(self, engine):
        assert engine._is_weekend('周三20:00') is False
    
    def test_count_h2h_wins(self, engine):
        assert engine._count_h2h_wins('近6场主队4胜1平1负', '主') == 4
        assert engine._count_h2h_wins('近6场主队4胜1平1负', '客') == 1
    
    def test_parse_recent_points(self, engine):
        pts = engine._parse_recent_points('4胜1平1负')
        assert pts == (4*3 + 1*1) / (6*3)
    
    def test_parse_recent_points_empty(self, engine):
        assert engine._parse_recent_points('') == 0.45
    
    def test_calc_injury_score(self, engine):
        assert engine._calc_injury_score('无', '无') == 1.0
        assert engine._calc_injury_score('主力缺阵', '无') == 0.95
    
    def test_calc_style_match(self, engine):
        assert engine._calc_style_match('高位压迫', '防守反击') == 1.05
        assert engine._calc_style_match('未知', '未知') == 1.00
    
    def test_detect_upset(self, engine):
        assert engine._detect_upset({'胜平负': {'胜': 1.30, '平': 4.50, '负': 8.00}}) == 0.15
        assert engine._detect_upset({'胜平负': {'胜': 2.00, '平': 3.00, '负': 4.00}}) == 0.0
    
    def test_get_top_options(self, engine, sample_match):
        result = engine.analyze_match(sample_match)
        top = engine.get_top_options(result, top_n=3)
        assert len(top) == 3
        assert top[0]['a_score'] >= top[1]['a_score']
