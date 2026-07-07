# WebBridge 数据采集指令集

## 阶段1：打开目标页面
```
操作：使用 WebBridge 导航到以下URL
URL：https://m.sporttery.cn/mjc/jsq/zqhhgg/
等待条件：页面中出现 ".match-list" 或 ".match-item" 元素（最长等待15秒）
```

## 阶段2：提取赛事列表
```javascript
const matches = [];
const items = document.querySelectorAll('.match-item, [class*="match"]');
items.forEach((item, idx) => {
    const id = item.getAttribute('data-matchid') || item.getAttribute('data-id') || `match_${idx}`;
    const home = item.querySelector('.home-team, .team-home, [class*="home"]')?.innerText?.trim() || '';
    const away = item.querySelector('.away-team, .team-away, [class*="away"]')?.innerText?.trim() || '';
    const league = item.querySelector('.league-name, [class*="league"]')?.innerText?.trim() || '';
    const time = item.querySelector('.match-time, [class*="time"]')?.innerText?.trim() || '';
    if (home && away) {
        matches.push({id, home, away, league, time});
    }
});
return JSON.stringify(matches, null, 2);
```

## 阶段3：逐场获取赔率详情
```
对于 matches 中的每场比赛（前2-3场即可）：

方式A：尝试 API 接口（优先）
```javascript
const mid = "从阶段2获取的match.id";
const resp = await fetch(`https://i.sporttery.cn/api/odds/match_detail?mid=${mid}`);
const data = await resp.json();
return JSON.stringify({
    id: mid,
    spf: data.spf || data.wdl,
    zjq: data.zjq || data.total_goals,
    bqc: data.bqc || data.half_full,
});
```

方式B：DOM 解析（如果 API 不可用）
```
操作：点击该场比赛的展开按钮或详情链接
等待：赔率表格出现
提取：
- 胜平负赔率（3个数字）
- 总进球数赔率（7个数字：0,1,2,3,4,5,6+）
- 半全场赔率（9个数字：胜胜到负负）
- 比分赔率（可选）
```

## 阶段4：获取基本面数据
```
对于每场比赛，查找以下信息（若页面提供）：
- "近期战绩" 或 "近期表现" 模块
- "历史交锋" 模块
- 提取文本即可，不需要精确结构化
```

## 阶段5：保存数据
```
将所有提取的数据合并为一个 JSON 对象，格式为：
{
    "fetch_time": "2026-07-07 10:30:00",
    "source": "m.sporttery.cn",
    "matches": [
        { 单场比赛的完整数据 }
    ]
}
保存为 /tmp/match_data.json
```

## 降级策略（当抓取不完整时）
- 若总进球数赔率缺失 → 该场比赛仅用于半全场分析
- 若半全场赔率缺失 → 使用胜平负替代保底
- 若基本面数据缺失 → Q_score 使用默认值（场均进球1.5，场均失球1.3）
- 若整体抓取失败 → 提示用户手动输入（见 FALLBACK_MANUAL_TEMPLATE）
