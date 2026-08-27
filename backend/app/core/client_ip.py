# =============================================================================
# AIVIS.ONE Backend -- Client IP extraction (TASK-6 4.1a consolidation)
# =============================================================================
#
# The single Request-layer source of a client's IP, for rate-limit keys
# and audit records. Before this module the exact same helper was
# copy-pasted under the name `_get_client_ip` into five routers (auth,
# companies/attachments_public, companies/public, products/public,
# referrals/public) and inlined a sixth time in documents/router.py --
# one rule, three spellings, seven sites (STAGE-III-FINDINGS.md #14).
# This is that rule stated once.
#
# WHY X-Real-IP AND NOT X-Forwarded-For. Nginx sets
# `X-Real-IP $remote_addr` unconditionally -- a proxy_set_header REPLACES
# any client-supplied value with nginx's own TCP view of the peer, which
# no client can write. X-Forwarded-For is deliberately NOT read: nginx
# APPENDS to it (`$proxy_add_x_forwarded_for`), so its leftmost entry is
# client-controlled and spoofable. The full trust-chain analysis is
# STAGE-III-FINDINGS.md #14.
#
# THE request.client FALLBACK IS FOR DEV/TEST ONLY. In production nothing
# reaches the app except through nginx (it is published on 127.0.0.1 only),
# so X-Real-IP is always present and the fallback never executes there.
# Unifying to the truthiness form below also fixes documents/router.py's
# latent inconsistency: its old `.get("X-Real-IP", <fallback>)` spelling
# returned "" for a present-but-empty header instead of falling through.
#
# ONE IMPLEMENTATION STAYS SEPARATE BY DESIGN: core/middleware.py reads
# the same header at the raw ASGI layer, before a Request object exists
# (off the byte-level scope). It cannot call this helper and is not a
# duplicate to fold in -- it is the same rule at a different layer.
# =============================================================================

from fastapi import Request


def get_client_ip(request: Request) -> str:
    """Return the client IP: X-Real-IP (set by nginx), else the peer.

    Falls back to request.client.host only where no nginx sits in front
    (dev/test); "unknown" if even the ASGI transport carries no peer.
    """
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"
