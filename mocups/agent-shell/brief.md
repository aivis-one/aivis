# Brief: CBS HOME — Agent Shell

## Overview

| Field | Value |
|-------|-------|
| Type | Agent cabinet (extends Investor) |
| Primary | Phone (390px) |
| Devices | Phone, Tablet, Desktop |
| Brand | CBS HOME (Teal #1A6B6A + Orange #E8651A, Montserrat) |

## Screens

| # | Screen | Description |
|---|--------|-------------|
| 1 | **Dashboard** | Приветствие, портфель, активный + пассивный баланс, быстрые действия, уведомления |
| 2 | **Agent Hub** | Центр агента: общая статистика (рефералы, комиссии, ранг), быстрые ссылки |
| 3 | **Referral Links** | Управление реферальными ссылками, создание новых, копирование |
| 4 | **Commissions** | История комиссий L1/L2/L3, фильтр по уровням, суммы |
| 5 | **Leaderboard** | Топ-20 агентов по объёму, позиция текущего агента, бонусный пул |
| 6 | **Passive Balance** | Пассивный баланс (заработок), вывод средств, перевод в активный |
| 7 | **Settings** | Профиль агента, сертификация, документы |

## Tab Bar

| Tab | Icon | Screen |
|-----|------|--------|
| Главная | 🏠 | Dashboard |
| Hub | 🤝 | Agent Hub |
| Комиссии | 💎 | Commissions |
| Баланс | 💰 | Passive Balance |
| Ещё | ⚙️ | Settings |

## Data Plan

| Entity | Fields | Count |
|--------|--------|-------|
| Agent profile | name, rank, referrals count, total commissions | 1 |
| Referral links | code, url, clicks, conversions, status | 3 |
| Commissions | level (L1/L2/L3), source user, amount EUR, product, date, status | 8 |
| Leaderboard | rank, name, avatar, volume EUR, change | 10 |
| Passive balance | confirmed EUR, frozen EUR (14-day cooldown) | 1 |
| Bonus pool | monthly 2% (top-20), quarterly 1% (top-10) | 2 |

## Notes

- Agent = Investor + agent features; this mockup focuses on agent-specific screens
- Passive balance has 14-day cooling-off for EU fiat withdrawals
- Commission levels: L1=10%, L2=3%, L3=1%
- Leaderboard updates every 60 minutes
