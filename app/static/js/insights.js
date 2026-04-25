// Health score, plain understandabke summaries, what-if engine, behavioural insights.
// scoring driven by risk metrics (Sharpe, VaR, drawdown, volatility).

// Helpers
function _pct(v)   { return (Number(v) * 100).toFixed(1) + '%'; }
function _abs(v)   { return Math.abs(Number(v)); }
function _f2(v)    { return Number(v).toFixed(2); }
function _has(v)   { return v !== undefined && v !== null && !isNaN(Number(v)); }
// reads the global experience level set by dashboard.html
function _lvl()    { return (window._userLevel || 'advanced').toLowerCase(); }

// Metric inline explanations 
const METRIC_EXPLAIN = {
  sharpe: v => {
    const n = Number(v);
    if (isNaN(n)) return 'Sharpe ratio: return earned per unit of risk.';
    if (n < 0)   return `Sharpe ${_f2(n)} — you're earning less than the risk-free rate. Risk is not being rewarded at all.`;
    if (n < 0.5) return `Sharpe ${_f2(n)} — poor. A passive index fund would likely beat this on a risk-adjusted basis.`;
    if (n < 1.0) return `Sharpe ${_f2(n)} — acceptable. You're being compensated for risk, though not strongly.`;
    if (n < 1.5) return `Sharpe ${_f2(n)} — good. Returns are well compensated relative to volatility. Most professional funds sit here.`;
    return `Sharpe ${_f2(n)} — excellent risk-adjusted return.`;
  },
  var: v => {
    const n = _abs(v) * 100;
    if (isNaN(n)) return 'VaR: maximum daily loss expected on 95% of trading days.';
    return `VaR ${n.toFixed(2)}% — on 95 out of 100 days your portfolio should not lose more than ${n.toFixed(2)}%. On the other 5 days, losses may exceed this.`;
  },
  cvar: v => {
    const n = _abs(v) * 100;
    if (isNaN(n)) return 'CVaR: average loss on your worst 5% of trading days.';
    return `CVaR ${n.toFixed(2)}% — on your worst 5% of days, the average loss is ${n.toFixed(2)}%. This is the severity behind VaR's threshold.`;
  },
  drawdown: v => {
    const n = _abs(v) * 100;
    if (isNaN(n)) return 'Max drawdown: worst peak-to-trough decline in portfolio history.';
    const rec = n > 0 ? ((100 / (100 - n) - 1) * 100).toFixed(1) : 0;
    if (n < 10)  return `Max drawdown ${n.toFixed(1)}% — very low. Portfolio has been resilient.`;
    if (n < 25)  return `Max drawdown ${n.toFixed(1)}% — moderate. Recovery from this requires a +${rec}% gain.`;
    if (n < 40)  return `Max drawdown ${n.toFixed(1)}% — significant. Recovery requires +${rec}%. Would you hold through this?`;
    return `Max drawdown ${n.toFixed(1)}% — severe. Recovery requires +${rec}%. This tests most investors' resolve.`;
  },
  volatility: v => {
    const n = Number(v) * 100;
    if (isNaN(n)) return 'Volatility: annualised standard deviation of daily returns.';
    if (n < 8)   return `Volatility ${n.toFixed(1)}%/yr — very low, typical of a bond-heavy portfolio.`;
    if (n < 15)  return `Volatility ${n.toFixed(1)}%/yr — low-moderate. Well-diversified equity portfolios often sit here.`;
    if (n < 25)  return `Volatility ${n.toFixed(1)}%/yr — moderate, in line with typical equity portfolios (S&P 500 averages 15–20%).`;
    if (n < 40)  return `Volatility ${n.toFixed(1)}%/yr — high. Check that your Sharpe ratio justifies this level of risk.`;
    return `Volatility ${n.toFixed(1)}%/yr — very high. This is concentrated or speculative portfolio territory.`;
  },
  annualised_return: v => {
    const n = Number(v) * 100;
    if (isNaN(n)) return 'Annualised return: historical performance scaled to a per-year figure.';
    if (n < 0)   return `Annualised return ${n.toFixed(1)}%/yr — portfolio is losing value over time.`;
    if (n < 4)   return `Annualised return ${n.toFixed(1)}%/yr — below the typical risk-free rate. Consider whether this justifies the risk.`;
    if (n < 8)   return `Annualised return ${n.toFixed(1)}%/yr — modest. Global equity indices have returned 7–10% long term.`;
    if (n < 15)  return `Annualised return ${n.toFixed(1)}%/yr — solid, in line with or above long-term equity market returns.`;
    return `Annualised return ${n.toFixed(1)}%/yr — strong. Significantly above long-term market averages.`;
  },
};

// portfolio health score returns; score, grade, colour, reasons, suggestions
function computeHealthScore(metrics, holdings) {
  const reasons     = [];  // what's contributing to the score
  const suggestions = [];  // what the user could do to improve
  let   score       = 100;

  const hasSharpe  = _has(metrics?.sharpe_ratio);
  const hasDD      = _has(metrics?.max_drawdown);
  const hasVol     = _has(metrics?.annualised_volatility);
  const hasReturn     = _has(metrics?.annualised_return);
  const hasVaR     = _has(metrics?.var);
  const hasData    = hasSharpe || hasDD || hasVol;

  // d1: diversification -30 points
  let divPoints = 30;
  const numH = holdings?.length || 0;
  const weights = (holdings || []).map(h => Number(h.weight) || 0);
  const maxW    = weights.length ? Math.max(...weights) : 0;
  const topH    = holdings?.find(h => Number(h.weight) === maxW);

  if (numH === 0) {
    divPoints = 0;
    reasons.push({ type: 'warn', text: 'No holdings... add positions to see your health score.' });
  } else if (numH === 1) {
    divPoints = 2;
    reasons.push({ type: 'bad', text: 'Single holding -> zero diversification. All risk is in one position.' });
    suggestions.push('Add at least 5–10 uncorrelated positions across different sectors to eliminate idiosyncratic risk.');
  } else if (numH < 5) {
    divPoints = 10;
    reasons.push({ type: 'warn', text: `Only ${numH} holdings provides limited diversification.` });
    suggestions.push(`Aim for at least 10–15 positions across different sectors. You currently hold ${numH}.`);
  } else if (numH < 10) {
    divPoints = 18;
    reasons.push({ type: 'info', text: `${numH} holdings, reasonable start. More positions would reduce idiosyncratic risk further.` });
  } else if (numH < 20) {
    divPoints = 25;
    reasons.push({ type: 'good', text: `${numH} holdings, well diversified by number of positions.` });
  } else {
    divPoints = 30;
    reasons.push({ type: 'good', text: `${numH} holdings, excellent diversification by count.` });
  }

  if (maxW > 0.45) {
    divPoints = Math.min(divPoints, 6);
    reasons.push({ type: 'bad', text: `${topH?.symbol || 'Top holding'} is ${_pct(maxW)} of portfolio, dangerously concentrated.` });
    suggestions.push(`Reduce ${topH?.symbol || 'your largest holding'} from ${_pct(maxW)} to below 20–25%. A single company event could devastate this portfolio.`);
  } else if (maxW > 0.3) {
    divPoints = Math.min(divPoints, 16);
    reasons.push({ type: 'warn', text: `${topH?.symbol || 'Top holding'} is ${_pct(maxW)} — above the recommended 25% ceiling.` });
    suggestions.push(`Consider trimming ${topH?.symbol || 'your largest position'} from ${_pct(maxW)} to below 25% and redistributing to underweight positions.`);
  } else if (maxW > 0.2 && numH >= 5) {
    reasons.push({ type: 'info', text: `Largest position at ${_pct(maxW)} — slightly concentrated but manageable.` });
  } else if (maxW <= 0.2 && numH >= 8) {
    reasons.push({ type: 'good', text: `No single position dominates — concentration risk is well controlled.` });
  }

  score -= (30 - divPoints);

  // D2: sharpe ratio 25 pts
  if (hasSharpe) {
    const s = Number(metrics.sharpe_ratio);
    let pts = 25;
    if (s < 0)       { pts = 0;  reasons.push({ type: 'bad',  text: `Sharpe ${_f2(s)} — returns below the risk-free rate. Risk is uncompensated.` }); suggestions.push('Your returns are below the risk-free rate. Review whether your holdings justify the volatility; a passive global index fund may outperform.'); }
    else if (s < 0.3){ pts = 5;  reasons.push({ type: 'warn', text: `Sharpe ${_f2(s)} — poor risk-adjusted return.` }); suggestions.push(`Sharpe of ${_f2(s)} is weak. Focus on improving diversification (which reduces the denominator σ) and consider trimming underperforming holdings.`); }
    else if (s < 0.6){ pts = 12; reasons.push({ type: 'info', text: `Sharpe ${_f2(s)} — below average. There is room to improve risk-adjusted returns.` }); suggestions.push(`A Sharpe of ${_f2(s)} means risk isn't being rewarded well, uh ohh. Reducing volatility through diversification would push this higher.`); }
    else if (s < 1.0){ pts = 18; reasons.push({ type: 'good', text: `Sharpe ${_f2(s)} — acceptable risk-adjusted performance.` }); }
    else if (s < 1.5){ pts = 22; reasons.push({ type: 'good', text: `Sharpe ${_f2(s)} — strong risk-adjusted return.` }); }
    else             { pts = 25; reasons.push({ type: 'good', text: `Sharpe ${_f2(s)} — excellent. Returns are very well compensated for risk.` }); }
    score -= (25 - pts);
  } else if (!hasData) {
    reasons.push({ type: 'info', text: 'Add holdings with valid ticker symbols to unlock Sharpe ratio, VaR, and drawdown scoring.' });
    suggestions.push('Make sure your holdings use recognised ticker symbols so live price data can be fetched automatically.');
    score -= 15; // implemeted a partial deduction for missing data
  }

  // dim 3: max drawdown - 25 points 
  if (hasDD) {
    const dd = _abs(metrics.max_drawdown);
    const rec = dd > 0 ? ((1 / (1 - dd) - 1) * 100).toFixed(0) : 0;
    let ddpoints = 25;
    if (dd > 0.5)       { ddpoints = 0;  reasons.push({ type: 'bad',  text: `Max drawdown ${_pct(metrics.max_drawdown)} — severe. Recovery needs +${rec}%.` }); suggestions.push(`A ${_pct(metrics.max_drawdown)} drawdown is severe. Reducing position sizes and improving diversification would lower your worst-case loss.`); }
    else if (dd > 0.35) { ddpoints = 8;  reasons.push({ type: 'warn', text: `Max drawdown ${_pct(metrics.max_drawdown)} — high. Recovery needs +${rec}%.` }); suggestions.push(`Your max drawdown of ${_pct(metrics.max_drawdown)} is high. Consider defensive positions or reducing exposure to high-beta holdings.`); }
    else if (dd > 0.2)  { ddpoints = 15; reasons.push({ type: 'info', text: `Max drawdown ${_pct(metrics.max_drawdown)} — moderate. Recovery needs +${rec}%.` }); }
    else if (dd > 0.1)  { ddpoints = 20; reasons.push({ type: 'good', text: `Max drawdown ${_pct(metrics.max_drawdown)} — manageable.` }); }
    else                { ddpoints = 25; reasons.push({ type: 'good', text: `Max drawdown ${_pct(metrics.max_drawdown)} — very low. Portfolio has been resilient.` }); }
    score -= (25 - ddpoints);
  }

  // 4: volatility 20 points
  if (hasVol && hasReturn) {
    const vol = Number(metrics.annualised_volatility);
    const ret = Number(metrics.annualised_return);
    let pts = 20;
    if (vol > 0.5)       { pts = 0;  reasons.push({ type: 'bad',  text: `Volatility ${_pct(metrics.annualised_volatility)}/yr — extremely high.` }); suggestions.push('Annualised volatility above 50% indicates a very concentrated or speculative portfolio. Diversify across uncorrelated assets to reduce this.'); }
    else if (vol > 0.35) { pts = 6;  reasons.push({ type: 'warn', text: `Volatility ${_pct(metrics.annualised_volatility)}/yr — high.` }); suggestions.push(`Volatility of ${_pct(metrics.annualised_volatility)}/yr is above typical equity portfolio range (15–25%). Adding defensive holdings (lower-beta stocks, bonds) would reduce this.`); }
    else if (vol > 0.22) { pts = 12; reasons.push({ type: 'info', text: `Volatility ${_pct(metrics.annualised_volatility)}/yr — above typical equity range.` }); }
    else if (vol > 0.1)  { pts = 17; reasons.push({ type: 'good', text: `Volatility ${_pct(metrics.annualised_volatility)}/yr — in a healthy range for an equity portfolio.` }); }
    else                 { pts = 20; reasons.push({ type: 'good', text: `Volatility ${_pct(metrics.annualised_volatility)}/yr — very well controlled.` }); }
    score -= (20 - pts);

    // Return context
    if (ret < 0 && hasReturn) {
      reasons.push({ type: 'bad', text: `Annualised return ${_pct(metrics.annualised_return)}/yr... portfolio is losing value.` });
      suggestions.push('Your portfolio has a negative annualised return. Review each holding for deteriorating fundamentals and consider rebalancing away from underperformers.');
      score -= 5;
    } else if (ret < 0.04 && hasReturn && vol > 0.15) {
      reasons.push({ type: 'warn', text: `Low return (${_pct(metrics.annualised_return)}/yr) relative to volatility (${_pct(metrics.annualised_volatility)}/yr).` });
      suggestions.push('You are bearing significant volatility for a low return. A global index ETF would likely deliver better risk-adjusted performance with less effort.');
    } else if (ret >= 0.10 && hasReturn) {
      reasons.push({ type: 'good', text: `Strong annualised return of ${_pct(metrics.annualised_return)}/yr.` });
    }
  }

  score = Math.max(0, Math.min(100, Math.round(score)));

  let grade, colour;
  if (score >= 85)      { grade = 'A'; colour = '#16a34a'; }
  else if (score >= 70) { grade = 'B'; colour = '#65a30d'; }
  else if (score >= 55) { grade = 'C'; colour = '#d97706'; }
  else if (score >= 40) { grade = 'D'; colour = '#ea580c'; }
  else                  { grade = 'F'; colour = '#dc2626'; }

  return { score, grade, colour, reasons, suggestions };
}

// portfolio summary for dashboard analytics 
function PortfolioSummary(metrics, holdings, health, name) {
  if (!holdings || holdings.length === 0) return 'Add holdings to see your portfolio summary.';

  const { score, grade, suggestions } = health;
  const numH    = holdings.length;
  const total   = Number(metrics?.total_invested || 0);
  const hasMets = _has(metrics?.sharpe_ratio);

  // diplayline based on grade assigned 
  const grademsg = {
    A: 'is in excellent shape',
    B: 'is in good shape with a few areas to refine',
    C: 'has some meaningful areas for improvement',
    D: 'has significant weaknesses that are likely costing returns',
    F: 'has serious structural issues that should be addressed',
  }[grade] || 'has been analysed';

  let lines = [`**${name || 'Your portfolio'}** scores **${score}/100 (${grade})** — it ${grademsg}.`];

  // Holdings summary
  if (numH === 1)     lines.push(`It holds a single position, there is no diversification protection if that holding moves against you.`);
  else if (numH < 5)  lines.push(`It holds ${numH} positions, which is a start but provides limited protection against any one stock falling sharply.`);
  else if (numH < 12) lines.push(`It holds ${numH} positions, giving reasonable but improvable diversification.`);
  else                lines.push(`It holds ${numH} positions, providing solid diversification across multiple companies.`);

  // performance narrativ language adapts to experience level
  if (hasMets) {
    const sharpe = Number(metrics.sharpe_ratio);
    const dd     = _abs(metrics.max_drawdown) * 100;
    const vol    = Number(metrics.annualised_volatility) * 100;
    const ret    = Number(metrics.annualised_return) * 100;
    const isBeginner     = _lvl() === 'beginner';
    const isIntermediate = _lvl() === 'intermediate';

    // growth / return line
    if (isBeginner) {
      if (ret < 0)       lines.push(`Your portfolio is losing money — it's shrinking by ${Math.abs(ret).toFixed(1)}% a year. It might be worth looking at what's dragging it down.`);
      else if (ret < 5)  lines.push(`Your portfolio is growing by about ${ret.toFixed(1)}% a year. That's positive! But for context, a simple index fund typically grows around 7–10% a year.`);
      else if (ret < 12) lines.push(`Your portfolio is growing by ${ret.toFixed(1)}% a year — that's solid, and right in line with what the stock market tends to deliver on average.`);
      else               lines.push(`Your portfolio is growing fast — ${ret.toFixed(1)}% a year is well above the typical market return. Great work!`);
    } else {
      if (ret < 0)       lines.push(`Annualised return is ${ret.toFixed(1)}%/yr — the portfolio is losing value over time.`);
      else if (ret < 5)  lines.push(`Annualised return is ${ret.toFixed(1)}%/yr — modest, and below the long-term equity market average of roughly 7–10%.`);
      else if (ret < 12) lines.push(`Annualised return is ${ret.toFixed(1)}%/yr — solid, broadly in line with equity market expectations.`);
      else               lines.push(`Annualised return is ${ret.toFixed(1)}%/yr — strong outperformance relative to long-term market averages.`);
    }

    // risk/reward line
    if (isBeginner) {
      if (sharpe < 0)        lines.push(`For the ups and downs your portfolio goes through, the returns aren't worth it right now. Think of it like a rough road going nowhere — you're taking on stress without the reward.`);
      else if (sharpe < 0.5) lines.push(`Your returns are a bit low compared to how much your portfolio moves around. A simple index fund might actually do better with less stress.`);
      else if (sharpe < 1.0) lines.push(`Your portfolio is earning a reasonable reward for the risk you're taking — nothing to worry about, but there is room to improve.`);
      else                   lines.push(`Your portfolio is working hard for you — you're earning strong returns without taking on too much risk.`);
    } else if (isIntermediate) {
      if (sharpe < 0)        lines.push(`Risk-adjusted return (Sharpe ${_f2(sharpe)}) is negative — returns aren't compensating for the volatility being taken on.`);
      else if (sharpe < 0.5) lines.push(`Sharpe ratio of ${_f2(sharpe)} is below average — the portfolio isn't being rewarded well for its risk level.`);
      else if (sharpe < 1.0) lines.push(`Sharpe ratio of ${_f2(sharpe)} is acceptable — returns are modestly compensating for volatility.`);
      else                   lines.push(`Sharpe ratio of ${_f2(sharpe)} is strong — returns are well compensated for the risk being taken.`);
    } else {
      if (sharpe < 0)        lines.push(`Risk-adjusted performance (Sharpe ${_f2(sharpe)}) is negative — you are taking volatility without being rewarded for it.`);
      else if (sharpe < 0.5) lines.push(`Risk-adjusted performance (Sharpe ${_f2(sharpe)}) is below average — a passive index fund would likely serve you better on this measure.`);
      else if (sharpe < 1.0) lines.push(`Risk-adjusted performance (Sharpe ${_f2(sharpe)}) is acceptable — returns are modestly compensating for the volatility taken.`);
      else                   lines.push(`Risk-adjusted performance (Sharpe ${_f2(sharpe)}) is strong — returns are well compensated for the risk being taken.`);
    }

    // drawdown line
    if (isBeginner) {
      if (dd > 35)       lines.push(`At its worst, your portfolio dropped ${dd.toFixed(1)}% from its peak — that would have been a very stressful time. The key question is: would you have held on or sold in a panic?`);
      else if (dd > 20)  lines.push(`Your portfolio's biggest dip from its peak was ${dd.toFixed(1)}% — that's pretty normal for stock-heavy portfolios. Markets go up and down!`);
      else if (dd > 0)   lines.push(`Your portfolio has stayed pretty steady — the worst it ever dipped was only ${dd.toFixed(1)}%, which means it's been quite resilient.`);
    } else {
      if (dd > 35)       lines.push(`The worst historical decline was ${dd.toFixed(1)}% — a severe drawdown that would have severely tested most investors' resolve to hold.`);
      else if (dd > 20)  lines.push(`The worst historical decline was ${dd.toFixed(1)}% — moderate and within typical equity market territory.`);
      else if (dd > 0)   lines.push(`The worst historical decline was ${dd.toFixed(1)}% — low, suggesting the portfolio has been relatively resilient.`);
    }
  } else {
    if (_lvl() === 'beginner') {
      lines.push(`We don't have enough price history yet to analyse how your portfolio performs. Once you've added holdings with real ticker symbols, we'll be able to show you how well your money is growing.`);
    } else {
      lines.push(`Risk metrics (Sharpe ratio, VaR, max drawdown, volatility) will appear automatically once your portfolio has holdings with live price data available.`);
    }
  }

  // suggestions
  if (suggestions.length > 0) {
    lines.push(`**Key improvement:** ${suggestions[0]}`);
  }

  // total invested
  if (total > 0) {
    lines.push(`Total invested: £${total.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}.`);
  }

  return lines.join(' ');
}

// future prediction outcomes / what happens when changes in the market/stock occur to the users 
function computeWhatIf(scenario, metrics, holdings) {
  if (!holdings || holdings.length === 0) return { error: 'No holdings found. Add positions to your portfolio first.' };
  if (!metrics?.total_invested)           return { error: 'No portfolio data available yet.' };

  const total  = Number(metrics.total_invested);
  const sharpe = Number(metrics.sharpe_ratio || 0);
  const dd     = Number(metrics.max_drawdown || 0);
  const vol    = Number(metrics.annualised_volatility || 0);
  const ret    = Number(metrics.annualised_return || 0);
  const varVal = Number(metrics.var || 0);
  const numH   = holdings.length;

  if (scenario === 'market_drop10' || scenario === 'market_drop20' || scenario === 'market_drop30') {
    const pct   = scenario === 'market_drop10' ? 0.10 : scenario === 'market_drop20' ? 0.20 : 0.30;
    const label = (pct * 100).toFixed(0) + '%';
    const loss  = total * pct;
    const newVal = total - loss;
    const newSharpe = Math.max(-2, sharpe - pct * 2).toFixed(2);
    const newDD = Math.max(_abs(dd), pct);
    const rec   = ((1 / (1 - newDD) - 1) * 100).toFixed(0);

    return {
      scenario: `If the market drops ${label}`,
      assumption: `Assumes your portfolio has average market sensitivity (beta ≈ 1.0). High-beta tech portfolios would fall more; defensive/low-beta portfolios less.`,
      beginnerAssumption: `This is a rough estimate — some portfolios would drop more, some less, depending on what's in them.`,
      changes: [
        { label: 'Portfolio value',   before: `£${total.toLocaleString('en-GB',{minimumFractionDigits:2})}`, after: `£${newVal.toLocaleString('en-GB',{minimumFractionDigits:2})}`, delta: `−£${loss.toLocaleString('en-GB',{minimumFractionDigits:2})}`,   bad: true  },
        { label: 'Sharpe ratio',      before: _f2(sharpe), after: newSharpe, delta: `${(Number(newSharpe)-sharpe).toFixed(2)}`, bad: true },
        { label: 'Biggest dip ever',  before: _pct(dd),    after: (newDD*100).toFixed(1)+'%', delta: `−${(pct*100).toFixed(0)}pp`, bad: true },
      ],
      insight: `A ${label} market fall would cost approximately £${loss.toLocaleString('en-GB',{minimumFractionDigits:2})}. ${_abs(dd) < pct ? `This would be your portfolio's worst-ever drawdown hence recovery would require a +${rec}% gain.` : `Your portfolio has already survived a worse drawdown of ${(_abs(dd)*100).toFixed(1)}%, so this is within its historical range.`} The critical question: would you hold through this decline without selling? Selling at the bottom locks in losses permanently and means missing the recovery.`,
      beginnerInsight: `If the market dropped ${label}, you'd lose roughly £${loss.toLocaleString('en-GB',{minimumFractionDigits:2})} on paper. ${_abs(dd) < pct ? `To get back to where you are now, you'd need a +${rec}% recovery gain after that.` : `Your portfolio has already survived a bigger dip than this, so it's within the range of what it's been through before.`} The biggest danger here isn't the drop itself — it's the temptation to sell in a panic. Selling when prices are down means you lock in the loss and miss out when prices recover.`,
    };
  }

  if (scenario === 'rebalance_equal') {
    const eqW    = 1 / numH;
    const maxW   = Math.max(...holdings.map(h => Number(h.weight) || 0));
    const topH   = holdings.find(h => Number(h.weight) === maxW);
    const newVol = vol * (maxW > 0.35 ? 0.82 : maxW > 0.2 ? 0.92 : 0.97);
    const newSharpe = newVol > 0 && ret !== 0 ? (ret / newVol).toFixed(2) : _f2(sharpe);

    return {
      scenario: 'If you spread your money equally across all holdings',
      assumption: 'Redistributes all holdings to equal weights. Transaction costs and taxes not modelled.',
      beginnerAssumption: 'This spreads your money evenly across everything you own. Fees and taxes are not included.',
      changes: [
        { label: 'Largest position',  before: _pct(maxW), after: _pct(eqW), delta: `−${((maxW-eqW)*100).toFixed(1)}pp`, bad: false },
        { label: 'Est. volatility',   before: _pct(vol),  after: _pct(newVol), delta: `${((newVol-vol)*100).toFixed(1)}pp`, bad: newVol > vol },
        { label: 'Est Sharpe ratio', before: _f2(sharpe), after: newSharpe, delta: `+${(Number(newSharpe)-sharpe).toFixed(2)}`, bad: Number(newSharpe) < sharpe },
      ],
      insight: `Equal-weighting would reduce ${topH?.symbol || 'your top holding'} from ${_pct(maxW)} to ${_pct(eqW)}. ${maxW > 0.3 ? `Your current concentration above ${_pct(maxW)} is above the recommended 20–25% threshold, rebalancing would meaningfully reduce idiosyncratic risk.` : `Your current weights are reasonably balanced; rebalancing would provide only marginal diversification benefit.`} In practice, rebalancing has transaction costs and potential capital gains tax implications... check these before acting.`,
      beginnerInsight: `Spreading your money equally would cut the amount in ${topH?.symbol || 'your biggest holding'} from ${_pct(maxW)} down to ${_pct(eqW)}. ${maxW > 0.3 ? `Right now you've got a lot riding on one company — rebalancing would mean if that company has a bad run, it hurts less.` : `Your money is already spread fairly evenly, so rebalancing wouldn't make a huge difference.`} Just be aware — moving money around can trigger taxes and fees, so it's worth checking those costs first.`,
    };
  }

  if (scenario === 'add_5pct_cash') {
    const add    = total * 0.05;
    const newTot = total + add;
    const grow10 = (add * Math.pow(1 + Math.max(ret, 0.05), 10));

    return {
      scenario: 'If you topped up your investment by 5%',
      assumption: `Adds £${add.toLocaleString('en-GB',{minimumFractionDigits:2})} proportionally across all holdings (maintaining current weights). Risk profile unchanged.`,
      beginnerAssumption: `Adds £${add.toLocaleString('en-GB',{minimumFractionDigits:2})} split evenly across your holdings. Your level of risk stays the same.`,
      changes: [
        { label: 'Total invested', before: `£${total.toLocaleString('en-GB',{minimumFractionDigits:2})}`, after: `£${newTot.toLocaleString('en-GB',{minimumFractionDigits:2})}`, delta: `+£${add.toLocaleString('en-GB',{minimumFractionDigits:2})}`, bad: false },
        { label: 'Risk level',     before: 'Unchanged', after: 'Unchanged', delta: '—', bad: false },
        { label: 'Est. in 10 yrs', before: '—', after: `£${grow10.toLocaleString('en-GB',{minimumFractionDigits:2})}`, delta: 'compounded', bad: false },
      ],
      insight: `Adding £${add.toLocaleString('en-GB',{minimumFractionDigits:2})} proportionally maintains your exact risk profile. The power of compounding means this additional investment, at your current ${(Math.max(ret,0.05)*100).toFixed(1)}%/yr return, would be worth approximately £${grow10.toLocaleString('en-GB',{minimumFractionDigits:2})} in 10 years. Every additional £1 invested early compounds into significantly more over time... this is the core argument for regular DCA contributions.`,
      beginnerInsight: `Adding an extra £${add.toLocaleString('en-GB',{minimumFractionDigits:2})} doesn't change how risky your portfolio is — it just gives it more fuel. Thanks to compound growth (where your gains earn their own gains), that extra £${add.toLocaleString('en-GB',{minimumFractionDigits:2})} could be worth around £${grow10.toLocaleString('en-GB',{minimumFractionDigits:2})} in 10 years at your current growth rate. The earlier you invest, the longer it has to grow — this is why even small regular top-ups make a big difference over time.`,
    };
  }

  return { error: `Unknown scenario: ${scenario}` };
}

// behavioural analtics 
function analyseBehaviour(trades, holdings, metrics) {
  const insights = [];
  trades = trades || [];

  // 0vertrading
  const now    = Date.now();
  const _30days   = now - 30  * 86400000;
  const _7days    = now - 7   * 86400000;
  const recent = trades.filter(t => new Date(t.ts).getTime() > _30days);
  const week   = trades.filter(t => new Date(t.ts).getTime() > _7days);

  const isBeg = _lvl() === 'beginner';

  if (recent.length > 15) {
    insights.push({ type:'warn', icon:'⚡', title:'High trading frequency',
      text: isBeg
        ? `You've made ${recent.length} trades in the last 30 days — that's a lot! Buying and selling too often usually costs more in fees and tends to lead to worse results. Try asking yourself: am I trading because I have a good reason, or because I'm feeling nervous?`
        : `${recent.length} trades in the last 30 days. Research shows overtrading reduces returns by 1–2%/yr due to costs and poor timing. Ask yourself: were these trades driven by analysis or emotion?`,
      bias: isBeg ? null : 'Overconfidence bias' });
  } else if (week.length > 5) {
    insights.push({ type:'info', icon:'📊', title:'Active week of trading',
      text: isBeg
        ? `You've made ${week.length} trades this week. That's quite active — just make sure each trade is for a reason you'd be happy to explain out loud, not just a gut feeling.`
        : `${week.length} trades this week. Frequent trading isn't bad if driven by analysis, but check whether each trade had a pre-written thesis.`,
      bias: isBeg ? null : 'Possible overconfidence' });
  }

  // concentration (behavioural signal)
  if (holdings?.length > 0) {
    const maxW  = Math.max(...holdings.map(h => Number(h.weight)||0));
    const topH  = holdings.find(h => Number(h.weight) === maxW);
    if (maxW > 0.45) {
      insights.push({ type:'warn', icon:'🎯', title:`Too much in one place: ${topH?.symbol||'one stock'} is ${_pct(maxW)}`,
        text: isBeg
          ? `Nearly half your money is in just one company (${topH?.symbol||'one stock'}). If that company has a bad day — or a bad year — your whole portfolio takes a big hit. Spreading your money across more companies reduces that risk.`
          : `${_pct(maxW)} in a single position may reflect overconfidence in that stock or an anchoring effect (reluctance to reduce a past winner from your holdings). MPT shows this adds uncompensated idiosyncratic risk.`,
        bias: isBeg ? null : 'Overconfidence / anchoring' });
    } else if (maxW > 0.28) {
      insights.push({ type:'info', icon:'⚖️', title:`${topH?.symbol||'Largest holding'} is ${_pct(maxW)} of portfolio`,
        text: isBeg
          ? `More than a quarter of your money is in ${topH?.symbol||'one stock'}. That's not necessarily bad, but it's worth checking — is this intentional, or has it just grown bigger over time without you noticing?`
          : `Above the 20–25% guideline. This may be intentional conviction or simply that the position has grown and you haven't rebalanced...may be worth reviewing.`,
        bias: isBeg ? null : 'Status quo bias' });
    }
  }

  // performance behaviour
  if (_has(metrics?.sharpe_ratio)) {
    const s = Number(metrics.sharpe_ratio);
    if (s < 0) {
      insights.push({ type:'bad', icon:'📉', title:"Returns aren't keeping up with the risk",
        text: isBeg
          ? `Your portfolio is going through a lot of ups and downs, but the overall growth isn't making up for it. This can tempt people to hold on to losing investments hoping they'll recover — but sometimes it's better to cut your losses and reinvest in something healthier.`
          : `Your Sharpe ratio is negative, you are bearing risk without being rewarded. This pattern can cause investors to double down on losing positions hoping for a recovery, rather than rationally reassessing each holding.`,
        bias: isBeg ? null : 'Loss aversion / sunk cost' });
    }
  }

  // selling during drawdown
  const sells = trades.filter(t => t.side === 'sell');
  if (sells.length >= 2 && _has(metrics?.max_drawdown) && _abs(metrics.max_drawdown) > 0.18) {
    insights.push({ type:'info', icon:'😰', title:'Selling when the market dipped',
      text: isBeg
        ? `Your portfolio had some big dips, and you made sell trades during that time. Selling when prices are down locks in the loss — you miss out on the recovery. It's one of the most common and costly investing mistakes. If you're feeling anxious about your portfolio, that's often a sign it's time to review your strategy, not sell.`
        : `Your portfolio experienced a ${(_abs(metrics.max_drawdown)*100).toFixed(1)}% drawdown. Selling during market declines locks in losses and typically means missing the recovery phase which is the most costly outcome in investing. Review whether sell decisions were driven by strategy or discomfort.`,
      bias: isBeg ? null : 'Loss aversion' });
  }

  // no patterns yet
  if (insights.length === 0) {
    if (trades.length === 0) {
      insights.push({ type:'good', icon:'✅', title:'No patterns yet',
        text: isBeg
          ? `Start making trades and we'll keep an eye on your habits — things like whether you're buying and selling too often, or panicking when the market dips. Good habits early on make a huge difference!`
          : `Start paper trading to build a trade history, Halo will analyse for overtrading, loss aversion, and FOMO patterns over time.`,
        bias: null });
    } else {
      insights.push({ type:'good', icon:'✅', title:'Looking good so far!',
        text: isBeg
          ? `Your trading looks calm and measured — no obvious panic selling or overtrading. Keep going and we'll flag anything worth watching as your history builds up.`
          : `Trading activity looks measured. Keep logging decisions in the Investment Diary... it reveals subtle bias patterns that numbers alone miss.`,
        bias: null });
    }
  }

  return insights;
}

// health score gauge
function renderHealthScore(containerId, health) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const { score, grade, colour, reasons, suggestions } = health;
  const isBeg = _lvl() === 'beginner';

  const warn = reasons.filter(r => r.type === 'bad' || r.type === 'warn').slice(0, 2);
  const good = reasons.filter(r => r.type === 'good').slice(0, 1);
  const info = reasons.filter(r => r.type === 'info').slice(0, 1);
  const show = [...warn, ...(warn.length < 2 ? info : []), ...(warn.length < 2 ? good : [])].slice(0, 3);

  // For beginners: strip technicals and replace jargon with easy explanation
  function cleanText(text) {
    if (!isBeg) return text;
    return text
      .replace(/\(Sharpe[\s\d.\-]+\)/gi, '')
      .replace(/\bSharpe\s[\d.\-]+\s?—\s?/gi, '')
      .replace(/\bMPT shows this adds uncompensated idiosyncratic risk\b/gi, 'This means one bad company event could hurt your whole portfolio')
      .replace(/\bidiosyncratic risk\b/gi, 'concentration risk')
      .replace(/\bannualised\b/gi, 'yearly')
      .replace(/\bvolatility\b/gi, 'ups and downs')
      .replace(/\bpeak-to-trough\b/gi, 'biggest dip')
      .replace(/\bmax drawdown\b/gi, 'biggest dip')
      .replace(/\bMax drawdown\b/gi, 'Biggest dip')
      .replace(/\b→\s*recovery needs \+[\d]+%\b/gi, '')
      .replace(/\bRecovery needs \+[\d]+%\./gi, '')
      .trim();
  }

  // grade label in plain English for beginners
  const gradeLabel = isBeg ? {
    'A': '🌟 Excellent — your portfolio is in great shape!',
    'B': '👍 Good — a few things to tune up',
    'C': '🟡 Fair — some areas need attention',
    'D': '⚠️ Needs work — worth reviewing soon',
    'F': '🔴 Struggling — consider getting some help',
  }[grade] || grade : grade;

  const improveLabel = isBeg ? '💡 Try this:' : 'Improve:';

  el.innerHTML = `
    <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
      <div style="text-align:center;flex-shrink:0;">
        <div style="width:72px;height:72px;border-radius:50%;border:5px solid ${colour};
          display:flex;align-items:center;justify-content:center;flex-direction:column;background:#fff;">
          <span style="font-size:24px;font-weight:700;color:${colour};font-family:'DM Sans',sans-serif;line-height:1;">${score}</span>
          <span style="font-size:10px;color:${colour};font-weight:600;font-family:'DM Sans',sans-serif;">/100</span>
        </div>
        <div style="margin-top:5px;font-size:${isBeg?'11':'20'}px;font-weight:700;color:${colour};font-family:'DM Sans',sans-serif;line-height:1.3;">${gradeLabel}</div>
      </div>
      <div style="flex:1;min-width:160px;">
        ${show.map(r => {
          const ic = r.type==='bad'?'✕':r.type==='warn'?'⚠':r.type==='good'?'✓':'ℹ';
          const cl = r.type==='bad'?'#dc2626':r.type==='warn'?'#d97706':r.type==='good'?'#16a34a':'#0284c7';
          return `<div style="display:flex;gap:7px;align-items:flex-start;margin-bottom:6px;">
            <span style="color:${cl};font-size:12px;flex-shrink:0;margin-top:1px;">${ic}</span>
            <span style="font-size:12px;color:#2d1f1a;font-family:'DM Sans',sans-serif;line-height:1.5;">${cleanText(r.text)}</span>
          </div>`;
        }).join('')}
        ${suggestions.length ? `
          <div style="margin-top:6px;padding:8px 10px;background:#fff;border-radius:8px;border-left:3px solid ${colour};">
            <span style="font-size:11px;font-weight:700;color:${colour};font-family:'DM Sans',sans-serif;text-transform:uppercase;letter-spacing:0.06em;">${improveLabel} </span>
            <span style="font-size:11px;color:#555;font-family:'DM Sans',sans-serif;line-height:1.5;">${cleanText(suggestions[0])}</span>
          </div>` : ''}
      </div>
    </div>`;
}

// whatif results
function renderWhatIf(containerId, result) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (result.error) {
    el.innerHTML = `<p style="color:#888;font-family:'DM Sans',sans-serif;font-size:13px;">${result.error}</p>`;
    return;
  }

  const isBeg = _lvl() === 'beginner';
  // beginners: hide rows that are pure jargon (Sharpe ratio, Est Sharpe ratio)
  const shownChanges = isBeg
    ? result.changes.filter(c => !c.label.toLowerCase().includes('sharpe') && !c.label.toLowerCase().includes('volatility'))
    : result.changes;

  // beginners get a simpler assumption line
  const assumptionText = isBeg
    ? (result.beginnerAssumption || result.assumption.replace(/beta[\s≈\d.]+/gi,'').replace(/idiosyncratic/gi,'').replace(/MPT/gi,''))
    : result.assumption;

  // pick insight text based on level
  const insightText = isBeg && result.beginnerInsight ? result.beginnerInsight : result.insight;

  el.innerHTML = `
    <div style="font-family:'DM Sans',sans-serif;">
      <div style="font-size:13px;font-weight:600;color:#2d1f1a;margin-bottom:3px;">${result.scenario}</div>
      <div style="font-size:11px;color:#888;margin-bottom:12px;line-height:1.5;">${assumptionText}</div>
      <table style="width:100%;border-collapse:collapse;margin-bottom:12px;">
        <thead><tr style="border-bottom:1.5px solid #e5e5e5;">
          <th style="text-align:left;font-size:11px;color:#888;font-weight:500;padding:3px 0;">${isBeg ? 'What changes' : 'Metric'}</th>
          <th style="text-align:right;font-size:11px;color:#888;font-weight:500;padding:3px 6px;">${isBeg ? 'Now' : 'Before'}</th>
          <th style="text-align:right;font-size:11px;color:#888;font-weight:500;padding:3px 6px;">${isBeg ? 'Would become' : 'After'}</th>
          <th style="text-align:right;font-size:11px;color:#888;font-weight:500;padding:3px 0;">Change</th>
        </tr></thead>
        <tbody>
          ${shownChanges.map(c => `<tr style="border-bottom:1px solid #f0f0f0;">
            <td style="font-size:12px;padding:6px 0;color:#2d1f1a;">${c.label}</td>
            <td style="text-align:right;font-size:12px;padding:6px;color:#666;">${c.before}</td>
            <td style="text-align:right;font-size:12px;padding:6px;font-weight:600;color:${c.bad?'#dc2626':'#16a34a'};">${c.after}</td>
            <td style="text-align:right;font-size:12px;padding:6px 0;color:${c.bad?'#dc2626':'#16a34a'};">${c.delta}</td>
          </tr>`).join('')}
        </tbody>
      </table>
      <div style="background:#fff;border-radius:9px;padding:10px 12px;font-size:12px;line-height:1.65;color:#2d1f1a;border-left:3px solid #c9837a;">
        💡 ${insightText}
      </div>
    </div>`;
}

// behavioural insights
function renderBehaviouralInsights(containerId, insights) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const pal = { good:'#16a34a', warn:'#d97706', bad:'#dc2626', info:'#0284c7' };
  const bg  = { good:'#f0fdf4', warn:'#fffbeb', bad:'#fef2f2', info:'#eff6ff' };
  el.innerHTML = insights.map(i => `
    <div style="background:${bg[i.type]||'#f9f9f9'};border-radius:10px;padding:11px 13px;margin-bottom:9px;
      border-left:3px solid ${pal[i.type]||'#ccc'};">
      <div style="display:flex;align-items:center;gap:7px;margin-bottom:4px;">
        <span style="font-size:14px;">${i.icon}</span>
        <span style="font-size:12px;font-weight:600;color:#2d1f1a;font-family:'DM Sans',sans-serif;">${i.title}</span>
        ${i.bias ? `<span style="margin-left:auto;font-size:10px;font-weight:600;color:${pal[i.type]};
          border:1px solid ${pal[i.type]};border-radius:20px;padding:1px 7px;font-family:'DM Sans',sans-serif;
          white-space:nowrap;">${i.bias}</span>` : ''}
      </div>
      <p style="font-size:12px;color:#555;margin:0;line-height:1.6;font-family:'DM Sans',sans-serif;">${i.text}</p>
    </div>`).join('');
}

// attachs explainable tooltip to a metric
function attachMetricTooltip(elementId, metricKey, value) {
  const el = document.getElementById(elementId);
  if (!el || !METRIC_EXPLAIN[metricKey]) return;
  const explanation = METRIC_EXPLAIN[metricKey](value);
  el.style.cursor = 'help';

  el.addEventListener('mouseenter', function() {
    document.getElementById('metric-tooltip')?.remove();
    const tip = document.createElement('div');
    tip.id = 'metric-tooltip';
    Object.assign(tip.style, {
      position:'fixed', zIndex:'9999', maxWidth:'300px',
      background:'#2d1f1a', color:'#fff',
      fontFamily:"'DM Sans',sans-serif", fontSize:'12px', lineHeight:'1.6',
      padding:'10px 13px', borderRadius:'11px',
      boxShadow:'0 8px 24px rgba(0,0,0,0.18)', pointerEvents:'none',
    });
    tip.textContent = explanation;
    document.body.appendChild(tip);
    const r = el.getBoundingClientRect();
    tip.style.left = Math.min(r.left, window.innerWidth - 320) + 'px';
    tip.style.top  = (r.bottom + 6) + 'px';
  });
  el.addEventListener('mouseleave', () => document.getElementById('metric-tooltip')?.remove());
}

// global ex
window.FlyingFundsInsights = {
  computeHealthScore,
  PortfolioSummary,
  computeWhatIf,
  analyseBehaviour,
  renderHealthScore,
  renderWhatIf,
  renderBehaviouralInsights,
  attachMetricTooltip,
  METRIC_EXPLAIN,
};