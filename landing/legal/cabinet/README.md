# cabinet/ -- the documents of the cabinet

A document of the cabinet (an agreement, a policy or a notice a user of the cabinet sees, in any of its roles, not on the public site) is written here as `cabinet/<type>/<type>.en.md` and `cabinet/<type>/<type>.ru.md`,
in the same form as the files under `public/`, and has an entry with scope `cabinet` and its `roles` in `registry.json`.
`python build.py --cabinet` writes each one as HTML to `frontend/public/legal/<lang>/<type>.html`.

The documents today: `cabinet_terms`, `kyc_notice`, `licence_agreement`, `risk_disclosure`, `integrator_agreement`, `aml_policy`.
The privacy policy of the cabinet is the one in `public/privacy/`.
