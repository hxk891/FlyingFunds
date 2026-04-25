import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/chat", tags=["chat"])

# TODO: move this to a separate file if it gets much longer
SYSTEM_PROMPT = """You are Halo, a friendly and knowledgeable personal finance assistant
built into FlyingFunds, a paper trading and investment portfolio management platform.

You help users with:
- Investment concepts: portfolio theory, diversification, risk/return, asset allocation
- Financial metrics: Sharpe ratio, VaR, CVaR, beta, alpha, max drawdown, Sortino ratio
- Platform features: creating portfolios, paper trading (buy/sell), watchlists, uploading
  CSV price data, reading analytics and risk charts, the efficient frontier page
- Market concepts: how stock markets work, index funds, ETFs, active vs passive investing
- Behavioural finance: loss aversion, overconfidence bias, anchoring, herding

Guidelines:
- Keep responses concise (under 180 words) unless a detailed explanation is truly needed
- Use plain English first, then provide formulas or deeper detail if the user asks for it.
- When referencing FlyingFunds features, be specific (e.g. "go to the Invest tab to paper trade")
- If a question is completely off-topic from finance or the platform, politely redirect the user
- Never give real financial advice or recommend specific stocks to buy or sell"""


class ChatIn(BaseModel):
    message: str
    history: list = []   # list of {role, content} dicts


@router.post("/halo")
def halo_chat(payload: ChatIn):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(503, "AI assistant not configured (ANTHROPIC_API_KEY missing)")

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
    except ImportError:
        raise HTTPException(503, "anthropic package not installed")

    # last 6 turns only — claude context window gets expensive fast
    messages = []
    for h in payload.history[-6:]:
        role = h.get("role") if isinstance(h, dict) else getattr(h, "role", None)
        content = h.get("content") if isinstance(h, dict) else getattr(h, "content", None)
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": payload.message.strip()})

    try:
        resp = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=350,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        reply = resp.content[0].text
        return {"reply": reply}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(502, f"AI error: {str(e)}")
