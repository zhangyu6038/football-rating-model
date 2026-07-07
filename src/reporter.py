from typing import Dict, List
from datetime import datetime


class ReportGenerator:
    """Markdown 报告生成器"""
    
    def __init__(self):
        self.lines = []
    
    def generate(self, analysis_results: Dict) -> str:
        """生成完整报告"""
        self.lines = []
        
        self._header()
        self._disclaimer()
        self._rating_summary(analysis_results.get('matches', []))
        self._options_ranking(analysis_results.get('rankings', []))
        self._portfolio(analysis_results.get('portfolio', {}))
        self._stress_test(analysis_results.get('portfolio', {}).get('stress_test', []))
        self._decision_advice(analysis_results.get('portfolio', {}))
        self._footer()
        
        return '
'.join(self.lines)
    
    def _header(self):
        today = datetime.now().strftime('%Y年%m月%d日')
        self.lines.append(f'# 竞彩足球分析报告')
        self.lines.append(f'**生成时间**：{today}')
        self.lines.append(f'**模型版本**：Football Rating Model V2.0')
        self.lines.append('')
    
    def _disclaimer(self):
        self.lines.append('> ⚠️ **风险提示**：本报告基于公开赔率数据和数学模型自动生成，')
        self.lines.append('> 仅供个人学习与研究之用，不构成任何投注建议。')
        self.lines.append('> 足球比赛结果具有高度不确定性，历史分析不代表未来表现。')
        self.lines.append('> 请理性购彩，未成年人不得参与。')
        self.lines.append('')
    
    def _rating_summary(self, matches: List[Dict]):
        self.lines.append('---')
        self.lines.append('## 一、赛事评级摘要')
        self.lines.append('')
        self.lines.append('| 比赛 | M_factor | H_factor | Q_score | 赔率稳定性 | 冷门信号 |')
        self.lines.append('|------|----------|----------|---------|------------|----------|')
        
        for m in matches:
            f = m.get('factors', {})
            self.lines.append(
                f"| {m.get('home','?')} vs {m.get('away','?')} "
                f"| {f.get('M_factor','N/A')} "
                f"| {f.get('H_factor','N/A')} "
                f"| {f.get('Q_score','N/A')} "
                f"| {f.get('stability','N/A')} "
                f"| {f.get('upset_signal','N/A')} |"
            )
        self.lines.append('')
    
    def _options_ranking(self, rankings: List[Dict]):
        self.lines.append('---')
        self.lines.append('## 二、选项吸引力排名')
        self.lines.append('')
        self.lines.append('| 比赛 | 选项 | 赔率 | 去偏概率 | A_Score |')
        self.lines.append('|------|------|------|----------|---------|')
        
        for r in rankings[:10]:
            self.lines.append(
                f"| {r.get('match','')} "
                f"| {r.get('option','')} "
                f"| {r.get('odds','')} "
                f"| {r.get('p_clean','')} "
                f"| {r.get('a_score','')} |"
            )
        self.lines.append('')
    
    def _portfolio(self, portfolio: Dict):
        self.lines.append('---')
        self.lines.append('## 三、推荐投注组合')
        self.lines.append('')
        
        core = portfolio.get('core_combinations', [])
        if core:
            self.lines.append('### 核心组合（总进球数 2串1）')
            self.lines.append('')
            self.lines.append('| 编号 | 组合内容 | 组合赔率 | 倍数 | 投入(元) | 命中回报 | 净利润 |')
            self.lines.append('|------|----------|----------|------|----------|----------|--------|')
            
            for i, c in enumerate(core, 1):
                total_cost = portfolio.get('total_cost', 30)
                net = round(c['return'] - total_cost, 2)
                self.lines.append(
                    f"| C{i} | {c['name']} | {c['odds']} | {c['multiplier']} | "
                    f"{c['cost']} | {c['return']} | {net if net > 0 else f'{net}(需其他组合)'} |"
                )
        
        hedge = portfolio.get('hedge')
        if hedge:
            self.lines.append('')
            self.lines.append('### 对冲组合')
            self.lines.append('')
            total_cost = portfolio.get('total_cost', 30)
            net = round(hedge['return'] - total_cost, 2)
            self.lines.append(
                f"| {hedge['name']} | {hedge['odds']} | {hedge['multiplier']} | "
                f"{hedge['cost']} | {hedge['return']} | {net}（极端对冲） |"
            )
        
        self.lines.append('')
        self.lines.append(f"**总投入**：{portfolio.get('total_cost', 0)} 元")
        is_protected = portfolio.get('is_protected', False)
        status = '✅ 已保本' if is_protected else '⚠️ 未完全保本，请检查'
        self.lines.append(f'**保本状态**：{status}')
        self.lines.append('')
    
    def _stress_test(self, scenarios: List[Dict]):
        self.lines.append('---')
        self.lines.append('## 四、压力测试')
        self.lines.append('')
        self.lines.append('| 情景 | 命中组合 | 总回报(元) | 盈亏(元) |')
        self.lines.append('|------|----------|------------|----------|')
        
        for s in scenarios:
            profit = s.get('盈亏', 0)
            symbol = '+' if profit >= 0 else ''
            self.lines.append(
                f"| {s['情景']} | {s['命中组合']} | {s['总回报']} | {symbol}{profit} |"
            )
        self.lines.append('')
    
    def _decision_advice(self, portfolio: Dict):
        self.lines.append('---')
        self.lines.append('## 五、决策建议')
        self.lines.append('')
        
        core = portfolio.get('core_combinations', [])
        if core:
            best = core[0]
            self.lines.append(f'- **首选组合**：{best["name"]}（期望回报 {best["expected_return"]}，A_Score {best["a_score"]}）')
            if len(core) >= 2:
                self.lines.append(f'- **次选组合**：{core[1]["name"]}')
        
        hedge = portfolio.get('hedge')
        if hedge:
            self.lines.append(f'- **对冲保底**：{hedge["name"]}（赔率 {hedge["odds"]}，占资金 {hedge["cost"]}元）')
        
        self.lines.append('- **执行提醒**：赛前1小时确认首发阵容后重新评估')
        self.lines.append('- **弃选说明**：A_Score < 0.45 的选项已自动排除')
        self.lines.append('')
    
    def _footer(self):
        self.lines.append('---')
        self.lines.append('')
        self.lines.append('*报告由 Football Rating Model V2.0 自动生成*')
        self.lines.append(f'*生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*')
