import json
import math
import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from collections import defaultdict


class BacktestEngine:
    """回测引擎：模拟历史投注并评估策略表现"""
    
    def __init__(self, config: dict):
        self.config = config
        self.iteration_config = config.get('iteration', {})
        self.batch_size = self.iteration_config.get('batch_size', 10)
        self.smooth_factor = self.iteration_config.get('smooth_factor', 0.8)
        self.history_dir = 'data/history'
        
        # 回测结果存储
        self.results = []
        self.metrics = {}
    
    def load_history(self, history_dir: Optional[str] = None) -> List[Dict]:
        """加载历史比赛结果数据"""
        directory = history_dir or self.history_dir
        matches = []
        if not os.path.exists(directory):
            return matches
        
        for filename in sorted(os.listdir(directory)):
            if filename.endswith('.json'):
                filepath = os.path.join(directory, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            matches.extend(data)
                        elif isinstance(data, dict) and 'matches' in data:
                            matches.extend(data['matches'])
                except (json.JSONDecodeError, IOError) as e:
                    print(f"[WARNING] 加载历史文件失败: {filename} - {e}")
        return matches
    
    def simulate_bet(self, prediction: Dict, actual_result: Dict) -> Dict:
        """单次投注模拟：对比预测与实际结果"""
        predicted_options = prediction.get('options', {})
        actual_outcome = actual_result.get('actual_result', '')
        
        hit = False
        best_option = None
        best_odds = 0.0
        best_a_score = 0.0
        
        for opt_name, opt_data in predicted_options.items():
            if opt_data.get('value') == actual_outcome:
                hit = True
                if opt_data.get('a_score', 0) > best_a_score:
                    best_a_score = opt_data['a_score']
                    best_option = opt_name
                    best_odds = opt_data.get('odds', 0)
        
        return {
            'match_id': prediction.get('match_id', 'unknown'),
            'hit': hit,
            'actual_result': actual_outcome,
            'best_option': best_option,
            'odds': best_odds,
            'a_score': best_a_score,
            'profit': best_odds - 1.0 if hit else -1.0,
        }
    
    def run_backtest(self, predictions: List[Dict], actual_results: List[Dict]) -> Dict:
        """执行完整回测，返回各项指标"""
        if len(predictions) != len(actual_results):
            raise ValueError("预测数据与实际结果数量不匹配")
        
        results = []
        for pred, actual in zip(predictions, actual_results):
            result = self.simulate_bet(pred, actual)
            results.append(result)
        
        self.results = results
        self.metrics = self._calculate_metrics(results)
        return self.metrics
    
    def _calculate_metrics(self, results: List[Dict]) -> Dict:
        """计算回测核心指标"""
        if not results:
            return self._empty_metrics()
        
        total = len(results)
        hits = sum(1 for r in results if r['hit'])
        
        # 基础命中率
        hit_rate = hits / total if total > 0 else 0.0
        
        # 总盈亏（按单位投注计算）
        total_profit = sum(r['profit'] for r in results)
        
        # 平均赔率（仅命中场次）
        hit_results = [r for r in results if r['hit']]
        avg_odds = sum(r['odds'] for r in hit_results) / len(hit_results) if hit_results else 0.0
        
        # 收益率 (ROI)
        roi = total_profit / total if total > 0 else 0.0
        
        # 最大连续亏损
        max_consecutive_losses = self._max_consecutive_losses(results)
        
        # 盈亏波动率 (Sharpe-like)
        profits = [r['profit'] for r in results]
        mean_profit = sum(profits) / len(profits) if profits else 0.0
        variance = sum((p - mean_profit) ** 2 for p in profits) / len(profits) if profits else 0.0
        std_profit = math.sqrt(variance)
        if std_profit > 0:
            sharpe_like = mean_profit / std_profit
        elif mean_profit > 0:
            sharpe_like = 10.0  # 无波动正收益 = 极高 Sharpe-like
        elif mean_profit < 0:
            sharpe_like = -10.0  # 无波动亏损
        else:
            sharpe_like = 0.0
        
        # 按 A_Score 分层的命中率
        tiered_hit_rate = self._tiered_hit_rate(results)
        
        return {
            'total_matches': total,
            'hits': hits,
            'hit_rate': round(hit_rate, 4),
            'total_profit': round(total_profit, 4),
            'avg_odds': round(avg_odds, 4),
            'roi': round(roi, 4),
            'max_consecutive_losses': max_consecutive_losses,
            'sharpe_like': round(sharpe_like, 4),
            'tiered_hit_rate': tiered_hit_rate,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
    
    def _empty_metrics(self) -> Dict:
        return {
            'total_matches': 0,
            'hits': 0,
            'hit_rate': 0.0,
            'total_profit': 0.0,
            'avg_odds': 0.0,
            'roi': 0.0,
            'max_consecutive_losses': 0,
            'sharpe_like': 0.0,
            'tiered_hit_rate': {},
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
    
    def _max_consecutive_losses(self, results: List[Dict]) -> int:
        """计算最大连续亏损次数"""
        max_streak = 0
        current_streak = 0
        for r in results:
            if not r['hit']:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0
        return max_streak
    
    def _tiered_hit_rate(self, results: List[Dict]) -> Dict[str, float]:
        """按 A_Score 分层统计命中率"""
        tiers = {
            'high': [],    # a_score >= 0.60
            'medium': [],  # 0.45 <= a_score < 0.60
            'low': [],     # a_score < 0.45
        }
        
        for r in results:
            a_score = r.get('a_score', 0)
            if a_score >= 0.60:
                tiers['high'].append(r['hit'])
            elif a_score >= 0.45:
                tiers['medium'].append(r['hit'])
            else:
                tiers['low'].append(r['hit'])
        
        return {
            tier: round(sum(hits) / len(hits), 4) if hits else 0.0
            for tier, hits in tiers.items()
        }
    
    def generate_backtest_report(self) -> str:
        """生成回测报告 Markdown"""
        if not self.metrics:
            return "# 回测报告\n\n暂无回测数据。"
        
        m = self.metrics
        lines = [
            '# 回测与自动校准报告',
            f'**生成时间**：{m["timestamp"]}',
            '',
            '## 一、核心指标',
            '',
            '| 指标 | 数值 |',
            '|------|------|',
            f'| 总场次 | {m["total_matches"]} |',
            f'| 命中场次 | {m["hits"]} |',
            f'| 命中率 | {m["hit_rate"]*100:.2f}% |',
            f'| 总盈亏 | {m["total_profit"]:+.4f} |',
            f'| 平均赔率 | {m["avg_odds"]:.4f} |',
            f'| 收益率 (ROI) | {m["roi"]*100:.2f}% |',
            f'| 最大连续亏损 | {m["max_consecutive_losses"]} 场 |',
            f'| 夏普-like | {m["sharpe_like"]:.4f} |',
            '',
            '## 二、分层命中率',
            '',
            '| A_Score 层级 | 命中情况 |',
            '|--------------|----------|',
        ]
        
        tier_labels = {'high': '高 (≥0.60)', 'medium': '中 (0.45-0.60)', 'low': '低 (<0.45)'}
        for tier, label in tier_labels.items():
            rate = m['tiered_hit_rate'].get(tier, 0.0)
            lines.append(f'| {label} | {rate*100:.2f}% |')
        
        lines.extend([
            '',
            '## 三、校准建议',
        ])
        
        if m['hit_rate'] < 0.25:
            lines.append('- ⚠️ 命中率低于 25%，建议检查模型输入数据质量')
        elif m['hit_rate'] > 0.45:
            lines.append('- ✅ 命中率表现优异，可考虑适度提高投注金额')
        
        if m['roi'] < -0.20:
            lines.append('- ⚠️ ROI 严重亏损，建议暂停投注并全面审查模型')
        elif m['roi'] > 0.10:
            lines.append('- ✅ ROI 为正，模型具备正向期望')
        
        lines.append('')
        lines.append('*报告由 BacktestEngine 自动生成*')
        
        return '\n'.join(lines)


class AutoCalibrator:
    """自动校准器：根据回测结果迭代优化权重与阈值"""
    
    def __init__(self, config: dict):
        self.config = config
        self.iteration = config.get('iteration', {})
        self.smooth_factor = self.iteration.get('smooth_factor', 0.8)
        self.batch_size = self.iteration.get('batch_size', 10)
        
        # 校准记录
        self.calibration_history = []
    
    def calibrate_weights(self, backtest_metrics: Dict, 
                          current_weights: Dict[str, float]) -> Dict[str, float]:
        """根据回测结果校准权重（平滑更新）"""
        if not backtest_metrics or backtest_metrics.get('total_matches', 0) < self.batch_size:
            return current_weights.copy()
        
        tiered = backtest_metrics.get('tiered_hit_rate', {})
        
        # 根据分层命中率调整权重方向
        high_rate = tiered.get('high', 0.0)
        medium_rate = tiered.get('medium', 0.0)
        low_rate = tiered.get('low', 0.0)
        
        adjustments = {}
        
        # 如果高 A_Score 选项命中率低，降低 p_clean 权重（去偏概率过于乐观）
        if high_rate < 0.35:
            adjustments['p_clean'] = -0.02
        elif high_rate > 0.50:
            adjustments['p_clean'] = 0.02
        
        # 如果中层命中率表现更好，说明 Q 因子可能需要更多权重
        if medium_rate > high_rate and medium_rate > 0.40:
            adjustments['q_score'] = 0.01
        
        # 如果低层命中率异常高，说明冷门信号权重不足
        if low_rate > 0.30:
            adjustments['upset_signal'] = 0.01
        
        # 平滑更新
        new_weights = current_weights.copy()
        for key, delta in adjustments.items():
            if key in new_weights:
                old_val = new_weights[key]
                new_val = old_val + self.smooth_factor * delta
                new_weights[key] = round(max(0.0, min(1.0, new_val)), 4)
        
        # 归一化确保总和为 1.0
        new_weights = self._normalize_weights(new_weights)
        
        self.calibration_history.append({
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'old_weights': current_weights.copy(),
            'new_weights': new_weights.copy(),
            'trigger_metrics': backtest_metrics,
        })
        
        return new_weights
    
    def calibrate_thresholds(self, backtest_metrics: Dict,
                            current_thresholds: Dict) -> Dict:
        """根据回测结果校准阈值"""
        new_thresholds = current_thresholds.copy()
        hit_rate = backtest_metrics.get('hit_rate', 0.0)
        total_matches = backtest_metrics.get('total_matches', 0)
        
        if total_matches < self.batch_size:
            return new_thresholds
        
        # 命中率过低 → 提高入选门槛，减少错误选择
        if hit_rate < 0.25:
            new_thresholds['a_score_entry'] = min(
                0.70, current_thresholds.get('a_score_entry', 0.55) + 0.02
            )
        # 命中率过高但 ROI 不足 → 降低门槛，增加覆盖面
        elif hit_rate > 0.45 and backtest_metrics.get('roi', 0.0) < 0.0:
            new_thresholds['a_score_entry'] = max(
                0.45, current_thresholds.get('a_score_entry', 0.55) - 0.02
            )
        
        return new_thresholds
    
    def detect_model_drift(self, recent_metrics: List[Dict]) -> Dict:
        """检测模型漂移：连续 N 批回测的命中率波动"""
        if len(recent_metrics) < 3:
            return {'drift_detected': False, 'message': '数据不足'}
        
        hit_rates = [m.get('hit_rate', 0.0) for m in recent_metrics[-10:]]
        mean_rate = sum(hit_rates) / len(hit_rates)
        variance = sum((r - mean_rate) ** 2 for r in hit_rates) / len(hit_rates)
        std_rate = math.sqrt(variance)
        
        # 如果命中率标准差超过 15% 视为漂移
        drift_threshold = 0.15
        drift_detected = std_rate > drift_threshold
        
        # 如果最近一批命中率偏离均值超过 2 个标准差
        latest = hit_rates[-1]
        z_score = abs(latest - mean_rate) / std_rate if std_rate > 0 else 0
        significant_shift = z_score > 2.0
        
        return {
            'drift_detected': drift_detected or significant_shift,
            'std_rate': round(std_rate, 4),
            'mean_rate': round(mean_rate, 4),
            'latest_rate': round(latest, 4),
            'z_score': round(z_score, 4),
            'message': '检测到模型漂移' if (drift_detected or significant_shift) else '模型稳定',
        }
    
    def _normalize_weights(self, weights: Dict[str, float]) -> Dict[str, float]:
        """归一化权重确保总和为 1.0"""
        total = sum(weights.values())
        if total == 0 or abs(total - 1.0) < 0.001:
            return weights
        return {k: round(v / total, 4) for k, v in weights.items()}
    
    def get_calibration_log(self) -> List[Dict]:
        """获取校准历史记录"""
        return self.calibration_history.copy()
    
    def export_calibration_summary(self, filepath: str):
        """导出校准摘要到 JSON 文件"""
        summary = {
            'total_calibrations': len(self.calibration_history),
            'latest_calibration': self.calibration_history[-1] if self.calibration_history else None,
            'history': self.calibration_history,
        }
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=str)


class WeightOptimizer:
    """权重优化器：基于历史数据搜索最优权重组合"""
    
    def __init__(self, config: dict):
        self.config = config
        self.search_steps = 5  # 网格搜索步数
    
    def grid_search(self, predictions: List[Dict], actual_results: List[Dict],
                    base_weights: Dict[str, float]) -> Dict[str, float]:
        """简单的网格搜索寻找最优权重（仅对关键权重微调）"""
        best_weights = base_weights.copy()
        best_roi = float('-inf')
        
        # 仅微调 p_clean, q_score, m_factor 三个核心权重
        keys_to_optimize = ['p_clean', 'q_score', 'm_factor']
        
        # 获取当前值
        current_values = {k: base_weights.get(k, 0.0) for k in keys_to_optimize}
        
        # 生成微调范围 ±0.10
        step = 0.05
        
        for p_delta in [-0.10, -0.05, 0.0, 0.05, 0.10]:
            for q_delta in [-0.10, -0.05, 0.0, 0.05, 0.10]:
                for m_delta in [-0.10, -0.05, 0.0, 0.05, 0.10]:
                    test_weights = base_weights.copy()
                    test_weights['p_clean'] = max(0.0, min(1.0, current_values['p_clean'] + p_delta))
                    test_weights['q_score'] = max(0.0, min(1.0, current_values['q_score'] + q_delta))
                    test_weights['m_factor'] = max(0.0, min(1.0, current_values['m_factor'] + m_delta))
                    
                    # 归一化
                    test_weights = self._normalize_weights(test_weights)
                    
                    # 模拟回测（简化版：只检查预测中 top 选项的命中率）
                    roi = self._quick_simulate(predictions, actual_results, test_weights)
                    
                    if roi > best_roi:
                        best_roi = roi
                        best_weights = test_weights.copy()
        
        return best_weights
    
    def _quick_simulate(self, predictions: List[Dict], actual_results: List[Dict],
                        weights: Dict[str, float]) -> float:
        """快速模拟：只检查每场预测中 A_Score 最高的选项"""
        total_profit = 0.0
        
        for pred, actual in zip(predictions, actual_results):
            options = pred.get('options', {})
            if not options:
                continue
            
            # 找到 A_Score 最高的选项
            top_option = max(options.items(), key=lambda x: x[1].get('a_score', 0))
            actual_outcome = actual.get('actual_result', '')
            
            if top_option[1].get('value') == actual_outcome:
                total_profit += top_option[1].get('odds', 1.0) - 1.0
            else:
                total_profit -= 1.0
        
        return total_profit / len(predictions) if predictions else 0.0
    
    def _normalize_weights(self, weights: Dict[str, float]) -> Dict[str, float]:
        """归一化权重"""
        total = sum(weights.values())
        if total == 0 or abs(total - 1.0) < 0.001:
            return weights
        return {k: round(v / total, 4) for k, v in weights.items()}


def run_full_backtest(predictions: List[Dict], actual_results: List[Dict],
                      config: dict) -> Dict:
    """便捷的完整回测入口函数"""
    engine = BacktestEngine(config)
    metrics = engine.run_backtest(predictions, actual_results)
    report = engine.generate_backtest_report()
    return {
        'metrics': metrics,
        'report': report,
        'engine': engine,
    }


def run_auto_calibration(backtest_metrics: Dict, config: dict) -> Dict:
    """便捷的自动校准入口函数"""
    calibrator = AutoCalibrator(config)
    
    current_weights = config.get('weights', {})
    new_weights = calibrator.calibrate_weights(backtest_metrics, current_weights)
    
    current_thresholds = config.get('thresholds', {})
    new_thresholds = calibrator.calibrate_thresholds(backtest_metrics, current_thresholds)
    
    return {
        'weights': new_weights,
        'thresholds': new_thresholds,
        'calibrator': calibrator,
    }
