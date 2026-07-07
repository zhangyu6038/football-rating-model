import pytest
import json
import os
import tempfile
from src.backtest import (
    BacktestEngine,
    AutoCalibrator,
    WeightOptimizer,
    run_full_backtest,
    run_auto_calibration,
)


# ---------- Fixtures ----------

@pytest.fixture
def sample_config():
    """提供测试用配置"""
    return {
        'weights': {
            'p_clean': 0.30,
            'm_factor': 0.15,
            'h_factor': 0.15,
            'q_score': 0.20,
            'stability': 0.10,
            'upset_signal': 0.10,
        },
        'thresholds': {
            'a_score_entry': 0.55,
            'a_score_downgrade': 0.45,
            'hedge_trigger': 0.35,
        },
        'iteration': {
            'batch_size': 5,
            'smooth_factor': 0.8,
        },
    }


@pytest.fixture
def sample_prediction():
    """单场比赛预测样本"""
    return {
        'match_id': 'test_001',
        'options': {
            '总进球2': {'type': '总进球数', 'value': '2', 'odds': 3.10, 'a_score': 0.62, 'p_clean': 0.32},
            '总进球3': {'type': '总进球数', 'value': '3', 'odds': 3.70, 'a_score': 0.55, 'p_clean': 0.28},
            '半全场胜胜': {'type': '半全场', 'value': '胜胜', 'odds': 4.50, 'a_score': 0.48, 'p_clean': 0.22},
        }
    }


@pytest.fixture
def sample_actual_hit():
    """实际结果：命中总进球2"""
    return {'actual_result': '2'}


@pytest.fixture
def sample_actual_miss():
    """实际结果：未命中（实际为4球）"""
    return {'actual_result': '4'}


# ---------- BacktestEngine Tests ----------

class TestBacktestEngine:

    def test_simulate_bet_hit(self, sample_config, sample_prediction, sample_actual_hit):
        """测试命中场景"""
        engine = BacktestEngine(sample_config)
        result = engine.simulate_bet(sample_prediction, sample_actual_hit)
        
        assert result['hit'] is True
        assert result['actual_result'] == '2'
        assert result['odds'] == 3.10
        assert result['profit'] == pytest.approx(2.10, rel=1e-3)
        assert result['match_id'] == 'test_001'

    def test_simulate_bet_miss(self, sample_config, sample_prediction, sample_actual_miss):
        """测试未命中场景"""
        engine = BacktestEngine(sample_config)
        result = engine.simulate_bet(sample_prediction, sample_actual_miss)
        
        assert result['hit'] is False
        assert result['actual_result'] == '4'
        assert result['profit'] == -1.0

    def test_run_backtest_success(self, sample_config):
        """测试完整回测流程"""
        predictions = [
            {
                'match_id': 'm1',
                'options': {
                    'optA': {'value': 'A', 'odds': 2.0, 'a_score': 0.60},
                }
            },
            {
                'match_id': 'm2',
                'options': {
                    'optB': {'value': 'B', 'odds': 3.0, 'a_score': 0.55},
                }
            },
            {
                'match_id': 'm3',
                'options': {
                    'optC': {'value': 'C', 'odds': 1.5, 'a_score': 0.50},
                }
            },
        ]
        actuals = [
            {'actual_result': 'A'},
            {'actual_result': 'B'},
            {'actual_result': 'X'},  # 未命中
        ]
        
        engine = BacktestEngine(sample_config)
        metrics = engine.run_backtest(predictions, actuals)
        
        assert metrics['total_matches'] == 3
        assert metrics['hits'] == 2
        assert metrics['hit_rate'] == pytest.approx(2/3, rel=1e-3)
        assert metrics['total_profit'] == pytest.approx(1.0 + 2.0 - 1.0, rel=1e-3)  # 命中利润=odds-1, 未命中=-1
        assert metrics['avg_odds'] == pytest.approx(2.5, rel=1e-3)  # (2+3)/2
        assert metrics['roi'] == pytest.approx(2.0/3, rel=1e-3)
        assert metrics['max_consecutive_losses'] == 1
        assert 'tiered_hit_rate' in metrics

    def test_run_backtest_mismatch(self, sample_config):
        """测试预测与实际结果数量不匹配"""
        engine = BacktestEngine(sample_config)
        with pytest.raises(ValueError, match='数量不匹配'):
            engine.run_backtest([{'match_id': 'm1'}], [{'actual_result': 'A'}, {'actual_result': 'B'}])

    def test_max_consecutive_losses(self, sample_config):
        """测试最大连续亏损计算"""
        engine = BacktestEngine(sample_config)
        
        # 构造结果序列：命中, 未命中, 未命中, 未命中, 命中, 未命中
        results = [
            {'hit': True}, {'hit': False}, {'hit': False}, {'hit': False},
            {'hit': True}, {'hit': False}
        ]
        max_loss = engine._max_consecutive_losses(results)
        assert max_loss == 3

    def test_tiered_hit_rate(self, sample_config):
        """测试分层命中率"""
        engine = BacktestEngine(sample_config)
        
        results = [
            {'hit': True, 'a_score': 0.65},
            {'hit': True, 'a_score': 0.62},
            {'hit': False, 'a_score': 0.50},
            {'hit': True, 'a_score': 0.48},
            {'hit': False, 'a_score': 0.40},
            {'hit': False, 'a_score': 0.30},
        ]
        tiered = engine._tiered_hit_rate(results)
        
        assert tiered['high'] == pytest.approx(1.0, rel=1e-3)    # 2/2
        assert tiered['medium'] == pytest.approx(0.5, rel=1e-3)   # 1/2
        assert tiered['low'] == pytest.approx(0.0, rel=1e-3)     # 0/2

    def test_generate_backtest_report(self, sample_config):
        """测试报告生成"""
        engine = BacktestEngine(sample_config)
        
        predictions = [
            {'match_id': 'm1', 'options': {'optA': {'value': 'A', 'odds': 2.0, 'a_score': 0.60}}},
            {'match_id': 'm2', 'options': {'optB': {'value': 'B', 'odds': 3.0, 'a_score': 0.55}}},
        ]
        actuals = [{'actual_result': 'A'}, {'actual_result': 'B'}]
        
        engine.run_backtest(predictions, actuals)
        report = engine.generate_backtest_report()
        
        assert '# 回测与自动校准报告' in report
        assert '核心指标' in report
        assert '分层命中率' in report
        assert '校准建议' in report
        assert '2' in report  # 总场次

    def test_load_history_empty(self, sample_config):
        """测试加载空历史目录"""
        engine = BacktestEngine(sample_config)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            matches = engine.load_history(tmpdir)
            assert matches == []

    def test_load_history_with_files(self, sample_config):
        """测试加载历史 JSON 文件"""
        engine = BacktestEngine(sample_config)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {
                'matches': [
                    {'match_id': 'h1', 'actual_result': 'A'},
                    {'match_id': 'h2', 'actual_result': 'B'},
                ]
            }
            filepath = os.path.join(tmpdir, '2026-07-01.json')
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f)
            
            matches = engine.load_history(tmpdir)
            assert len(matches) == 2
            assert matches[0]['match_id'] == 'h1'

    def test_empty_metrics(self, sample_config):
        """测试空数据指标"""
        engine = BacktestEngine(sample_config)
        metrics = engine._calculate_metrics([])
        
        assert metrics['total_matches'] == 0
        assert metrics['hit_rate'] == 0.0
        assert metrics['roi'] == 0.0


# ---------- AutoCalibrator Tests ----------

class TestAutoCalibrator:

    def test_normalize_weights(self, sample_config):
        """测试权重归一化"""
        calibrator = AutoCalibrator(sample_config)
        
        weights = {'a': 0.3, 'b': 0.3, 'c': 0.4}
        normalized = calibrator._normalize_weights(weights)
        total = sum(normalized.values())
        assert total == pytest.approx(1.0, abs=0.001)

    def test_normalize_weights_no_change(self, sample_config):
        """测试已归一化权重不修改"""
        calibrator = AutoCalibrator(sample_config)
        
        weights = {'a': 0.3333, 'b': 0.3333, 'c': 0.3334}
        normalized = calibrator._normalize_weights(weights)
        assert normalized == weights

    def test_calibrate_weights_with_data(self, sample_config):
        """测试有足够数据时的权重校准"""
        calibrator = AutoCalibrator(sample_config)
        
        metrics = {
            'total_matches': 10,
            'tiered_hit_rate': {
                'high': 0.20,   # 低于0.35，应降低 p_clean
                'medium': 0.50,  # 高于 high，应提高 q_score
                'low': 0.10,
            },
            'hit_rate': 0.30,
            'roi': -0.05,
        }
        current_weights = sample_config['weights'].copy()
        new_weights = calibrator.calibrate_weights(metrics, current_weights)
        
        # 确保权重总和为 1.0
        assert sum(new_weights.values()) == pytest.approx(1.0, abs=0.01)
        # 校准历史应被记录
        assert len(calibrator.get_calibration_log()) == 1

    def test_calibrate_weights_insufficient_data(self, sample_config):
        """测试数据不足时不校准"""
        calibrator = AutoCalibrator(sample_config)
        
        metrics = {'total_matches': 2}  # 少于 batch_size=5
        current_weights = sample_config['weights'].copy()
        new_weights = calibrator.calibrate_weights(metrics, current_weights)
        
        assert new_weights == current_weights

    def test_calibrate_thresholds_low_hit_rate(self, sample_config):
        """测试命中率低时提高阈值"""
        calibrator = AutoCalibrator(sample_config)
        
        metrics = {
            'total_matches': 10,
            'hit_rate': 0.20,  # 低于 0.25
            'roi': -0.30,
        }
        current_thresholds = {'a_score_entry': 0.55, 'a_score_downgrade': 0.45}
        new_thresholds = calibrator.calibrate_thresholds(metrics, current_thresholds)
        
        assert new_thresholds['a_score_entry'] > 0.55

    def test_calibrate_thresholds_high_hit_rate(self, sample_config):
        """测试命中率高但 ROI 为负时降低阈值"""
        calibrator = AutoCalibrator(sample_config)
        
        metrics = {
            'total_matches': 10,
            'hit_rate': 0.50,  # 高于 0.45
            'roi': -0.05,      # 为负
        }
        current_thresholds = {'a_score_entry': 0.55, 'a_score_downgrade': 0.45}
        new_thresholds = calibrator.calibrate_thresholds(metrics, current_thresholds)
        
        assert new_thresholds['a_score_entry'] < 0.55

    def test_detect_model_drift_detected(self, sample_config):
        """测试漂移检测：波动大时"""
        calibrator = AutoCalibrator(sample_config)
        
        recent_metrics = [
            {'hit_rate': 0.50},
            {'hit_rate': 0.20},
            {'hit_rate': 0.55},
            {'hit_rate': 0.15},
        ]
        result = calibrator.detect_model_drift(recent_metrics)
        
        assert result['drift_detected'] is True
        assert '检测到模型漂移' in result['message']

    def test_detect_model_drift_stable(self, sample_config):
        """测试漂移检测：稳定时"""
        calibrator = AutoCalibrator(sample_config)
        
        recent_metrics = [
            {'hit_rate': 0.35},
            {'hit_rate': 0.36},
            {'hit_rate': 0.34},
        ]
        result = calibrator.detect_model_drift(recent_metrics)
        
        assert result['drift_detected'] is False
        assert '模型稳定' in result['message']

    def test_detect_model_drift_insufficient_data(self, sample_config):
        """测试数据不足时漂移检测"""
        calibrator = AutoCalibrator(sample_config)
        
        result = calibrator.detect_model_drift([{'hit_rate': 0.5}])
        assert result['drift_detected'] is False
        assert '数据不足' in result['message']

    def test_export_calibration_summary(self, sample_config, tmp_path):
        """测试校准摘要导出"""
        calibrator = AutoCalibrator(sample_config)
        
        # 先执行一次校准
        metrics = {
            'total_matches': 10,
            'tiered_hit_rate': {'high': 0.20, 'medium': 0.50, 'low': 0.10},
        }
        calibrator.calibrate_weights(metrics, sample_config['weights'])
        
        output_path = tmp_path / "calibration_summary.json"
        calibrator.export_calibration_summary(str(output_path))
        
        assert output_path.exists()
        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert data['total_calibrations'] == 1
        assert data['latest_calibration'] is not None


# ---------- WeightOptimizer Tests ----------

class TestWeightOptimizer:

    def test_quick_simulate(self, sample_config):
        """测试快速模拟"""
        optimizer = WeightOptimizer(sample_config)
        
        predictions = [
            {
                'options': {
                    'optA': {'value': 'A', 'odds': 2.0, 'a_score': 0.60},
                    'optB': {'value': 'B', 'odds': 3.0, 'a_score': 0.40},
                }
            },
            {
                'options': {
                    'optA': {'value': 'A', 'odds': 1.5, 'a_score': 0.55},
                    'optB': {'value': 'B', 'odds': 4.0, 'a_score': 0.45},
                }
            },
        ]
        actuals = [{'actual_result': 'A'}, {'actual_result': 'B'}]
        
        weights = sample_config['weights']
        roi = optimizer._quick_simulate(predictions, actuals, weights)
        
        # 第一场命中 optA (2.0-1=1.0), 第二场未命中 optA (-1.0)
        assert roi == pytest.approx(0.0, abs=0.001)

    def test_grid_search(self, sample_config):
        """测试网格搜索能返回有效权重"""
        optimizer = WeightOptimizer(sample_config)
        
        predictions = [
            {
                'options': {
                    'optA': {'value': 'A', 'odds': 2.0, 'a_score': 0.60},
                }
            },
            {
                'options': {
                    'optB': {'value': 'B', 'odds': 3.0, 'a_score': 0.55},
                }
            },
        ]
        actuals = [{'actual_result': 'A'}, {'actual_result': 'B'}]
        
        base_weights = sample_config['weights']
        best_weights = optimizer.grid_search(predictions, actuals, base_weights)
        
        assert isinstance(best_weights, dict)
        assert len(best_weights) == len(base_weights)
        total = sum(best_weights.values())
        assert total == pytest.approx(1.0, abs=0.01)

    def test_normalize_weights(self, sample_config):
        """测试权重归一化"""
        optimizer = WeightOptimizer(sample_config)
        
        weights = {'a': 1.0, 'b': 1.0, 'c': 2.0}
        normalized = optimizer._normalize_weights(weights)
        total = sum(normalized.values())
        assert total == pytest.approx(1.0, abs=0.001)


# ---------- Integration Tests ----------

class TestIntegration:

    def test_run_full_backtest(self, sample_config):
        """测试便捷回测入口"""
        predictions = [
            {'match_id': 'm1', 'options': {'optA': {'value': 'A', 'odds': 2.0, 'a_score': 0.60}}},
            {'match_id': 'm2', 'options': {'optB': {'value': 'B', 'odds': 3.0, 'a_score': 0.55}}},
        ]
        actuals = [{'actual_result': 'A'}, {'actual_result': 'B'}]
        
        result = run_full_backtest(predictions, actuals, sample_config)
        
        assert 'metrics' in result
        assert 'report' in result
        assert 'engine' in result
        assert result['metrics']['total_matches'] == 2
        assert result['metrics']['hits'] == 2
        assert '# 回测与自动校准报告' in result['report']

    def test_run_auto_calibration(self, sample_config):
        """测试便捷自动校准入口"""
        metrics = {
            'total_matches': 10,
            'tiered_hit_rate': {
                'high': 0.20,
                'medium': 0.50,
                'low': 0.10,
            },
            'hit_rate': 0.30,
            'roi': -0.05,
        }
        
        result = run_auto_calibration(metrics, sample_config)
        
        assert 'weights' in result
        assert 'thresholds' in result
        assert 'calibrator' in result
        assert sum(result['weights'].values()) == pytest.approx(1.0, abs=0.01)

    def test_end_to_end_workflow(self, sample_config, tmp_path):
        """测试端到端工作流：回测 + 校准 + 导出"""
        # 1. 准备模拟数据
        predictions = []
        actuals = []
        for i in range(12):
            predictions.append({
                'match_id': f'match_{i}',
                'options': {
                    'optA': {'value': 'A', 'odds': 2.0, 'a_score': 0.60 + (i % 3) * 0.05},
                    'optB': {'value': 'B', 'odds': 3.0, 'a_score': 0.50 - (i % 3) * 0.05},
                }
            })
            actuals.append({'actual_result': 'A' if i % 2 == 0 else 'B'})
        
        # 2. 执行回测
        backtest_result = run_full_backtest(predictions, actuals, sample_config)
        
        # 3. 执行校准
        calibration_result = run_auto_calibration(backtest_result['metrics'], sample_config)
        
        # 4. 导出校准记录
        output_path = tmp_path / "calibration.json"
        calibration_result['calibrator'].export_calibration_summary(str(output_path))
        
        assert output_path.exists()
        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert data['total_calibrations'] >= 1

    def test_sharpe_like_calculation(self, sample_config):
        """测试夏普-like 计算：数据波动越大，值越小"""
        engine = BacktestEngine(sample_config)
        
        # 构造稳定盈利的结果
        stable_results = [{'profit': 0.5, 'hit': True, 'a_score': 0.6, 'odds': 1.5} for _ in range(10)]
        stable_metrics = engine._calculate_metrics(stable_results)
        
        # 构造波动大的结果
        volatile_results = [{'profit': 5.0, 'hit': True, 'a_score': 0.6, 'odds': 6.0} if i % 2 == 0 
                           else {'profit': -1.0, 'hit': False, 'a_score': 0.6, 'odds': 0.0} 
                           for i in range(10)]
        volatile_metrics = engine._calculate_metrics(volatile_results)
        
        # 稳定结果的 sharpe-like 应该更高（或无穷大，因为标准差接近0）
        assert stable_metrics['sharpe_like'] > volatile_metrics['sharpe_like']


# ---------- Edge Cases ----------

class TestEdgeCases:

    def test_single_match(self, sample_config):
        """测试单场比赛回测"""
        engine = BacktestEngine(sample_config)
        
        predictions = [{'match_id': 'm1', 'options': {'optA': {'value': 'A', 'odds': 2.0, 'a_score': 0.60}}}]
        actuals = [{'actual_result': 'A'}]
        
        metrics = engine.run_backtest(predictions, actuals)
        assert metrics['hit_rate'] == 1.0
        assert metrics['max_consecutive_losses'] == 0

    def test_all_misses(self, sample_config):
        """测试全部未命中"""
        engine = BacktestEngine(sample_config)
        
        predictions = [
            {'match_id': 'm1', 'options': {'optA': {'value': 'A', 'odds': 2.0, 'a_score': 0.60}}},
            {'match_id': 'm2', 'options': {'optB': {'value': 'B', 'odds': 3.0, 'a_score': 0.55}}},
        ]
        actuals = [{'actual_result': 'X'}, {'actual_result': 'Y'}]
        
        metrics = engine.run_backtest(predictions, actuals)
        assert metrics['hit_rate'] == 0.0
        assert metrics['total_profit'] == -2.0
        assert metrics['max_consecutive_losses'] == 2

    def test_empty_predictions(self, sample_config):
        """测试空预测列表"""
        engine = BacktestEngine(sample_config)
        metrics = engine._calculate_metrics([])
        
        assert metrics['total_matches'] == 0
        assert metrics['hit_rate'] == 0.0

    def test_missing_actual_result(self, sample_config):
        """测试实际结果缺失"""
        engine = BacktestEngine(sample_config)
        
        prediction = {
            'match_id': 'm1',
            'options': {'optA': {'value': 'A', 'odds': 2.0, 'a_score': 0.60}}
        }
        actual = {}  # 缺少 actual_result
        
        result = engine.simulate_bet(prediction, actual)
        assert result['hit'] is False
        assert result['actual_result'] == ''

    def test_missing_options(self, sample_config):
        """测试预测中缺少选项"""
        engine = BacktestEngine(sample_config)
        
        prediction = {'match_id': 'm1', 'options': {}}
        actual = {'actual_result': 'A'}
        
        result = engine.simulate_bet(prediction, actual)
        assert result['hit'] is False
        assert result['best_option'] is None
