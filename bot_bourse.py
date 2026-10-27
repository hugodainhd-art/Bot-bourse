import os
import time
import json
import requests
import feedparser
import yfinance as yf

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

BUDGET = 100              # € de départ
MAX_PAR_POSITION = 0.20   # max 20 % du budget par position
STOP_LOSS = 0.05          # stop-loss à -5 %

WATCHLIST = {
    "Nvidia": ("NVDA", "Nvidia stock"),
    "Apple": ("AAPL", "Apple stock"),
    "Microsoft": ("MSFT", "Microsoft stock"),
    "Tesla": ("TSLA", "Tesla stock"),
    "TotalEnergies": ("TTE.PA", "TotalEnergies"),
    "LVMH": ("MC.PA", "LVMH stock"),
    "ETF S&P 500": ("SPY", "S&P 500"),
    "Bitcoin": ("BTC-USD", "Bitcoin price"),
    "Ethereum": ("ETH-USD", "Ethereum price"),
    "EUR/USD": ("EURUSD=X", "euro dollar ECB Fed"),
}

MOTS_POSITIFS = ["surge", "soar", "beat", "record", "upgrade", "rally", "profit",
                 "growth", "jump", "approval", "partnership", "gain", "bullish"]
MOTS_NEGATIFS = ["plunge", "fall", "miss", "downgrade", "lawsuit", "probe", "recall",
                 "loss", "cut", "ban", "fraud", "crash", "bearish", "layoff", "warning"]

FICHIER_ETAT = "etat.json"
try:
    dernier_signal = json.load(open(FICHIER_ETAT))
except Exception:
    dernier_signal = {}


def telegram(texte):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": texte},
        timeout=15,
    )


def rsi(close, n=14):
    d = close.diff()
    gain = d.clip(lower=0).rolling(n).mean()
    perte = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - 100 / (1 + gain / perte)


def score_news(requete):
    url = f"https://news.google.com/rss/search?q={requete.replace(' ', '+')}&hl=en"
    titres = [e.title.lower() for e in feedparser.parse(url).entries[:10]]
    pos = sum(any(m in t for m in MOTS_POSITIFS) for t in titres)
    neg = sum(any(m in t for m in MOTS_NEGATIFS) for t in titres)
    return pos - neg, titres[:2]


def analyser(symbole, requete):
    c = yf.Ticker(symbole).history(period="6mo")["Close"].dropna()
    if len(c) < 60:
        return None
    score, raisons = 0, []

    r = rsi(c).iloc[-1]
    if r < 30:
        score += 1
        raisons.append(f"RSI {r:.0f} : survendu")
    elif r > 70:
        score -= 1
        raisons.append(f"RSI {r:.0f} : suracheté")

    sma20, sma50 = c.rolling(20).mean().iloc[-1], c.rolling(50).mean().iloc[-1]
    if sma20 > sma50:
        score += 1
        raisons.append("tendance haussière (MM20 > MM50)")
    else:
        score -= 1
        raisons.append("tendance baissière (MM20 < MM50)")

    sn, titres = score_news(requete)
    if sn >= 2:
        score += 1
        raisons.append(f"actus plutôt positives ({sn:+d})")
    elif sn <= -2:
        score -= 1
        raisons.append(f"actus plutôt négatives ({sn:+d})")

    var = (c.iloc[-1] / c.iloc[-2] - 1) * 100
    return {"prix": c.iloc[-1], "var": var, "score": score, "raisons": raisons, "titres": titres}


def executer():
    for nom, (symbole, requete) in WATCHLIST.items():
        try:
            a = analyser(symbole, requete)
        except Exception as e:
            print(f"{nom}: erreur {e}")
            continue
        if not a:
            continue

        if a["score"] >= 2:
            signal = "ACHAT"
        elif a["score"] <= -2:
            signal = "VENTE"
        else:
            signal = None

        if signal and dernier_signal.get(nom) != signal:
            mise = BUDGET * MAX_PAR_POSITION
            msg = (
                f"{'🟢' if signal == 'ACHAT' else '🔴'} Signal {signal} : {nom}\n"
                f"Prix : {a['prix']:.2f} ({a['var']:+.1f} % aujourd'hui)\n"
                f"Raisons : " + " ; ".join(a["raisons"]) + "\n"
            )
            if a["titres"]:
                msg += "Actus : " + " | ".join(a["titres"]) + "\n"
            if signal == "ACHAT":
                msg += f"Mise max conseillée : {mise:.0f} € | stop-loss : -{STOP_LOSS*100:.0f} %\n"
            msg += "Signal automatique, pas un conseil financier. Vérifie avant d'agir."
            telegram(msg)
        dernier_signal[nom] = signal
        time.sleep(2)
    json.dump(dernier_signal, open(FICHIER_ETAT, "w"))


if __name__ == "__main__":
    executer()
