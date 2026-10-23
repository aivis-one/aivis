# HTML letters

The AIVIS e-mail letters as HTML on the design system: tables, inline CSS, the
literal colours of `design-system/tokens/tokens-resolved.json` (light only),
width 600, a font stack that falls back to Segoe UI, Roboto and Arial, and the
logo as a PNG at `{logo_url}` (the site publishes it at `/email/logo.png`).
comms does not send the html part yet: this folder is the input of the comms
release that adds an `email.html` field next to `email.subject` and
`email.body`. Until then the letters go out as the plain text of
`../templates/<locale>.yaml`.

## Files

- `en/<layout>.html`, `ru/<layout>.html` -- the five layouts, one per locale.
- `copy.yaml` -- for each type: its layout and the words that go into the
  layout's slots, in both languages. Three letters nothing sends yet
  (`welcome`, `installment.reminder`, `news.digest`) are marked `sent: false`
  and also carry their subject and plain text.
- `compose.py` -- writes the slot words into a layout and leaves the data
  variables for comms: `python compose.py --out DIR` writes
  `DIR/<type>.<locale>.html`, one per type and locale, each ready to be a
  template leaf. It also holds `render()`, which fills the variables and
  HTML-escapes every value; comms must escape the same way before it puts a
  variable into an html part.

## Layouts

| Layout | For | Slots |
|---|---|---|
| `code` | a one-time code | `heading`, `lead`, `valid_note`, `ignore_note`; data: `{code}` |
| `document` | a document is ready, five rows and one button | `heading`, `lead`, `row1..5_label/_value`, `button_text`, `button_url`, `note` |
| `notice` | a status of money or a debt: one amount row, one status row, a button | `heading`, `lead`, `detail_label/_value`, `status_label/_text/_color`, `note`, `button_text`, `button_url` |
| `action` | one thing to do, one button | `heading`, `lead`, `highlight`, `button_text`, `button_url`, `note` |
| `digest` | the news mailing: a lead and three items, an unsubscribe link | `heading`, `lead`; data: `{item1..3_title/_text/_url}`, `{unsubscribe_url}` |

Every layout also uses the shared variables the backend sends
(`backend/app/core/email_vars.py`): `{logo_url}`, `{support_url}` (the support
bot), `{support_email}`, `{cabinet_url}`, `{site_url}`.
Colours of a status: success `#0E6E45`, in progress or overdue `#B1581B`,
failure `#9C231E`.

## Which types use which layout

- `code`: `auth.verification_code`
- `action`: `auth.password_reset`, and the unsent `welcome` and `installment.reminder`
- `document`: `purchase.agreement`, `ownership.certificate`
- `notice`: `withdrawal.processing`, `.completed`, `.rejected`, `.failed`,
  `installment.tranche_overdue`, `installment.plan_defaulted`
- `digest`: the unsent `news.digest` (marketing mail: its own sending domain
  and an unsubscribe link come with it)

## Checks

`python compose.py` fails when a slot is left unfilled. The composed letters
pass comms's own template check (the profile loader's leaf dry run and domain
fence): no `http` literal anywhere, every link is a variable.
