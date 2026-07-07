import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from calibration import CalibrationEngine


@pytest.fixture
def config():
    return {
        'calibration': {
            'rsi_hot_threshold': 0.75,
            'rsi_discount': 0.95,
            'prd_max': 1.08,
            'prd_min': 1.00,
            'hedge_odds_min': 5.0,
        },
        'thresholds': {
            'hedge_trigger': 0.35,
        }
    }


@pytest.fixture
def calib(config):
    return CalibrationEngine(config)


class TestCalibrationEngine:
    def test_init(self, calib):
        assert calib.rsi_hot == 0.75
        assert calib.rsi_discount == 0.95
        assert calib.hedge_trigger == 0.35
    
    def test_calibrate_options_no_change(self, calib):
        options = {
            'opt1': {'a_score': 0.60, 'p_clean': 0.20, 'odds': 3.0}
        }
        result = calib.calibrate_options(options, market_heat=0.5, q_change=0.0, odds_change=0.0)
        assert result['opt1']['a_score'] == 0.60
        assert result['opt1']['calibrated'] is True
    
    def test_rsi_calibration_reduces_score(self, calib):
        options = {
            'opt1': {'a_score': 0.80, 'p_clean': 0.30, 'odds': 2.0}
        }
        result = calib.calibrate_options(options, market_heat=0.80, q_change=0.0, odds_change=0.0)
        assert result['opt1']['a_score'] == pytest.approx(0.76, 0.01)  # 0.80 * 0.95
    
    def test_prd_compensation_increases_score(self, calib):
        options = {
            'opt1': {'a_score': 0.60, 'p_clean': 0.25, 'odds': 3.0}
        }
        result = calib.calibrate_options(options, market_heat=0.5, q_change=0.10, odds_change=0.02)
        assert result['opt1']['a_score'] > 0.60
    
    def test_calc_prd_no_change(self, calib):
        assert calib._calc_prd(q_change=0.0, odds_change=0.0) == 1.0
    
    def test_calc_prd_with_q_change(self, calib):
        prd = calib._calc_prd(q_change=0.10, odds_change=0.02)
        assert prd > 1.0
        assert prd <= 1.08
    
    def test_check_hedge_needed_empty(self, calib):
        assert calib.check_hedge_needed([]) is True
    
    def test_check_hedge_needed_low_prob(self, calib):
        combos = [{'prob': 0.20}, {'prob': 0.40}]
        assert calib.check_hedge_needed(combos) is True
    
    def test_check_hedge_needed_high_prob(self, calib):
        combos = [{'prob': 0.50}, {'prob': 0.60}]
        assert calib.check_hedge_needed(combos) is False
    
    def test_select_hedge_option_no_candidates(self, calib):
        options = {
            'opt1': {'type': '总进球数', 'odds': 3.0, 'a_score': 0.30}
        }
        result = calib.select_hedge_option(options, 'm1')
        assert result is None
    
    def test_select_hedge_option_fallback(self, calib):
        options = {
            'spf1': {'type': '胜平负', 'odds': 3.0, 'a_score': 0.30, 'value': '胜'}
        }
        result = calib.select_hedge_option(options, 'm1')
        assert result is not None
        assert result['type'] == '胜平负'
