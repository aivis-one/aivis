# E-mail letters

AIVIS builds every e-mail letter itself and hands it to comms whole, in the
`email` block of the notification request: `{subject, text, html}`. comms
sends exactly that (comms >= 3.12.0 with the block). The builder is
`__init__.py` beside this file; it is the only place a letter is made.

The layouts are tables with inline CSS, the literal colours of
`design-system/tokens/tokens-resolved.json` (light only), width 600, a font
stack that falls back to Segoe UI, Roboto and Arial, and the logo as a PNG at
`{logo_url}` (the site publishes it at `/email/logo.png`).

## Files

- `layouts/<layout>.html` -- the five layouts. They carry no words of their
  own and serve both languages: `{lang}` is the letter's language, every
  word is a slot.
- `copy.yaml` -- the words. `common`: the footer of every layout and the
  digest's fixed words, per language. `types`: for each type, its layout,
  and per language its subject, the words of the layout's slots, and -- for
  a type that also lands in the cabinet's bell -- `bell_title` and
  `bell_body`. Three letters nothing sends yet (`welcome`,
  `installment.reminder`, `news.digest`) are marked `sent: false`.

## Layouts

| Layout | For | Slots |
|---|---|---|
| `code` | a one-time code | `heading`, `lead`, `valid_note`, `ignore_note`; data: `{code}` |
| `document` | a document is ready, five rows and one button | `heading`, `lead`, `row1..5_label/_value`, `button_text`, `button_url`, `note` |
| `notice` | a status of money or a debt: one amount row, one status row, a button | `heading`, `lead`, `detail_label/_value`, `status_label/_text/_color`, `note`, `button_text`, `button_url` |
| `action` | one thing to do, one button | `heading`, `lead`, `highlight`, `button_text`, `button_url`, `note` |
| `digest` | the news mailing: a lead and three items, an unsubscribe link | `heading`, `lead`; data: `{item1..3_title/_text/_url}`, `{unsubscribe_url}` |

Every layout also uses the footer words (`footer_company`, `footer_support`,
`footer_bot`) and the shared variables of `backend/app/core/email_vars.py`
`letter_vars()`: `{logo_url}`, `{support_url}` (the support bot),
`{support_email}`, `{cabinet_url}`, `{site_url}`.
Colours of a status: success `#0E6E45`, in progress or overdue `#B1581B`,
failure `#9C231E`.

## Which types use which layout

- `code`: `auth.verification_code`, `auth.telegram_link_code`
- `action`: `auth.password_reset`, `auth.telegram_linked`, and the unsent `welcome` and `installment.reminder`
- `document`: `purchase.agreement`, `ownership.certificate`
- `notice`: `withdrawal.processing`, `.completed`, `.rejected`, `.failed`,
  `installment.tranche_overdue`, `installment.plan_defaulted`
- `digest`: the unsent `news.digest` (marketing mail: its own sending domain
  and an unsubscribe link come with it)

## The text part

The same slots in the layout's plain shape: one line per paragraph (a mail
client wraps it), an empty line between paragraphs, one line per row of a
table ("Label: value"), a button as "Text: link", the footer last. The two
parts take their words from the same entries, so they cannot say different
things.

## Checks

The builder's loader refuses `copy.yaml` at import on a missing or extra
slot, a missing language, a blank word, a key written twice, a NUL, or a
layout that lost one of its slots. `tests/test_letters.py` builds every type
in both languages. No `http` literal anywhere: every link is a variable
(`checks/deploy_addresses.py` scans this folder).
