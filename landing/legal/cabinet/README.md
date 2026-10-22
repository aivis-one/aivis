# cabinet/ -- the documents of the cabinet

A document of the cabinet (an agreement, a policy or a notice a user of the cabinet sees, in any of its roles, not on the public site) is written here as `cabinet/<type>/<type>.en.md` and `cabinet/<type>/<type>.ru.md`,
in the same form as the files under `public/`, and has an entry with scope `cabinet` and its `roles` in `registry.json`.
`python build.py --cabinet` writes each one as HTML to `frontend/public/legal/<lang>/<type>.html`.

The documents today: `cabinet_terms`, `privacy_policy`, `buyer_agreement`, `pre_purchase_disclosure`, `agent_integrator_agreement`, `aml_policy`, `company_agreement`, `kyc_notice`, `index_rules`, `licence_agreement`.
The privacy policy of the cabinet, `privacy_policy`, is a byte copy of the text in `public/privacy/`; both are changed together, and `cmp public/privacy/privacy.en.md cabinet/privacy_policy/privacy_policy.en.md` and `cmp public/privacy/privacy.ru.md cabinet/privacy_policy/privacy_policy.ru.md`, run from landing/legal, print nothing while they agree.
