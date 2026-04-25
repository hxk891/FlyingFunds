// ============================================================================
// halo.js — Halo NLP Finance Chatbot Engine
// Loaded by base.html via: <script src="/static/js/halo.js"></script>
// Zero external dependencies. Pure browser JavaScript.
// NLP pipeline: spell correction → entity extraction → TF-IDF cosine
//   similarity → intent detection → conversation memory follow-ups
// ============================================================================

const HALO = (() => {

    // ── Stop words (stripped before TF-IDF scoring) ───────────────────────────
    const STOP = new Set([
      'a','an','the','is','it','in','on','of','to','for','and','or','but','not',
      'do','does','did','what','when','where','who','how','why','can','could',
      'would','should','will','i','me','my','we','you','your','this','that',
      'these','those','am','are','was','were','be','been','have','has','had',
      'about','with','from','at','by','as','if','so','then','than','just','also',
      'very','really','please','tell','explain','describe','give','help','want',
      'know','understand','show','get','its','our','their','there','here','some',
      'any','all','more','much','mean','means','like','think'
    ]);
  
    // ── Lightweight stemmer ────────────────────────────────────────────────────
    function stem(w) {
      if (w.length <= 4) return w;
      return w
        .replace(/ational$/, 'ate').replace(/tional$/, 'tion')
        .replace(/enci$/, 'ence').replace(/anci$/, 'ance')
        .replace(/iser$|izer$/, 'ise').replace(/alism$/, 'al')
        .replace(/iveness$/, 'ive').replace(/fulness$/, 'ful')
        .replace(/ousness$/, 'ous').replace(/aliti$/, 'al')
        .replace(/iviti$/, 'ive').replace(/biliti$/, 'ble')
        .replace(/ating$|ation$|ations$/, 'ate')
        .replace(/ings?$/, '').replace(/edly$/, '')
        .replace(/ness$/, '').replace(/ment$|ments$/, '')
        .replace(/ers?$/, '').replace(/ies$/, 'y')
        .replace(/s$/, '');
    }
  
    function tokenise(text) {
      return text.toLowerCase()
        .replace(/[^a-z0-9\s]/g, ' ')
        .split(/\s+/)
        .filter(t => t.length > 2 && !STOP.has(t))
        .map(stem);
    }
  
    // ── Spell correction ───────────────────────────────────────────────────────
    const FIXES = {
      'sharpi':'sharpe','sharpee':'sharpe','markwitz':'markowitz',
      'markovitz':'markowitz','behaviorial':'behavioural','behavioral':'behavioural',
      'valueatrisk':'var','diversfy':'diversify','diversifcation':'diversification',
      'volatilty':'volatility','volitility':'volatility',
      'portfoilio':'portfolio','portfolo':'portfolio',
      'intrest':'interest','inflaton':'inflation','drawdonw':'drawdown'
    };
  
    function correct(text) {
      let t = text.toLowerCase();
      Object.entries(FIXES).forEach(([w, r]) => { t = t.replace(new RegExp(w, 'gi'), r); });
      return t;
    }
  
    // ── Knowledge base ─────────────────────────────────────────────────────────
    const KB = [
      {
        id: 'greeting',
        keywords: ['hello','hi','hey','morning','afternoon','evening'],
        variants: ['hello there','hi how are you','hey halo','good morning','hi there'],
        response: () => ["Hi! I'm **Halo**, your finance tutor on FlyingFunds. Ask me about portfolio theory, risk metrics, market concepts, or how to use the platform. What would you like to learn?",
          "Hello! I can explain anything from the Sharpe ratio to behavioural finance. What's on your mind?"][Math.random()>.5?1:0]
      },
      {
        id: 'thanks',
        keywords: ['thanks','thank','cheers','great','awesome','perfect','helpful'],
        variants: ['thanks','thank you','that was helpful','great answer'],
        response: () => ["You're welcome! Ask me anything else — I'm always here.", "Happy to help! Any more questions?"][Math.random()>.5?1:0]
      },
      {
        id: 'who_are_you',
        keywords: ['who','halo','name','chatbot','bot','assistant','what are you','how do you work'],
        variants: ['who are you','what are you','what is halo','tell me about yourself','are you an ai','what can you do'],
        response: "I'm **Halo** — the built-in finance tutor for FlyingFunds. I run entirely in your browser with no external API.\n\nI can explain concepts like CAPM, Sharpe ratio, VaR, behavioural finance, Modern Portfolio Theory, and more. I also know every feature of FlyingFunds. What would you like to explore?"
      },
      {
        id: 'mpt',
        keywords: ['markowitz','modern portfolio theory','mpt','portfolio theory','mean variance'],
        variants: [
          'what is modern portfolio theory','explain markowitz','what is mpt',
          'portfolio theory explained','how does diversification work mathematically',
          'what did markowitz discover','mean variance optimisation',
          'how to build an optimal portfolio','what is portfolio construction',
          'why does combining stocks reduce risk'
        ],
        response: "**Modern Portfolio Theory (Markowitz, 1952)** changed investing forever. Before Markowitz, people evaluated stocks in isolation. He proved what matters is how securities interact *as a portfolio*.\n\n**Core insight:** Combining assets with imperfect correlation reduces portfolio volatility without reducing expected return — the only genuine free lunch in finance.\n\n**Portfolio variance formula:**\nσ²_p = Σᵢ Σⱼ wᵢwⱼσᵢⱼ\n(weights × covariance between each pair of assets)\n\n**The Efficient Frontier:** The curve of portfolios that maximise expected return for each level of risk. Any portfolio below it is suboptimal — you're taking more risk than necessary.\n\nWant me to go deeper on the Efficient Frontier, or how CAPM built on this work?"
      },
      {
        id: 'efficient_frontier',
        keywords: ['efficient frontier','optimal portfolio','frontier','risk return curve','best portfolio'],
        variants: [
          'what is the efficient frontier','explain efficient frontier',
          'how do you find the optimal portfolio','what does the efficient frontier show',
          'how is the frontier calculated','how do i know if my portfolio is optimal',
          'where does my portfolio sit on the frontier'
        ],
        response: "The **Efficient Frontier** is a curve on a risk-return chart. Every point represents a portfolio that is mathematically optimal — no other portfolio offers higher return for the same risk.\n\n**How it's built:**\n1. Take your holdings and their historical return correlations\n2. Run thousands of random weight combinations (Monte Carlo)\n3. For each, compute expected return and standard deviation\n4. The upper-left boundary of all those points is the frontier\n\n**Reading it:**\n• Portfolio **below** the frontier → suboptimal (too much risk for the return)\n• Portfolio **on** the frontier → optimal for its risk level\n\nA future FlyingFunds update will plot your portfolio against the frontier so you can see exactly how close to optimal you are."
      },
      {
        id: 'capm',
        keywords: ['capm','capital asset pricing','systematic risk','expected return','market risk premium','equity risk premium'],
        variants: [
          'what is capm','explain capital asset pricing model','how does capm work',
          'what is systematic risk','how do you calculate expected return',
          'capm formula','what is the equity risk premium','what is market risk',
          'how do i know if a stock is worth the risk','how much return should i expect'
        ],
        response: "**CAPM (Capital Asset Pricing Model)** by Sharpe (1964) answers: how much return should you expect for a given level of market risk?\n\n**Formula:**\nE(Rᵢ) = Rf + βᵢ × (E(Rm) − Rf)\n\n• **Rf** = risk-free rate (UK gilt ~4.5%)\n• **βᵢ** = beta of the asset\n• **E(Rm) − Rf** = market risk premium (~5–6% historically)\n\n**The key principle:** Only *systematic* (market-wide) risk deserves compensation. Company-specific risk can be diversified away for free — the market won't pay you extra for bearing it.\n\n**Beta tells you market sensitivity:**\n• β = 1.0 → moves with the market\n• β = 1.5 → 50% more volatile than market\n• β = 0.5 → half as sensitive (utilities, staples)\n\nWant me to explain the Sharpe ratio or Jensen's alpha — both built directly on CAPM?"
      },
      {
        id: 'beta',
        keywords: ['beta','market beta','systematic sensitivity','stock beta','what does beta mean'],
        variants: [
          'what is beta','what does beta mean','how do you calculate beta',
          'what is a high beta stock','what is low beta stock','what is negative beta',
          'how sensitive is my portfolio to the market','beta explained in simple terms'
        ],
        response: "**Beta (β)** measures how much an asset moves relative to the overall market — the key input to CAPM.\n\n• **β = 1.0** → moves exactly with the market\n• **β > 1.0** → more volatile than market (tech stocks: typically 1.2–1.8)\n• **β < 1.0** → less sensitive (utilities, healthcare: 0.3–0.7)\n• **β < 0** → tends to move *against* the market (gold sometimes)\n\n**Example:** β = 1.4 means if the market rises 10%, this stock is expected to rise 14%. If the market falls 10%, the stock falls 14%. That extra exposure is compensated by higher expected return in CAPM.\n\n**Important:** Beta only captures systematic risk. Company-specific events (scandals, product failures) are idiosyncratic risk — not captured by beta, and not compensated by the market."
      },
      {
        id: 'alpha',
        keywords: ['alpha','jensens alpha','excess return','outperform benchmark','beat benchmark','active return'],
        variants: [
          'what is alpha','what is jensens alpha','how do i know if im outperforming',
          'what is excess return','am i beating the market',
          'how do i measure fund performance','what does alpha mean in investing'
        ],
        response: "**Jensen's Alpha** measures whether your portfolio outperforms what CAPM predicts given its beta.\n\n**Formula:**\nα = Rp − [Rf + β(Rm − Rf)]\n\n• **α > 0** → generating returns above what your beta-level risk deserves — skill or luck\n• **α = 0** → returns match CAPM prediction — no value added\n• **α < 0** → underperforming the risk-adjusted benchmark — a passive index fund would have done better\n\n**The uncomfortable truth:** Most actively managed funds produce negative alpha net of fees over 10+ year periods. That's the core empirical case for passive index investing."
      },
      {
        id: 'sharpe',
        keywords: ['sharpe','risk adjusted return','reward variability','sharpe ratio','performance measure','return per unit risk'],
        variants: [
          'what is the sharpe ratio','explain sharpe ratio','how do i interpret my sharpe ratio',
          'sharpe ratio formula','what is a good sharpe ratio','what does my sharpe ratio mean',
          'how much return per unit of risk','risk adjusted performance',
          'is my sharpe ratio good','my sharpe ratio is low what does that mean',
          'how do i improve my sharpe ratio','what sharpe ratio should i aim for'
        ],
        response: "The **Sharpe Ratio** is the most widely used single measure of risk-adjusted performance.\n\n**Formula:** S = (Rp − Rf) / σp\n• Rp = annualised portfolio return\n• Rf = risk-free rate (often simplified to 0)\n• σp = annualised volatility\n\n**Benchmarks:**\n• Below 0 → underperforming the risk-free rate\n• 0–0.5 → poor — risk not adequately rewarded\n• 0.5–1.0 → acceptable\n• 1.0–2.0 → good (most professional funds land here)\n• Above 2.0 → excellent (or check your data)\n\nYour Sharpe ratio is on the **Analytics page** in FlyingFunds.\n\n**Key limitation:** Treats upside and downside volatility equally. The **Sortino ratio** fixes this by using only downside deviation in the denominator."
      },
      {
        id: 'sortino',
        keywords: ['sortino','downside deviation','downside volatility','sortino ratio'],
        variants: [
          'what is sortino ratio','sortino vs sharpe','difference between sharpe and sortino',
          'what is downside deviation','downside risk measure','when to use sortino'
        ],
        response: "The **Sortino Ratio** refines the Sharpe ratio by only penalising *downside* volatility.\n\n**Formula:** Sortino = (Rp − Rf) / σ_downside\n\nThe denominator uses only the standard deviation of returns below the target. Upside swings are ignored.\n\n**Why it matters:** A stock that occasionally surges looks risky under Sharpe. The Sortino ratio correctly ignores upside variability and only measures loss volatility.\n\n**Rule of thumb:** Sortino noticeably higher than Sharpe → your volatility is mostly upside (good sign). Similar values → symmetric volatility."
      },
      {
        id: 'var',
        keywords: ['var','value at risk','worst loss','5th percentile','how bad can losses get','daily loss limit'],
        variants: [
          'what is var','what is value at risk','explain var','how is var calculated',
          'what does var tell you','what is 95% var','how do i read my var',
          'what is the worst i could lose','how bad can my losses get',
          'what does my var mean','var on my portfolio'
        ],
        response: "**Value at Risk (VaR)** answers: how bad could my losses get on a typical bad day?\n\n**At 95% confidence, 1-day horizon:** On 95 out of 100 trading days, losses will not exceed VaR. On 5 out of 100, they will be worse.\n\nFlyingFunds uses **Historical VaR** — the 5th percentile of your actual daily return distribution, making no assumptions about return shapes.\n\n**Example:** VaR = −2.1% on a £10,000 portfolio → expect to lose no more than £210 on 95% of days.\n\n**Critical limitation:** VaR says nothing about *how bad* losses are on those 5% of bad days. That's where CVaR comes in.\n\nYour VaR is on the **Analytics page**."
      },
      {
        id: 'cvar',
        keywords: ['cvar','expected shortfall','conditional var','tail risk','average worst case loss'],
        variants: [
          'what is cvar','explain expected shortfall','conditional value at risk explained',
          'cvar vs var','what happens on my worst days',
          'tail risk explained','why is cvar better than var','what is expected shortfall'
        ],
        response: "**CVaR (Conditional Value at Risk)**, also called Expected Shortfall, measures the *average loss on your worst days* — the days that actually breach VaR.\n\n**Formula:** CVaR = −E[R | R ≤ VaR_threshold]\n\n**Example:** VaR = −2.1%, CVaR = −3.4%\n→ On your worst 5% of days, you lose an average of 3.4%, not just 2.1%\n→ CVaR is always ≥ VaR in absolute magnitude\n\n**Why CVaR is superior to VaR:**\n• Measures tail *severity* not just the threshold\n• Mathematically coherent (subadditive)\n• Required by Basel III for bank capital calculations\n• The 2008 crisis exposed VaR's failure — CVaR directly addresses it\n\nBoth metrics are on your FlyingFunds **Analytics page**."
      },
      {
        id: 'drawdown',
        keywords: ['drawdown','max drawdown','peak trough','underwater period','worst decline','recovery time'],
        variants: [
          'what is max drawdown','explain drawdown','what is peak to trough',
          'how do i read a drawdown chart','worst portfolio decline',
          'maximum drawdown formula','how long to recover from drawdown',
          'what does drawdown mean for my portfolio','how do i see my drawdown'
        ],
        response: "**Max Drawdown** is the worst peak-to-trough decline in your portfolio before a new high is reached.\n\n**Formula:** Max DD = (Trough − Peak) / Peak\n\n**Example:** Portfolio peaks at £12,000, falls to £8,400 → Max DD = **−30%**\n\n**Why the recovery maths is so important:**\n• −20% drawdown → needs +25% to break even\n• −30% drawdown → needs +43% to break even\n• −50% drawdown → needs +100% to break even\n\nThis asymmetry is why controlling downside matters. A strategy with moderate returns but small drawdowns often beats a high-return/high-drawdown strategy over a full cycle — because investors panic-sell at the trough.\n\nSee your drawdown chart on the **Dashboard** by switching to Drawdown mode on the performance chart."
      },
      {
        id: 'volatility',
        keywords: ['volatility','standard deviation','annualised vol','vix','how volatile','portfolio fluctuation'],
        variants: [
          'what is volatility','what does volatility mean','how is volatility calculated',
          'what is annualised volatility','what is a good volatility','how do you annualise returns',
          'what is the vix','high vs low volatility','is my portfolio too volatile','what causes volatility'
        ],
        response: "**Volatility** is the annualised standard deviation of daily returns — measuring how much your portfolio bounces around.\n\n**Calculation:**\n1. Daily returns: r_t = (P_t − P_{t−1}) / P_{t−1}\n2. Standard deviation of all daily returns\n3. Annualise: σ_annual = σ_daily × √252\n\n**Typical ranges:**\n• Global equity index (S&P 500): 15–20%/year\n• Individual growth stocks: 25–60%\n• Bonds/gilts: 5–10%\n• Well-diversified portfolio: 10–18%\n\n**The VIX** is the market's real-time estimate of 30-day S&P 500 volatility from options prices. Called the 'fear index' — spikes during stress (COVID: 85, 2008: 90).\n\n**Key point:** High volatility isn't inherently bad — it depends whether you're compensated for it. That's what the Sharpe ratio measures."
      },
      {
        id: 'diversification',
        keywords: ['diversif','correlation','covariance','uncorrelated assets','spread risk','how many stocks needed'],
        variants: [
          'what is diversification','why should i diversify','how many stocks do i need',
          'what is correlation in finance','does diversification reduce risk',
          'how does diversification work','eggs in one basket analogy',
          'how do i diversify my portfolio','am i too concentrated','is my portfolio diversified'
        ],
        response: "**Diversification** is reducing portfolio risk by combining assets with imperfect correlation — without reducing expected return. It is the only genuine free lunch in finance (Markowitz proved this).\n\n**Why it works:**\nPortfolio variance = Σᵢ Σⱼ wᵢwⱼσᵢⱼ\nWhen correlations are below 1.0, covariance terms partially cancel, reducing total portfolio variance.\n\n**How many stocks?** Around 20–30 genuinely uncorrelated stocks eliminates most idiosyncratic risk. Beyond that, you're mostly adding systematic (market) risk which can't be diversified away.\n\n**Common mistakes:**\n• 20 tech stocks — all highly correlated, NOT diversified\n• US-only portfolio — concentrated geographic risk\n• All equities — no asset class diversification\n\n**Rule of thumb:** No single holding above 20–25%. Your allocation chart in FlyingFunds shows your current distribution."
      },
      {
        id: 'emh',
        keywords: ['efficient market','emh','random walk','market efficiency','fama','beat market','stock price information'],
        variants: [
          'what is the efficient markets hypothesis','can you beat the market',
          'is the market efficient','what is a random walk','emh explained',
          'what are the three forms of emh','does technical analysis work',
          'does fundamental analysis work','why cant most funds beat the index',
          'should i try to pick stocks','is it possible to consistently outperform'
        ],
        response: "The **Efficient Markets Hypothesis (EMH)** by Eugene Fama (1970) claims market prices fully reflect all available information, making it impossible to *consistently* beat the market.\n\n**Three forms:**\n• **Weak:** Prices reflect all historical price data → technical analysis can't generate consistent alpha\n• **Semi-strong:** Prices reflect all public information → fundamental analysis can't consistently outperform\n• **Strong:** Prices reflect *all* information including private → even insider trading doesn't help (rejected — it's illegal because it works)\n\n**The evidence:**\n• 80–90% of active managers underperform their benchmark net of fees over 15 years\n• Past outperformance doesn't predict future outperformance\n\n**But anomalies persist:** Momentum, value premium, size effect challenge pure EMH.\n\n**Practical implication:** For most investors, a low-cost passive index fund is very hard to beat over 20+ years."
      },
      {
        id: 'active_passive',
        keywords: ['active investing','passive investing','index fund etf','stock picking','closet indexing','passive strategy'],
        variants: [
          'should i invest actively or passively','active vs passive investing',
          'is index investing better','are etfs better than picking stocks',
          'what is passive investing','why do active funds underperform',
          'should i just buy an index fund','is stock picking worth it',
          'what is a factor etf','smart beta explained'
        ],
        response: "**Active vs Passive** — the evidence leans clearly one way.\n\n**Active:** Picking stocks or timing markets to beat the index. Higher fees, requires research and skill.\n\n**Passive:** Buying a broad market index fund (e.g. Vanguard FTSE Global All Cap), accepting market returns minus minimal fees (~0.1–0.2%/year).\n\n**The evidence (SPIVA reports, Fama & French):**\n• After fees, 80–90% of active equity managers underperform over 15 years\n• Past outperformance does not predict future outperformance\n• Higher-fee funds statistically underperform lower-fee funds\n\n**Why active often fails:**\n• Markets are fairly efficient — genuine mispricings are quickly corrected\n• Fees compound into large drags over decades\n• Many managers 'closet-index' to protect their career from a bad year\n\n**Where active can work:** Small-cap/emerging markets (less coverage), deep specialist expertise, factor/smart-beta strategies.\n\n**Bottom line:** Low-cost global index fund as the core. Add complexity only if you have genuine edge."
      },
      {
        id: 'behavioural',
        keywords: ['behavioural finance','behavioral','psychology investing','kahneman','tversky','prospect theory','cognitive bias'],
        variants: [
          'what is behavioural finance','explain prospect theory',
          'how does psychology affect investing','why do investors make bad decisions',
          'what are cognitive biases in finance','behavioural economics investing',
          'why are investors irrational'
        ],
        response: "**Behavioural Finance** studies how psychology drives financial decisions — and markets — away from the rational efficiency that classical models assume.\n\n**Prospect Theory (Kahneman & Tversky, 1979):**\n• People are **loss-averse**: losses feel ~2× more painful than equivalent gains feel good\n• People evaluate outcomes relative to a **reference point** (e.g. purchase price), not in absolute terms\n• People are risk-averse in the domain of gains but risk-seeking in the domain of losses\n\n**Key market implications:**\n• **Disposition effect:** Selling winners too early, holding losers too long\n• **Momentum:** Investors underreact initially, then overreact — creating persistent price trends\n• **Bubbles and crashes:** Herding, overconfidence, and FOMO create prices disconnected from value\n\nThe **Investment Diary** in FlyingFunds was designed around this research — logging your emotional state when trading helps reveal bias patterns over time.\n\nWant me to explain a specific bias — loss aversion, overconfidence, anchoring, or herding?"
      },
      {
        id: 'loss_aversion',
        keywords: ['loss aversion','loss averse','disposition effect','hold losers too long','sell winners too early'],
        variants: [
          'what is loss aversion','why do i hold losing stocks too long',
          'what is the disposition effect','why do i sell winners too early',
          'how does loss aversion affect my portfolio','why do losses hurt more than gains feel good',
          'how do i stop holding losers','dealing with loss aversion'
        ],
        response: "**Loss aversion** (Kahneman & Tversky): losses feel roughly **twice as painful** as equivalent gains feel pleasurable — hard-wired human psychology, not a rational calculation.\n\n**How it shows up in portfolios:**\n\n**The Disposition Effect:** Selling winning stocks too early (locking in pleasure) and holding losers too long (avoiding the pain of realising a loss). This is the *opposite* of optimal — 'cut losses, let winners run.'\n\n**Panic selling at bottoms:** When accumulated losses feel unbearable, many investors sell at exactly the wrong moment, turning temporary losses into permanent ones.\n\n**How to counteract it:**\n• Set exit rules *before* you buy (e.g. 'I'll sell if it falls 20% from entry')\n• Focus on total portfolio return, not individual position P&L\n• Ask: 'Would I buy this today at the current price?' If no — why hold it?\n• Use your Investment Diary to log reasoning and review it after 3 months"
      },
      {
        id: 'overconfidence',
        keywords: ['overconfidence','confirmation bias','trade too much','illusion of control','dunning kruger investing'],
        variants: [
          'what is overconfidence bias','why do i trade too much',
          'what is confirmation bias in investing','dunning kruger effect investing',
          'why do investors think they can beat the market',
          'am i overconfident as an investor','how overconfidence hurts returns'
        ],
        response: "**Overconfidence bias** is one of the most costly investor biases. Research shows individual investors consistently overestimate their ability to pick stocks and time the market.\n\n**Effects:**\n• **Excessive trading:** Overconfident investors trade ~40% more — each trade has costs, and frequent trading typically destroys value\n• **Underdiversification:** Taking concentrated bets on 'sure things'\n• **Underestimating downside:** Not believing bad outcomes can happen to you\n\n**Confirmation bias** (closely linked): Seeking information that confirms your view and dismissing contradictory evidence.\n\n**The Dunning-Kruger effect:** Beginners often show the highest confidence — they don't know what they don't know. As you learn more finance theory, you typically become *more* humble. That humility is a good sign.\n\n**The calibration test:** Write down predictions with prices and timelines. Track actual vs predicted outcomes. Most investors discover they were poorly calibrated."
      },
      {
        id: 'anchoring',
        keywords: ['anchoring bias','anchor reference point','purchase price fixation','52 week high anchor'],
        variants: [
          'what is anchoring bias','what is anchoring in investing',
          'why do i focus on my purchase price','how does anchoring affect decisions',
          'why cant i sell below what i paid','what is price anchoring in stocks'
        ],
        response: "**Anchoring bias:** Fixating on an irrelevant reference point when making investment decisions.\n\n**The classic example:** You bought at £50. It falls to £32. You wait until it 'gets back to £50' — even though your entry price has zero bearing on future value.\n\nThe correct question is always: **'Would I buy this today at £32 given what I know now?'** If no — sell. The original price is irrelevant.\n\n**Other common anchors:**\n• Measuring cheapness vs 52-week high rather than intrinsic value\n• Setting targets at round numbers without valuation support\n• Refusing to average down because it 'admits' the original decision was wrong\n\n**The fix:** Write your investment thesis before buying. If the thesis changes, your target should too — not your entry price."
      },
      {
        id: 'herding',
        keywords: ['herding','fomo investing','following the crowd','asset bubble cause','social proof investing'],
        variants: [
          'what is herding in finance','what is fomo investing',
          'why do investors follow the crowd','what causes asset bubbles',
          'why do people buy at market tops','social proof in investing',
          'meme stock bubble explained','crypto bubble explained'
        ],
        response: "**Herding** means following the crowd rather than your own analysis — a primary driver of asset bubbles and crashes.\n\n**Why it happens:**\n• **Social proof:** If many people are buying, it feels validated\n• **Career risk (fund managers):** Being wrong alongside everyone is survivable; being wrong alone is not\n• **FOMO:** Watching an asset rise while not holding creates intense pressure to buy — usually near the peak\n\n**Historical examples:** Dot-com bubble (1999–2000), US housing (2004–2007), meme stocks (2021), crypto peaks (2017, 2021). Each involved prices disconnecting from fundamentals via herding.\n\n**How to protect yourself:**\n• Have a written thesis for *why* you're buying *before* you buy\n• 'Everyone is buying it' is a warning sign, not a thesis\n• Use the watchlist to observe without buying impulsively"
      },
      {
        id: 'compounding',
        keywords: ['compounding','compound interest','compound return','rule of 72','time in market','eighth wonder'],
        variants: [
          'what is compounding','explain compound interest','how does compounding work',
          'rule of 72','why is starting early important','how long to double money',
          'power of compounding','why invest early rather than later'
        ],
        response: "**Compounding** is earning returns on your previous returns — and over long periods, the effect is extraordinary.\n\n**Example: £10,000 at 8%/year:**\n• 10 years → £21,589\n• 20 years → £46,610\n• 30 years → £100,627\n\nThe last 10 years produce more growth than the first 20 combined. Starting a decade earlier often matters more than the rate of return.\n\n**The Rule of 72:** Divide 72 by annual return to estimate years to double:\n• 6% → 12 years | 8% → 9 years | 12% → 6 years\n\n**The enemies of compounding:**\n• **Fees:** A 1% annual fee on £100,000 costs ~£28,000 over 20 years vs 0% fees\n• **Selling at lows:** Withdrawing capital at market bottoms permanently removes it from future compounding\n• **Tax drag:** Repeatedly realising gains interrupts the cycle"
      },
      {
        id: 'dca',
        keywords: ['dollar cost averaging','dca','regular investing','invest monthly','drip feed investment'],
        variants: [
          'what is dollar cost averaging','should i invest lump sum or monthly',
          'what is dca','how does regular investing work',
          'is it better to invest all at once or spread it','drip feed investing',
          'investing fixed amount every month','monthly contribution strategy'
        ],
        response: "**Dollar Cost Averaging (DCA)** means investing a fixed amount at regular intervals regardless of market conditions.\n\n**How it works:**\n• High prices → fixed amount buys fewer shares\n• Low prices → fixed amount buys more shares\n• Result: average cost per share is naturally below the average price over the period\n\n**Does DCA beat lump sum?** Research shows lump-sum outperforms DCA ~2/3 of the time in rising markets — money gets invested sooner. But DCA has real advantages:\n1. **Psychological:** Removes market-timing pressure\n2. **Practical:** Most people invest from monthly income anyway\n\n**The real enemy of both approaches:** Not investing at all, or panic-selling during downturns. Either method beats cash over 10+ years.\n\nIn FlyingFunds, use paper trading to simulate a DCA strategy and track the results."
      },
      {
        id: 'inflation',
        keywords: ['inflation','purchasing power','real return','nominal return','cpi inflation','bank of england rate'],
        variants: [
          'what is inflation','how does inflation affect my portfolio',
          'what is the real return on investment','nominal vs real return difference',
          'how do stocks protect against inflation','what is purchasing power erosion',
          'fisher equation finance','inflation and interest rates relationship'
        ],
        response: "**Inflation** erodes purchasing power — £1,000 today buys more than £1,000 will in 10 years at 3% annual inflation.\n\n**Real vs Nominal returns:**\n• **Nominal:** what you see — e.g. 7%/year\n• **Real:** nominal minus inflation — 7% − 3% = 4% real return\n• **Fisher equation:** Real ≈ Nominal − Inflation\n\n**Why it matters:** A savings account paying 2% when inflation is 4% is losing purchasing power in real terms, even though the balance grows.\n\n**Equities as inflation protection:**\n• Long term: equities have historically outpaced inflation — companies raise prices and grow nominal earnings\n• Short term: high inflation can be negative for equities as rising rates compress valuations\n• 2022 example: UK CPI hit 11%, BoE raised rates aggressively → significant equity market falls\n\n**UK context:** Bank of England targets 2% CPI. Index-linked gilts directly track RPI as a direct inflation hedge."
      },
      {
        id: 'paper_trading',
        keywords: ['paper trading','virtual cash','simulated trading','practice investing','invest page flyingfunds'],
        variants: [
          'how does paper trading work','what is paper trading',
          'how do i practise trading without real money','how do i use the invest page',
          'virtual portfolio flyingfunds','how do i test a trading strategy',
          'simulated trading explained','paper trading benefits'
        ],
        response: "**Paper trading** lets you practise investing with simulated money — no real capital at risk.\n\n**In FlyingFunds:** You get **£10,000 virtual cash**. Go to the **Invest** page, select a portfolio, search any symbol, and execute a buy or sell at the live market price.\n\n**What you can track:**\n• Remaining cash balance\n• P&L per trade and per portfolio\n• Full transaction history\n• Investment chart per holding\n\n**Why it's valuable:**\n• Learn how markets move without financial risk\n• Test strategies with live prices\n• Build position-sizing and process discipline before using real money\n\n**Honest limitation:** Paper trading removes emotional stakes. Research shows people hold positions differently with virtual money. The psychological challenge of real losses is only truly learned with real capital — but paper trading builds the knowledge base first."
      },
      {
        id: 'watchlist_feature',
        keywords: ['watchlist','watch list','target price alert','tracking stocks','stock monitoring'],
        variants: [
          'how do i use the watchlist','what is the watchlist feature for',
          'how do i add a stock to my watchlist','how do price alerts work on watchlist',
          'how does the watchlist auto-refresh','watchlist target price explained'
        ],
        response: "The **Watchlist** lets you track stocks you're researching but don't yet own.\n\n**Features:**\n• **Live quotes** auto-refreshing every 30 seconds\n• **Target price** — set a level and see a ⚡ Near! badge when within 2%\n• **Notes** — write your investment thesis for each stock\n\n**Best practice — 'watchlist before portfolio':**\n1. Before adding any stock to your portfolio, put it on the watchlist first\n2. Write your thesis in notes: *why* would you want to own this?\n3. Observe its behaviour over several weeks\n4. If thesis still holds and price is near your target, consider buying\n\nThis discipline helps prevent reactive, impulse buying — one of the most common and costly investor mistakes."
      },
      {
        id: 'csv_upload',
        keywords: ['csv upload','price data upload','historical price data','real portfolio data','simulated chart fix'],
        variants: [
          'how do i upload price data','how do i get real charts not simulated',
          'what format is the csv file','where do i upload the csv in flyingfunds',
          'how do i get historical price data for my portfolio',
          'my charts are showing simulated data how to fix','upload price history'
        ],
        response: "To see **real historical charts**, upload a price CSV in **Settings → Data & Export → Upload Price CSV**.\n\n**Required CSV format:**\n```\ndate,symbol,close\n2024-01-05,AAPL,185.20\n2024-01-05,MSFT,374.50\n```\n\n**Where to get historical prices:**\nYahoo Finance → search symbol → Historical Data tab → set date range → Download CSV. Do this for each holding, merge into one file, upload.\n\n**What changes after upload:** All analytics update with your real prices — portfolio value chart, Sharpe ratio, VaR, CVaR, drawdown, and volatility become accurate.\n\n**Without uploaded prices:** FlyingFunds shows a GBM-simulated chart clearly labelled 'Simulated', so you can still explore the analytics."
      },
      {
        id: 'risk_types',
        keywords: ['risk management','types of risk','systematic vs unsystematic','idiosyncratic risk','how to reduce risk'],
        variants: [
          'how do i manage portfolio risk','what types of risk are there in investing',
          'systematic vs unsystematic risk explained','how risky is my portfolio',
          'what is idiosyncratic risk','how do i reduce my portfolio risk',
          'risk management strategies for investors'
        ],
        response: "Portfolio risk has two main components:\n\n**1. Systematic risk (market risk):**\nAffects all assets — recessions, rate changes, geopolitical events. Cannot be diversified away. Measured by **beta**. Compensated by the market risk premium.\n\n**2. Unsystematic risk (idiosyncratic risk):**\nSpecific to individual companies — scandals, product failures, management changes. Can be largely eliminated through diversification. The market doesn't compensate you for it.\n\n**Your FlyingFunds risk toolkit:**\n• **Sharpe ratio** — compensated for the risk you're taking?\n• **VaR & CVaR** — how bad on a bad/extreme day?\n• **Max drawdown** — worst historical peak-to-trough decline\n• **Volatility** — day-to-day variation\n• **Allocation chart** — too concentrated in any single holding?\n\n**Quick wins:** Diversify across sectors and geographies; keep single positions below 20–25%."
      },
      {
        id: 'portfolio_how',
        keywords: ['create portfolio','add portfolio','add holdings','set up portfolio','how to track investments'],
        variants: [
          'how do i create a portfolio','how do i add holdings to my portfolio',
          'how do i use the portfolios page','getting started with flyingfunds portfolio',
          'how do i track my investments in flyingfunds','how to set up my portfolio'
        ],
        response: "**Getting started with your portfolio:**\n\n**1. Create a portfolio**\nGo to **Portfolios** (📁 in the sidebar). Click 'New portfolio' → name it and pick a category (e.g. 'Tech Growth', 'ISA', 'Long-term').\n\n**2. Add holdings**\nOpen the portfolio → 'Add holding' → enter:\n• **Symbol** (e.g. AAPL, MSFT, TSLA, GSK.L)\n• **Quantity** (number of shares you hold)\n• **Average buy price** (your cost basis per share)\n\n**3. Explore analytics**\nOnce holdings are added, the analytics page shows allocation, portfolio value chart, and all risk metrics (Sharpe, VaR, CVaR, drawdown, volatility).\n\n**Tip:** Create multiple portfolios for different strategies — ISA holdings, paper trades, sector-specific bets."
      },
      {
        id: 'flyingfunds_overview',
        keywords: ['flyingfunds features','platform overview','navigate app','what pages available'],
        variants: [
          'what can flyingfunds do','overview of flyingfunds platform',
          'how does flyingfunds work','what features does flyingfunds have',
          'guide to all flyingfunds features','what pages are in flyingfunds'
        ],
        response: "**FlyingFunds at a glance:**\n\n📊 **Dashboard** — Home base. Portfolio overview, live market snapshot, value chart.\n📁 **Portfolios** — Create and manage multiple portfolios.\n📈 **Invest** — Paper trade with £10,000 virtual cash at live prices.\n👁 **Watchlist** — Track stocks with live quotes, target price alerts, notes.\n📊 **Market** — Interactive chart explorer. Any symbol, 7 time ranges, 3 modes.\n📓 **Diary** — Investment journal, mood tracking, calendar, to-do list.\n🎓 **Learn** — Finance education with Halo on every concept.\n⚙️ **Settings** — Profile, 2FA, CSV price upload, account management.\n\nWhat would you like help with specifically?"
      },
      {
        id: 'pe_ratio',
        keywords: ['pe ratio','price to earnings','price earnings ratio','valuation ratio','shiller cape'],
        variants: [
          'what is the pe ratio','how do you value a stock with pe',
          'what is a good pe ratio','explain price to earnings',
          'what is the shiller cape ratio','how do i know if a stock is overvalued',
          'what does a high pe ratio mean'
        ],
        response: "The **P/E ratio (Price-to-Earnings)** measures how much investors pay per £1 of annual earnings.\n\n**Formula:** P/E = Share Price / Earnings Per Share\n\n**General benchmarks:**\n• P/E 5–12 → low growth or potential undervaluation\n• P/E 15–25 → 'fair value' range for established companies\n• P/E 30–100+ → high growth expectations (tech stocks) — or overvaluation\n• Negative P/E → company is loss-making\n\n**Context is everything:** Always compare within the same sector and against the company's own history — not just an absolute number.\n\n**The Shiller CAPE:** Uses 10-year average real earnings to smooth business cycles. A CAPE above 30 on the S&P 500 has historically preceded below-average 10-year returns — a valuation warning signal, not a timing tool."
      },
      {
        id: 'market_cycles',
        keywords: ['bull market','bear market','market cycle','market crash','correction','recession'],
        variants: [
          'what is a bull market','what is a bear market',
          'what is a stock market crash','how long do bear markets last',
          'what is a market correction','should i invest during a bear market',
          'how do market cycles work'
        ],
        response: "**Market cycles** are the recurring pattern of expansion and contraction.\n\n**Bull market:** Sustained 20%+ rise from a trough. Rising earnings, economic growth, optimism. US bull market 2009–2020 was the longest on record.\n\n**Bear market:** 20%+ decline from a peak. Often accompanies recession, rising unemployment, fear. Average: ~15 months duration, ~35% peak-to-trough decline.\n\n**Corrections:** Shorter-term 10–20% declines, common even within bull markets.\n\n**Historical context:**\n• COVID crash (2020): −34% in 23 days → recovered in ~5 months\n• 2008 financial crisis: −57% → ~4 years to recover\n• Dot-com bust (2000): −49% → ~7 years to recover\n\n**For long-term investors:** Equities in developed markets have recovered from every bear market. The biggest risk is panic-selling at the bottom and missing the recovery."
      },
      // Catch-all — must be last
      { id: '_fallback', keywords: [], variants: [], response: null }
    ];
  
    // ── Pre-build TF-IDF index ─────────────────────────────────────────────────
    const INDEX = KB.filter(e => e.id !== '_fallback').map(entry => {
      const freq = {};
      entry.variants.forEach(v => tokenise(v).forEach(t => freq[t] = (freq[t]||0) + 1));
      entry.keywords.forEach(k => tokenise(k).forEach(t => freq[t] = (freq[t]||0) + 4)); // 4× boost
      return { entry, freq };
    });
  
    // ── Direct entity → id map ─────────────────────────────────────────────────
    function extractEntity(msg) {
      const m = msg.toLowerCase();
      if (/\bsharpe\b/.test(m)) return 'sharpe';
      if (/\bsortino\b/.test(m)) return 'sortino';
      if (/\bvar\b|value.?at.?risk/.test(m)) return 'var';
      if (/\bcvar\b|expected shortfall/.test(m)) return 'cvar';
      if (/\bdrawdown\b/.test(m)) return 'drawdown';
      if (/\bcapm\b|capital asset pricing/.test(m)) return 'capm';
      if (/\bbeta\b/.test(m)) return 'beta';
      if (/\balpha\b|jensen/.test(m)) return 'alpha';
      if (/markowitz|\bmpt\b|modern portfolio theory/.test(m)) return 'mpt';
      if (/efficient frontier/.test(m)) return 'efficient_frontier';
      if (/\bvolatility\b|standard deviation|\bvix\b/.test(m)) return 'volatility';
      if (/diversif|covariance|correlat/.test(m)) return 'diversification';
      if (/\bemh\b|efficient market/.test(m)) return 'emh';
      if (/behavioural|behavioral|prospect theory|kahneman/.test(m)) return 'behavioural';
      if (/loss aversion|disposition effect/.test(m)) return 'loss_aversion';
      if (/overconfidence|confirmation bias/.test(m)) return 'overconfidence';
      if (/\banchor/.test(m)) return 'anchoring';
      if (/herd|fomo/.test(m)) return 'herding';
      if (/compound/.test(m)) return 'compounding';
      if (/\binflation\b|purchasing power/.test(m)) return 'inflation';
      if (/dollar cost averag|\bdca\b/.test(m)) return 'dca';
      if (/active.*passive|passive.*active|index fund/.test(m)) return 'active_passive';
      if (/paper trad|virtual cash/.test(m)) return 'paper_trading';
      if (/watchlist/.test(m)) return 'watchlist_feature';
      if (/csv|upload.*price/.test(m)) return 'csv_upload';
      if (/\bpe\b|price.?to.?earn|price.?earn/.test(m)) return 'pe_ratio';
      if (/bull|bear|market cycle|recession/.test(m)) return 'market_cycles';
      return null;
    }
  
    // ── Conversation memory ────────────────────────────────────────────────────
    function lastTopic(history) {
      if (!history || history.length < 2) return null;
      const last = (history[history.length - 1]?.content || '').toLowerCase();
      if (/sharpe ratio/.test(last)) return 'sharpe';
      if (/value at risk|\bvar\b/.test(last)) return 'var';
      if (/cvar|expected shortfall/.test(last)) return 'cvar';
      if (/capm|capital asset/.test(last)) return 'capm';
      if (/markowitz|efficient frontier/.test(last)) return 'mpt';
      if (/drawdown/.test(last)) return 'drawdown';
      if (/behavioural|prospect theory/.test(last)) return 'behavioural';
      if (/loss aversion/.test(last)) return 'loss_aversion';
      if (/diversif/.test(last)) return 'diversification';
      if (/volatility/.test(last)) return 'volatility';
      if (/active.*passive/.test(last)) return 'active_passive';
      if (/\bbeta\b/.test(last)) return 'beta';
      if (/herding|fomo/.test(last)) return 'herding';
      return null;
    }
  
    const FOLLOW_UPS = {
      sharpe:          "Since we covered the Sharpe ratio, would you like to explore the **Sortino ratio** (downside-only version), **Jensen's alpha** (return above CAPM prediction), or **max drawdown** (worst historical decline)?",
      var:             "Now that you understand VaR, **CVaR (Expected Shortfall)** is the natural next step — it measures the average severity of losses on the days you breach VaR. Want me to explain it?",
      cvar:            "With VaR and CVaR covered, **max drawdown** rounds out your downside picture — the worst peak-to-trough decline. Shall I explain it?",
      capm:            "CAPM connects to **beta** (market sensitivity), **Jensen's alpha** (excess return over CAPM prediction), and the **Fama-French model** (adds size and value factors). What would you like next?",
      mpt:             "Modern Portfolio Theory leads naturally to **CAPM** (which built on Markowitz's work) and **diversification** (the practical application). Which would you like to explore?",
      drawdown:        "Drawdown, **VaR**, and **volatility** together give a complete risk picture. Want me to cover either?",
      behavioural:     "Behavioural finance covers specific biases: **loss aversion**, **overconfidence**, **anchoring**, and **herding**. Which interests you?",
      loss_aversion:   "Loss aversion connects to **overconfidence** and the broader **disposition effect**. Want me to explain overconfidence bias next?",
      diversification: "Diversification is grounded in **Modern Portfolio Theory** and driven by **correlation** between assets. Want me to go deeper on either?",
      volatility:      "Volatility feeds into the **Sharpe ratio** (return per unit of vol) and **VaR** (extreme downside). Both are on your Analytics page. Want me to explain either?",
      active_passive:  "The active/passive debate ties into **EMH** (the theory behind why passive often wins) and **factor investing** (the middle ground). Which would you like?",
      beta:            "Beta leads naturally to the full **CAPM formula** and **Jensen's alpha**. Shall I explain either?",
      herding:         "Herding connects to the broader **behavioural finance** literature and specifically **FOMO** and **asset bubbles**. Want me to explain prospect theory — the psychological root of herding?",
    };
  
    // ── Intent detection ───────────────────────────────────────────────────────
    function detectIntent(msg) {
      if (/^(what is|what are|define|definition|meaning|explain|describe)/i.test(msg)) return 'define';
      if (/(example|give me|show me|illustrate)/i.test(msg)) return 'example';
      if (/(compare|versus|\bvs\b|difference between|which is better)/i.test(msg)) return 'compare';
      if (/(how (do|does|can|should)|how to|steps|guide|navigate|how do i use)/i.test(msg)) return 'howto';
      if (/(why|reason|cause)/i.test(msg)) return 'why';
      if (/(calculate|formula|equation|compute)/i.test(msg)) return 'formula';
      return 'general';
    }
  
    // ── Main respond function ──────────────────────────────────────────────────
    function respond(rawMsg, history = []) {
      const msg = correct(rawMsg.trim());
  
      // Short follow-up check
      if (/^(tell me more|more|go on|continue|what else|yes please|ok|okay|sure|next|elaborate|and\??|what about)/i.test(msg)) {
        const topic = lastTopic(history);
        if (topic && FOLLOW_UPS[topic]) return FOLLOW_UPS[topic];
      }
  
      // Direct entity shortcut
      const entity = extractEntity(msg);
      if (entity) {
        const match = KB.find(e => e.id === entity);
        if (match) {
          const r = match.response;
          return typeof r === 'function' ? r() : r;
        }
      }
  
      // TF-IDF cosine similarity
      const qFreq = {};
      tokenise(msg).forEach(t => qFreq[t] = (qFreq[t]||0) + 1);
  
      let bestScore = 0, bestEntry = null;
      INDEX.forEach(({ entry, freq }) => {
        const terms = new Set([...Object.keys(qFreq), ...Object.keys(freq)]);
        let dot = 0, mQ = 0, mE = 0;
        terms.forEach(t => {
          const q = qFreq[t]||0, e = freq[t]||0;
          dot += q*e; mQ += q*q; mE += e*e;
        });
        if (!mQ || !mE) return;
        const score = dot / (Math.sqrt(mQ) * Math.sqrt(mE));
        if (score > bestScore) { bestScore = score; bestEntry = entry; }
      });
  
      if (bestScore > 0.07 && bestEntry) {
        const r = bestEntry.response;
        return typeof r === 'function' ? r() : r;
      }
  
      // Graceful fallback
      const intent = detectIntent(msg);
      const picks = ['Sharpe ratio','Value at Risk','CAPM','Modern Portfolio Theory',
        'diversification','behavioural finance','max drawdown','active vs passive investing',
        'compounding','efficient markets hypothesis','beta','dollar cost averaging'];
      const s = picks[Math.floor(Math.random() * picks.length)];
  
      if (intent === 'howto') return "For help navigating FlyingFunds, try: 'how do I add a portfolio', 'how do I use the watchlist', 'how do I upload price data', or 'how does paper trading work'. What are you trying to do?";
      if (intent === 'define') return `I don't have a specific entry for that term yet. Could you rephrase, or try asking about **${s}**? You can also browse topics in the Learn section.`;
      return `I'm not sure I caught that — could you rephrase? I cover topics like **${s}** and all FlyingFunds features. What would you like to know?`;
    }
  
    return { respond };
  })();
  
  // Global entry point — called by base.html and learn.html
  function haloRespond(message, history) {
    return HALO.respond(message, history);
  }