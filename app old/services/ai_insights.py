"""
AI-powered portfolio insights using Claude API

This service provides:
- Risk assessment
- Diversification analysis
- Personalized recommendations
- News sentiment analysis
"""

import os
import json
from typing import Dict, List, Optional
from anthropic import Anthropic
import asyncio


class AIInsightsService:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        
        self.client = Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"
    
    async def analyze_portfolio(
        self,
        portfolio_data: Dict,
        risk_metrics: Dict,
        market_context: Optional[Dict] = None
    ) -> Dict:
        """
        Comprehensive portfolio analysis using Claude
        
        Args:
            portfolio_data: Holdings with symbols, quantities, weights
            risk_metrics: Volatility, Sharpe, VaR, etc.
            market_context: Optional recent market data
        
        Returns:
            {
                "risk_assessment": str,
                "diversification_score": float,
                "recommendations": List[str],
                "sector_analysis": str,
                "sentiment": str,
                "confidence": float
            }
        """
        
        prompt = self._build_analysis_prompt(portfolio_data, risk_metrics, market_context)
        
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                temperature=0.3,  # Lower temperature for more consistent analysis
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            # Parse response
            response_text = message.content[0].text
            return self._parse_analysis_response(response_text)
            
        except Exception as e:
            print(f"AI analysis error: {e}")
            return self._get_fallback_analysis()
    
    def _build_analysis_prompt(
        self,
        portfolio_data: Dict,
        risk_metrics: Dict,
        market_context: Optional[Dict]
    ) -> str:
        """Build comprehensive analysis prompt"""
        
        holdings_summary = "\n".join([
            f"- {h['symbol']}: {h['weight']*100:.1f}% (£{h['invested_value']:.2f})"
            for h in portfolio_data.get('holdings', [])
        ])
        
        risk_summary = f"""
- Annualized Volatility: {risk_metrics.get('annualised_volatility', 0)*100:.2f}%
- Sharpe Ratio: {risk_metrics.get('sharpe_ratio', 0):.2f}
- Max Drawdown: {risk_metrics.get('max_drawdown', 0)*100:.2f}%
- VaR (95%): {risk_metrics.get('var', 0)*100:.2f}%
- Cumulative Return: {risk_metrics.get('cumulative_return', 0)*100:.2f}%
"""
        
        market_info = ""
        if market_context:
            market_info = f"\n\nRecent Market Context:\n{json.dumps(market_context, indent=2)}"
        
        prompt = f"""You are an expert financial advisor analyzing an investment portfolio. 

Portfolio Holdings:
{holdings_summary}

Total Invested: £{portfolio_data.get('total_invested', 0):.2f}
Number of Holdings: {portfolio_data.get('num_holdings', 0)}

Risk Metrics:
{risk_summary}
{market_info}

Please provide a comprehensive analysis in the following JSON format:

{{
    "risk_assessment": "2-3 paragraph assessment of portfolio risk considering volatility, concentration, and drawdown",
    "diversification_score": <0-100 score based on number of holdings, sector exposure, correlation>,
    "diversification_explanation": "Brief explanation of the diversification score",
    "recommendations": [
        "Specific, actionable recommendation 1",
        "Specific, actionable recommendation 2",
        "Specific, actionable recommendation 3"
    ],
    "sector_analysis": "Analysis of sector exposure and concentration risks",
    "sentiment": "bullish/neutral/bearish",
    "confidence": <0-100 confidence in the analysis>,
    "key_strengths": ["strength 1", "strength 2"],
    "key_concerns": ["concern 1", "concern 2"]
}}

Focus on:
1. Practical, actionable insights
2. Risk-adjusted returns vs pure returns
3. Portfolio balance and concentration
4. Whether metrics align with investor goals (assuming moderate risk tolerance)
5. Specific symbols that may need attention

Be honest about both strengths and weaknesses. Use UK terminology (£, FTSE, etc. where relevant).
"""
        
        return prompt
    
    def _parse_analysis_response(self, response_text: str) -> Dict:
        """Parse Claude's JSON response"""
        
        try:
            # Try to find JSON in the response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx != -1 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                result = json.loads(json_str)
                return result
            else:
                # Fallback: treat entire response as risk assessment
                return {
                    "risk_assessment": response_text,
                    "diversification_score": 50.0,
                    "diversification_explanation": "Unable to calculate",
                    "recommendations": ["Review portfolio with a financial advisor"],
                    "sector_analysis": "Analysis unavailable",
                    "sentiment": "neutral",
                    "confidence": 50.0,
                    "key_strengths": [],
                    "key_concerns": []
                }
        except json.JSONDecodeError:
            return self._get_fallback_analysis()
    
    def _get_fallback_analysis(self) -> Dict:
        """Return fallback analysis if AI fails"""
        return {
            "risk_assessment": "AI analysis temporarily unavailable. Please try again later.",
            "diversification_score": 0.0,
            "diversification_explanation": "Analysis unavailable",
            "recommendations": ["Ensure your portfolio is well-diversified across sectors and asset types"],
            "sector_analysis": "Manual review recommended",
            "sentiment": "neutral",
            "confidence": 0.0,
            "key_strengths": [],
            "key_concerns": []
        }
    
    async def analyze_news_sentiment(
        self,
        articles: List[Dict],
        symbols: List[str]
    ) -> Dict:
        """
        Analyze news sentiment for portfolio holdings
        
        Args:
            articles: List of news articles with title, description, source
            symbols: Portfolio stock symbols
        
        Returns:
            {
                "overall_sentiment": str,
                "symbol_sentiments": {symbol: {...}},
                "key_themes": List[str],
                "risk_signals": List[str]
            }
        """
        
        if not articles:
            return {
                "overall_sentiment": "neutral",
                "symbol_sentiments": {},
                "key_themes": [],
                "risk_signals": []
            }
        
        articles_summary = "\n\n".join([
            f"Title: {a.get('title', 'N/A')}\n"
            f"Source: {a.get('source', {}).get('name', 'Unknown')}\n"
            f"Summary: {a.get('description', 'N/A')[:200]}"
            for a in articles[:10]  # Limit to 10 most recent
        ])
        
        prompt = f"""Analyze these recent news articles for sentiment regarding these portfolio holdings: {', '.join(symbols)}

News Articles:
{articles_summary}

Provide analysis in JSON format:
{{
    "overall_sentiment": "positive/negative/neutral",
    "symbol_sentiments": {{
        "SYMBOL": {{
            "sentiment": "positive/negative/neutral",
            "confidence": <0-100>,
            "reasoning": "Brief explanation"
        }}
    }},
    "key_themes": ["theme1", "theme2", "theme3"],
    "risk_signals": ["signal1", "signal2"],
    "opportunities": ["opportunity1", "opportunity2"]
}}

Focus on market-moving news and company-specific developments. If a symbol isn't mentioned in the news, mark sentiment as "neutral" with low confidence.
"""
        
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = message.content[0].text
            return self._parse_sentiment_response(response_text)
            
        except Exception as e:
            print(f"Sentiment analysis error: {e}")
            return {
                "overall_sentiment": "neutral",
                "symbol_sentiments": {s: {"sentiment": "neutral", "confidence": 0} for s in symbols},
                "key_themes": [],
                "risk_signals": []
            }
    
    def _parse_sentiment_response(self, response_text: str) -> Dict:
        """Parse sentiment analysis response"""
        try:
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx != -1 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                return json.loads(json_str)
            else:
                return {
                    "overall_sentiment": "neutral",
                    "symbol_sentiments": {},
                    "key_themes": [],
                    "risk_signals": []
                }
        except json.JSONDecodeError:
            return {
                "overall_sentiment": "neutral",
                "symbol_sentiments": {},
                "key_themes": [],
                "risk_signals": []
            }
    
    async def generate_rebalancing_suggestions(
        self,
        portfolio_data: Dict,
        target_allocation: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Generate smart rebalancing suggestions
        
        Args:
            portfolio_data: Current holdings and weights
            target_allocation: Optional target weights per symbol
        
        Returns:
            List of trade suggestions with reasoning
        """
        
        holdings_desc = "\n".join([
            f"- {h['symbol']}: {h['weight']*100:.1f}% (qty: {h['quantity']}, avg price: £{h['avg_buy_price']:.2f})"
            for h in portfolio_data.get('holdings', [])
        ])
        
        target_desc = ""
        if target_allocation:
            target_desc = f"\n\nTarget Allocation:\n" + "\n".join([
                f"- {symbol}: {weight*100:.1f}%"
                for symbol, weight in target_allocation.items()
            ])
        
        prompt = f"""You are a portfolio manager. Analyze this portfolio and suggest rebalancing trades.

Current Holdings:
{holdings_desc}

Total Value: £{portfolio_data.get('total_invested', 0):.2f}
{target_desc}

Provide rebalancing suggestions in JSON format:
{{
    "suggestions": [
        {{
            "action": "buy/sell",
            "symbol": "SYMBOL",
            "quantity": <number of shares>,
            "reasoning": "Why this trade makes sense",
            "priority": "high/medium/low",
            "expected_impact": "Brief description of how this improves portfolio"
        }}
    ],
    "overall_strategy": "Brief explanation of the rebalancing approach",
    "estimated_cost": <approximate transaction costs if applicable>
}}

Consider:
1. Over-concentrated positions (>20% in single holding)
2. Under-diversified portfolio (<5 holdings)
3. Balancing across sectors/regions if possible
4. Tax implications (prefer smaller adjustments)

If no rebalancing needed, return empty suggestions list with explanation in overall_strategy.
"""
        
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                temperature=0.4,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = message.content[0].text
            result = self._parse_rebalancing_response(response_text)
            return result.get('suggestions', [])
            
        except Exception as e:
            print(f"Rebalancing suggestions error: {e}")
            return []
    
    def _parse_rebalancing_response(self, response_text: str) -> Dict:
        """Parse rebalancing suggestions response"""
        try:
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx != -1 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                return json.loads(json_str)
            else:
                return {"suggestions": [], "overall_strategy": "Unable to generate suggestions"}
        except json.JSONDecodeError:
            return {"suggestions": [], "overall_strategy": "Unable to generate suggestions"}


# Singleton instance
_ai_service = None

def get_ai_service() -> AIInsightsService:
    """Get or create AI service instance"""
    global _ai_service
    if _ai_service is None:
        _ai_service = AIInsightsService()
    return _ai_service
