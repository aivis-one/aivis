"""Composes the HTML letters: a layout of <locale>/<layout>.html with the slot
texts of copy.yaml written in, the data variables left for comms to render.

    python compose.py                 check every type and locale, print a summary
    python compose.py --out DIR       also write DIR/<type>.<locale>.html

compose(type_key, locale) -> the letter's HTML, still carrying {variables};
render(html, data)        -> the letter with the variables filled and every
                             value HTML-escaped (what comms must do before it
                             puts a variable into an html part).

Needs PyYAML. Reads files next to itself and writes only under --out.
"""
import argparse
import html
import pathlib
import string
import sys

import yaml

HERE = pathlib.Path(__file__).resolve().parent

# Variables every letter may carry: the shared addresses (the backend's
# core/email_vars.py) and the notification's own title.
SHARED = {"logo_url", "support_url", "support_email", "cabinet_url", "site_url", "title"}

# The slots of each layout (what copy.yaml fills). Anything else in a layout is
# a data variable.
LAYOUT_SLOTS = {
    "code": {"heading", "lead", "valid_note", "ignore_note"},
    "document": {"heading", "lead", "note", "button_text", "button_url",
                 *[f"row{i}_{k}" for i in range(1, 6) for k in ("label", "value")]},
    "notice": {"heading", "lead", "note", "button_text", "button_url", "detail_label",
               "detail_value", "status_label", "status_text", "status_color"},
    "action": {"heading", "lead", "highlight", "note", "button_text", "button_url"},
    "digest": {"heading", "lead"},
}


class _Keep(dict):
    """format_map mapping that leaves an unknown {name} as it was."""

    def __missing__(self, key):
        return "{" + key + "}"


def names(text):
    return {n for _, n, _, _ in string.Formatter().parse(text) if n}


def load_copy():
    with (HERE / "copy.yaml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def compose(type_key, locale, copy=None):
    copy = copy or load_copy()
    entry = copy[type_key]
    layout = entry["layout"]
    text = (HERE / locale / f"{layout}.html").read_text(encoding="utf-8")
    slots = {k: html.escape(str(v), quote=False)
             for k, v in entry[locale].items() if k in LAYOUT_SLOTS[layout]}
    missing = LAYOUT_SLOTS[layout] - set(slots)
    if layout == "digest":
        missing = set()
    if missing:
        raise ValueError(f"{type_key}/{locale}: slots without text: {sorted(missing)}")
    return text.format_map(_Keep(slots))


def render(composed, data):
    """Fill {variables}; every value is HTML-escaped first."""
    safe = {k: html.escape(str(v), quote=True) for k, v in data.items()}
    return composed.format_map(_Keep(safe))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=pathlib.Path)
    args = parser.parse_args()
    copy = load_copy()
    count = 0
    for type_key, entry in copy.items():
        for locale in ("en", "ru"):
            composed = compose(type_key, locale, copy)
            layout_slots = LAYOUT_SLOTS[entry["layout"]]
            leftover = names(composed) & layout_slots
            if leftover:
                sys.exit(f"{type_key}/{locale}: unfilled slots {sorted(leftover)}")
            if args.out:
                args.out.mkdir(parents=True, exist_ok=True)
                (args.out / f"{type_key}.{locale}.html").write_text(composed, encoding="utf-8", newline="\n")
            count += 1
    print(f"composed {count} letters ({len(copy)} types x 2 locales); no slot left unfilled")


if __name__ == "__main__":
    main()
