import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from optimizer import PortfolioOptimizer


@pytest.fixture
def config():
    return {
        'constraints': {
            'max_total_cost': 30,
            'max_combinations': 3,
            'max_multiplier': 3,
            'core_budget_ratio': 0.70,
            'hedge_budget_ratio': 0.20,
        }
    }


@pytest.fixture
def optimizer(config):
    return PortfolioOptimizer(config)


@pytest.fixture
def match_options_a():
    return [
        {'value': '2', 'p_clean': 0.30, 'odds': 3.50, 'a_score': 0.65, 'type': '总进球数'},
        {'value': '3', 'p_clean': 0.25, 'odds': 4.00, 'a_score': 0.60, 'type': '总进球数'},
    ]


@pytest.fixture
def match_options_b():
    return [
        {'value': '1', 'p_clean': 0.20, 'odds': 6.00, 'a_score': 0.55, 'type': '总进球数'},
        {'value': '2', 'p_clean': 0.30, 'odds': 3.50, 'a_score': 0.62, 'type': '总进球数'},
    ]


class TestPortfolioOptimizer:
    def test_init(self, optimizer):
        assert optimizer.max_cost == 30
        assert optimizer.max_combos == 3
        assert optimizer.max_mult == 3
    
    def test_generate_combinations_returns_core(self, optimizer, match_options_a, match_options_b):
        result = optimizer.generate_combinations(match_options_a, match_options_b)
        assert 'core_combinations' in result
        assert len(result['core_combinations']) > 0
    
    def test_total_cost_within_limit(self, optimizer, match_options_a, match_options_b):
        result = optimizer.generate_combinations(match_options_a, match_options_b)
        assert result['total_cost'] <= 30
    
    def test_empty_options_returns_warning(self, optimizer):
        result = optimizer.generate_combinations([], [])
        assert 'warning' in result
        assert result['core_combinations'] == []
    
    def test_stress_test_has_scenarios(self, optimizer, match_options_a, match_options_b):
        result = optimizer.generate_combinations(match_options_a, match_options_b)
        stress = result['stress_test']
        assert len(stress) >= 2
        scenarios = [s['情景'] for s in stress]
        assert '最优' in scenarios
        assert '极端（全黑）' in scenarios
    
    def test_hedge_added_when_needed(self, optimizer, match_options_a, match_options_b):
        hedge = {'value': '负', 'odds': 5.50, 'a_score': 0.30, 'type': '胜平负'}
        result = optimizer.generate_combinations(match_options_a, match_options_b, hedge)
        assert result['hedge'] is not None
        assert result['hedge']['type'] == 'hedge'
    
    def test_empty_result(self, optimizer):
        result = optimizer._empty_result("测试")
        assert result['core_combinations'] == []
        assert result['warning'] == "测试"
        assert result['is_protected'] is False
    
    def test_multiplier_within_limit(self, optimizer, match_options_a, match_options_b):
        result = optimizer.generate_combinations(match_options_a, match_options_b)
        for c in result['core_combinations']:
            assert c['multiplier'] <= 3
            assert c['cost'] == c['multiplier'] * 2
