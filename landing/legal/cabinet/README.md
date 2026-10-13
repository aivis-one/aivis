# cabinet/ -- the documents of the cabinet

Empty for now. A document of the cabinet (an agreement, a policy or a notice a user of the cabinet sees, in any of its roles, not on the public site) is written here as `cabinet/<type>/<type>.en.md` and `cabinet/<type>/<type>.ru.md`,
in the same form as the files under `public/`. `python build.py --cabinet` writes each one as HTML to
`frontend/public/legal/<lang>/<type>.html`.
