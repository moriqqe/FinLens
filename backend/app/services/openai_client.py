from __future__ import annotations
import json
import os
import re
from collections import defaultdict

import httpx

from app.services.parsers.base import Transaction


def _analysis_model() -> str:
    return os.getenv("OPENAI_ANALYSIS_MODEL", "gpt-4o").strip() or "gpt-4o"


def _analysis_temperature() -> float:
    raw = os.getenv("OPENAI_ANALYSIS_TEMPERATURE", "0.35").strip()
    try:
        return max(0.0, min(2.0, float(raw)))
    except ValueError:
        return 0.35


def _looks_like_retail_or_fuel_or_food_pos(t: Transaction) -> bool:
    """Recurring purchases at supermarkets / cafes / fuel — NOT digital subscriptions."""
    c = str(t.category or "").lower()
    if any(x in c for x in ("5411", "5412", "5499", "5462", "5541", "5542")):
        # Groceries, restaurants, misc food, bakeries, fuel/service stations
        return True
    d = (t.description or "").lower()
    needles = (
        "hofer",
        "silpo",
        "сільпо",
        "атб",
        "novus",
        "фора",
        "єва",
        "metro",
        "rozetka",
        "епіцентр",
        "supermarket",
        "grocery",
        "варус",
        "київський маркет",
        "food retail",
        "mcdonald",
        "kfc ",
        "coffee",
        "кафе",
        "ресторан",
        "pizza",
        "shell",
        "wog ",
        "окко",
        "socar",
        "азс",
        "fuel",
        "аптека",
        "pharmacy",
    )
    return any(n in d for n in needles)


def _merchant_key(description: str, category: str) -> str:
    d = (description or "").strip().lower()
    d = re.sub(r"\*\d+", "", d)
    d = re.sub(r"#\d+", "", d)
    d = re.sub(r"\d{10,}", "", d)
    d = re.sub(r"\s+", " ", d).strip()
    if "," in d:
        d = d.split(",")[0].strip()
    if len(d) < 4:
        return f"{category}|{d}"
    return d[:58]


def _subscription_hints(expenses: list[Transaction]) -> str:
    """Легкий локальний аналіз повторів — підказки лише для ймовірних сервісів (не супермаркети)."""
    if not expenses:
        return "(даних немає / no data)"

    groups: dict[str, list[Transaction]] = defaultdict(list)
    for t in expenses:
        key = _merchant_key(t.description, t.category)
        groups[key].append(t)

    lines: list[str] = []
    for key, txs in sorted(groups.items(), key=lambda kv: (-len({str(t.date)[:7] for t in kv[1]}), -len(kv[1]))):
        months = {str(t.date)[:7] for t in txs}
        amounts = [abs(float(t.amount_uah)) for t in txs]
        if len(months) < 2 and len(txs) < 3:
            continue
        retail_n = sum(1 for t in txs if _looks_like_retail_or_fuel_or_food_pos(t))
        if retail_n >= max(1, len(txs) // 2):
            continue
        avg = sum(amounts) / len(amounts)
        spread = max(amounts) - min(amounts) if amounts else 0
        if spread > max(avg * 0.5, 100) and len(months) < 3:
            continue
        lines.append(
            f"- «{key}»: платежів/txn={len(txs)}, місяців/months={len(months)}, "
            f"середня ~avg={avg:.0f} UAH (ймовірний сервіс / likely recurring service)"
        )

    if not lines:
        return "(авто-підказок немає; все одно шукай підписки в тексті транзакцій / no auto clusters)"

    return "\n".join(lines[:55])


async def analyze_transactions(api_key: str, transactions: list[Transaction]) -> dict:
    expenses = [t for t in transactions if t.is_expense]
    total = sum(abs(t.amount_uah) for t in expenses)

    cat_sums: dict[str, float] = {}
    for t in expenses:
        cat_sums[t.category] = cat_sums.get(t.category, 0) + abs(t.amount_uah)

    top_cats = sorted(cat_sums.items(), key=lambda x: x[1], reverse=True)[:15]
    top_cats_str = "\n".join(f"{c}: {round(v)} UAH" for c, v in top_cats)

    expenses_sorted = sorted(expenses, key=lambda x: x.date)
    if len(expenses_sorted) <= 220:
        sample = expenses_sorted
    else:
        sample = expenses_sorted[:110] + expenses_sorted[-110:]
    sample_str = "\n".join(
        f"{t.date} | {t.category} | {t.description[:55]} | {t.amount_uah:.0f} UAH"
        for t in sample
    )

    hints_block = _subscription_hints(expenses)

    months = sorted({str(t.date)[:7] for t in transactions})
    n_months = len(months) or 1
    period_label = f"{months[0]} – {months[-1]}" if months else "—"

    prompt = f"""Ти фінансовий аналітик. Дані містять опис українською та англійською — трактуй обидві однаково серйозно.
You MUST treat Ukrainian AND English transaction descriptions equally when finding subscriptions and patterns.

Період / Period: {period_label}
ЗАГАЛЬНА СУМА ВИТРАТ / Total expenses: {round(total)} UAH за {n_months} міс. (avg ~{round(total / n_months)} UAH/mo)

ТОП КАТЕГОРІЇ:
{top_cats_str}

АВТО-ПІДКАЗКИ ЙМОВІРНИХ СЕРВІСІВ (перевір по тексту транзакції; НЕ роздріб зі списку нижче):
AUTO-HINTS — likely recurring digital/services only (verify against description; ignore retail chains):
{hints_block}

ПОВНА ВИБІРКА ВИТРАТ (до ~220 рядків, хронологічно / expense rows):
{sample_str}

ПІДПИСКИ VS ЗВИЧАЙНІ ПОКУПКИ / SUBSCRIPTIONS VS ROUTINE SPENDING (критично важливо):
- У JSON_SUBS потрапляють лише регулярні ЦИФРОВІ або сервісні платежі: стримінг, софт/SaaS, хмара, VPN, домени, Microsoft/Google/Apple підписки, Zoom, Adobe, Patreon, підписки доставки їжі ЯК ОКРЕМИЙ ПЛАТІЖНИЙ ПРОДУКТ (де явно сервіс), мобільний тариф як абонплата до оператора (не поповнення розумної кількості разово), фітнес абонемент як списання до клубу з однаковим шаблоном назви.
- НЕ є підпискою для JSON_SUBS (не додавай, або згадай лише в ANALYSIS як звичку витрат): супермаркети й гіпери (MCC 5411 та подібні описи POS: Hofer, АТБ, Novus, Silpo тощо), навіть якщо суми щомісяця схожі — це звичайний шопінг продуктів, не SaaS.
- Так само виключи: АЗС, кафе/ресторани/фастфуд, аптеки (типовий роздріб), випадкові повтори одного ТЦ без сервісного дескриптора.
- Увага на маркетплейси: покупки на Amazon/eBay як магазин — не підписка; окремий рядок Prime/eBay store subscription — підписка, якщо опис це підтверджує.
- Повторення в різних місяцях САМО ПО СОБІ не робить операцію підпискою: спочатку класифікуй тип мерчанта (роздріб vs digital/service).

ІНСТРУКЦІЇ ДЛЯ JSON_SUBS:
1. Пройдись по рядках вибірки й відфільтруй лише сервісні/цифрові регулярні платежі (Netflix, Spotify, Google One, Apple, AWS, VPN, хостинг тощо — UA/EN).
2. Якщо позиція сумнівна між «підписка» і «раз на місяць ходили в магазин» — не включай у JSON_SUBS; коротко опиши в ANALYSIS як звичку без підписного сервісу.
3. У JSON_SUBS типово 5–25 позицій; якщо сумнівно але можливо сервіс — verdict=\"review\", інакше keep або cut.
4. Авто-підказки вище неповні — доповнюй підписки з тексту транзакцій, але завжди розділяй роздріб і сервіс.

Відповідай ЛИШЕ такою структурою (ANALYSIS українською):
ANALYSIS:
[3-6 речень українською]

JSON_RECS:
{{"recommendations":[{{"type":"cut|watch|ok","title":"...","desc":"...","saving_uah":NUMBER|null}}]}}

JSON_SUBS:
{{"subscriptions":[{{"name":"...","amount_uah":NUMBER,"period":"monthly|yearly|unknown","verdict":"keep|cut|review"}}]}}
"""

    model = _analysis_model()
    temperature = _analysis_temperature()

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "max_tokens": 4096,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()

    text = resp.json()["choices"][0]["message"]["content"]
    return _parse_response(text)


def _parse_response(text: str) -> dict:
    result: dict = {"analysis": "", "recommendations": [], "subscriptions": []}
    try:
        m = re.search(r"ANALYSIS:\s*([\s\S]*?)(?=JSON_RECS:|$)", text)
        if m:
            result["analysis"] = m.group(1).strip()

        m = re.search(r"JSON_RECS:\s*([\s\S]*?)(?=JSON_SUBS:|$)", text)
        if m:
            raw = m.group(1).strip().replace("```json", "").replace("```", "")
            result["recommendations"] = json.loads(raw).get("recommendations", [])

        m = re.search(r"JSON_SUBS:\s*([\s\S]*?)$", text)
        if m:
            raw = m.group(1).strip().replace("```json", "").replace("```", "")
            result["subscriptions"] = json.loads(raw).get("subscriptions", [])
    except Exception:
        result["analysis"] = text
    return result
